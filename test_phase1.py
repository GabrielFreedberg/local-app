#!/usr/bin/env python3
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import app
from http.server import ThreadingHTTPServer


class Phase1ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name)
        app.DB_PATH = cls.temp_path / "phase1-test.db"
        app.NOTIFICATION_LOG = cls.temp_path / "notification-log.jsonl"
        app.MATCH_RUN_LOG = cls.temp_path / "match-run-log.jsonl"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.AppHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp_dir.cleanup()

    def setUp(self):
        for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM", "ANTHROPIC_API_KEY", "AI_CATEGORY_MODEL", "PORT"):
            os.environ.pop(key, None)
        app.ai_extract_categories.cache_clear()
        with app.LOGIN_ATTEMPT_LOCK:
            app.LOGIN_ATTEMPTS.clear()
        if app.DB_PATH.exists():
            app.DB_PATH.unlink()
        if app.NOTIFICATION_LOG.exists():
            app.NOTIFICATION_LOG.unlink()
        if app.MATCH_RUN_LOG.exists():
            app.MATCH_RUN_LOG.unlink()
        app.update_scheduler_state(
            enabled=False,
            intervalSeconds=0,
            lastTrigger="",
            lastStartedAt="",
            lastCompletedAt="",
            lastSucceededAt="",
            lastRunNotifications=0,
            lastRunError="",
            runCount=0,
        )
        app.init_db()
        app.ensure_mock_pizza_deals()
        app.ensure_mock_grocery_deals()

    def api(self, path, method="GET", data=None, token=None):
        body = None if data is None else json.dumps(data).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.url(path), data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read().decode("utf-8")
                return response.status, json.loads(payload or "{}")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8")
            return exc.code, json.loads(payload or "{}")

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def unique_email(self, prefix):
        return f"{prefix}-{time.time_ns()}@example.com"

    def signup_user(self, **overrides):
        payload = {
            "accountType": "user",
            "phoneNumber": "555-111-2222",
            "email": self.unique_email("user"),
            "password": "Pass1234",
            "zipCode": "80205",
        }
        payload.update(overrides)
        return self.api("/api/signup", method="POST", data=payload)

    def signup_company(self, **overrides):
        payload = {
            "accountType": "company",
            "companyName": "Test Pizza Co",
            "phoneNumber": "555-333-4444",
            "email": self.unique_email("company"),
            "password": "Pass1234",
            "zipCode": "80205",
        }
        payload.update(overrides)
        return self.api("/api/signup", method="POST", data=payload)

    def test_signup_hashes_password_and_returns_session(self):
        status, payload = self.signup_user()
        self.assertEqual(status, 201)
        self.assertTrue(payload["sessionToken"])
        conn = app.get_db()
        row = conn.execute("SELECT password FROM users WHERE id = ?", (payload["user"]["id"],)).fetchone()
        session_row = conn.execute("SELECT token, token_hash FROM sessions WHERE user_id = ?", (payload["user"]["id"],)).fetchone()
        conn.close()
        self.assertTrue(row["password"].startswith("pbkdf2_sha256$"))
        self.assertNotEqual(row["password"], "Pass1234")
        self.assertIsNotNone(session_row)
        self.assertNotEqual(session_row["token"], payload["sessionToken"])
        self.assertEqual(session_row["token_hash"], app.hash_token(payload["sessionToken"]))

    def test_signup_rejects_weak_password(self):
        status, payload = self.signup_user(password="weakpass")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "Password must include at least one number")

    def test_duplicate_email_conflicts(self):
        email = self.unique_email("dupe")
        first_status, _ = self.signup_user(email=email)
        second_status, payload = self.signup_user(email=email)
        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 409)
        self.assertEqual(payload["error"], "An account with that email already exists")

    def test_protected_routes_require_authentication(self):
        status_users, payload_users = self.api("/api/users")
        status_notifications, payload_notifications = self.api("/api/notifications")
        status_match, payload_match = self.api("/api/match", method="POST", data={})
        self.assertEqual((status_users, payload_users["error"]), (401, "Authentication required"))
        self.assertEqual((status_notifications, payload_notifications["error"]), (401, "Authentication required"))
        self.assertEqual((status_match, payload_match["error"]), (401, "Authentication required"))

    def test_user_can_update_own_interests_with_normalization(self):
        _, signup = self.signup_user()
        token = signup["sessionToken"]
        user_id = signup["user"]["id"]
        status, payload = self.api(
            f"/api/users/{user_id}/interests",
            method="PUT",
            token=token,
            data={"alertInterests": [" Pizza ", "pizza", "  cold brew ", ""]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["alertInterests"], ["pizza", "cold brew"])

    def test_user_cannot_update_another_users_interests(self):
        _, first = self.signup_user()
        _, second = self.signup_user()
        status, payload = self.api(
            f"/api/users/{second['user']['id']}/interests",
            method="PUT",
            token=first["sessionToken"],
            data={"alertInterests": ["pizza"]},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Not authorized")

    def test_company_deal_flow_create_update_delete(self):
        _, signup = self.signup_company()
        token = signup["sessionToken"]
        create_status, create_payload = self.api(
            "/api/company-deals",
            method="POST",
            token=token,
            data={
                "companyName": "Test Pizza Co",
                "zipCode": "80205",
                "address": "123 Blake St, Denver, CO 80205",
                "status": "active",
                "expiresOn": "2099-12-31",
                "dealDescription": "Two slices and a drink for lunch.",
            },
        )
        self.assertEqual(create_status, 201)
        deal_id = create_payload["dealId"]

        deals_status, deals_payload = self.api("/api/deals")
        self.assertEqual(deals_status, 200)
        self.assertTrue(any(deal["id"] == deal_id for deal in deals_payload["deals"]))

        company_feed_status, company_feed_payload = self.api("/api/company-deals", token=token)
        self.assertEqual(company_feed_status, 200)
        mine = next(deal for deal in company_feed_payload["deals"] if deal["id"] == deal_id)
        self.assertEqual(mine["status"], "active")
        self.assertEqual(mine["expiresOn"], "2099-12-31")

        update_status, update_payload = self.api(
            f"/api/company-deals/{deal_id}",
            method="PUT",
            token=token,
            data={
                "companyName": "Test Pizza Co",
                "zipCode": "80205",
                "address": "400 Larimer St, Denver, CO 80205",
                "status": "draft",
                "expiresOn": "2099-11-30",
                "dealDescription": "Updated dinner special with garlic knots.",
            },
        )
        self.assertEqual(update_status, 200)
        self.assertEqual(update_payload["message"], "Company deal updated.")

        delete_status, delete_payload = self.api(
            f"/api/company-deals/{deal_id}",
            method="DELETE",
            token=token,
            data={},
        )
        self.assertEqual(delete_status, 200)
        self.assertEqual(delete_payload["message"], "Company deal removed.")

        refreshed_status, refreshed_payload = self.api("/api/deals")
        self.assertEqual(refreshed_status, 200)
        self.assertFalse(any(deal["id"] == deal_id for deal in refreshed_payload["deals"]))

    def test_duplicate_company_deal_create_archives_older_exact_match(self):
        _, signup = self.signup_company()
        token = signup["sessionToken"]
        payload = {
            "companyName": "Test Pizza Co",
            "zipCode": "80205",
            "address": "123 Blake St, Denver, CO 80205",
            "status": "active",
            "expiresOn": "2099-12-31",
            "dealDescription": "Same exact dinner special.",
        }
        first_status, first_payload = self.api("/api/company-deals", method="POST", token=token, data=payload)
        second_status, second_payload = self.api("/api/company-deals", method="POST", token=token, data=payload)
        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 201)
        self.assertNotEqual(first_payload["dealId"], second_payload["dealId"])

        feed_status, feed_payload = self.api("/api/company-deals", token=token)
        self.assertEqual(feed_status, 200)
        visible = [deal for deal in feed_payload["deals"] if deal["description"] == payload["dealDescription"]]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["id"], second_payload["dealId"])

        conn = app.get_db()
        rows = conn.execute(
            "SELECT id, status FROM deals WHERE created_by_user_id = ? AND description = ? ORDER BY created_at DESC",
            (signup["user"]["id"], payload["dealDescription"]),
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], second_payload["dealId"])
        self.assertEqual(rows[0]["status"], "active")
        self.assertEqual(rows[1]["id"], first_payload["dealId"])
        self.assertEqual(rows[1]["status"], "archived")

    def test_expired_company_deal_stays_in_merchant_feed_but_leaves_public_feed(self):
        _, signup = self.signup_company()
        token = signup["sessionToken"]
        create_status, create_payload = self.api(
            "/api/company-deals",
            method="POST",
            token=token,
            data={
                "companyName": "Test Pizza Co",
                "zipCode": "80205",
                "address": "123 Blake St, Denver, CO 80205",
                "status": "active",
                "expiresOn": "2001-01-01",
                "dealDescription": "This offer should expire immediately.",
            },
        )
        self.assertEqual(create_status, 201)
        deal_id = create_payload["dealId"]

        public_status, public_payload = self.api("/api/deals")
        self.assertEqual(public_status, 200)
        self.assertFalse(any(deal["id"] == deal_id for deal in public_payload["deals"]))

        company_feed_status, company_feed_payload = self.api("/api/company-deals", token=token)
        self.assertEqual(company_feed_status, 200)
        expired_deal = next(deal for deal in company_feed_payload["deals"] if deal["id"] == deal_id)
        self.assertEqual(expired_deal["status"], "expired")
        self.assertEqual(expired_deal["expiresOn"], "2001-01-01")

    def test_company_deal_requires_address(self):
        _, signup = self.signup_company()
        status, payload = self.api(
            "/api/company-deals",
            method="POST",
            token=signup["sessionToken"],
            data={
                "companyName": "Test Pizza Co",
                "zipCode": "80205",
                "address": "",
                "dealDescription": "One free topping tonight.",
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "Street address is required")

    def test_company_deal_defaults_expiration_when_omitted(self):
        _, signup = self.signup_company()
        token = signup["sessionToken"]
        create_status, create_payload = self.api(
            "/api/company-deals",
            method="POST",
            token=token,
            data={
                "companyName": "Test Pizza Co",
                "zipCode": "80205",
                "address": "123 Blake St, Denver, CO 80205",
                "status": "active",
                "dealDescription": "Default expiration should be applied.",
            },
        )
        self.assertEqual(create_status, 201)

        company_feed_status, company_feed_payload = self.api("/api/company-deals", token=token)
        self.assertEqual(company_feed_status, 200)
        created = next(deal for deal in company_feed_payload["deals"] if deal["id"] == create_payload["dealId"])
        self.assertTrue(created["expiresOn"])
        expected = (datetime.now(timezone.utc) + timedelta(days=app.DEFAULT_COMPANY_DEAL_TTL_DAYS)).date().isoformat()
        self.assertEqual(created["expiresOn"], expected)

    def test_user_cannot_create_company_deal(self):
        _, signup = self.signup_user()
        status, payload = self.api(
            "/api/company-deals",
            method="POST",
            token=signup["sessionToken"],
            data={
                "companyName": "Not Allowed",
                "zipCode": "80205",
                "address": "123 Main St, Denver, CO 80205",
                "dealDescription": "Should not work.",
            },
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Company account required")

    def test_password_reset_flow_revokes_old_session_and_rejects_reuse(self):
        _, signup = self.signup_user()
        old_token = signup["sessionToken"]
        email = signup["user"]["email"]

        request_status, request_payload = self.api(
            "/api/password-reset/request",
            method="POST",
            data={"email": email},
        )
        self.assertEqual(request_status, 200)
        self.assertIn("resetToken", request_payload)
        reset_token = request_payload["resetToken"]
        conn = app.get_db()
        reset_row = conn.execute("SELECT token, token_hash FROM password_reset_tokens").fetchone()
        conn.close()
        self.assertIsNotNone(reset_row)
        self.assertNotEqual(reset_row["token"], reset_token)
        self.assertEqual(reset_row["token_hash"], app.hash_token(reset_token))

        confirm_status, confirm_payload = self.api(
            "/api/password-reset/confirm",
            method="POST",
            data={"token": reset_token, "newPassword": "Better123"},
        )
        self.assertEqual(confirm_status, 200)
        self.assertTrue(confirm_payload["sessionToken"])

        old_session_status, _ = self.api("/api/session", token=old_token)
        self.assertEqual(old_session_status, 401)

        login_old_status, _ = self.api(
            "/api/login",
            method="POST",
            data={"email": email, "password": "Pass1234"},
        )
        self.assertEqual(login_old_status, 401)

        login_new_status, login_new_payload = self.api(
            "/api/login",
            method="POST",
            data={"email": email, "password": "Better123"},
        )
        self.assertEqual(login_new_status, 200)
        self.assertTrue(login_new_payload["sessionToken"])

        reuse_status, reuse_payload = self.api(
            "/api/password-reset/confirm",
            method="POST",
            data={"token": reset_token, "newPassword": "Another123"},
        )
        self.assertEqual(reuse_status, 400)
        self.assertIn(reuse_payload["error"], {"Reset link has already been used", "Reset link is invalid"})

    def test_logout_revokes_current_session(self):
        _, signup = self.signup_user()
        token = signup["sessionToken"]

        logout_status, logout_payload = self.api("/api/logout", method="POST", token=token, data={})
        self.assertEqual(logout_status, 200)
        self.assertTrue(logout_payload["ok"])

        session_status, session_payload = self.api("/api/session", token=token)
        self.assertEqual(session_status, 401)
        self.assertEqual(session_payload["error"], "Session not found")

    def test_match_flow_only_creates_notifications_for_matching_zip_and_interest(self):
        _, signup = self.signup_user(zipCode="80205")
        token = signup["sessionToken"]
        user_id = signup["user"]["id"]
        self.api(
            f"/api/users/{user_id}/interests",
            method="PUT",
            token=token,
            data={"alertInterests": ["pizza"]},
        )

        first_status, first_payload = self.api("/api/match", method="POST", token=token, data={})
        self.assertEqual(first_status, 200)
        self.assertGreater(first_payload["notificationsSent"], 0)

        notifications_status, notifications_payload = self.api("/api/notifications", token=token)
        self.assertEqual(notifications_status, 200)
        mine = [item for item in notifications_payload["notifications"] if item["userId"] == user_id]
        self.assertTrue(mine)
        self.assertTrue(all(item["matchedInterest"] == "pizza" for item in mine))
        self.assertTrue(all("80205" in item["message"] for item in mine))

        second_status, second_payload = self.api("/api/match", method="POST", token=token, data={})
        self.assertEqual(second_status, 200)
        self.assertEqual(second_payload["notificationsSent"], 0)

    def test_notifications_endpoint_only_returns_authenticated_users_alerts(self):
        _, first_signup = self.signup_user(zipCode="80205")
        _, second_signup = self.signup_user(zipCode="80205")
        first_token = first_signup["sessionToken"]
        first_user_id = first_signup["user"]["id"]
        second_user_id = second_signup["user"]["id"]
        self.api(
            f"/api/users/{first_user_id}/interests",
            method="PUT",
            token=first_token,
            data={"alertInterests": ["pizza"]},
        )
        self.api(
            f"/api/users/{second_user_id}/interests",
            method="PUT",
            token=second_signup["sessionToken"],
            data={"alertInterests": ["pizza"]},
        )

        status, _ = self.api("/api/match", method="POST", token=first_token, data={})
        self.assertEqual(status, 200)

        notifications_status, notifications_payload = self.api("/api/notifications", token=first_token)
        self.assertEqual(notifications_status, 200)
        self.assertTrue(notifications_payload["notifications"])
        self.assertTrue(all(item["userId"] == first_user_id for item in notifications_payload["notifications"]))

    def test_local_match_flow_dedupes_before_email_send(self):
        _, signup = self.signup_user(zipCode="80205")
        token = signup["sessionToken"]
        user_id = signup["user"]["id"]
        self.api(
            f"/api/users/{user_id}/interests",
            method="PUT",
            token=token,
            data={"alertInterests": ["pizza"]},
        )

        with mock.patch.object(app, "send_match_email", return_value={"channel": "email", "status": "mocked", "error": None}) as send_mock:
            first_status, first_payload = self.api("/api/match", method="POST", token=token, data={})
            second_status, second_payload = self.api("/api/match", method="POST", token=token, data={})

        self.assertEqual(first_status, 200)
        self.assertGreater(first_payload["notificationsSent"], 0)
        self.assertEqual(second_status, 200)
        self.assertEqual(second_payload["notificationsSent"], 0)
        # Digesting: however many deals matched, this one user gets exactly
        # ONE email covering all of them in this run, and zero on the second
        # (fully deduped) run.
        self.assertEqual(send_mock.call_count, 1)
        sent_matches = send_mock.call_args.args[1]
        self.assertEqual(len(sent_matches), first_payload["notificationsSent"])

    def test_system_status_reports_mock_mode_without_smtp(self):
        status, payload = self.api("/api/system-status")
        self.assertEqual(status, 200)
        self.assertEqual(payload["authProvider"], "local_prototype")
        self.assertEqual(payload["authMode"], "local_session_tokens")
        self.assertFalse(payload["smtpConfigured"])
        self.assertEqual(payload["notificationMode"], "mock_email")
        self.assertEqual(payload["passwordResetMode"], "manual_token")
        self.assertIn("matchingScheduler", payload)
        self.assertFalse(payload["matchingScheduler"]["enabled"])

    def test_manual_match_updates_scheduler_run_state(self):
        _, signup = self.signup_user(zipCode="80205")
        token = signup["sessionToken"]
        user_id = signup["user"]["id"]
        self.api(
            f"/api/users/{user_id}/interests",
            method="PUT",
            token=token,
            data={"alertInterests": ["pizza"]},
        )

        status, payload = self.api("/api/match", method="POST", token=token, data={})
        self.assertEqual(status, 200)
        scheduler = payload["matchingScheduler"]
        self.assertEqual(scheduler["lastTrigger"], "manual")
        self.assertTrue(scheduler["lastStartedAt"])
        self.assertTrue(scheduler["lastCompletedAt"])
        self.assertTrue(scheduler["lastSucceededAt"])
        self.assertGreaterEqual(scheduler["lastRunNotifications"], 1)
        self.assertEqual(scheduler["runCount"], 1)
        self.assertEqual(scheduler["lastRunError"], "")
        self.assertTrue(app.MATCH_RUN_LOG.exists())

    def test_local_signup_and_login_endpoints_are_blocked_when_hosted_auth_is_enabled(self):
        with mock.patch.object(app, "supabase_is_configured", return_value=True):
            signup_status, signup_payload = self.api(
                "/api/signup",
                method="POST",
                data={
                    "accountType": "user",
                    "phoneNumber": "555-111-2222",
                    "email": self.unique_email("hosted"),
                    "password": "Pass1234",
                    "zipCode": "80205",
                },
            )
            login_status, login_payload = self.api(
                "/api/login",
                method="POST",
                data={"email": "hosted@example.com", "password": "Pass1234"},
            )
        self.assertEqual(signup_status, 400)
        self.assertEqual(login_status, 400)
        self.assertEqual(signup_payload["error"], "Hosted Supabase auth is enabled. Complete auth actions through Supabase.")
        self.assertEqual(login_payload["error"], "Hosted Supabase auth is enabled. Complete auth actions through Supabase.")

    def test_all_deals_uses_supabase_in_hosted_mode(self):
        supabase_rows = [
            {
                "id": "deal-1",
                "deal_type": "company",
                "company_id": "company-1",
                "title": "River North Pizza",
                "description": "Free knots with any pie",
                "zip_code": "80205",
                "address": "123 Main St, Denver, CO 80205",
                "sale_price": None,
                "regular_price": None,
                "unit": "offer",
                "category": "Local Business",
                "source_store_name": "River North Pizza",
                "status": "active",
                "ends_at": "2099-12-31T23:59:59+00:00",
                "created_at": "2026-07-27T10:00:00+00:00",
                "updated_at": "2026-07-27T10:00:00+00:00",
            }
        ]
        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "supabase_rest_request", return_value=supabase_rows):
            deals = app.all_deals()
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0]["id"], "deal-1")
        self.assertEqual(deals[0]["createdByUserId"], "company-1")
        self.assertEqual(deals[0]["sourceStore"], "River North Pizza")
        self.assertEqual(deals[0]["expiresOn"], "2099-12-31")

    def test_company_deal_create_uses_supabase_in_hosted_mode(self):
        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "get_authenticated_user", return_value=({"id": "company-1", "account_type": "company"}, "token")), \
             mock.patch.object(app, "create_supabase_company_deal", return_value={"id": "deal-123"}) as create_mock:
            conn = app.get_db()
            conn.execute(
                """
                INSERT INTO users (id, account_type, email, password, phone_number, zip_code, company_name, alert_interests, created_at, updated_at)
                VALUES (?, 'company', ?, ?, ?, ?, ?, '[]', ?, ?)
                """,
                ("company-1", "merchant@example.com", "supabase_auth_managed", "555-333-4444", "80205", "Test Pizza Co", app.now_iso(), app.now_iso()),
            )
            conn.commit()
            conn.close()
            status, payload = self.api(
                "/api/company-deals",
                method="POST",
                token="hosted-token",
                data={
                    "companyName": "Test Pizza Co",
                    "zipCode": "80205",
                    "address": "123 Blake St, Denver, CO 80205",
                    "status": "active",
                    "expiresOn": "2099-12-31",
                    "dealDescription": "Two slices and a drink for lunch.",
                },
            )
        self.assertEqual(status, 201)
        self.assertEqual(payload["dealId"], "deal-123")
        create_mock.assert_called_once()

    def test_notifications_endpoint_uses_supabase_in_hosted_mode(self):
        hosted_notifications = [
            {
                "userId": "user-1",
                "dealId": "deal-1",
                "matchedInterest": "pizza",
                "channel": "email",
                "status": "mocked",
                "message": "River North Pizza has free knots at area 80205.",
                "createdAt": "2026-07-27T10:00:00+00:00",
            },
            {
                "userId": "user-2",
                "dealId": "deal-2",
                "matchedInterest": "coffee",
                "channel": "email",
                "status": "mocked",
                "message": "Coffee spot has half off at area 80205.",
                "createdAt": "2026-07-27T11:00:00+00:00",
            }
        ]
        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "get_authenticated_user", return_value=({"id": "user-1", "account_type": "user"}, "token")), \
             mock.patch.object(app, "all_notifications", return_value=hosted_notifications):
            status, payload = self.api("/api/notifications", token="hosted-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload["notifications"], [hosted_notifications[0]])

    def test_session_endpoint_uses_supabase_bearer_in_hosted_mode(self):
        conn = app.get_db()
        conn.execute(
            """
            INSERT INTO users (id, account_type, email, password, phone_number, zip_code, company_name, alert_interests, created_at, updated_at)
            VALUES (?, 'user', ?, ?, ?, ?, ?, '[]', ?, ?)
            """,
            ("user-1", "hosted-user@example.com", "supabase_auth_managed", "555-111-2222", "80205", None, app.now_iso(), app.now_iso()),
        )
        conn.commit()
        expected_row = conn.execute("SELECT * FROM users WHERE id = ?", ("user-1",)).fetchone()
        conn.close()

        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "get_supabase_user", return_value={"id": "user-1", "email": "hosted-user@example.com"}), \
             mock.patch.object(app, "ensure_local_user_from_supabase", return_value=expected_row) as ensure_mock:
            status, payload = self.api("/api/session", token="hosted-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload["sessionToken"], "hosted-token")
        self.assertEqual(payload["user"]["id"], "user-1")
        ensure_mock.assert_called_once()

    def test_update_interests_uses_supabase_write_path_in_hosted_mode(self):
        conn = app.get_db()
        conn.execute(
            """
            INSERT INTO users (id, account_type, email, password, phone_number, zip_code, company_name, alert_interests, created_at, updated_at)
            VALUES (?, 'user', ?, ?, ?, ?, ?, '[]', ?, ?)
            """,
            ("user-1", "hosted-user@example.com", "supabase_auth_managed", "555-111-2222", "80205", None, app.now_iso(), app.now_iso()),
        )
        conn.commit()
        synced_row = conn.execute("SELECT * FROM users WHERE id = ?", ("user-1",)).fetchone()
        conn.close()

        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "get_supabase_user", return_value={"id": "user-1", "email": "hosted-user@example.com"}), \
             mock.patch.object(app, "ensure_local_user_from_supabase", return_value=synced_row) as ensure_mock, \
             mock.patch.object(app, "replace_supabase_alert_interests") as replace_mock:
            status, payload = self.api(
                "/api/users/user-1/interests",
                method="PUT",
                token="hosted-token",
                data={"alertInterests": [" Pizza ", "coffee"]},
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["id"], "user-1")
        self.assertEqual(payload["user"]["alertInterests"], ["pizza", "coffee"])
        replace_mock.assert_called_once_with("user-1", ["pizza", "coffee"])
        self.assertGreaterEqual(ensure_mock.call_count, 1)

    def test_match_flow_uses_supabase_notification_writes_in_hosted_mode(self):
        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "all_users", return_value=[
                 {
                     "id": "user-1",
                     "accountType": "user",
                     "email": "user@example.com",
                     "phoneNumber": "",
                     "zipCode": "80205",
                     "companyName": None,
                     "alertInterests": ["pizza"],
                     "createdAt": "2026-07-27T10:00:00+00:00",
                     "updatedAt": "2026-07-27T10:00:00+00:00",
                 }
             ]), \
             mock.patch.object(app, "all_deals", return_value=[
                 {
                     "id": "deal-1",
                     "dealType": "company",
                     "createdByUserId": "company-1",
                     "title": "River North Pizza",
                     "description": "Free knots with any pie",
                     "zipCode": "80205",
                     "address": "123 Main St",
                     "salePrice": None,
                     "regularPrice": None,
                     "unit": "offer",
                     "category": "Local Business",
                     "sourceStore": "River North Pizza",
                     "status": "active",
                     "expiresAt": None,
                     "expiresOn": "",
                     "createdAt": "2026-07-27T10:00:00+00:00",
                     "updatedAt": "2026-07-27T10:00:00+00:00",
                 }
             ]), \
             mock.patch.object(app, "all_notifications", return_value=[]), \
             mock.patch.object(app, "send_match_email", return_value={"channel": "email", "status": "mocked", "error": None}), \
             mock.patch.object(app, "insert_supabase_notification") as insert_mock:
            sent = app.match_and_notify()
        self.assertEqual(sent, 1)
        insert_mock.assert_called_once()

    def test_init_db_migrates_legacy_schema_columns(self):
        legacy_db = self.temp_path / "legacy-phase1.db"
        conn = sqlite3.connect(legacy_db)
        conn.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                account_type TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone_number TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                company_name TEXT,
                alert_interests TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE deals (
                id TEXT PRIMARY KEY,
                deal_type TEXT NOT NULL,
                created_by_user_id TEXT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                sale_price REAL,
                regular_price REAL,
                unit TEXT,
                category TEXT,
                source_store TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );

            CREATE TABLE password_reset_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT
            );
            """
        )
        conn.commit()
        conn.close()

        original_db_path = app.DB_PATH
        original_schema_ready = app.DB_SCHEMA_READY
        app.DB_PATH = legacy_db
        app.DB_SCHEMA_READY = False
        try:
            app.init_db()
            conn = sqlite3.connect(legacy_db)
            conn.row_factory = sqlite3.Row
            deal_columns = {row["name"] for row in conn.execute("PRAGMA table_info(deals)").fetchall()}
            user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
            reset_columns = {row["name"] for row in conn.execute("PRAGMA table_info(password_reset_tokens)").fetchall()}
            conn.close()
        finally:
            app.DB_PATH = original_db_path
            app.DB_SCHEMA_READY = original_schema_ready

        self.assertIn("address", deal_columns)
        self.assertIn("ends_at", deal_columns)
        self.assertIn("password", user_columns)
        self.assertIn("token_hash", session_columns)
        self.assertIn("token_hash", reset_columns)

    def test_ensure_mock_grocery_deals_uses_supabase_in_hosted_mode(self):
        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "supabase_rest_request", side_effect=[[], [{"id": "g-1"}], [{"id": "g-1"}, {"id": "g-2"}]]) as rest_mock:
            count = app.ensure_mock_grocery_deals()
        self.assertEqual(count, 2)
        self.assertEqual(rest_mock.call_args_list[0].args[0], "deals?select=id&deal_type=eq.grocery")
        self.assertEqual(rest_mock.call_args_list[1].args[0], "deals")
        self.assertEqual(rest_mock.call_args_list[1].kwargs["method"], "POST")
        payload = rest_mock.call_args_list[1].kwargs["payload"]
        self.assertEqual(len(payload), len(app.MOCK_GROCERY_DEALS))
        self.assertEqual(payload[0]["category"], app.MOCK_GROCERY_DEALS[0]["category"])
        self.assertEqual(rest_mock.call_args_list[2].args[0], "deals?select=id&deal_type=eq.grocery")

    def test_ensure_mock_pizza_deals_uses_supabase_in_hosted_mode(self):
        with mock.patch.object(app, "supabase_is_configured", return_value=True), \
             mock.patch.object(app, "supabase_rest_request", side_effect=[[], [{"id": "p-1"}], [{"id": "p-1"}, {"id": "p-2"}, {"id": "p-3"}]]) as rest_mock:
            count = app.ensure_mock_pizza_deals()
        self.assertEqual(count, 3)
        self.assertEqual(rest_mock.call_args_list[0].args[0], "deals?select=id&category=eq.Demo%20Pizza")
        self.assertEqual(rest_mock.call_args_list[1].args[0], "deals")
        self.assertEqual(rest_mock.call_args_list[1].kwargs["method"], "POST")
        payload = rest_mock.call_args_list[1].kwargs["payload"]
        self.assertEqual(len(payload), len(app.MOCK_PIZZA_DEALS))
        self.assertTrue(all(item["category"] == "Demo Pizza" for item in payload))
        self.assertEqual(rest_mock.call_args_list[2].args[0], "deals?select=id&category=eq.Demo%20Pizza")

    # --- interest_matches_haystack: word-boundary matching -----------------

    def test_interest_matches_haystack_rejects_substring_false_positive(self):
        # "ice" must NOT match "service"/"price"/"spice" — the bug in the
        # original plain `interest in haystack` substring check.
        self.assertFalse(app.interest_matches_haystack("ice", "great service and fair price today"))
        self.assertTrue(app.interest_matches_haystack("ice", "free ice with any order"))

    def test_interest_matches_haystack_matches_simple_plural(self):
        self.assertTrue(app.interest_matches_haystack("pizza", "buy two pizzas get one free"))
        self.assertTrue(app.interest_matches_haystack("taco", "tacos tuesday special"))

    def test_interest_matches_haystack_matches_whole_word_only(self):
        self.assertTrue(app.interest_matches_haystack("pizza", "fresh pizza tonight"))
        self.assertFalse(app.interest_matches_haystack("pin", "everything in the shop is on sale"))

    def test_matching_interest_for_deal_uses_word_boundary(self):
        deal = {"title": "Great Service Special", "description": "Fair price on every visit", "sourceStore": None}
        self.assertIsNone(app.matching_interest_for_deal(["ice"], deal))
        deal2 = {"title": "Free Ice Cream Friday", "description": "Kids scoop free", "sourceStore": None}
        self.assertEqual(app.matching_interest_for_deal(["ice"], deal2), "ice")

    # --- ai_extract_categories: optional AI-assisted matching --------------

    def test_ai_extract_categories_returns_empty_when_not_configured(self):
        self.assertEqual(app.ai_extract_categories("tacos and margaritas"), frozenset())

    def test_ai_extract_categories_parses_model_response(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        class FakeResponse:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        payload = json.dumps({"content": [{"type": "text", "text": '["mexican", "bar"]'}]}).encode("utf-8")
        with mock.patch.object(app.urllib_request, "urlopen", return_value=FakeResponse(payload)) as urlopen_mock:
            result = app.ai_extract_categories("Taco Tuesday with $5 margaritas")
        self.assertEqual(result, frozenset({"mexican", "bar"}))
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.headers.get("X-api-key"), "test-key")

    def test_ai_extract_categories_ignores_tags_outside_taxonomy(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        class FakeResponse:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        payload = json.dumps({"content": [{"type": "text", "text": '["mexican", "made-up-tag"]'}]}).encode("utf-8")
        with mock.patch.object(app.urllib_request, "urlopen", return_value=FakeResponse(payload)):
            result = app.ai_extract_categories("Taco night")
        self.assertEqual(result, frozenset({"mexican"}))

    def test_ai_extract_categories_fails_closed_on_network_error(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        with mock.patch.object(app.urllib_request, "urlopen", side_effect=urllib.error.URLError("boom")):
            result = app.ai_extract_categories("anything at all")
        self.assertEqual(result, frozenset())

    def test_matching_interest_for_deal_uses_ai_category_overlap_when_keywords_miss(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        deal = {"title": "Cinco de Mayo Fiesta Special", "description": "Half-off margaritas all night", "sourceStore": None}

        def fake_categories(text):
            if "cinco de mayo" in text or "margaritas" in text:
                return frozenset({"mexican", "bar"})
            if text == "tacos":
                return frozenset({"mexican"})
            return frozenset()

        with mock.patch.object(app, "ai_extract_categories", side_effect=fake_categories):
            matched = app.matching_interest_for_deal(["tacos"], deal)
        self.assertEqual(matched, "tacos")

    def test_matching_interest_for_deal_skips_ai_when_not_configured(self):
        deal = {"title": "Cinco de Mayo Fiesta Special", "description": "Half-off margaritas all night", "sourceStore": None}
        # No ANTHROPIC_API_KEY set (cleared in setUp) — should stay keyword-only.
        self.assertIsNone(app.matching_interest_for_deal(["tacos"], deal))

    # --- Login rate limiting -------------------------------------------

    def test_login_locks_out_after_repeated_failures(self):
        email = self.unique_email("lockout")
        self.signup_user(email=email, password="Pass1234")
        for _ in range(app.LOGIN_MAX_ATTEMPTS):
            status, _ = self.api("/api/login", method="POST", data={"email": email, "password": "wrong-password"})
            self.assertEqual(status, 401)
        locked_status, locked_payload = self.api(
            "/api/login", method="POST", data={"email": email, "password": "wrong-password"}
        )
        self.assertEqual(locked_status, 429)
        self.assertIn("Too many failed attempts", locked_payload["error"])
        # Even the CORRECT password is refused while locked out.
        still_locked_status, _ = self.api("/api/login", method="POST", data={"email": email, "password": "Pass1234"})
        self.assertEqual(still_locked_status, 429)

    def test_successful_login_clears_failure_count(self):
        email = self.unique_email("recover")
        self.signup_user(email=email, password="Pass1234")
        for _ in range(app.LOGIN_MAX_ATTEMPTS - 1):
            self.api("/api/login", method="POST", data={"email": email, "password": "wrong-password"})
        success_status, _ = self.api("/api/login", method="POST", data={"email": email, "password": "Pass1234"})
        self.assertEqual(success_status, 200)
        # Failure counter reset by the success — next wrong attempt is just a normal 401, not a lockout.
        next_status, _ = self.api("/api/login", method="POST", data={"email": email, "password": "wrong-password"})
        self.assertEqual(next_status, 401)

    def test_login_requires_email_and_password(self):
        status, payload = self.api("/api/login", method="POST", data={"email": "", "password": ""})
        self.assertEqual(status, 400)
        self.assertIn("required", payload["error"])

    # --- Password reset token exposure gating ---------------------------

    def test_reset_token_included_in_response_when_not_hosted(self):
        email = self.unique_email("resettoken")
        self.signup_user(email=email)
        status, payload = self.api("/api/password-reset/request", method="POST", data={"email": email})
        self.assertEqual(status, 200)
        self.assertIn("resetToken", payload)

    def test_reset_token_omitted_from_response_when_running_on_hosting_platform(self):
        email = self.unique_email("resettoken-hosted")
        self.signup_user(email=email)
        with mock.patch.object(app, "running_on_hosting_platform", return_value=True):
            status, payload = self.api("/api/password-reset/request", method="POST", data={"email": email})
        self.assertEqual(status, 200)
        self.assertNotIn("resetToken", payload)


if __name__ == "__main__":
    unittest.main()
