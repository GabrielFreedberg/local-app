const STORAGE_KEY = "phase1-auth-session";
const ACTIVE_TAB_KEY = "phase1-active-tab";
const FAVORITE_SUGGESTIONS = ["pizza", "chicken", "coffee", "tacos", "rice", "beer"];
const STATUS_REFRESH_MS = 30000;
const DASHBOARD_REFRESH_MS = 45000;
let currentUser = null;
let sessionToken = "";
let authView = "login";
let activeExpandedCard = null;
let systemStatus = null;
let supabaseClient = null;
let lastSupabaseEvent = "";
let lastFocusedDealCard = null;
let activeTabId = "searchPage";
let hasRenderedAuthenticatedShell = false;
let resultMessageTimers = new Map();
let pendingVerificationEmail = "";
let statusRefreshTimer = null;
let dashboardRefreshTimer = null;
let dashboardState = {
  users: [],
  deals: [],
  notifications: [],
  companyDeals: [],
};
const initialResetToken = new URLSearchParams(window.location.search).get("resetToken") || "";

function isHostedAuthMode() {
  return systemStatus?.authMode === "hosted_supabase";
}

function isFileRuntime() {
  return window.location.protocol === "file:";
}

async function api(path, options = {}) {
  if (isFileRuntime()) {
    throw new Error("Open http://127.0.0.1:8000/ instead of the file preview so the app can reach its backend.");
  }
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (sessionToken) {
    headers.Authorization = `Bearer ${sessionToken}`;
  }
  const response = await fetch(path, {
    headers,
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    if (response.status === 401 && sessionToken) {
      clearSession();
      renderSession();
    }
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function formDataToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function validateSignup(values) {
  if ((values.password || "").length < 8) throw new Error("Password must be at least 8 characters.");
  if (!/[A-Za-z]/.test(values.password || "")) throw new Error("Password must include at least one letter.");
  if (!/\d/.test(values.password || "")) throw new Error("Password must include at least one number.");
  if (values.password !== values.confirmPassword) throw new Error("Passwords do not match.");
}

function validatePasswordReset(values) {
  if (!usingHostedAuth() && !values.token) throw new Error("Reset token is required.");
  if ((values.newPassword || "").length < 8) throw new Error("Password must be at least 8 characters.");
  if (!/[A-Za-z]/.test(values.newPassword || "")) throw new Error("Password must include at least one letter.");
  if (!/\d/.test(values.newPassword || "")) throw new Error("Password must include at least one number.");
  if (values.newPassword !== values.confirmPassword) throw new Error("Passwords do not match.");
}

function validateChangePassword(values) {
  if (!values.currentPassword) throw new Error("Current password is required.");
  if ((values.newPassword || "").length < 8) throw new Error("Password must be at least 8 characters.");
  if (!/[A-Za-z]/.test(values.newPassword || "")) throw new Error("Password must include at least one letter.");
  if (!/\d/.test(values.newPassword || "")) throw new Error("Password must include at least one number.");
  if (values.newPassword !== values.confirmPassword) throw new Error("Passwords do not match.");
  if (values.currentPassword === values.newPassword) throw new Error("Choose a new password that is different from the current one.");
}

function unique(items) {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))];
}

function normalizeInterestLabel(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function setResultMessage(elementId, message, tone = "default") {
  const node = document.getElementById(elementId);
  if (!node) return;
  const existingTimer = resultMessageTimers.get(elementId);
  if (existingTimer) {
    window.clearTimeout(existingTimer);
    resultMessageTimers.delete(elementId);
  }
  node.textContent = message;
  node.classList.remove("is-success", "is-error", "is-muted");
  if (tone === "success") node.classList.add("is-success");
  if (tone === "error") node.classList.add("is-error");
  if (tone === "muted") node.classList.add("is-muted");
  if (message && (tone === "success" || tone === "muted")) {
    const timeoutId = window.setTimeout(() => {
      if (node.textContent === message) {
        node.textContent = "";
        node.classList.remove("is-success", "is-error", "is-muted");
      }
      resultMessageTimers.delete(elementId);
    }, 4200);
    resultMessageTimers.set(elementId, timeoutId);
  }
}

function setButtonLoading(button, isLoading, idleLabel, loadingLabel = "Working...") {
  if (!button) return;
  if (!button.dataset.idleLabel) {
    button.dataset.idleLabel = idleLabel || button.textContent.trim();
  }
  button.disabled = isLoading;
  button.classList.toggle("is-loading", isLoading);
  button.textContent = isLoading ? loadingLabel : (idleLabel || button.dataset.idleLabel);
}

function statusClassSuffix(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-");
}

function renderSystemStatus() {
  const badge = document.getElementById("systemStatusBadge");
  const note = document.getElementById("systemStatusNote");
  const schedulerNote = document.getElementById("systemSchedulerNote");
  if (!badge || !note || !schedulerNote) return;
  badge.classList.remove("is-live", "is-mock");
  if (!systemStatus) {
    badge.textContent = "Checking email mode...";
    note.textContent = "Loading system status.";
    schedulerNote.textContent = "Loading matching scheduler.";
    return;
  }
  const scheduler = systemStatus.matchingScheduler || {};
  const intervalSeconds = Number(scheduler.intervalSeconds || 0);
  const intervalMinutes = intervalSeconds ? Math.max(1, Math.round(intervalSeconds / 60)) : 0;
  const lastSuccess = scheduler.lastSucceededAt ? formatAlertTimestamp(scheduler.lastSucceededAt) : "No successful runs yet";
  const lastRunCount = Number(scheduler.lastRunNotifications || 0);
  if (scheduler.enabled) {
    schedulerNote.textContent = scheduler.lastRunError
      ? `Automatic matching is on every ${intervalMinutes} minute${intervalMinutes === 1 ? "" : "s"}, but the last run failed: ${scheduler.lastRunError}`
      : `Automatic matching is on every ${intervalMinutes} minute${intervalMinutes === 1 ? "" : "s"}. Last success: ${lastSuccess}. Last run created ${lastRunCount} alert${lastRunCount === 1 ? "" : "s"}.`;
  } else {
    schedulerNote.textContent = "Automatic matching is off right now. Use Run Matching to simulate the delivery job manually.";
  }
  if (systemStatus.smtpConfigured) {
    badge.textContent = "Live Email Enabled";
    badge.classList.add("is-live");
    note.textContent = systemStatus.authMode === "hosted_supabase"
      ? "Hosted Supabase auth is enabled, and email delivery can send through your configured SMTP account."
      : "Matching alerts and password recovery can send real email through your configured SMTP account.";
    return;
  }
  badge.textContent = "Mock Email Mode";
  badge.classList.add("is-mock");
  note.textContent = systemStatus?.authMode === "hosted_supabase"
    ? "Hosted Supabase auth is enabled. SMTP is not configured yet, so alerts stay local while password reset runs through Supabase email links."
    : "SMTP is not configured yet, so alerts stay local and password recovery uses a manual token.";
}

function setHeroActionMessage(message, tone = "default") {
  setResultMessage("heroActionResult", message, tone);
}

function renderRuntimeModeNote() {
  const note = document.getElementById("runtimeModeNote");
  if (!note) return;
  const usingFileRuntime = isFileRuntime();
  note.classList.toggle("hidden", !usingFileRuntime);
  if (usingFileRuntime) {
    note.textContent = "You are viewing the static file preview. Open http://127.0.0.1:8000/ for working auth, search, alerts, and automatic matching.";
  }
}

async function loadSystemStatus() {
  if (isFileRuntime()) {
    systemStatus = null;
    renderAuthModeUI();
    renderSystemStatus();
    renderRuntimeModeNote();
    return;
  }
  try {
    systemStatus = await api("/api/system-status");
  } catch {
    systemStatus = null;
  }
  renderAuthModeUI();
  renderSystemStatus();
  renderRuntimeModeNote();
}

function usingHostedAuth() {
  return isHostedAuthMode() && Boolean(supabaseClient);
}

function clearAuthMessages() {
  setResultMessage("loginResult", "", "default");
  setResultMessage("userSignupResult", "", "default");
  setResultMessage("companySignupResult", "", "default");
  setResultMessage("passwordResetRequestResult", "", "default");
  setResultMessage("passwordResetConfirmResult", "", "default");
}

function renderAuthModeUI() {
  const loginModeCopy = document.getElementById("loginModeCopy");
  const resetRequestCopy = document.getElementById("resetRequestCopy");
  const resetConfirmCopy = document.getElementById("resetConfirmCopy");
  const resetTokenField = document.getElementById("resetTokenField");
  const resetTokenInput = document.getElementById("passwordResetTokenInput");
  const securityCopy = document.getElementById("securityCopy");
  const resendVerificationBtn = document.getElementById("resendVerificationBtn");
  const manualResetTokenLink = document.getElementById("manualResetTokenLink");
  const hosted = systemStatus?.authMode === "hosted_supabase";
  if (loginModeCopy) {
    loginModeCopy.textContent = hosted
      ? "Hosted auth is active here. Sign in with the email and password from your verified Supabase account."
      : "Use the same email and password you created for your shopper or business account.";
  }
  if (resetRequestCopy) {
    resetRequestCopy.textContent = hosted
      ? "Enter your email and we’ll send a secure reset link through Supabase."
      : "Enter your email and we’ll send reset instructions. In prototype mode, a manual token will be shown here if email is not configured.";
  }
  if (resetConfirmCopy) {
    resetConfirmCopy.textContent = hosted
      ? "Open the reset link from your email, then choose your new password here."
      : "Paste your reset token, choose a new password, and you’ll be signed in automatically.";
  }
  if (resetTokenField) {
    resetTokenField.classList.toggle("hidden", hosted);
  }
  if (resetTokenInput) {
    resetTokenInput.required = !hosted;
    if (hosted) resetTokenInput.value = "";
  }
  if (manualResetTokenLink) {
    manualResetTokenLink.classList.toggle("hidden", hosted);
  }
  if (resendVerificationBtn) {
    resendVerificationBtn.classList.toggle("hidden", !(hosted && pendingVerificationEmail));
  }
  if (securityCopy) {
    securityCopy.textContent = hosted
      ? "Keep your account secure by updating your password any time. In hosted auth mode, the password change is handled through Supabase."
      : "Keep your account secure by updating your password any time. Changing it will revoke your older sessions.";
  }
}

function clearSession() {
  currentUser = null;
  sessionToken = "";
  localStorage.removeItem(STORAGE_KEY);
}

function restoreStoredPrototypeSession() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return;
    const parsed = JSON.parse(stored);
    currentUser = parsed.user || null;
    sessionToken = parsed.sessionToken || "";
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function persistActiveTab(tabId) {
  activeTabId = tabId;
  localStorage.setItem(ACTIVE_TAB_KEY, tabId);
}

function defaultTabForUser(user = currentUser) {
  return user?.accountType === "company" ? "companyPage" : "searchPage";
}

function formatDateInputValue(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function defaultCompanyExpiryValue(daysAhead = 7) {
  const date = new Date();
  date.setDate(date.getDate() + daysAhead);
  return formatDateInputValue(date);
}

function focusFirstField(container) {
  const firstField = container?.querySelector("input, textarea, select");
  if (firstField) firstField.focus();
}

function wirePasswordToggles(scope = document) {
  scope.querySelectorAll("[data-toggle-password]").forEach((button) => {
    if (button.dataset.wired === "true") return;
    button.dataset.wired = "true";
    button.textContent = "Show";
    button.addEventListener("click", () => {
      const wrapper = button.closest(".password-field");
      const input = wrapper?.querySelector('input[type="password"], input[type="text"]');
      if (!input) return;
      const isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      button.textContent = isHidden ? "Hide" : "Show";
    });
  });
}

function setSession(payload) {
  const previousUserId = currentUser?.id || "";
  currentUser = payload?.user || null;
  sessionToken = payload?.sessionToken || "";
  if (currentUser && currentUser.id !== previousUserId) {
    persistActiveTab(defaultTabForUser(currentUser));
    hasRenderedAuthenticatedShell = false;
  }
  persistSessionState();
  renderSession();
  if (currentUser) {
    renderCurrentDashboardState();
  }
}

function persistSessionState() {
  if (isHostedAuthMode()) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  if (currentUser && sessionToken) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ user: currentUser, sessionToken }));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function clearHostedAuthUrlArtifacts() {
  const url = new URL(window.location.href);
  let changed = false;
  ["code", "type", "access_token", "refresh_token", "expires_at", "expires_in", "token_type"].forEach((key) => {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  });
  if (url.hash && /(access_token|refresh_token|type=)/i.test(url.hash)) {
    url.hash = "";
    changed = true;
  }
  if (!changed) return;
  const query = url.searchParams.toString();
  const nextUrl = `${url.pathname}${query ? `?${query}` : ""}`;
  window.history.replaceState({}, "", nextUrl);
}

async function fetchHostedSessionProfile(accessToken) {
  const response = await fetch("/api/session", {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || "Hosted session failed");
  }
  return data;
}

async function syncHostedSession(session, options = {}) {
  if (!session?.access_token) {
    clearSession();
    renderSession();
    return null;
  }
  const payload = await fetchHostedSessionProfile(session.access_token);
  setSession({
    user: payload.user,
    sessionToken: session.access_token,
  });
  clearHostedAuthUrlArtifacts();
  if (options.refresh !== false) {
    await refreshDashboardEventually({ attempts: 5, delayMs: 900 });
  }
  return payload;
}

async function initializeHostedAuth() {
  if (systemStatus?.authMode !== "hosted_supabase") return;
  if (!window.supabase?.createClient || !systemStatus.supabaseUrl || !systemStatus.supabaseAnonKey) return;
  supabaseClient = window.supabase.createClient(systemStatus.supabaseUrl, systemStatus.supabaseAnonKey, {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
    },
  });
  supabaseClient.auth.onAuthStateChange(async (event, session) => {
    lastSupabaseEvent = event;
    if (event === "PASSWORD_RECOVERY") {
      setAuthView("resetConfirm");
      setResultMessage("passwordResetConfirmResult", "Choose your new password to complete recovery.", "muted");
      return;
    }
    if (event === "SIGNED_OUT") {
      pendingVerificationEmail = "";
      renderAuthModeUI();
      setAuthView("login");
      clearSession();
      renderSession();
      return;
    }
    if (!session?.access_token) return;
    try {
      pendingVerificationEmail = "";
      renderAuthModeUI();
      await syncHostedSession(session, { refresh: Boolean(currentUser) });
    } catch (error) {
      setResultMessage("loginResult", error.message, "error");
    }
  });
}

function setAuthView(nextView) {
  authView = nextView;
  document.querySelectorAll("[data-auth-view]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.authView !== authView);
  });
  if (authView === "resetConfirm" && initialResetToken) {
    const tokenInput = document.getElementById("passwordResetTokenInput");
    if (tokenInput && !tokenInput.value) tokenInput.value = initialResetToken;
  }
  const activePanel = document.querySelector(`[data-auth-view="${authView}"]`);
  requestAnimationFrame(() => focusFirstField(activePanel));
}

function setPendingVerification(email) {
  pendingVerificationEmail = String(email || "").trim().toLowerCase();
  const loginForm = document.getElementById("loginForm");
  const emailInput = loginForm?.querySelector('input[name="email"]');
  const passwordInput = loginForm?.querySelector('input[name="password"]');
  if (emailInput && pendingVerificationEmail) {
    emailInput.value = pendingVerificationEmail;
  }
  if (passwordInput) passwordInput.value = "";
  renderAuthModeUI();
}

function hostedAuthRedirectUrl() {
  return `${systemStatus?.appBaseUrl || window.location.origin}/`;
}

function isEmailVerificationError(error) {
  return /email.*confirm|confirm.*email|not confirmed|not verified/i.test(String(error?.message || error || ""));
}

function allowedTabs() {
  return currentUser?.accountType === "company" ? ["companyPage"] : ["searchPage", "favoritesPage"];
}

function scrollIntoViewIfNeeded(element, options = {}) {
  if (!element) return;
  const rect = element.getBoundingClientRect();
  const topBuffer = options.topBuffer ?? 96;
  const bottomBuffer = options.bottomBuffer ?? 48;
  const isAboveViewport = rect.top < topBuffer;
  const isBelowViewport = rect.bottom > window.innerHeight - bottomBuffer;
  if (!isAboveViewport && !isBelowViewport) return;
  element.scrollIntoView({
    behavior: options.behavior || "smooth",
    block: options.block || "start",
  });
}

function activateTab(targetId, options = {}) {
  const allowed = allowedTabs();
  const resolved = allowed.includes(targetId) ? targetId : allowed[0];
  persistActiveTab(resolved);
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === resolved);
    tab.classList.toggle("hidden", !tab.classList.contains(`role-${currentUser?.accountType}`));
    tab.setAttribute("aria-selected", tab.dataset.tab === resolved ? "true" : "false");
  });
  document.querySelectorAll(".tab-page").forEach((page) => {
    page.classList.toggle("hidden", page.id !== resolved);
  });
  const activePage = document.getElementById(resolved);
  renderWorkspaceIntro(resolved);
  if (options.scroll !== false) {
    requestAnimationFrame(() => scrollIntoViewIfNeeded(activePage, { topBuffer: 112 }));
  }
}

function renderWorkspaceIntro(tabId = activeTabId) {
  const kicker = document.getElementById("workspaceKicker");
  const title = document.getElementById("workspaceTitle");
  const copy = document.getElementById("workspaceCopy");
  const chips = document.getElementById("workspaceChips");
  if (!kicker || !title || !copy || !chips || !currentUser) return;

  const favoritesCount = currentUser.alertInterests?.length || 0;
  const accountZip = currentUser.zipCode || "your area";

  if (currentUser.accountType === "company") {
    kicker.textContent = "Merchant Workspace";
    title.textContent = tabId === "companyPage" ? "Keep your deals fresh and visible" : "Company dashboard";
    copy.textContent = `Post timely offers in ${accountZip}, keep expired deals from piling up, and make your local feed feel active.`;
    chips.innerHTML = `
      <span class="workspace-chip is-accent">${escapeHtml(currentUser.companyName || "Company account")}</span>
      <span class="workspace-chip">Zip ${escapeHtml(accountZip)}</span>
      <span class="workspace-chip">Merchant-only workflow</span>
    `;
    return;
  }

  if (tabId === "favoritesPage") {
    kicker.textContent = "Alert Preferences";
    title.textContent = favoritesCount ? "Shape the alerts you actually want" : "Start building your alert list";
    copy.textContent = favoritesCount
      ? `You have ${favoritesCount} saved favorite${favoritesCount === 1 ? "" : "s"}. Only matching deals in ${accountZip} should reach you.`
      : `Add foods, drinks, or products you genuinely care about so alerts stay high-signal in ${accountZip}.`;
    chips.innerHTML = `
      <span class="workspace-chip is-accent">${favoritesCount} saved favorite${favoritesCount === 1 ? "" : "s"}</span>
      <span class="workspace-chip">Zip ${escapeHtml(accountZip)}</span>
      <span class="workspace-chip">Only favorites trigger alerts</span>
    `;
    return;
  }

  kicker.textContent = "Local Search";
  title.textContent = "Browse nearby deals without the noise";
  copy.textContent = `Search every available local deal in and around ${accountZip}. Alerts stay filtered by favorites, but search stays open for everything else.`;
  chips.innerHTML = `
    <span class="workspace-chip is-accent">Zip ${escapeHtml(accountZip)}</span>
    <span class="workspace-chip">${favoritesCount} favorite${favoritesCount === 1 ? "" : "s"} powering alerts</span>
    <span class="workspace-chip">Search all local business deals</span>
  `;
}

async function saveAlertInterests(alertInterests) {
  if (!currentUser?.id) throw new Error("You must be logged in.");
  const data = await api(`/api/users/${currentUser.id}/interests`, {
    method: "PUT",
    body: JSON.stringify({ alertInterests }),
  });
  currentUser = data.user;
  persistSessionState();
  renderFavorites();
  renderCurrentDashboardState();
  void refreshDashboardEventually();
  return data.user;
}

function renderFavorites() {
  const list = document.getElementById("favoritesList");
  const count = document.getElementById("favoritesCount");
  const interests = currentUser?.alertInterests || [];
  const suggestions = document.getElementById("favoriteSuggestions");
  const summary = document.getElementById("favoritesSummary");
  const insights = document.getElementById("favoritesInsights");
  count.textContent = String(interests.length);
  if (summary) {
    summary.textContent = interests.length
      ? `${interests.length} saved interest${interests.length === 1 ? "" : "s"} ready to match against nearby deals.`
      : "Save a few favorites to make alerts feel personal instead of noisy.";
  }
  renderWorkspaceIntro(activeTabId);
  if (insights) {
    const leadInterest = interests[0] || "None yet";
    insights.innerHTML = `
      <article class="favorites-insight-card">
        <span class="favorites-insight-label">Coverage</span>
        <strong>${escapeHtml(currentUser?.zipCode || "No zip yet")}</strong>
        <p>Alerts only fire when a saved favorite matches a deal in this zip code.</p>
      </article>
      <article class="favorites-insight-card">
        <span class="favorites-insight-label">First favorite</span>
        <strong>${escapeHtml(leadInterest)}</strong>
        <p>${interests.length ? "Edit or remove anything here whenever your interests change." : "Start with foods or products you would genuinely want to hear about."}</p>
      </article>
    `;
  }
  suggestions.innerHTML = FAVORITE_SUGGESTIONS.map((item) => {
    const active = interests.includes(item);
    return `
      <button
        class="suggestion-chip${active ? " is-active" : ""}"
        type="button"
        data-suggestion="${item}"
        ${active ? "disabled" : ""}
      >${escapeHtml(item)}</button>
    `;
  }).join("");
  suggestions.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nextValue = button.dataset.suggestion;
      const alertInterests = unique([...(currentUser.alertInterests || []), nextValue]);
      if (alertInterests.length === (currentUser.alertInterests || []).length) {
        setResultMessage("favoritesResult", `"${nextValue}" is already saved.`, "muted");
        return;
      }
      await saveAlertInterests(alertInterests);
      document.getElementById("favoritesDropdown")?.setAttribute("open", "open");
      setResultMessage("favoritesResult", `"${nextValue}" added to favorites.`, "success");
      if (activeTabId !== "favoritesPage") activateTab("favoritesPage");
    });
  });
  if (!interests.length) {
    list.innerHTML = '<div class="empty">No favorites saved yet. Try adding a few items like pizza, rice, coffee, or chicken.</div>';
    return;
  }
  list.innerHTML = interests
    .map(
      (interest) => `
        <div class="favorite-item">
          <div class="favorite-item-copy">
            <strong>${escapeHtml(interest)}</strong>
            <span>Alerts will trigger when this matches a deal in your zip code.</span>
          </div>
          <div class="favorite-item-actions">
            <button class="favorite-edit" type="button" data-edit-interest="${escapeHtml(interest)}">Edit</button>
            <button class="heart" type="button" data-interest="${escapeHtml(interest)}" aria-label="Remove ${escapeHtml(interest)}">♥</button>
          </div>
        </div>
      `
    )
    .join("");
  list.querySelectorAll("[data-edit-interest]").forEach((button) => {
    button.addEventListener("click", () => {
      const currentValue = button.dataset.editInterest || "";
      const row = button.closest(".favorite-item");
      if (!row) return;
      row.classList.add("is-editing");
      row.innerHTML = `
        <div class="favorite-edit-row">
          <input class="favorite-edit-input" type="text" value="${escapeHtml(currentValue)}" aria-label="Edit favorite" />
          <div class="favorite-edit-actions">
            <button class="favorite-save" type="button">Save</button>
            <button class="favorite-cancel" type="button">Cancel</button>
          </div>
        </div>
      `;
      const input = row.querySelector(".favorite-edit-input");
      const finishCancel = () => renderFavorites();
      const finishSave = async () => {
        const nextValue = normalizeInterestLabel(input?.value);
        if (!nextValue) {
          setResultMessage("favoritesResult", "Favorite cannot be blank.", "error");
          return;
        }
        const existing = currentUser.alertInterests || [];
        const duplicate = existing.some((item) => item !== currentValue && item === nextValue);
        if (duplicate) {
          setResultMessage("favoritesResult", `"${nextValue}" is already saved.`, "muted");
          renderFavorites();
          return;
        }
        const nextInterests = existing.map((item) => (item === currentValue ? nextValue : item));
        await saveAlertInterests(nextInterests);
        setResultMessage("favoritesResult", `"${currentValue}" updated to "${nextValue}".`, "success");
        document.getElementById("favoritesDropdown")?.setAttribute("open", "open");
      };
      row.querySelector(".favorite-cancel")?.addEventListener("click", finishCancel);
      row.querySelector(".favorite-save")?.addEventListener("click", () => {
        finishSave().catch((error) => setResultMessage("favoritesResult", error.message, "error"));
      });
      input?.addEventListener("keydown", (event) => {
        if (event.key === "Escape") finishCancel();
        if (event.key === "Enter") {
          event.preventDefault();
          finishSave().catch((error) => setResultMessage("favoritesResult", error.message, "error"));
        }
      });
      input?.focus();
      input?.select();
    });
  });
  list.querySelectorAll(".heart").forEach((button) => {
    button.addEventListener("click", async () => {
      const updated = (currentUser.alertInterests || []).filter((item) => item !== button.dataset.interest);
      await saveAlertInterests(updated);
      setResultMessage("favoritesResult", `"${button.dataset.interest}" removed from favorites.`, "success");
      document.getElementById("favoritesDropdown")?.setAttribute("open", "open");
      if (activeTabId !== "favoritesPage") activateTab("favoritesPage");
    });
  });
}

function renderSession() {
  const authShell = document.getElementById("authShell");
  const appShell = document.getElementById("appShell");
  if (!currentUser) {
    authShell.classList.remove("hidden");
    appShell.classList.add("hidden");
    hasRenderedAuthenticatedShell = false;
    setAuthView(authView);
    return;
  }
  authShell.classList.add("hidden");
  appShell.classList.remove("hidden");
  document.getElementById("sessionEmail").textContent = currentUser.email;
  document.getElementById("sessionMeta").textContent = `${currentUser.accountType} account • zip ${currentUser.zipCode}`;
  if (currentUser.accountType === "company") {
    document.getElementById("companyNameInput").value = currentUser.companyName || "";
    document.getElementById("companyZipInput").value = currentUser.zipCode || "";
    document.querySelector('#companyDealForm input[name="expiresOn"]').value = "";
    document.querySelector('#companyDealForm select[name="status"]').value = "active";
    document.querySelector('#companyDealForm textarea[name="dealDescription"]').value = "";
    syncCompanyFormState({ withDefaultExpiry: true });
  }
  renderFavorites();
  const preferredTab = hasRenderedAuthenticatedShell ? activeTabId : defaultTabForUser(currentUser);
  hasRenderedAuthenticatedShell = true;
  activateTab(preferredTab);
  if (currentUser.accountType === "user") {
    loadDeals().catch((error) => {
      document.getElementById("dealSearchResult").innerHTML =
        `<div class="search-empty-state">${escapeHtml(error.message)}</div>`;
    });
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function dealBadge(deal) {
  return "Local business";
}

function dealAddress(deal) {
  return deal.address || "Address coming soon";
}

function dealPrice(deal) {
  if (deal.dealType === "company") return deal.sourceStore || deal.title;
  return `$${Number(deal.salePrice).toFixed(2)}/${deal.unit}`;
}

function dealPreview(deal) {
  if (deal.dealType === "grocery") return `${deal.title} for ${dealPrice(deal)}`;
  return deal.description.length > 58 ? `${deal.description.slice(0, 58)}...` : deal.description;
}

function dealCardName(deal) {
  return deal.sourceStore || deal.title || "Deal";
}

function dealCardSummary(deal) {
  if (deal.dealType === "grocery") {
    return `${deal.title} for ${dealPrice(deal)}`;
  }
  return deal.description.length > 96 ? `${deal.description.slice(0, 96)}...` : deal.description;
}

function dealCardInfo(deal) {
  if (deal.dealType === "grocery") {
    return `${deal.title} now ${dealPrice(deal)}${deal.regularPrice ? `, down from $${Number(deal.regularPrice).toFixed(2)}` : ""}.`;
  }
  return deal.description;
}

function dealFrontChip(deal) {
  if (deal.dealType === "grocery") {
    return deal.category || "Fresh";
  }
  return deal.address ? "Near you" : "Local favorite";
}

function dealVisualMarkup(deal) {
  const imageUrl = deal.imageUrl || "";
  if (imageUrl) {
    return `
      <div class="deal-thumb has-image">
        <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(dealCardName(deal))}" />
      </div>
    `;
  }
  return `
    <div class="deal-thumb" aria-hidden="true"></div>
  `;
}

function dealCompactSummary(deal) {
  if (deal.dealType === "grocery") {
    return `${deal.title} for ${dealPrice(deal)}`;
  }
  const compact = (deal.description || "").trim();
  if (!compact) return "Local offer available now";
  return compact.length > 68 ? `${compact.slice(0, 68)}...` : compact;
}

function dealCardLocationTag(deal) {
  if (currentUser?.zipCode && deal.zipCode === currentUser.zipCode) return `Zip ${deal.zipCode}`;
  if (deal.zipCode) return `Area ${deal.zipCode}`;
  return "Nearby";
}

function dealCardFooterLabel(deal) {
  if (isDealFavorited(deal)) return "Saved favorite";
  return "Tap for details";
}

function favoriteTermForDeal(deal) {
  return (deal.title || dealCardName(deal) || "").trim().toLowerCase();
}

function isDealFavorited(deal) {
  const favoriteTerm = favoriteTermForDeal(deal);
  return Boolean(favoriteTerm) && (currentUser?.alertInterests || []).includes(favoriteTerm);
}

function scoreDealForSearch(deal, normalizedKeyword) {
  let score = 0;
  const source = (deal.sourceStore || "").toLowerCase();
  const title = (deal.title || "").toLowerCase();
  const description = (deal.description || "").toLowerCase();
  const inUserZip = currentUser?.zipCode && deal.zipCode === currentUser.zipCode;

  if (normalizedKeyword) {
    if (source === normalizedKeyword || title === normalizedKeyword) score += 140;
    if (source.startsWith(normalizedKeyword) || title.startsWith(normalizedKeyword)) score += 80;
    if (source.includes(normalizedKeyword) || title.includes(normalizedKeyword)) score += 50;
    if (description.includes(normalizedKeyword)) score += 20;
  }

  if (inUserZip) score += 35;
  if (deal.dealType === "company") score += 12;
  if (deal.address) score += 6;
  return score;
}

function renderDealCard(deal, actions = "") {
  const isFavorited = isDealFavorited(deal);
  return `
    <article
      class="deal-card js-deal-card${isFavorited ? " is-saved" : ""}"
      data-deal-id="${escapeHtml(deal.id || "")}"
      tabindex="0"
      role="button"
      aria-label="View details for ${escapeHtml(dealCardName(deal))}"
    >
      <div class="deal-card-top">
        ${dealVisualMarkup(deal)}
      </div>
      <div class="deal-card-copy">
        <div class="deal-card-heading">
          <p class="deal-card-kicker">${escapeHtml(dealFrontChip(deal))}</p>
          <span class="deal-card-status${isFavorited ? " is-saved" : ""}">${isFavorited ? "Saved" : "Fresh"}</span>
        </div>
        <h3 class="deal-card-title">${escapeHtml(dealCardName(deal))}</h3>
        <p class="deal-card-preview">${escapeHtml(dealCompactSummary(deal))}</p>
      </div>
      <div class="deal-card-footer">
        <span class="deal-card-meta">${escapeHtml(dealCardLocationTag(deal))}</span>
        <span class="deal-card-meta is-accent">${escapeHtml(dealCardFooterLabel(deal))}</span>
      </div>
      ${actions}
    </article>
  `;
}

function renderDealModalMarkup(deal) {
  const subtitle = deal.title && deal.title !== dealCardName(deal)
    ? `<p class="deal-modal-subtitle">${escapeHtml(deal.title)}</p>`
    : "";
  const isFavorited = isDealFavorited(deal);
  const footerLabel = dealCardFooterLabel(deal);
  const favoriteAction = currentUser?.accountType === "user"
    ? `
      <div class="deal-modal-actions">
        <button
          class="deal-favorite-button${isFavorited ? " is-saved" : ""}"
          type="button"
          data-toggle-favorite
        >
          ${isFavorited ? "Remove from favorites" : "Add to favorites"}
        </button>
      </div>
    `
    : "";
  return `
    <section class="deal-modal-panel" role="dialog" aria-modal="true" aria-label="Deal details for ${escapeHtml(dealCardName(deal))}">
      <button class="deal-modal-close" type="button" data-close-card aria-label="Close details">×</button>
      <div class="deal-modal-hero">
        <div class="deal-modal-media">
          ${dealVisualMarkup(deal)}
        </div>
        <div class="deal-modal-headline">
          <div class="deal-modal-heading-row">
            <p class="deal-modal-kicker">${escapeHtml(dealFrontChip(deal))}</p>
            <span class="deal-modal-status${isFavorited ? " is-saved" : ""}">${isFavorited ? "Saved" : "Live now"}</span>
          </div>
          <h2>${escapeHtml(dealCardName(deal))}</h2>
          ${subtitle}
          <div class="deal-modal-micro">
            <span>${escapeHtml(dealCardLocationTag(deal))}</span>
            <span>${escapeHtml(footerLabel)}</span>
          </div>
        </div>
      </div>
      <div class="deal-modal-body">
        <div class="deal-modal-block">
          <span class="deal-meta-label">Address</span>
          <p class="deal-modal-copy">${escapeHtml(dealAddress(deal))}</p>
        </div>
        <div class="deal-modal-block">
          <span class="deal-meta-label">Deal Info</span>
          <p class="deal-modal-copy">${escapeHtml(dealCardInfo(deal))}</p>
        </div>
      </div>
      ${favoriteAction}
    </section>
  `;
}

function bindDealModalActions(modal, deal) {
  if (!modal || !deal) return;
  const closeButton = modal.querySelector("[data-close-card]");
  if (closeButton) {
    closeButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      closeDealCard();
    });
  }
  const favoriteButton = modal.querySelector("[data-toggle-favorite]");
  if (favoriteButton) {
    favoriteButton.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await toggleDealFavorite(deal);
    });
  }
}

function attachFlipCardInteractions(scope, deals) {
  const dealsById = new Map(deals.map((deal) => [String(deal.id), deal]));
  scope.querySelectorAll(".js-deal-card").forEach((card) => {
    const deal = dealsById.get(card.dataset.dealId);
    if (!deal) return;
    card.addEventListener("click", (event) => {
      if (event.target.closest(".deal-card-actions button")) return;
      openDealCard(deal, card);
    });
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openDealCard(deal, card);
    });
  });
}

function syncBackdrop() {
  const backdrop = document.getElementById("dealCardBackdrop");
  const modal = document.getElementById("dealModal");
  if (!backdrop) return;
  backdrop.classList.toggle("hidden", !activeExpandedCard);
  backdrop.classList.toggle("is-visible", Boolean(activeExpandedCard));
  backdrop.setAttribute("aria-hidden", activeExpandedCard ? "false" : "true");
  if (modal) {
    modal.classList.toggle("hidden", !activeExpandedCard);
    modal.classList.toggle("is-visible", Boolean(activeExpandedCard));
    modal.setAttribute("aria-hidden", activeExpandedCard ? "false" : "true");
  }
}

function openDealCard(deal, triggerCard = null) {
  if (!deal) return;
  activeExpandedCard = deal;
  lastFocusedDealCard = triggerCard || document.activeElement;
  const modal = document.getElementById("dealModal");
  if (modal) {
    modal.innerHTML = renderDealModalMarkup(deal);
    bindDealModalActions(modal, deal);
  }
  document.body.classList.add("has-open-card");
  syncBackdrop();
  requestAnimationFrame(() => {
    modal?.querySelector("[data-close-card]")?.focus();
  });
}

async function toggleDealFavorite(deal) {
  if (!currentUser || currentUser.accountType !== "user") return;
  const favoriteTerm = favoriteTermForDeal(deal);
  if (!favoriteTerm) return;
  const alreadyFavorited = (currentUser.alertInterests || []).includes(favoriteTerm);
  const alertInterests = alreadyFavorited
    ? (currentUser.alertInterests || []).filter((item) => item !== favoriteTerm)
    : unique([...(currentUser.alertInterests || []), favoriteTerm]);
  const data = await api(`/api/users/${currentUser.id}/interests`, {
    method: "PUT",
    body: JSON.stringify({ alertInterests }),
  });
  currentUser = data.user;
  persistSessionState();
  if (activeExpandedCard?.id === deal.id) {
    activeExpandedCard = deal;
  }
  renderFavorites();
  const favoritesResult = document.getElementById("favoritesResult");
  if (favoritesResult) {
    setResultMessage(
      "favoritesResult",
      alreadyFavorited ? `"${favoriteTerm}" removed from favorites.` : `"${favoriteTerm}" added to favorites.`,
      "success"
    );
  }
  await refreshDashboard();
  const searchKeyword = document.getElementById("dealSearchInput")?.value || "";
  const visibleDeals = shopperDashboardDeals();
  const matches = filterDealsForSearch(visibleDeals, searchKeyword, currentSearchFormValues());
  renderSearchResults(matches, searchKeyword.trim(), { preserveOpenCard: true });
  const modal = document.getElementById("dealModal");
  if (modal && activeExpandedCard?.id === deal.id) {
    modal.innerHTML = renderDealModalMarkup(deal);
    bindDealModalActions(modal, deal);
  }
}

function closeDealCard() {
  activeExpandedCard = null;
  const modal = document.getElementById("dealModal");
  if (modal) {
    modal.innerHTML = "";
  }
  document.body.classList.remove("has-open-card");
  syncBackdrop();
  if (lastFocusedDealCard && typeof lastFocusedDealCard.focus === "function") {
    lastFocusedDealCard.focus();
  }
  lastFocusedDealCard = null;
}

function closeAllOpenDealCards(options = {}) {
  if (activeExpandedCard) {
    closeDealCard();
  } else {
    document.body.classList.remove("has-open-card");
    syncBackdrop();
  }
}

function formatDealStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "active") return "Active";
  if (normalized === "draft") return "Draft";
  if (normalized === "expired") return "Expired";
  if (normalized === "archived") return "Archived";
  return normalized || "Unknown";
}

function formatExpirationLabel(deal) {
  if (!deal?.expiresOn) return "No expiration date";
  return `Expires ${deal.expiresOn}`;
}

function formatExpirationPreview(value) {
  if (!value) return "No expiration date";
  return `Expires ${value}`;
}

function formatAlertTimestamp(value) {
  if (!value) return "Just now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function renderMerchantHealthBoard(deals) {
  const board = document.getElementById("merchantHealthBoard");
  if (!board) return;
  const ordered = [...deals].sort((left, right) => new Date(right.createdAt || 0) - new Date(left.createdAt || 0));
  const latest = ordered[0] || null;
  const active = ordered.filter((deal) => deal.status === "active");
  const drafts = ordered.filter((deal) => deal.status === "draft");
  const expired = ordered.filter((deal) => deal.status === "expired");
  const checklist = [];

  if (!ordered.length) checklist.push("Post your first restaurant deal.");
  if (!active.length) checklist.push("Keep at least one active offer live.");
  if (drafts.length) checklist.push("Review and publish any draft offers.");
  if (expired.length) checklist.push("Refresh expired offers before they go stale.");
  if (latest?.address && !/denver|st|ave|road|blvd|lane|way/i.test(latest.address)) {
    checklist.push("Tighten the address so it feels precise.");
  }
  if (!checklist.length) checklist.push("Your merchant setup is in a healthy state right now.");

  board.innerHTML = `
    <article class="merchant-health-card">
      <span class="merchant-health-label">Latest Offer</span>
      <strong>${escapeHtml(latest?.description || "No offer posted yet")}</strong>
      <p>${escapeHtml(latest ? `${latest.sourceStore || currentUser?.companyName || "Your restaurant"} • ${formatExpirationLabel(latest)}` : "Once you post a deal, this card will summarize what shoppers are seeing.")}</p>
    </article>
    <article class="merchant-health-card">
      <span class="merchant-health-label">Next Steps</span>
      <strong>${active.length ? "Keep momentum going" : "You need one live offer"}</strong>
      <ul>${checklist.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </article>
  `;
}

function merchantInsightTone(value, thresholds = { strong: 80, okay: 55 }) {
  if (value >= thresholds.strong) return "is-strong";
  if (value >= thresholds.okay) return "is-okay";
  return "is-risk";
}

function daysUntilExpiration(deal) {
  if (!deal?.expiresOn) return null;
  const end = new Date(`${deal.expiresOn}T23:59:59`);
  if (Number.isNaN(end.getTime())) return null;
  const diff = end.getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

function renderMerchantInsightDeck(deals) {
  const deck = document.getElementById("merchantInsightDeck");
  if (!deck) return;
  if (!deals.length) {
    deck.innerHTML = `
      <article class="merchant-insight-card">
        <span class="merchant-insight-label">Merchant Insight</span>
        <strong>Post one offer to unlock dashboard guidance</strong>
        <p>Your activity, freshness, and coverage signals will appear here once your first deal is live.</p>
      </article>
    `;
    return;
  }

  const active = deals.filter((deal) => deal.status === "active");
  const drafts = deals.filter((deal) => deal.status === "draft");
  const withAddress = deals.filter((deal) => Boolean((deal.address || "").trim()));
  const expiringSoon = active.filter((deal) => {
    const days = daysUntilExpiration(deal);
    return days !== null && days >= 0 && days <= 3;
  });
  const recentlyUpdated = [...deals].sort((left, right) => new Date(right.updatedAt || 0) - new Date(left.updatedAt || 0))[0] || null;

  const readinessScore = Math.min(100, Math.round(((active.length * 55) + (withAddress.length * 25) + ((deals.length - drafts.length) * 20)) / deals.length));
  const freshnessScore = Math.max(25, 100 - (expiringSoon.length * 18) - (drafts.length * 12));
  const coverageScore = Math.round((withAddress.length / deals.length) * 100);

  deck.innerHTML = `
    <article class="merchant-insight-card">
      <div class="merchant-insight-top">
        <span class="merchant-insight-label">Offer Readiness</span>
        <span class="merchant-insight-score ${merchantInsightTone(readinessScore)}">${readinessScore}%</span>
      </div>
      <strong>${active.length ? `${active.length} live offer${active.length === 1 ? "" : "s"} shoppers can see now` : "No active offers are live right now"}</strong>
      <p>${drafts.length ? `${drafts.length} draft${drafts.length === 1 ? "" : "s"} still need a final review before publishing.` : "Your current feed is publish-ready from a status standpoint."}</p>
    </article>
    <article class="merchant-insight-card">
      <div class="merchant-insight-top">
        <span class="merchant-insight-label">Freshness Window</span>
        <span class="merchant-insight-score ${merchantInsightTone(freshnessScore, { strong: 75, okay: 50 })}">${freshnessScore}%</span>
      </div>
      <strong>${expiringSoon.length ? `${expiringSoon.length} active offer${expiringSoon.length === 1 ? "" : "s"} expire within 3 days` : "Your active offers do not have immediate expiration pressure"}</strong>
      <p>${recentlyUpdated ? `Most recently touched: ${recentlyUpdated.sourceStore || recentlyUpdated.title} on ${formatAlertTimestamp(recentlyUpdated.updatedAt)}.` : "Update a deal to keep your feed feeling current."}</p>
    </article>
    <article class="merchant-insight-card">
      <div class="merchant-insight-top">
        <span class="merchant-insight-label">Location Coverage</span>
        <span class="merchant-insight-score ${merchantInsightTone(coverageScore, { strong: 90, okay: 70 })}">${coverageScore}%</span>
      </div>
      <strong>${withAddress.length === deals.length ? "Every offer includes a street address" : `${deals.length - withAddress.length} offer${deals.length - withAddress.length === 1 ? "" : "s"} still need a precise address`}</strong>
      <p>Precise location details help nearby shoppers trust the listing and decide faster.</p>
    </article>
  `;
}

function renderCompanyDeals(deals) {
  const view = document.getElementById("companyDealsView");
  const summary = document.getElementById("merchantFeedSummary");
  const metrics = document.getElementById("merchantFeedMetrics");
  closeAllOpenDealCards({ immediate: true });
  const mine = deals.filter((deal) => deal.createdByUserId === currentUser?.id);
  const activeCount = mine.filter((deal) => deal.status === "active").length;
  const draftCount = mine.filter((deal) => deal.status === "draft").length;
  const expiredCount = mine.filter((deal) => deal.status === "expired").length;
  if (summary) {
    summary.textContent = mine.length
      ? `${mine.length} total offer${mine.length === 1 ? "" : "s"}: ${activeCount} active, ${draftCount} draft, ${expiredCount} expired.`
      : "Track active, draft, and expired offers in one place.";
  }
  if (metrics) {
    metrics.innerHTML = mine.length
      ? `
        <span class="merchant-feed-chip is-active">${activeCount} active</span>
        <span class="merchant-feed-chip is-draft">${draftCount} draft</span>
        <span class="merchant-feed-chip is-expired">${expiredCount} expired</span>
        <span class="merchant-feed-chip">${mine.length} total posted</span>
      `
      : `
        <span class="merchant-feed-chip">0 active</span>
        <span class="merchant-feed-chip">0 draft</span>
        <span class="merchant-feed-chip">0 expired</span>
      `;
  }
  renderMerchantHealthBoard(mine);
  renderMerchantInsightDeck(mine);
  if (!mine.length) {
    view.innerHTML = '<div class="search-empty-state">Post your first deal to build your company feed.</div>';
    return;
  }
  view.innerHTML = mine
    .map((deal) => `
      <article class="merchant-deal-item">
        <div class="merchant-deal-top">
          <div>
            <strong>${escapeHtml(deal.sourceStore || deal.title || currentUser?.companyName || "Company deal")}</strong>
            <p class="merchant-deal-address">${escapeHtml(deal.address || "Address coming soon")}</p>
          </div>
          <span class="alert-status is-${statusClassSuffix(deal.status)}">${escapeHtml(formatDealStatus(deal.status))}</span>
        </div>
        <p class="merchant-deal-description">${escapeHtml(deal.description || "")}</p>
        <div class="merchant-deal-meta">
          <span>${escapeHtml(deal.zipCode || "")}</span>
          <span>${escapeHtml(formatExpirationLabel(deal))}</span>
        </div>
        <div class="deal-card-actions">
          <button class="secondary-button small-button edit-deal-btn" type="button" data-deal-id="${deal.id}">Edit</button>
          <button class="secondary-button small-button delete-deal-btn" type="button" data-deal-id="${deal.id}">Archive</button>
        </div>
      </article>
    `)
    .join("");
  view.querySelectorAll(".edit-deal-btn").forEach((button) => {
    button.addEventListener("click", () => startDealEdit(button.dataset.dealId, mine));
  });
  view.querySelectorAll(".delete-deal-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const data = await api(`/api/company-deals/${button.dataset.dealId}`, {
          method: "DELETE",
          body: JSON.stringify({}),
        });
        if (document.getElementById("editingDealId").value === button.dataset.dealId) resetCompanyForm();
        setResultMessage("companyDealResult", data.message, "success");
        dashboardState.companyDeals = companyDashboardDeals().filter((deal) => deal.id !== button.dataset.dealId);
        renderCurrentDashboardState();
        void refreshDashboardEventually({ attempts: 5, delayMs: 1000 });
        document.getElementById("companyDealForm")?.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        setResultMessage("companyDealResult", error.message, "error");
      }
    });
  });
}

function companyDashboardDeals() {
  return currentUser?.accountType === "company"
    ? (dashboardState.companyDeals || [])
    : [];
}

function shopperDashboardDeals() {
  return (dashboardState.deals || []).filter((deal) => deal.dealType === "company");
}

function currentSearchFormValues() {
  const form = document.getElementById("dealSearchForm");
  return form ? formDataToObject(form) : {};
}

function filterDealsForSearch(deals, keyword = "", options = {}) {
  const normalized = keyword.trim().toLowerCase();
  const zipFilter = String(options.zipFilter || "").trim();
  const typeFilter = String(options.typeFilter || "").trim();
  return deals
    .filter((deal) => {
      const matchesKeyword = normalized
        ? `${deal.title} ${deal.description} ${deal.address || ""} ${deal.sourceStore || ""}`
            .toLowerCase()
            .includes(normalized)
        : true;
      const matchesZip = zipFilter ? deal.zipCode === zipFilter : true;
      const matchesType = typeFilter ? deal.dealType === typeFilter : true;
      return matchesKeyword && matchesZip && matchesType;
    })
    .sort((left, right) => {
      const scoreDelta = scoreDealForSearch(right, normalized) - scoreDealForSearch(left, normalized);
      if (scoreDelta !== 0) return scoreDelta;
      return new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime();
    });
}

function renderCurrentDashboardState() {
  if (!currentUser) return;
  const shopperDeals = shopperDashboardDeals();
  const overviewDeals = currentUser.accountType === "company" ? companyDashboardDeals() : shopperDeals;
  renderOverview(dashboardState.users || [], overviewDeals, dashboardState.notifications || []);
  if (currentUser.accountType === "user") renderAlerts(dashboardState.notifications || [], shopperDeals);
  if (currentUser.accountType === "company") renderCompanyDeals(companyDashboardDeals());
}

async function refreshDashboardEventually(options = {}) {
  const attempts = options.attempts || 4;
  const delayMs = options.delayMs || 900;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const ok = await refreshDashboardSafely();
    if (ok) return true;
    if (attempt < attempts - 1) await new Promise((resolve) => window.setTimeout(resolve, delayMs));
  }
  return false;
}

function renderSearchResults(matches, keyword, options = {}) {
  const result = document.getElementById("dealSearchResult");
  if (!options.preserveOpenCard) {
    closeAllOpenDealCards({ immediate: true });
  }
  if (!matches.length) {
    result.innerHTML = `
      <div class="search-empty-state">
        <strong>${keyword ? `No deals matched "${escapeHtml(keyword)}".` : "No deals matched your current filters."}</strong>
        <span>Try a simpler keyword, remove a filter, or browse the latest deals.</span>
      </div>
    `;
    return;
  }
  const summary = keyword
    ? `${matches.length} matching deals for "${escapeHtml(keyword)}"`
    : `${matches.length} latest deals ready to browse`;
  const modeNote = systemStatus?.smtpConfigured
    ? "Alert delivery is ready for real email sends."
    : "Alert delivery is still in mock mode until SMTP is configured.";
  const nearbyCount = matches.filter((deal) => deal.zipCode === currentUser?.zipCode).length;
  const businessCount = matches.filter((deal) => deal.dealType === "company").length;
  const favoritesCount = currentUser?.alertInterests?.length || 0;
  result.innerHTML = `
    <div class="search-results-stack">
      <div class="search-summary">
        <div class="search-summary-copy">
          <strong>${summary}</strong>
          <span>${modeNote}</span>
        </div>
        <div class="search-summary-chips">
          <span class="search-summary-chip">${nearbyCount} in your zip</span>
          <span class="search-summary-chip">${businessCount} local business${businessCount === 1 ? "" : "es"}</span>
        </div>
      </div>
      <div class="search-guidance">
        <strong>${favoritesCount ? `${favoritesCount} favorite${favoritesCount === 1 ? "" : "s"} currently shape alerts` : "Search is open even before favorites are set"}</strong>
        <span>${favoritesCount ? "These results are searchable by everyone, but only favorites in your zip should trigger alerts." : "Set favorites to turn this broad search feed into a more personal alert experience later."}</span>
      </div>
      <div class="search-cards">
        ${matches.map((deal) => renderDealCard(deal)).join("")}
      </div>
    </div>
  `;
  attachFlipCardInteractions(result, matches);
}

function renderAlerts(notifications, deals) {
  const alertsView = document.getElementById("alertsView");
  const alertsSummary = document.getElementById("alertsSummary");
  const alertsMetrics = document.getElementById("alertsMetrics");
  const visibleDeals = deals.filter((deal) => deal.dealType === "company");
  const dealsById = new Map(visibleDeals.map((deal) => [deal.id, deal]));
  const mine = notifications
    .filter((notification) => notification.userId === currentUser?.id)
    .sort((left, right) => new Date(right.createdAt || 0) - new Date(left.createdAt || 0));
  if (!mine.length) {
    if (alertsSummary) {
      alertsSummary.textContent = "No alerts yet. Your saved interests will start shaping this feed once matching runs.";
    }
    if (alertsMetrics) {
      alertsMetrics.innerHTML = `
        <span class="alerts-metric-chip">0 matched favorites</span>
        <span class="alerts-metric-chip">0 delivered</span>
      `;
    }
    alertsView.innerHTML =
      '<div class="search-empty-state">No alerts yet. Run matching or add favorites to see personalized deals.</div>';
    return;
  }
  const sentCount = mine.filter((notification) => notification.status === "sent" || notification.status === "mocked").length;
  const uniqueMatched = unique(mine.map((notification) => notification.matchedInterest).filter(Boolean));
  if (alertsSummary) {
    alertsSummary.textContent = `${mine.length} alert${mine.length === 1 ? "" : "s"} ready, including ${sentCount} delivered or mocked results tied to your saved interests.`;
  }
  if (alertsMetrics) {
    alertsMetrics.innerHTML = `
      <span class="alerts-metric-chip">${uniqueMatched.length} matched favorite${uniqueMatched.length === 1 ? "" : "s"}</span>
      <span class="alerts-metric-chip">${sentCount} delivered</span>
      <span class="alerts-metric-chip">${mine.length - sentCount} queued or recent</span>
    `;
  }
  alertsView.innerHTML = mine
    .map((notification) => {
      const deal = dealsById.get(notification.dealId);
      const title = deal?.title || (notification.matchedInterest ? `${notification.matchedInterest} match` : "Matching deal");
      const source = deal?.sourceStore || deal?.title || "Local business";
      const location = deal?.address || deal?.zipCode || currentUser?.zipCode || "Nearby";
      return `
        <article class="alert-card">
          <div class="alert-card-top">
            <span class="deal-badge">Matched ${escapeHtml(notification.matchedInterest)}</span>
            <span class="alert-status is-${statusClassSuffix(notification.status)}">${escapeHtml(notification.status)}</span>
          </div>
          <strong>${escapeHtml(title)}</strong>
          <p>${escapeHtml(notification.message)}</p>
          <div class="alert-meta">
            <span>${escapeHtml(source)}</span>
            <span>${escapeHtml(formatAlertTimestamp(notification.createdAt))}</span>
          </div>
          <div class="alert-location">${escapeHtml(location)}</div>
        </article>
      `;
    })
    .join("");
}

function renderOverview(users, deals, notifications) {
  const primaryLabel = document.getElementById("overviewPrimaryLabel");
  const primaryValue = document.getElementById("overviewPrimaryValue");
  const primaryNote = document.getElementById("overviewPrimaryNote");
  const secondaryLabel = document.getElementById("overviewSecondaryLabel");
  const secondaryValue = document.getElementById("overviewSecondaryValue");
  const secondaryNote = document.getElementById("overviewSecondaryNote");
  const tertiaryLabel = document.getElementById("overviewTertiaryLabel");
  const tertiaryValue = document.getElementById("overviewTertiaryValue");
  const tertiaryNote = document.getElementById("overviewTertiaryNote");

  if (currentUser?.accountType === "company") {
    const mine = deals.filter((deal) => deal.createdByUserId === currentUser.id);
    const activeDeals = mine.filter((deal) => deal.status === "active");
    const expiredDeals = mine.filter((deal) => deal.status === "expired");
    primaryLabel.textContent = "Merchant";
    primaryValue.textContent = `${activeDeals.length}`;
    primaryNote.textContent = "active deals currently visible";
    secondaryLabel.textContent = "Expired";
    secondaryValue.textContent = `${expiredDeals.length}`;
    secondaryNote.textContent = "offers ready for refresh or repost";
    tertiaryLabel.textContent = "Nearby Users";
    tertiaryValue.textContent = `${users.filter((user) => user.accountType === "user" && user.zipCode === currentUser.zipCode).length}`;
    tertiaryNote.textContent = `${currentUser.companyName || "company"} in zip ${currentUser.zipCode}`;
    return;
  }

  const mine = notifications.filter((notification) => notification.userId === currentUser?.id);
  const inZip = deals.filter((deal) => deal.zipCode === currentUser?.zipCode);
  primaryLabel.textContent = "Favorites";
  primaryValue.textContent = `${currentUser?.alertInterests?.length || 0}`;
  primaryNote.textContent = "saved alert interests";
  secondaryLabel.textContent = "Matched Alerts";
  secondaryValue.textContent = `${mine.length}`;
  secondaryNote.textContent = "personalized deal alerts ready now";
  tertiaryLabel.textContent = "Local Deals";
  tertiaryValue.textContent = `${inZip.length}`;
  tertiaryNote.textContent = `searchable deals in zip ${currentUser?.zipCode || ""}`;
}

async function loadDeals(keyword = "") {
  const data = await api("/api/deals");
  const visibleDeals = data.deals.filter((deal) => deal.dealType === "company");
  const matches = filterDealsForSearch(visibleDeals, keyword, currentSearchFormValues());
  renderSearchResults(matches, keyword.trim());
  return visibleDeals;
}

function renderCompanyFormPreview() {
  const form = document.getElementById("companyDealForm");
  if (!form) return;
  const values = formDataToObject(form);
  const title = document.getElementById("companyPreviewTitle");
  const deal = document.getElementById("companyPreviewDeal");
  const address = document.getElementById("companyPreviewAddress");
  const expiration = document.getElementById("companyPreviewExpiration");
  const descriptionCount = document.getElementById("companyDescriptionCount");
  const statusHint = document.getElementById("companyStatusHint");
  const dateHint = document.getElementById("companyDateHint");

  const companyName = String(values.companyName || currentUser?.companyName || "Your business name").trim();
  const description = String(values.dealDescription || "").trim();
  const addressValue = String(values.address || "").trim();
  const expiresValue = String(values.expiresOn || "").trim();
  const statusValue = String(values.status || "active").trim();

  if (title) title.textContent = companyName || "Your business name";
  if (deal) {
    deal.textContent = description || "Your deal summary will appear here as you type.";
  }
  if (address) {
    address.textContent = addressValue || "Address preview";
  }
  if (expiration) {
    expiration.textContent = formatExpirationPreview(expiresValue);
  }
  if (descriptionCount) {
    const count = description.length;
    descriptionCount.textContent = `${count} character${count === 1 ? "" : "s"}`;
  }
  if (statusHint) {
    statusHint.textContent = statusValue === "draft"
      ? "Draft deals stay in your merchant feed until you are ready to publish."
      : "Active deals appear in search immediately.";
  }
  if (dateHint) {
    dateHint.textContent = expiresValue
      ? `This deal will stop circulating after ${expiresValue}.`
      : "Deals without an expiration date are harder to keep fresh.";
  }
}

function syncCompanyFormState(options = {}) {
  const form = document.getElementById("companyDealForm");
  if (!form) return;
  const expiresInput = form.querySelector('input[name="expiresOn"]');
  if (options.withDefaultExpiry && expiresInput && !expiresInput.value) {
    expiresInput.value = defaultCompanyExpiryValue();
  }
  renderCompanyFormPreview();
}

function resetCompanyForm() {
  const form = document.getElementById("companyDealForm");
  form.querySelector('input[name="address"]').value = "";
  form.querySelector('input[name="expiresOn"]').value = defaultCompanyExpiryValue();
  form.querySelector('select[name="status"]').value = "active";
  form.querySelector('textarea[name="dealDescription"]').value = "";
  document.getElementById("editingDealId").value = "";
  document.getElementById("companySubmitBtn").textContent = "Post Deal";
  document.getElementById("companyCancelBtn").classList.add("hidden");
  syncCompanyFormState();
  form.querySelector('input[name="companyName"]').focus();
}

function startDealEdit(dealId, deals) {
  const deal = deals.find((item) => item.id === dealId);
  if (!deal) return;
  const form = document.getElementById("companyDealForm");
  form.querySelector('input[name="companyName"]').value = deal.sourceStore || deal.title || currentUser.companyName || "";
  form.querySelector('input[name="zipCode"]').value = deal.zipCode || currentUser.zipCode || "";
  form.querySelector('input[name="address"]').value = deal.address || "";
  form.querySelector('input[name="expiresOn"]').value = deal.expiresOn || "";
  form.querySelector('select[name="status"]').value = deal.status === "expired" ? "active" : (deal.status || "active");
  form.querySelector('textarea[name="dealDescription"]').value = deal.description || "";
  document.getElementById("editingDealId").value = deal.id;
  document.getElementById("companySubmitBtn").textContent = "Save Deal Changes";
  document.getElementById("companyCancelBtn").classList.remove("hidden");
  syncCompanyFormState();
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  form.querySelector('input[name="address"]').focus();
}

async function refreshDashboard() {
  if (!currentUser) return;
  const requests = [
    api("/api/users"),
    api("/api/deals"),
    api("/api/notifications"),
  ];
  if (currentUser.accountType === "company") {
    requests.push(api("/api/company-deals"));
  }
  const [users, deals, notifications, companyDeals] = await Promise.all(requests);
  dashboardState = {
    users: users.users || [],
    deals: deals.deals || [],
    notifications: notifications.notifications || [],
    companyDeals: companyDeals?.deals || [],
  };
  document.getElementById("usersView").textContent = JSON.stringify(users.users, null, 2);
  document.getElementById("dealsView").textContent = JSON.stringify(deals.deals, null, 2);
  document.getElementById("notificationsView").textContent = JSON.stringify(notifications.notifications, null, 2);
  renderCurrentDashboardState();
}

async function refreshDashboardSafely() {
  if (isFileRuntime()) {
    renderRuntimeModeNote();
    return false;
  }
  try {
    await refreshDashboard();
    return true;
  } catch (error) {
    const fallbackMessage = currentUser?.accountType === "company"
      ? "Dashboard data did not fully load yet."
      : "Some dashboard data did not fully load yet.";
    setHeroActionMessage(error?.message || fallbackMessage, "error");
    return false;
  }
}

function startBackgroundRefreshLoops() {
  if (statusRefreshTimer) window.clearInterval(statusRefreshTimer);
  if (dashboardRefreshTimer) window.clearInterval(dashboardRefreshTimer);
  statusRefreshTimer = window.setInterval(() => {
    loadSystemStatus().catch(() => {});
  }, STATUS_REFRESH_MS);
  dashboardRefreshTimer = window.setInterval(() => {
    if (!currentUser || isFileRuntime()) return;
    refreshDashboardSafely().catch(() => {});
  }, DASHBOARD_REFRESH_MS);
}

document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = event.currentTarget.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Log In", "Logging in...");
  try {
    const values = formDataToObject(event.currentTarget);
    if (usingHostedAuth()) {
      const { data, error } = await supabaseClient.auth.signInWithPassword({
        email: values.email,
        password: values.password,
      });
      if (error) throw error;
      pendingVerificationEmail = "";
      renderAuthModeUI();
      await syncHostedSession(data.session, { refresh: true });
    } else {
      const data = await api("/api/login", {
        method: "POST",
        body: JSON.stringify(values),
      });
      setSession(data);
      await refreshDashboard();
    }
    setAuthView("login");
    setResultMessage("loginResult", "Logged in.", "success");
    setHeroActionMessage("", "default");
  } catch (error) {
    if (usingHostedAuth() && isEmailVerificationError(error)) {
      setPendingVerification(formDataToObject(event.currentTarget).email);
    }
    setResultMessage("loginResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, "Log In");
  }
});

document.getElementById("userSignupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Create User Account", "Creating account...");
  try {
    const values = formDataToObject(form);
    validateSignup(values);
    if (usingHostedAuth()) {
      const { data, error } = await supabaseClient.auth.signUp({
        email: values.email,
        password: values.password,
        options: {
          emailRedirectTo: hostedAuthRedirectUrl(),
          data: {
            account_type: "user",
            phone_number: values.phoneNumber,
            zip_code: values.zipCode,
            display_name: values.email.split("@")[0],
          },
        },
      });
      if (error) throw error;
      if (data.session?.access_token) {
        await syncHostedSession(data.session, { refresh: true });
        setResultMessage("userSignupResult", "User account created. You are now logged in.", "success");
      } else {
        setPendingVerification(values.email);
        setAuthView("login");
        setResultMessage("loginResult", "User account created. Check your email to verify the account, then log in.", "success");
      }
    } else {
      const data = await api("/api/signup", {
        method: "POST",
        body: JSON.stringify({
          accountType: "user",
          phoneNumber: values.phoneNumber,
          email: values.email,
          password: values.password,
          zipCode: values.zipCode,
        }),
      });
      setSession(data);
      setResultMessage("userSignupResult", `${data.message} You are now logged in.`, "success");
      await refreshDashboard();
    }
    if (!currentUser) form.reset();
    setHeroActionMessage("", "default");
  } catch (error) {
    setResultMessage("userSignupResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, "Create User Account");
  }
});

document.getElementById("companySignupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Create Company Account", "Creating account...");
  try {
    const values = formDataToObject(form);
    validateSignup(values);
    if (usingHostedAuth()) {
      const { data, error } = await supabaseClient.auth.signUp({
        email: values.email,
        password: values.password,
        options: {
          emailRedirectTo: hostedAuthRedirectUrl(),
          data: {
            account_type: "company",
            company_name: values.companyName,
            phone_number: values.phoneNumber,
            zip_code: values.zipCode,
            contact_name: values.companyName,
          },
        },
      });
      if (error) throw error;
      if (data.session?.access_token) {
        await syncHostedSession(data.session, { refresh: true });
        setResultMessage("companySignupResult", "Company account created. You are now logged in.", "success");
      } else {
        setPendingVerification(values.email);
        setAuthView("login");
        setResultMessage("loginResult", "Company account created. Check your email to verify the account, then log in.", "success");
      }
    } else {
      const data = await api("/api/signup", {
        method: "POST",
        body: JSON.stringify({
          accountType: "company",
          companyName: values.companyName,
          phoneNumber: values.phoneNumber,
          email: values.email,
          password: values.password,
          zipCode: values.zipCode,
        }),
      });
      setSession(data);
      setResultMessage("companySignupResult", `${data.message} You are now logged in.`, "success");
      await refreshDashboard();
    }
    if (!currentUser) form.reset();
    setHeroActionMessage("", "default");
  } catch (error) {
    setResultMessage("companySignupResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, "Create Company Account");
  }
});

document.getElementById("passwordResetRequestForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Send Reset Instructions", "Sending...");
  try {
    const values = formDataToObject(form);
    if (usingHostedAuth()) {
      const { error } = await supabaseClient.auth.resetPasswordForEmail(values.email, {
        redirectTo: hostedAuthRedirectUrl(),
      });
      if (error) throw error;
      setResultMessage("passwordResetRequestResult", "Check your email for a secure password reset link.", "success");
    } else {
      const data = await api("/api/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email: values.email }),
      });
      systemStatus = { ...systemStatus, ...data };
      renderAuthModeUI();
      renderSystemStatus();
      const extra = data.resetToken ? ` Reset token: ${data.resetToken}` : "";
      setResultMessage("passwordResetRequestResult", `${data.message}${extra}`, "success");
      const tokenInput = document.getElementById("passwordResetTokenInput");
      if (tokenInput && data.resetToken) tokenInput.value = data.resetToken;
      if (data.resetToken) {
        setAuthView("resetConfirm");
      }
    }
  } catch (error) {
    setResultMessage("passwordResetRequestResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, "Send Reset Instructions");
  }
});

document.getElementById("passwordResetConfirmForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Update Password", "Updating...");
  try {
    const values = formDataToObject(form);
    validatePasswordReset(values);
    if (usingHostedAuth()) {
      const { data: sessionData } = await supabaseClient.auth.getSession();
      if (!sessionData.session?.access_token && lastSupabaseEvent !== "PASSWORD_RECOVERY") {
        throw new Error("Open the password reset link from your email first.");
      }
      const { error } = await supabaseClient.auth.updateUser({ password: values.newPassword });
      if (error) throw error;
      const { data: refreshedSession } = await supabaseClient.auth.getSession();
      pendingVerificationEmail = "";
      renderAuthModeUI();
      await syncHostedSession(refreshedSession.session, { refresh: true });
      setResultMessage("passwordResetConfirmResult", "Password updated. You are now logged in.", "success");
    } else {
      const data = await api("/api/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({ token: values.token, newPassword: values.newPassword }),
      });
      setSession(data);
      setResultMessage("passwordResetConfirmResult", data.message, "success");
      await refreshDashboard();
    }
    window.history.replaceState({}, "", window.location.pathname);
    setHeroActionMessage("", "default");
  } catch (error) {
    setResultMessage("passwordResetConfirmResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, "Update Password");
  }
});

document.getElementById("changePasswordForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Change Password", "Changing...");
  try {
    const values = formDataToObject(form);
    validateChangePassword(values);
    if (usingHostedAuth()) {
      const { error: signInError } = await supabaseClient.auth.signInWithPassword({
        email: currentUser.email,
        password: values.currentPassword,
      });
      if (signInError) throw new Error("Current password is incorrect");
      const { error } = await supabaseClient.auth.updateUser({ password: values.newPassword });
      if (error) throw error;
      const { data: refreshedSession } = await supabaseClient.auth.getSession();
      await syncHostedSession(refreshedSession.session, { refresh: false });
      setResultMessage("changePasswordResult", "Password changed through hosted auth.", "success");
    } else {
      const data = await api("/api/account/password", {
        method: "POST",
        body: JSON.stringify({
          currentPassword: values.currentPassword,
          newPassword: values.newPassword,
        }),
      });
      setSession(data);
      setResultMessage("changePasswordResult", data.message, "success");
    }
    form.reset();
  } catch (error) {
    setResultMessage("changePasswordResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, "Change Password");
    wirePasswordToggles(form);
  }
});

document.getElementById("companyDealForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.getElementById("companySubmitBtn");
  setButtonLoading(submitButton, true, submitButton.textContent.trim(), "Saving deal...");
  try {
    const values = formDataToObject(form);
    const editingDealId = values.editingDealId;
    const data = await api(editingDealId ? `/api/company-deals/${editingDealId}` : "/api/company-deals", {
      method: editingDealId ? "PUT" : "POST",
      body: JSON.stringify(values),
    });
    setResultMessage("companyDealResult", data.message, "success");
    if (data.deal) {
      const existing = companyDashboardDeals().filter((deal) => deal.id !== data.deal.id);
      dashboardState.companyDeals = [data.deal, ...existing];
      renderCurrentDashboardState();
    }
    resetCompanyForm();
    void refreshDashboardEventually({ attempts: 5, delayMs: 1000 });
    document.getElementById("companyDealsView")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setResultMessage("companyDealResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, document.getElementById("editingDealId").value ? "Save Deal Changes" : "Post Deal");
  }
});

document.getElementById("companyDealForm").addEventListener("input", () => {
  syncCompanyFormState();
});

document.getElementById("companyDealForm").addEventListener("change", () => {
  syncCompanyFormState();
});

document.getElementById("dealSearchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = event.currentTarget.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Search", "Searching...");
  const values = formDataToObject(event.currentTarget);
  try {
    await loadDeals(values.keyword || "");
    scrollIntoViewIfNeeded(document.getElementById("dealSearchResult"), { topBuffer: 120 });
  } catch (error) {
    document.getElementById("dealSearchResult").innerHTML =
      `<div class="search-empty-state">${escapeHtml(error.message)}</div>`;
  } finally {
    setButtonLoading(submitButton, false, "Search");
  }
});

document.getElementById("browseLatestBtn").addEventListener("click", async () => {
  const button = document.getElementById("browseLatestBtn");
  setButtonLoading(button, true, "Browse Latest Deals", "Loading deals...");
  document.getElementById("dealSearchForm").reset();
  try {
    await loadDeals();
    scrollIntoViewIfNeeded(document.getElementById("dealSearchResult"), { topBuffer: 120 });
  } catch (error) {
    document.getElementById("dealSearchResult").innerHTML =
      `<div class="search-empty-state">${escapeHtml(error.message)}</div>`;
  } finally {
    setButtonLoading(button, false, "Browse Latest Deals");
  }
});

document.getElementById("clearSearchFiltersBtn").addEventListener("click", async () => {
  const form = document.getElementById("dealSearchForm");
  const button = document.getElementById("clearSearchFiltersBtn");
  setButtonLoading(button, true, "Clear Filters", "Clearing...");
  form.reset();
  try {
    await loadDeals();
    setHeroActionMessage("", "default");
  } catch (error) {
    document.getElementById("dealSearchResult").innerHTML =
      `<div class="search-empty-state">${escapeHtml(error.message)}</div>`;
  } finally {
    setButtonLoading(button, false, "Clear Filters");
  }
});

document.querySelectorAll("[data-search-shortcut]").forEach((button) => {
  button.addEventListener("click", async () => {
    const keyword = button.dataset.searchShortcut || "";
    const form = document.getElementById("dealSearchForm");
    const input = form.querySelector('input[name="keyword"]');
    if (input) input.value = keyword;
    try {
      await loadDeals(keyword);
      scrollIntoViewIfNeeded(document.getElementById("dealSearchResult"), { topBuffer: 120 });
    } catch (error) {
      document.getElementById("dealSearchResult").innerHTML =
        `<div class="search-empty-state">${escapeHtml(error.message)}</div>`;
    }
  });
});

document.getElementById("companyCancelBtn").addEventListener("click", () => {
  resetCompanyForm();
  setResultMessage("companyDealResult", "Edit canceled.", "muted");
});

document.getElementById("favoritesForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  setButtonLoading(submitButton, true, "Add To Favorites", "Saving favorites...");
  try {
    const values = formDataToObject(form);
    const newInterests = values.alertInterests
      .split(",")
      .map((item) => normalizeInterestLabel(item))
      .filter(Boolean);
    const existing = currentUser.alertInterests || [];
    const additions = newInterests.filter((item) => !existing.includes(item));
    if (!additions.length) {
      setResultMessage("favoritesResult", "Those favorites are already saved.", "muted");
      form.reset();
      form.querySelector('input[name="alertInterests"]').focus();
      return;
    }
    const alertInterests = unique([...existing, ...additions]);
    await saveAlertInterests(alertInterests);
    setResultMessage(
      "favoritesResult",
      additions.length === 1 ? `"${additions[0]}" added to favorites.` : `${additions.length} favorites added.`,
      "success"
    );
    form.reset();
    document.getElementById("favoritesDropdown")?.setAttribute("open", "open");
    if (activeTabId !== "favoritesPage") activateTab("favoritesPage");
    form.querySelector('input[name="alertInterests"]').focus();
  } catch (error) {
    setResultMessage("favoritesResult", error.message, "error");
  } finally {
    setButtonLoading(submitButton, false, "Add To Favorites");
  }
});

const ingestButton = document.getElementById("ingestBtn");
if (ingestButton) {
  ingestButton.addEventListener("click", async () => {
    setButtonLoading(ingestButton, true, "Ingest Mock Grocery Deals", "Ingesting...");
    try {
      const data = await api("/api/ingest", { method: "POST", body: "{}" });
      systemStatus = data;
      renderSystemStatus();
      setHeroActionMessage(`Mock grocery deals ready: ${data.dealsIngested}.`, "success");
      await refreshDashboard();
    } catch (error) {
      setHeroActionMessage(error.message, "error");
    } finally {
      setButtonLoading(ingestButton, false, "Ingest Mock Grocery Deals");
    }
  });
}

document.getElementById("matchBtn").addEventListener("click", async () => {
  const button = document.getElementById("matchBtn");
  setButtonLoading(button, true, "Run Matching", "Matching...");
  try {
    const data = await api("/api/match", { method: "POST", body: "{}" });
    systemStatus = data;
    renderSystemStatus();
    const modeLabel = data.smtpConfigured ? "real email delivery" : "mock email logging";
    setHeroActionMessage(`Notifications created: ${data.notificationsSent} using ${modeLabel}.`, "success");
    await refreshDashboard();
  } catch (error) {
    setHeroActionMessage(error.message, "error");
  } finally {
    setButtonLoading(button, false, "Run Matching");
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activeExpandedCard) {
    event.preventDefault();
    closeDealCard();
  }
});

document.getElementById("refreshBtn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  setButtonLoading(button, true, "Refresh Dashboard", "Refreshing...");
  try {
    await refreshDashboard();
  } finally {
    setButtonLoading(button, false, "Refresh Dashboard");
  }
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    if (!currentUser) return;
    activateTab(button.dataset.tab);
  });
});

document.querySelectorAll("[data-auth-target]").forEach((button) => {
  button.addEventListener("click", () => {
    clearAuthMessages();
    setAuthView(button.dataset.authTarget);
  });
});

document.getElementById("logoutBtn").addEventListener("click", () => {
  (async () => {
    try {
      if (usingHostedAuth()) {
        await supabaseClient.auth.signOut();
      } else if (sessionToken) {
        await api("/api/logout", { method: "POST", body: "{}" });
      }
    } catch {
      // Ignore logout failures and clear locally.
    } finally {
      pendingVerificationEmail = "";
      renderAuthModeUI();
      setAuthView("login");
      clearSession();
      renderSession();
      clearAuthMessages();
    }
  })();
});

document.getElementById("resendVerificationBtn")?.addEventListener("click", async (event) => {
  if (!usingHostedAuth() || !pendingVerificationEmail) return;
  const button = event.currentTarget;
  setButtonLoading(button, true, "Resend Verification Email", "Sending...");
  try {
    const { error } = await supabaseClient.auth.resend({
      type: "signup",
      email: pendingVerificationEmail,
      options: { emailRedirectTo: hostedAuthRedirectUrl() },
    });
    if (error) throw error;
    setResultMessage("loginResult", `Verification email sent to ${pendingVerificationEmail}.`, "success");
  } catch (error) {
    setResultMessage("loginResult", error.message, "error");
  } finally {
    setButtonLoading(button, false, "Resend Verification Email");
  }
});

try {
  activeTabId = localStorage.getItem(ACTIVE_TAB_KEY) || "searchPage";
} catch {
  localStorage.removeItem(ACTIVE_TAB_KEY);
}

async function bootstrapApp() {
  wirePasswordToggles();
  syncCompanyFormState({ withDefaultExpiry: true });
  renderRuntimeModeNote();
  renderSession();
  renderSystemStatus();
  startBackgroundRefreshLoops();
  await loadSystemStatus();
  await initializeHostedAuth();
  if (initialResetToken && !currentUser && !usingHostedAuth()) {
    setAuthView("resetConfirm");
  }
  if (usingHostedAuth()) {
    clearSession();
    try {
      const { data } = await supabaseClient.auth.getSession();
      if (data.session?.access_token) {
        pendingVerificationEmail = "";
        renderAuthModeUI();
        await syncHostedSession(data.session, { refresh: true });
      } else {
        clearSession();
        renderSession();
      }
    } catch {
      clearSession();
      renderSession();
    }
    return;
  }
  restoreStoredPrototypeSession();
  renderSession();
  if (sessionToken) {
    api("/api/session")
      .then((data) => {
        setSession(data);
        return refreshDashboardSafely();
      })
      .catch(() => {
        clearSession();
        renderSession();
      });
  } else {
    refreshDashboardSafely();
  }
}

bootstrapApp();
