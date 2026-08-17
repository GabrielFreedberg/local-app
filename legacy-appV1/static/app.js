const pretty = (data) => JSON.stringify(data, null, 2);
const STORAGE_KEY = "v1-user";
let currentUser = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function formDataToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function filterDealsByKeyword(deals, keyword) {
  const needle = keyword.trim().toLowerCase();
  if (!needle) return [];
  return deals.filter((deal) =>
    `${deal.productName} ${deal.description}`.toLowerCase().includes(needle)
  );
}

function formatDealMatch(deal) {
  if (deal.dealType === "company") {
    const area = deal.zipCodes?.[0] || "unknown area";
    return `${deal.companyName} has ${deal.description} at area ${area}`;
  }

  const area = deal.zipCodes?.[0] || "unknown area";
  const price =
    deal.salePrice == null ? "" : ` for $${Number(deal.salePrice).toFixed(2)}/${deal.unit}`;
  return `${deal.productName} is available${price} at area ${area}`;
}

function formatMatches(matches, keyword) {
  return matches.length
    ? matches.map((deal) => `- ${formatDealMatch(deal)}`).join("\n\n")
    : `No deals matched "${keyword}". Try another keyword or ingest deals first.`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function dealTitle(deal) {
  return deal.dealType === "company" ? deal.companyName : deal.productName;
}

function dealSource(deal) {
  if (deal.dealType === "company") return "Local Business";
  return deal.category || "Grocery";
}

function dealPriceLabel(deal) {
  if (deal.dealType === "company" || deal.salePrice == null) return "Local Offer";
  return `$${Number(deal.salePrice).toFixed(2)} / ${deal.unit}`;
}

function dealSavingsLabel(deal) {
  if (deal.salePrice == null || deal.regularPrice == null) return "";
  const savings = Number(deal.regularPrice) - Number(deal.salePrice);
  if (savings <= 0) return "";
  return `Save $${savings.toFixed(2)}`;
}

function matchingInterestForDeal(deal) {
  if (!currentUser || currentUser.accountType !== "user") return "";
  const interests = currentUser.alertInterests || [];
  const haystack = `${deal.productName} ${deal.description} ${deal.companyName || ""}`.toLowerCase();
  return interests.find((interest) => haystack.includes(interest.toLowerCase())) || "";
}

function renderDealsFeed(deals) {
  const feed = document.getElementById("dealsFeed");
  if (!feed) return;

  if (!currentUser || currentUser.accountType !== "user") {
    feed.innerHTML = "";
    return;
  }

  if (!deals.length) {
    feed.innerHTML = `
      <div class="feed-empty">
        <strong>No deals in the feed yet.</strong>
        <span>Click "Ingest Mock Deals" to load sample deals, then refresh the feed.</span>
      </div>
    `;
    return;
  }

  feed.innerHTML = deals
    .map((deal) => {
      const area = deal.zipCodes?.[0] || "Any area";
      const matchedInterest = matchingInterestForDeal(deal);
      const savings = dealSavingsLabel(deal);
      return `
        <article class="deal-post">
          <div class="deal-post-topline">
            <span>${escapeHtml(dealSource(deal))}</span>
            <span>Area ${escapeHtml(area)}</span>
          </div>
          <h3>${escapeHtml(dealTitle(deal))}</h3>
          <p>${escapeHtml(deal.description)}</p>
          <div class="deal-post-meta">
            <strong>${escapeHtml(dealPriceLabel(deal))}</strong>
            ${savings ? `<span>${escapeHtml(savings)}</span>` : ""}
            ${matchedInterest ? `<span class="match-chip">Matches ${escapeHtml(matchedInterest)}</span>` : ""}
          </div>
        </article>
      `;
    })
    .join("");
}

function activateTab(targetId) {
  document.querySelectorAll(".tab").forEach((tabButton) => {
    tabButton.classList.toggle("is-active", tabButton.dataset.tab === targetId);
  });

  document.querySelectorAll(".tab-page").forEach((page) => {
    page.classList.toggle("is-active", page.id === targetId);
  });
}

function currentActiveTab() {
  return document.querySelector(".tab.is-active")?.dataset.tab || null;
}

function defaultTabForUser(user) {
  return user?.accountType === "company" ? "companyPage" : "feedPage";
}

function allowedTabsForUser(user) {
  return user?.accountType === "company"
    ? ["companyPage"]
    : ["feedPage", "searchPage", "interestsPage"];
}

function resolvedTabForUser(user, preferredTab) {
  const allowedTabs = allowedTabsForUser(user);
  if (preferredTab && allowedTabs.includes(preferredTab)) {
    return preferredTab;
  }
  return defaultTabForUser(user);
}

function uniqueInterests(items) {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))];
}

async function saveAlertInterests(alertInterests) {
  const data = await api(`/api/users/${currentUser.userId}/interests`, {
    method: "PUT",
    body: JSON.stringify({ alertInterests }),
  });
  setCurrentUser(data.user);
  await refreshDashboard();
  return data.user;
}

function renderFavoritesList() {
  const container = document.getElementById("currentInterestsView");
  const count = document.getElementById("favoritesCount");

  if (!currentUser) {
    container.innerHTML = "";
    count.textContent = "0";
    return;
  }

  const interests = currentUser.alertInterests || [];
  count.textContent = String(interests.length);

  if (!interests.length) {
    container.innerHTML = '<div class="favorites-empty">No favorites saved yet.</div>';
    return;
  }

  container.innerHTML = interests
    .map(
      (interest) => `
        <div class="favorite-item">
          <span class="favorite-label">${interest}</span>
          <button
            class="favorite-heart"
            type="button"
            data-interest="${interest}"
            aria-label="Remove ${interest} from favorites"
            title="Remove from favorites"
          >♥</button>
        </div>
      `
    )
    .join("");

  container.querySelectorAll(".favorite-heart").forEach((button) => {
    button.addEventListener("click", async () => {
      const interestToRemove = button.dataset.interest;
      const updatedInterests = (currentUser.alertInterests || []).filter(
        (interest) => interest !== interestToRemove
      );
      await saveAlertInterests(updatedInterests);
      document.getElementById("interestsResult").textContent = `"${interestToRemove}" removed from favorites.`;
    });
  });
}

function setCurrentUser(user) {
  const activeTab = currentActiveTab();
  currentUser = user;
  if (user) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
  renderSession(activeTab);
}

function renderSession(preferredTab = null) {
  const authShell = document.getElementById("authShell");
  const appShell = document.getElementById("appShell");

  if (!currentUser) {
    authShell.classList.remove("hidden");
    appShell.classList.add("hidden");
    return;
  }

  authShell.classList.add("hidden");
  appShell.classList.remove("hidden");
  document.getElementById("sessionEmail").textContent = currentUser.email;
  document.getElementById("sessionType").textContent = currentUser.accountType === "company" ? "Company Account" : "User Account";
  document.getElementById("sessionZip").textContent = `Zip ${currentUser.zipCode}`;
  document.querySelectorAll(".role-company, .role-company-page").forEach((element) => {
    element.classList.toggle("hidden", currentUser.accountType !== "company");
  });
  document.querySelectorAll(".role-user, .role-user-page").forEach((element) => {
    element.classList.toggle("hidden", currentUser.accountType !== "user");
  });
  if (currentUser.accountType === "company") {
    document.getElementById("companyNameInput").value = currentUser.companyName || "";
    document.querySelector('#companyDealForm input[name="zipCode"]').value = currentUser.zipCode || "";
    document.querySelector('#companyDealForm textarea[name="dealDescription"]').value = "";
  }
  renderFavoritesList();
  activateTab(resolvedTabForUser(currentUser, preferredTab));
}

async function refreshDashboard() {
  if (!currentUser) return;
  const [users, deals, notifications] = await Promise.all([
    api("/api/users"),
    api("/api/deals"),
    api("/api/notifications"),
  ]);
  const emailOutbox = notifications.notifications.filter(
    (notification) => notification.channel === "email"
  );

  document.getElementById("usersView").textContent = pretty(users.users);
  document.getElementById("dealsView").textContent = pretty(deals.deals);
  document.getElementById("notificationsView").textContent = pretty(notifications.notifications);
  document.getElementById("emailOutboxView").textContent = pretty(emailOutbox);
  renderDealsFeed(deals.deals);
}

document.querySelectorAll(".tab").forEach((tabButton) => {
  tabButton.addEventListener("click", () => activateTab(tabButton.dataset.tab));
});

document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = document.getElementById("loginResult");
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify(formDataToObject(event.currentTarget)),
    });
    currentUser = data.user;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data.user));
    renderSession(defaultTabForUser(data.user));
    result.textContent = "Logged in.";
    await refreshDashboard();
  } catch (error) {
    result.textContent = error.message;
  }
});

document.getElementById("userSignupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const result = document.getElementById("userSignupResult");
  try {
    const payload = {
      ...formDataToObject(form),
      accountType: "user",
    };
    const data = await api("/api/signup", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    currentUser = data.user;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data.user));
    renderSession(defaultTabForUser(data.user));
    result.textContent = `${data.message} You are now logged in.`;
    form.reset();
    await refreshDashboard();
  } catch (error) {
    result.textContent = error.message;
  }
});

document.getElementById("companySignupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const result = document.getElementById("companySignupResult");
  try {
    const payload = {
      ...formDataToObject(form),
      accountType: "company",
    };
    const data = await api("/api/signup", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    currentUser = data.user;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data.user));
    renderSession(defaultTabForUser(data.user));
    result.textContent = `${data.message} You are now logged in.`;
    form.reset();
    await refreshDashboard();
  } catch (error) {
    result.textContent = error.message;
  }
});

document.getElementById("companyDealForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = document.getElementById("companyDealResult");
  if (!currentUser || currentUser.accountType !== "company") {
    result.textContent = "Only company accounts can add deals.";
    return;
  }
  try {
    const data = await api("/api/company-deals", {
      method: "POST",
      body: JSON.stringify(formDataToObject(event.currentTarget)),
    });
    result.textContent = pretty(data);
    await refreshDashboard();
  } catch (error) {
    result.textContent = error.message;
  }
});

document.getElementById("dealSearchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = formDataToObject(event.currentTarget);
  const result = document.getElementById("dealSearchResult");
  if (!currentUser || currentUser.accountType !== "user") {
    result.textContent = "Only user accounts can search deals.";
    return;
  }
  try {
    const data = await api("/api/deals");
    const matches = filterDealsByKeyword(data.deals, values.keyword);
    result.textContent = formatMatches(matches, values.keyword);
    await refreshDashboard();
  } catch (error) {
    result.textContent = error.message;
  }
});

document.getElementById("interestsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formDataToObject(event.currentTarget);
  const result = document.getElementById("interestsResult");
  if (!currentUser || currentUser.accountType !== "user") {
    result.textContent = "Only user accounts can manage favorites.";
    return;
  }
  try {
    const newInterests = values.alertInterests
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const existingInterests = currentUser.alertInterests || [];
    const alertInterests = uniqueInterests([...existingInterests, ...newInterests]);
    await saveAlertInterests(alertInterests);
    result.textContent = "Favorites updated.";
    form.reset();
  } catch (error) {
    result.textContent = error.message;
  }
});

document.getElementById("ingestBtn").addEventListener("click", async () => {
  const data = await api("/api/ingest", { method: "POST", body: "{}" });
  alert(`Mock ingestion complete. Deals loaded: ${data.dealsIngested}`);
  await refreshDashboard();
});

document.getElementById("matchBtn").addEventListener("click", async () => {
  const data = await api("/api/match", { method: "POST", body: "{}" });
  alert(
    `Match pass complete. Notifications sent: ${data.notificationsSent} ` +
      `(sms: ${data.notificationsByChannel.sms}, email: ${data.notificationsByChannel.email})`
  );
  await refreshDashboard();
});

document.getElementById("refreshBtn").addEventListener("click", refreshDashboard);
document.getElementById("refreshFeedBtn").addEventListener("click", refreshDashboard);

document.getElementById("logoutBtn").addEventListener("click", () => {
  setCurrentUser(null);
  document.getElementById("loginResult").textContent = "";
  document.getElementById("userSignupResult").textContent = "";
  document.getElementById("companySignupResult").textContent = "";
});

try {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    currentUser = JSON.parse(stored);
  }
} catch {
  localStorage.removeItem(STORAGE_KEY);
}

renderSession();
refreshDashboard().catch(() => {});
