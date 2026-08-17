#!/usr/bin/env python3
import json
import os
import sqlite3
import ssl
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
DB_PATH = ROOT / "prototype.db"
NOTIFICATION_LOG = ROOT / "notification_log.jsonl"


MOCK_STORES = {
    "80205": [
        {
            "storeId": "62000001",
            "storeName": "Kroger Denver Central",
            "address": "1350 Main St, Denver, CO",
        },
        {
            "storeId": "62000002",
            "storeName": "Kroger Five Points",
            "address": "2550 Welton St, Denver, CO",
        },
    ],
    "80301": [
        {
            "storeId": "62000003",
            "storeName": "Kroger Boulder North",
            "address": "2900 Iris Ave, Boulder, CO",
        }
    ],
}

STORE_ZIP_CODES = {
    store["storeId"]: [zip_code]
    for zip_code, stores in MOCK_STORES.items()
    for store in stores
}


MOCK_DEALS = {
    "62000001": [
        {
            "productId": "111",
            "productName": "Boneless Skinless Chicken Breast",
            "description": "Boneless Skinless Chicken Breast Family Pack",
            "salePrice": 2.99,
            "regularPrice": 5.49,
            "unit": "lb",
            "category": "Meat & Seafood",
        },
        {
            "productId": "112",
            "productName": "Large Eggs",
            "description": "Grade A Large Eggs 12 Count",
            "salePrice": 2.49,
            "regularPrice": 3.99,
            "unit": "each",
            "category": "Dairy",
        },
        {
            "productId": "113",
            "productName": "Whole Milk",
            "description": "Whole Milk Gallon",
            "salePrice": 2.79,
            "regularPrice": 3.79,
            "unit": "gallon",
            "category": "Dairy",
        },
    ],
    "62000002": [
        {
            "productId": "221",
            "productName": "Avocados",
            "description": "Hass Avocados",
            "salePrice": 0.99,
            "regularPrice": 1.69,
            "unit": "each",
            "category": "Produce",
        },
        {
            "productId": "222",
            "productName": "Jasmine Rice",
            "description": "Jasmine Rice 5 lb Bag",
            "salePrice": 5.99,
            "regularPrice": 8.99,
            "unit": "bag",
            "category": "Pantry",
        },
    ],
    "62000003": [
        {
            "productId": "331",
            "productName": "Atlantic Salmon",
            "description": "Fresh Atlantic Salmon Fillets",
            "salePrice": 8.99,
            "regularPrice": 12.99,
            "unit": "lb",
            "category": "Seafood",
        }
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            phone_number TEXT NOT NULL UNIQUE,
            email TEXT,
            password TEXT,
            account_type TEXT NOT NULL DEFAULT 'user',
            company_name TEXT,
            zip_code TEXT NOT NULL,
            tracked_items TEXT NOT NULL DEFAULT '[]',
            stores TEXT NOT NULL DEFAULT '[]',
            sms_confirmed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            description TEXT NOT NULL,
            sale_price REAL NOT NULL,
            regular_price REAL NOT NULL,
            unit TEXT NOT NULL,
            category TEXT NOT NULL,
            zip_codes TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT NOT NULL,
            raw_data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS company_deals (
            deal_id TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            deal_description TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            channel TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    user_columns = {row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "password" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN password TEXT")
    if "account_type" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN account_type TEXT NOT NULL DEFAULT 'user'")
    if "company_name" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN company_name TEXT")
    deal_columns = {row["name"] for row in cur.execute("PRAGMA table_info(deals)").fetchall()}
    if "zip_codes" not in deal_columns:
        cur.execute("ALTER TABLE deals ADD COLUMN zip_codes TEXT NOT NULL DEFAULT '[]'")
    conn.commit()
    conn.close()


def json_response(handler: BaseHTTPRequestHandler, payload, status=HTTPStatus.OK):
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def read_json(handler: BaseHTTPRequestHandler):
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8"))


def parse_list_field(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []


def user_to_dict(row: sqlite3.Row):
    return {
        "userId": row["user_id"],
        "phoneNumber": row["phone_number"],
        "email": row["email"],
        "accountType": row["account_type"],
        "companyName": row["company_name"],
        "zipCode": row["zip_code"],
        "alertInterests": parse_list_field(row["tracked_items"]),
        "smsConfirmed": bool(row["sms_confirmed"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def log_notification(entry):
    with NOTIFICATION_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def email_config():
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_email": os.getenv("EMAIL_FROM", "").strip(),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() != "false",
    }


def send_email(recipient: str, subject: str, body: str):
    config = email_config()
    if not all([config["host"], config["from_email"], recipient]):
        return {"status": "mocked", "detail": "SMTP not configured"}

    try:
        message = EmailMessage()
        message["From"] = config["from_email"]
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        if config["use_tls"]:
            context = ssl.create_default_context()
            with smtplib.SMTP(config["host"], config["port"], timeout=15) as server:
                server.starttls(context=context)
                if config["username"]:
                    server.login(config["username"], config["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(config["host"], config["port"], timeout=15) as server:
                if config["username"]:
                    server.login(config["username"], config["password"])
                server.send_message(message)
    except Exception as exc:
        return {"status": "failed", "detail": str(exc)}

    return {"status": "sent", "detail": f"Delivered to {recipient}"}


def send_notification(user, kind, channel, payload, dedupe_key):
    created_at = now_iso()
    delivery = {"status": "sent", "detail": "Logged notification"}
    if channel == "email":
        delivery = send_email(
            user.get("email", ""),
            payload.get("subject", "v1"),
            payload.get("message", ""),
        )

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO notifications (id, user_id, kind, dedupe_key, channel, payload, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                user["userId"],
                kind,
                dedupe_key,
                channel,
                json.dumps(payload),
                delivery["status"],
                created_at,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False
    conn.close()

    log_entry = {
        "createdAt": created_at,
        "kind": kind,
        "channel": channel,
        "phoneNumber": user["phoneNumber"],
        "email": user["email"],
        "status": delivery["status"],
        "detail": delivery["detail"],
        "payload": payload,
    }
    log_notification(log_entry)
    return True


def build_all_deals():
    conn = get_db()
    grocery_rows = conn.execute(
        """
        SELECT store_id, product_id, product_name, description, sale_price,
               regular_price, unit, category, zip_codes, valid_from, valid_to
        FROM deals
        ORDER BY store_id, product_name
        """
    ).fetchall()
    company_rows = conn.execute(
        """
        SELECT deal_id, company_name, zip_code, deal_description, created_at
        FROM company_deals
        ORDER BY created_at DESC
        """
    ).fetchall()
    conn.close()

    deals = [
        {
            "dealType": "grocery",
            "storeId": row["store_id"],
            "productId": row["product_id"],
            "productName": row["product_name"],
            "description": row["description"],
            "salePrice": row["sale_price"],
            "regularPrice": row["regular_price"],
            "unit": row["unit"],
            "category": row["category"],
            "zipCodes": json.loads(row["zip_codes"]),
            "validFrom": row["valid_from"],
            "validTo": row["valid_to"],
        }
        for row in grocery_rows
    ]
    deals.extend(
        {
            "dealType": "company",
            "dealId": row["deal_id"],
            "companyName": row["company_name"],
            "productName": row["company_name"],
            "description": row["deal_description"],
            "salePrice": None,
            "regularPrice": None,
            "unit": "offer",
            "category": "Local Business",
            "zipCodes": [row["zip_code"]],
            "validFrom": row["created_at"],
            "validTo": row["created_at"],
        }
        for row in company_rows
    )
    return deals


def upsert_mock_deals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM deals")
    valid_from = now_iso()
    valid_to = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59).isoformat()

    inserted = 0
    for store_id, deals in MOCK_DEALS.items():
        for deal in deals:
            cur.execute(
                """
                INSERT INTO deals (
                    id, store_id, product_id, product_name, description,
                    sale_price, regular_price, unit, category, zip_codes, valid_from, valid_to, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    store_id,
                    deal["productId"],
                    deal["productName"],
                    deal["description"],
                    deal["salePrice"],
                    deal["regularPrice"],
                    deal["unit"],
                    deal["category"],
                    json.dumps(STORE_ZIP_CODES.get(store_id, [])),
                    valid_from,
                    valid_to,
                    json.dumps(deal),
                ),
            )
            inserted += 1
    conn.commit()
    conn.close()
    return inserted


def match_and_notify():
    conn = get_db()
    users = [user_to_dict(row) for row in conn.execute("SELECT * FROM users ORDER BY created_at DESC")]
    conn.close()
    deals = build_all_deals()

    sent = {"sms": 0, "email": 0}
    for user in users:
        if user["accountType"] != "user":
            continue
        alert_interests = [item.strip().lower() for item in user["alertInterests"] if item.strip()]
        if not alert_interests:
            continue
        for deal in deals:
            zip_codes = deal["zipCodes"]
            if user["zipCode"] not in zip_codes:
                continue
            haystack = f"{deal['productName']} {deal['description']}".lower()
            matched_item = next((item for item in alert_interests if item in haystack), None)
            if not matched_item:
                continue
            deal_summary = {
                "dealType": deal["dealType"],
                "storeName": deal.get("storeId", deal.get("companyName", "Local Deal")),
                "storeId": deal.get("storeId"),
                "companyName": deal.get("companyName"),
                "zipCodes": zip_codes,
                "userZipCode": user["zipCode"],
                "matchedItem": matched_item,
                "productName": deal["productName"],
                "description": deal["description"],
                "salePrice": deal["salePrice"],
                "regularPrice": deal["regularPrice"],
                "unit": deal["unit"],
            }
            if deal["dealType"] == "grocery":
                sms_payload = {
                    **deal_summary,
                    "message": (
                        f"Deal Alert! {deal['productName']} is ${deal['salePrice']:.2f}/{deal['unit']} "
                        f"in zip {user['zipCode']} (reg ${deal['regularPrice']:.2f})."
                    ),
                }
                sms_dedupe_key = (
                    f"user:{user['userId']}|type:{deal['dealType']}|deal:{deal.get('productId', deal.get('dealId'))}"
                    f"|match:{matched_item}|channel:sms"
                )
                if send_notification(user, "deal_match", "sms", sms_payload, sms_dedupe_key):
                    sent["sms"] += 1

            if user["email"]:
                if deal["dealType"] == "company":
                    email_message = (
                        f"{deal['companyName']} has {deal['description']} at area {user['zipCode']}.\n\n"
                        f"Phone number: {user['phoneNumber']}\n"
                        f"Matching interest: {matched_item}"
                    )
                else:
                    email_message = (
                        f"Zip Code Deal Match: {deal['productName']} is ${deal['salePrice']:.2f}/{deal['unit']} "
                        f"for zip {user['zipCode']}.\n\n"
                        f"Phone number: {user['phoneNumber']}\n"
                        f"Matching interest: {matched_item}\n"
                        f"Regular price: ${deal['regularPrice']:.2f}"
                    )
                email_payload = {
                    **deal_summary,
                    "phoneNumber": user["phoneNumber"],
                    "subject": f"Deal Match for {user['zipCode']}",
                    "message": email_message,
                }
                email_dedupe_key = (
                    f"user:{user['userId']}|type:{deal['dealType']}|deal:{deal.get('productId', deal.get('dealId'))}"
                    f"|match:{matched_item}|channel:email"
                )
                if send_notification(user, "deal_match_zip_email", "email", email_payload, email_dedupe_key):
                    sent["email"] += 1
    return sent


class AppHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
        self.end_headers()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_file("index.html")
        if parsed.path.startswith("/static/"):
            return self.serve_file(parsed.path.replace("/static/", "", 1))
        if parsed.path.startswith("/api/users/") and parsed.path.endswith("/interests"):
            user_id = parsed.path.split("/")[3]
            return self.handle_get_interests(user_id)
        if parsed.path == "/api/deals":
            return self.handle_get_deals()
        if parsed.path == "/api/notifications":
            return self.handle_get_notifications()
        if parsed.path == "/api/users":
            return self.handle_get_users()
        return json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/signup":
                return self.handle_signup()
            if parsed.path == "/api/login":
                return self.handle_login()
            if parsed.path == "/api/company-deals":
                return self.handle_company_deal()
            if parsed.path == "/api/ingest":
                return self.handle_ingest()
            if parsed.path == "/api/match":
                return self.handle_match()
            return json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return json_response(self, {"error": f"Request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/users/") and parsed.path.endswith("/interests"):
                user_id = parsed.path.split("/")[3]
                return self.handle_update_interests(user_id)
            return json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return json_response(self, {"error": f"Request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_file(self, relative_path):
        target = STATIC_DIR / relative_path
        if not target.exists() or not target.is_file():
            return json_response(self, {"error": "File not found"}, HTTPStatus.NOT_FOUND)
        content = target.read_bytes()
        content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "text/css; charset=utf-8" if target.suffix == ".css" else "application/javascript; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def handle_signup(self):
        body = read_json(self)
        user_id = str(uuid.uuid4())
        timestamp = now_iso()
        account_type = body.get("accountType", "user")
        conn = get_db()
        cur = conn.cursor()
        existing = conn.execute("SELECT user_id FROM users WHERE email = ?", (body["email"],)).fetchone()
        if existing:
            conn.close()
            return json_response(self, {"error": "Email already exists"}, HTTPStatus.CONFLICT)
        try:
            cur.execute(
                """
                INSERT INTO users (
                    user_id, phone_number, email, password, account_type, company_name,
                    zip_code, tracked_items, stores, sms_confirmed, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '[]', 1, ?, ?)
                """,
                (
                    user_id,
                    body["phoneNumber"],
                    body["email"],
                    body["password"],
                    account_type,
                    body.get("companyName"),
                    body["zipCode"],
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return json_response(self, {"error": "Phone number already exists"}, HTTPStatus.CONFLICT)
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        return json_response(
            self,
            {
                "userId": user_id,
                "message": f"{account_type.title()} account created.",
                "user": user_to_dict(row),
            },
            HTTPStatus.CREATED,
        )

    def handle_login(self):
        body = read_json(self)
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (body["email"], body["password"]),
        ).fetchone()
        conn.close()
        if not row:
            return json_response(self, {"error": "Invalid email or password"}, HTTPStatus.UNAUTHORIZED)
        return json_response(self, {"user": user_to_dict(row), "ok": True})

    def handle_get_interests(self, user_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if not row:
            return json_response(self, {"error": "User not found"}, HTTPStatus.NOT_FOUND)
        user = user_to_dict(row)
        return json_response(self, {"alertInterests": user["alertInterests"]})

    def handle_update_interests(self, user_id):
        body = read_json(self)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET tracked_items = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                json.dumps(body.get("alertInterests", [])),
                now_iso(),
                user_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if not row:
            return json_response(self, {"error": "User not found"}, HTTPStatus.NOT_FOUND)
        return json_response(self, {"user": user_to_dict(row)})

    def handle_ingest(self):
        inserted = upsert_mock_deals()
        return json_response(self, {"ok": True, "dealsIngested": inserted})

    def handle_match(self):
        sent = match_and_notify()
        return json_response(
            self,
            {
                "ok": True,
                "notificationsSent": sent["sms"] + sent["email"],
                "notificationsByChannel": sent,
            },
        )

    def handle_get_deals(self):
        return json_response(self, {"deals": build_all_deals()})

    def handle_company_deal(self):
        body = read_json(self)
        created_at = now_iso()
        deal_id = str(uuid.uuid4())
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO company_deals (deal_id, company_name, zip_code, deal_description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (deal_id, body["companyName"], body["zipCode"], body["dealDescription"], created_at),
        )
        users = [
            user_to_dict(row)
            for row in conn.execute(
                "SELECT * FROM users WHERE zip_code = ? AND account_type = 'user'",
                (body["zipCode"],),
            ).fetchall()
        ]
        conn.commit()
        conn.close()

        notified = 0
        for user in users:
            alert_interests = [item.strip().lower() for item in user["alertInterests"] if item.strip()]
            haystack = f"{body['companyName']} {body['dealDescription']}".lower()
            matched_item = next((item for item in alert_interests if item in haystack), None)
            if not matched_item:
                continue
            payload = {
                "companyName": body["companyName"],
                "zipCode": body["zipCode"],
                "dealDescription": body["dealDescription"],
                "phoneNumber": user["phoneNumber"],
                "subject": f"New Local Deal in {body['zipCode']}",
                "message": (
                    f"{body['companyName']}: {body['dealDescription']}\n\n"
                    f"This deal matches your zip code: {body['zipCode']}.\n"
                    f"Phone number: {user['phoneNumber']}\n"
                    f"Matching interest: {matched_item}"
                ),
            }
            dedupe_key = f"company:{deal_id}|user:{user['userId']}"
            if send_notification(user, "company_deal", "email", payload, dedupe_key):
                notified += 1

        return json_response(
            self,
            {"dealId": deal_id, "usersNotified": notified},
            HTTPStatus.CREATED,
        )

    def handle_get_notifications(self):
        conn = get_db()
        rows = conn.execute(
            """
            SELECT user_id, kind, channel, payload, status, created_at
            FROM notifications
            ORDER BY created_at DESC
            """
        ).fetchall()
        conn.close()
        notifications = [
            {
                "userId": row["user_id"],
                "kind": row["kind"],
                "channel": row["channel"],
                "payload": json.loads(row["payload"]),
                "status": row["status"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
        return json_response(self, {"notifications": notifications})

    def handle_get_users(self):
        conn = get_db()
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        conn.close()
        return json_response(self, {"users": [user_to_dict(row) for row in rows]})


def main():
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), AppHandler)
    print("Prototype running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
