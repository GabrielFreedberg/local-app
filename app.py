#!/usr/bin/env python3
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import quote, urlparse


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
DB_PATH = ROOT / "phase1.db"
NOTIFICATION_LOG = ROOT / "notification_log.jsonl"
MATCH_RUN_LOG = ROOT / "match_run_log.jsonl"
SESSION_TTL_DAYS = 30
PASSWORD_RESET_TTL_MINUTES = 30
DEFAULT_COMPANY_DEAL_TTL_DAYS = 7
DB_SCHEMA_LOCK = threading.Lock()
DB_SCHEMA_READY = False
SCHEDULER_STATE_LOCK = threading.Lock()
MATCHING_SCHEDULER_STATE = {
    "enabled": False,
    "intervalSeconds": 0,
    "lastTrigger": "",
    "lastStartedAt": "",
    "lastCompletedAt": "",
    "lastSucceededAt": "",
    "lastRunNotifications": 0,
    "lastRunError": "",
    "runCount": 0,
}


class AuthError(Exception):
    pass


MOCK_GROCERY_DEALS = [
    {
        "dealType": "grocery",
        "title": "Boneless Skinless Chicken Breast",
        "description": "Boneless skinless chicken breast family pack",
        "zipCode": "80205",
        "salePrice": 2.99,
        "regularPrice": 5.49,
        "unit": "lb",
        "category": "Meat",
        "sourceStore": "Kroger Denver Central",
    },
    {
        "dealType": "grocery",
        "title": "Large Eggs",
        "description": "Grade A large eggs 12 count",
        "zipCode": "80205",
        "salePrice": 2.49,
        "regularPrice": 3.99,
        "unit": "each",
        "category": "Dairy",
        "sourceStore": "Kroger Denver Central",
    },
    {
        "dealType": "grocery",
        "title": "Whole Milk",
        "description": "Whole milk gallon",
        "zipCode": "80205",
        "salePrice": 2.79,
        "regularPrice": 3.79,
        "unit": "gallon",
        "category": "Dairy",
        "sourceStore": "Kroger Denver Central",
    },
    {
        "dealType": "grocery",
        "title": "Jasmine Rice",
        "description": "Jasmine rice 5 lb bag",
        "zipCode": "80205",
        "salePrice": 5.99,
        "regularPrice": 8.99,
        "unit": "bag",
        "category": "Pantry",
        "sourceStore": "Kroger Five Points",
    },
    {
        "dealType": "grocery",
        "title": "Craft Beer Variety Pack",
        "description": "Craft beer variety pack 12 count",
        "zipCode": "80205",
        "salePrice": 14.99,
        "regularPrice": 18.99,
        "unit": "pack",
        "category": "Beverages",
        "sourceStore": "Kroger Five Points",
    },
]

MOCK_PIZZA_DEALS = [
    {
        "title": "Marco's Coal Oven Pizza",
        "description": "Buy one large pepperoni pizza, get a second large cheese pizza free.",
        "zipCode": "80205",
        "sourceStore": "Marco's Coal Oven Pizza",
        "address": "2121 Larimer St, Denver, CO 80205",
    },
    {
        "title": "Five Points Pizza Club",
        "description": "Late-night slice combo with garlic knots and a fountain drink.",
        "zipCode": "80205",
        "sourceStore": "Five Points Pizza Club",
        "address": "2510 Welton St, Denver, CO 80205",
    },
    {
        "title": "Brickline Pizza House",
        "description": "Family pizza bundle with two pies, salad, and tiramisu.",
        "zipCode": "80205",
        "sourceStore": "Brickline Pizza House",
        "address": "2731 Blake St, Denver, CO 80205",
    },
    {
        "title": "Union Station Pizza Bar",
        "description": "Half-off margherita pizza before 5pm every weekday.",
        "zipCode": "80202",
        "sourceStore": "Union Station Pizza Bar",
        "address": "1701 Wynkoop St, Denver, CO 80202",
    },
    {
        "title": "Riverside Pie Co.",
        "description": "Two giant New York slices and a canned soda for one easy lunch price.",
        "zipCode": "80205",
        "sourceStore": "Riverside Pie Co.",
        "address": "3300 Brighton Blvd, Denver, CO 80205",
    },
    {
        "title": "Cherry Creek Pizza Kitchen",
        "description": "Free cheesy bread with any artisan pizza order over $20.",
        "zipCode": "80206",
        "sourceStore": "Cherry Creek Pizza Kitchen",
        "address": "250 Fillmore St, Denver, CO 80206",
    },
    {
        "title": "Capitol Hill Slice Works",
        "description": "Three specialty pizza slices for the price of two.",
        "zipCode": "80203",
        "sourceStore": "Capitol Hill Slice Works",
        "address": "1301 N Pearl St, Denver, CO 80203",
    },
    {
        "title": "LoDo Pizza Yard",
        "description": "Weekend rooftop pizza happy hour with discounted wood-fired pies.",
        "zipCode": "80202",
        "sourceStore": "LoDo Pizza Yard",
        "address": "1946 Market St, Denver, CO 80202",
    },
    {
        "title": "Baker Street Pizza Oven",
        "description": "Personal pizza and Caesar salad combo at lunch.",
        "zipCode": "80223",
        "sourceStore": "Baker Street Pizza Oven",
        "address": "55 Broadway, Denver, CO 80223",
    },
    {
        "title": "Northside Pizza Garage",
        "description": "Free topping upgrade on every Detroit-style pizza this week.",
        "zipCode": "80211",
        "sourceStore": "Northside Pizza Garage",
        "address": "3559 W 38th Ave, Denver, CO 80211",
    },
    {
        "title": "Tennyson Pizza Social",
        "description": "Date-night pizza special with one pie, one salad, and two drinks.",
        "zipCode": "80212",
        "sourceStore": "Tennyson Pizza Social",
        "address": "4319 Tennyson St, Denver, CO 80212",
    },
    {
        "title": "Park Hill Pizza Pantry",
        "description": "Take-and-bake pizza deal with free cookie dough.",
        "zipCode": "80207",
        "sourceStore": "Park Hill Pizza Pantry",
        "address": "5059 E 28th Ave, Denver, CO 80207",
    },
    {
        "title": "South Pearl Pizza Table",
        "description": "Large veggie pizza for $14 every Thursday.",
        "zipCode": "80210",
        "sourceStore": "South Pearl Pizza Table",
        "address": "1549 S Pearl St, Denver, CO 80210",
    },
    {
        "title": "Santa Fe Pizza Depot",
        "description": "Double points and discounted calzones with any pizza order.",
        "zipCode": "80223",
        "sourceStore": "Santa Fe Pizza Depot",
        "address": "721 Santa Fe Dr, Denver, CO 80223",
    },
    {
        "title": "Highlands Pizza Market",
        "description": "Neighborhood pizza night with $3 slices and half-price cannoli.",
        "zipCode": "80211",
        "sourceStore": "Highlands Pizza Market",
        "address": "3644 W 32nd Ave, Denver, CO 80211",
    },
    {
        "title": "Larimer Pizza Exchange",
        "description": "Large barbecue chicken pizza special with free ranch dips.",
        "zipCode": "80205",
        "sourceStore": "Larimer Pizza Exchange",
        "address": "2901 Larimer St, Denver, CO 80205",
    },
    {
        "title": "Golden Triangle Pizza Counter",
        "description": "Museum district lunch special with one slice, soup, and sparkling water.",
        "zipCode": "80204",
        "sourceStore": "Golden Triangle Pizza Counter",
        "address": "1350 Bannock St, Denver, CO 80204",
    },
    {
        "title": "Bluebird Pizza Corner",
        "description": "Student night deal with discounted cheese pizzas and brownie bites.",
        "zipCode": "80206",
        "sourceStore": "Bluebird Pizza Corner",
        "address": "3053 E Colfax Ave, Denver, CO 80206",
    },
    {
        "title": "Civic Center Pizza Stop",
        "description": "Quick lunch pizza package with a drink and side salad.",
        "zipCode": "80203",
        "sourceStore": "Civic Center Pizza Stop",
        "address": "101 Broadway, Denver, CO 80203",
    },
    {
        "title": "RiNo Pizza Lab",
        "description": "Experimental pizza flight featuring four mini pies and house dips.",
        "zipCode": "80205",
        "sourceStore": "RiNo Pizza Lab",
        "address": "3501 Wazee St, Denver, CO 80205",
    },
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def future_iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def parse_iso(value):
    return datetime.fromisoformat(value)


def hash_token(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def generate_opaque_token():
    selector = secrets.token_urlsafe(12)
    secret = secrets.token_urlsafe(32)
    raw_token = f"{selector}.{secret}"
    return selector, raw_token, hash_token(raw_token)


def get_db():
    global DB_SCHEMA_READY
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    if not DB_SCHEMA_READY:
        with DB_SCHEMA_LOCK:
            if not DB_SCHEMA_READY:
                ensure_db_schema(conn)
                conn.commit()
                DB_SCHEMA_READY = True
    return conn


def ensure_db_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            account_type TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            company_name TEXT,
            alert_interests TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY,
            deal_type TEXT NOT NULL,
            created_by_user_id TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            address TEXT,
            sale_price REAL,
            regular_price REAL,
            unit TEXT,
            category TEXT,
            source_store TEXT,
            status TEXT NOT NULL,
            ends_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            deal_id TEXT NOT NULL,
            matched_interest TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, deal_id, matched_interest, channel)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            token_hash TEXT,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            token_hash TEXT,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        );
        """
    )
    deal_columns = {row["name"] for row in conn.execute("PRAGMA table_info(deals)").fetchall()}
    if "address" not in deal_columns:
        conn.execute("ALTER TABLE deals ADD COLUMN address TEXT")
    if "ends_at" not in deal_columns:
        conn.execute("ALTER TABLE deals ADD COLUMN ends_at TEXT")
    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "password" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN password TEXT")
    session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "token_hash" not in session_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN token_hash TEXT")
    reset_columns = {row["name"] for row in conn.execute("PRAGMA table_info(password_reset_tokens)").fetchall()}
    if "token_hash" not in reset_columns:
        conn.execute("ALTER TABLE password_reset_tokens ADD COLUMN token_hash TEXT")
    conn.execute("UPDATE sessions SET token_hash = ? WHERE token_hash IS NULL AND token IS NOT NULL", ("",))
    conn.execute("UPDATE password_reset_tokens SET token_hash = ? WHERE token_hash IS NULL AND token IS NOT NULL", ("",))
    for row in conn.execute("SELECT token FROM sessions WHERE token_hash = ''").fetchall():
        conn.execute("UPDATE sessions SET token_hash = ? WHERE token = ?", (hash_token(row["token"]), row["token"]))
    for row in conn.execute("SELECT token FROM password_reset_tokens WHERE token_hash = ''").fetchall():
        conn.execute(
            "UPDATE password_reset_tokens SET token_hash = ? WHERE token = ?",
            (hash_token(row["token"]), row["token"]),
        )


def init_db():
    global DB_SCHEMA_READY
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with DB_SCHEMA_LOCK:
        ensure_db_schema(conn)
        conn.commit()
        DB_SCHEMA_READY = True
    conn.close()


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8"))


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def user_to_dict(row):
    return {
        "id": row["id"],
        "accountType": row["account_type"],
        "email": row["email"],
        "phoneNumber": row["phone_number"],
        "zipCode": row["zip_code"],
        "companyName": row["company_name"],
        "alertInterests": json.loads(row["alert_interests"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_zip_code(value):
    return str(value or "").strip()


def normalize_phone_number(value):
    return str(value or "").strip()


def normalize_company_name(value):
    return str(value or "").strip()


def normalize_account_type(value):
    return "company" if str(value or "").strip().lower() == "company" else "user"


def normalize_alert_interests(values):
    cleaned = []
    seen = set()
    for value in values or []:
        normalized = " ".join(str(value or "").strip().lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def normalize_company_deal_status(value):
    normalized = str(value or "").strip().lower()
    if normalized not in {"active", "draft"}:
        return "active"
    return normalized


def normalize_ends_on(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError("Expiration date must be in YYYY-MM-DD format")
    return f"{raw}T23:59:59+00:00"


def default_company_deal_ends_at(days=DEFAULT_COMPANY_DEAL_TTL_DAYS):
    base = datetime.now(timezone.utc) + timedelta(days=days)
    return datetime(base.year, base.month, base.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()


def iso_to_date_input(value):
    if not value:
        return ""
    return str(value).split("T", 1)[0]


def normalized_haystack(*parts):
    return " ".join(" ".join(str(part or "").lower().split()) for part in parts if part).strip()


def validate_signup(body):
    if normalize_account_type(body.get("accountType")) not in {"user", "company"}:
        raise ValueError("Invalid account type")
    email = normalize_email(body.get("email"))
    if not email:
        raise ValueError("Email is required")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid email address")
    validate_password_strength(body.get("password"))
    phone_number = normalize_phone_number(body.get("phoneNumber"))
    if not phone_number:
        raise ValueError("Phone number is required")
    zip_code = normalize_zip_code(body.get("zipCode"))
    if not zip_code:
        raise ValueError("Zip code is required")
    if not re.fullmatch(r"\d{5}", zip_code):
        raise ValueError("Zip code must be 5 digits")
    if normalize_account_type(body.get("accountType")) == "company" and not normalize_company_name(body.get("companyName")):
        raise ValueError("Company name is required")


def validate_password_strength(password):
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[A-Za-z]", password or ""):
        raise ValueError("Password must include at least one letter")
    if not re.search(r"\d", password or ""):
        raise ValueError("Password must include at least one number")


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(stored, candidate):
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        _, iterations, salt, digest = stored.split("$", 3)
        test_digest = hashlib.pbkdf2_hmac(
            "sha256",
            candidate.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, test_digest)
    return hmac.compare_digest(stored, candidate)


def create_session(conn, user_id):
    selector, raw_token, token_hash = generate_opaque_token()
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO sessions (token, token_hash, user_id, created_at, expires_at, revoked_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (selector, token_hash, user_id, timestamp, future_iso(SESSION_TTL_DAYS)),
    )
    return raw_token


def revoke_all_sessions(conn, user_id):
    conn.execute(
        "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (now_iso(), user_id),
    )


def create_password_reset_token(conn, user_id):
    selector, raw_token, token_hash = generate_opaque_token()
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO password_reset_tokens (token, token_hash, user_id, created_at, expires_at, used_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (
            selector,
            token_hash,
            user_id,
            timestamp,
            (datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)).isoformat(),
        ),
    )
    return raw_token


def get_valid_password_reset_row(conn, token):
    token_hash = hash_token(token)
    row = conn.execute(
        """
        SELECT password_reset_tokens.*, users.email
        FROM password_reset_tokens
        JOIN users ON users.id = password_reset_tokens.user_id
        WHERE password_reset_tokens.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()
    if not row:
        raise ValueError("Reset link is invalid")
    if row["used_at"]:
        raise ValueError("Reset link has already been used")
    if parse_iso(row["expires_at"]) <= datetime.now(timezone.utc):
        raise ValueError("Reset link has expired")
    return row


def get_authenticated_user(handler, conn):
    auth_header = handler.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthError("Authentication required")
    token = auth_header.replace("Bearer ", "", 1).strip()
    if not token:
        raise AuthError("Authentication required")
    token_hash = hash_token(token)
    row = conn.execute(
        """
        SELECT users.*
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token_hash = ?
          AND sessions.revoked_at IS NULL
        """,
        (token_hash,),
    ).fetchone()
    if not row:
        supabase_user = get_supabase_user(token)
        if not supabase_user:
            raise AuthError("Session not found")
        row = ensure_local_user_from_supabase(conn, supabase_user)
        return row, token
    session_row = conn.execute("SELECT expires_at FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
    if not session_row or parse_iso(session_row["expires_at"]) <= datetime.now(timezone.utc):
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (now_iso(), token_hash),
        )
        conn.commit()
        raise AuthError("Session expired")
    return row, token


def cleanup_auth_artifacts(conn):
    timestamp = now_iso()
    conn.execute(
        "DELETE FROM password_reset_tokens WHERE used_at IS NOT NULL OR expires_at <= ?",
        (timestamp,),
    )
    conn.execute(
        "DELETE FROM sessions WHERE revoked_at IS NOT NULL OR expires_at <= ?",
        (timestamp,),
    )


def sync_company_deal_statuses(conn):
    conn.execute(
        """
        UPDATE deals
        SET status = 'expired', updated_at = ?
        WHERE deal_type = 'company'
          AND status IN ('active', 'draft')
          AND ends_at IS NOT NULL
          AND ends_at <= ?
        """,
        (now_iso(), now_iso()),
    )


def archive_duplicate_company_deals(conn, user_id=None):
    where_clauses = ["deal_type = 'company'", "status != 'archived'"]
    params = []
    if user_id:
        where_clauses.append("created_by_user_id = ?")
        params.append(user_id)
    rows = conn.execute(
        f"""
        SELECT id, created_by_user_id, title, description, zip_code, address, source_store, status, ends_at, created_at, updated_at
        FROM deals
        WHERE {' AND '.join(where_clauses)}
        ORDER BY updated_at DESC, created_at DESC
        """,
        params,
    ).fetchall()
    keepers = set()
    duplicates = []
    for row in rows:
        dedupe_key = (
            row["created_by_user_id"] or "",
            row["title"] or "",
            row["description"] or "",
            row["zip_code"] or "",
            row["address"] or "",
            row["source_store"] or "",
            row["status"] or "",
            row["ends_at"] or "",
        )
        if dedupe_key in keepers:
            duplicates.append(row["id"])
            continue
        keepers.add(dedupe_key)
    if duplicates:
        timestamp = now_iso()
        conn.executemany(
            "UPDATE deals SET status = 'archived', updated_at = ? WHERE id = ? AND status != 'archived'",
            [(timestamp, deal_id) for deal_id in duplicates],
        )
    return duplicates


def deal_row_to_dict(row):
    return {
        "id": row["id"],
        "dealType": row["deal_type"],
        "createdByUserId": row["created_by_user_id"],
        "title": row["title"],
        "description": row["description"],
        "zipCode": row["zip_code"],
        "address": row["address"],
        "salePrice": row["sale_price"],
        "regularPrice": row["regular_price"],
        "unit": row["unit"],
        "category": row["category"],
        "sourceStore": row["source_store"],
        "status": row["status"],
        "expiresAt": row["ends_at"],
        "expiresOn": iso_to_date_input(row["ends_at"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def supabase_deal_to_dict(row):
    return {
        "id": row.get("id"),
        "dealType": row.get("deal_type"),
        "createdByUserId": row.get("company_id"),
        "title": row.get("title"),
        "description": row.get("description"),
        "zipCode": row.get("zip_code"),
        "address": row.get("address"),
        "salePrice": row.get("sale_price"),
        "regularPrice": row.get("regular_price"),
        "unit": row.get("unit"),
        "category": row.get("category"),
        "sourceStore": row.get("source_store_name"),
        "status": row.get("status"),
        "expiresAt": row.get("ends_at"),
        "expiresOn": iso_to_date_input(row.get("ends_at")),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def smtp_settings():
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": int(os.environ.get("SMTP_PORT", "0") or "0"),
        "username": os.environ.get("SMTP_USERNAME", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", "").strip(),
        "email_from": os.environ.get("EMAIL_FROM", "").strip(),
    }


def supabase_settings():
    anon_key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip()
    publishable_key = os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "").strip()
    return {
        "url": os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip(),
        "anon_key": anon_key or publishable_key,
        "service_role_key": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        "db_url": os.environ.get("SUPABASE_DB_URL", "").strip(),
    }


def supabase_is_configured():
    settings = supabase_settings()
    return all(
        [
            settings["url"],
            settings["anon_key"],
            settings["service_role_key"],
            settings["db_url"],
        ]
    )


def get_supabase_user(access_token):
    if not supabase_is_configured() or not access_token:
        return None
    settings = supabase_settings()
    request = urllib_request.Request(
        f"{settings['url'].rstrip('/')}/auth/v1/user",
        headers={
            "apikey": settings["anon_key"],
            "Authorization": f"Bearer {access_token}",
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            return payload if isinstance(payload, dict) else None
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def supabase_rest_headers(use_service_role=True, access_token=None):
    settings = supabase_settings()
    if use_service_role:
        api_key = settings["service_role_key"]
        bearer = settings["service_role_key"]
    else:
        api_key = settings["anon_key"]
        bearer = access_token or settings["anon_key"]
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }


def supabase_rest_request(path, method="GET", payload=None, use_service_role=True, access_token=None, expect_repr=False):
    if not supabase_is_configured():
        raise ValueError("Supabase is not configured")
    settings = supabase_settings()
    request = urllib_request.Request(
        f"{settings['url'].rstrip('/')}/rest/v1/{path.lstrip('/')}",
        headers=supabase_rest_headers(use_service_role=use_service_role, access_token=access_token),
        method=method,
    )
    if expect_repr:
        request.add_header("Prefer", "return=representation")
    if payload is not None:
        request.data = json.dumps(payload).encode("utf-8")
    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return None
            parsed = json.loads(raw)
            return parsed
    except urllib_error.HTTPError as exc:
        try:
            details = json.loads(exc.read().decode("utf-8") or "{}")
            message = details.get("message") or details.get("error_description") or details.get("error")
        except json.JSONDecodeError:
            message = None
        raise ValueError(message or f"Supabase request failed with status {exc.code}") from exc
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError("Supabase request failed") from exc


def fetch_supabase_account_snapshot(user_id):
    encoded_user_id = quote(str(user_id).strip(), safe="")
    profile_rows = supabase_rest_request(
        f"profiles?select=id,account_type,email,phone_number,zip_code&id=eq.{encoded_user_id}"
    ) or []
    if not profile_rows:
        return None
    profile = profile_rows[0]
    account_type = normalize_account_type(profile.get("account_type"))
    account_details = None
    if account_type == "company":
        details = supabase_rest_request(
            f"company_profiles?select=company_name,contact_name,status&id=eq.{encoded_user_id}"
        ) or []
        account_details = details[0] if details else {}
    else:
        details = supabase_rest_request(
            f"user_profiles?select=display_name,alert_channel_email,alert_channel_sms&id=eq.{encoded_user_id}"
        ) or []
        account_details = details[0] if details else {}
    interest_rows = supabase_rest_request(
        f"alert_interests?select=id,label,normalized_label&user_id=eq.{encoded_user_id}&order=created_at.asc"
    ) or []
    return {
        "profile": profile,
        "accountDetails": account_details,
        "alertInterests": interest_rows,
    }


def upsert_local_user(
    conn,
    *,
    user_id,
    account_type,
    email,
    phone_number,
    zip_code,
    company_name,
    alert_interests,
    password_value="supabase_auth_managed",
):
    timestamp = now_iso()
    existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    serialized_interests = json.dumps(normalize_alert_interests(alert_interests))
    if existing:
        conn.execute(
            """
            UPDATE users
            SET account_type = ?, email = ?, phone_number = ?, zip_code = ?, company_name = ?, alert_interests = ?, updated_at = ?
            WHERE id = ?
            """,
            (account_type, email, phone_number, zip_code, company_name, serialized_interests, timestamp, user_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO users (id, account_type, email, password, phone_number, zip_code, company_name, alert_interests, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                account_type,
                email,
                password_value,
                phone_number,
                zip_code,
                company_name,
                serialized_interests,
                timestamp,
                timestamp,
            ),
        )
    conn.commit()
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def ensure_local_user_from_supabase(conn, supabase_user):
    if not supabase_user or not supabase_user.get("id"):
        raise AuthError("Supabase session is invalid")
    metadata = supabase_user.get("user_metadata") or {}
    snapshot = fetch_supabase_account_snapshot(supabase_user["id"]) if supabase_is_configured() else None
    profile = snapshot.get("profile") if snapshot else {}
    account_details = snapshot.get("accountDetails") if snapshot else {}
    interest_rows = snapshot.get("alertInterests") if snapshot else []
    account_type = normalize_account_type(profile.get("account_type") or metadata.get("account_type"))
    email = normalize_email(profile.get("email") or supabase_user.get("email"))
    zip_code = normalize_zip_code(profile.get("zip_code") or metadata.get("zip_code"))
    if not email or not zip_code:
        raise AuthError("Supabase account metadata is incomplete")
    company_name = None
    if account_type == "company":
        company_name = normalize_company_name(account_details.get("company_name") or metadata.get("company_name"))
    phone_number = normalize_phone_number(profile.get("phone_number") or metadata.get("phone_number") or supabase_user.get("phone") or "")
    alert_interests = [row.get("normalized_label") or row.get("label") for row in interest_rows]
    return upsert_local_user(
        conn,
        user_id=supabase_user["id"],
        account_type=account_type,
        email=email,
        phone_number=phone_number,
        zip_code=zip_code,
        company_name=company_name,
        alert_interests=alert_interests,
    )


def replace_supabase_alert_interests(user_id, alert_interests):
    encoded_user_id = quote(str(user_id).strip(), safe="")
    existing_rows = supabase_rest_request(
        f"alert_interests?select=id,normalized_label&user_id=eq.{encoded_user_id}&order=created_at.asc"
    ) or []
    existing_by_label = {row.get("normalized_label"): row for row in existing_rows}
    desired_labels = normalize_alert_interests(alert_interests)
    for row in existing_rows:
        normalized_label = row.get("normalized_label")
        if normalized_label not in desired_labels:
            supabase_rest_request(
                f"alert_interests?id=eq.{quote(str(row.get('id')), safe='')}",
                method="DELETE",
            )
    inserts = [
        {"user_id": user_id, "label": label, "normalized_label": label}
        for label in desired_labels
        if label not in existing_by_label
    ]
    if inserts:
        supabase_rest_request("alert_interests", method="POST", payload=inserts, expect_repr=True)
    return desired_labels


def hosted_auth_guard():
    if supabase_is_configured():
        raise ValueError("Hosted Supabase auth is enabled. Complete auth actions through Supabase.")


def app_base_url():
    return os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")


def app_host():
    explicit = os.environ.get("APP_HOST", "").strip()
    if explicit:
        return explicit
    # Hosting platforms like Railway/Render/Heroku inject PORT and expect the
    # app to bind every interface, not just loopback. If PORT is present and
    # APP_HOST wasn't explicitly set, assume we're running on one of those.
    if os.environ.get("PORT", "").strip():
        return "0.0.0.0"
    return "127.0.0.1"


def app_port():
    # APP_PORT (our own convention) wins if set; otherwise fall back to PORT
    # (the convention most hosting platforms inject automatically), then 8000.
    raw = (os.environ.get("APP_PORT", "").strip() or os.environ.get("PORT", "").strip() or "8000")
    try:
        value = int(raw)
    except ValueError:
        value = 8000
    return min(65535, max(1, value))


def env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def matching_scheduler_interval_seconds():
    raw = os.environ.get("MATCHING_SCHEDULER_INTERVAL_SECONDS", "300").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 300
    return max(30, value)


def matching_scheduler_is_enabled():
    return env_flag("MATCHING_SCHEDULER_ENABLED", True)


def scheduler_state_snapshot():
    with SCHEDULER_STATE_LOCK:
        return dict(MATCHING_SCHEDULER_STATE)


def update_scheduler_state(**changes):
    with SCHEDULER_STATE_LOCK:
        MATCHING_SCHEDULER_STATE.update(changes)
        return dict(MATCHING_SCHEDULER_STATE)


def smtp_is_configured():
    settings = smtp_settings()
    return all(
        [
            settings["host"],
            settings["port"],
            settings["username"],
            settings["password"],
            settings["email_from"],
        ]
    )


def system_status():
    hosted_auth = supabase_is_configured()
    smtp_ready = smtp_is_configured()
    scheduler_state = scheduler_state_snapshot()
    return {
        "authProvider": "supabase" if hosted_auth else "local_prototype",
        "authMode": "hosted_supabase" if hosted_auth else "local_session_tokens",
        "supabaseUrl": supabase_settings()["url"] if hosted_auth else "",
        "supabaseAnonKey": supabase_settings()["anon_key"] if hosted_auth else "",
        "appBaseUrl": app_base_url(),
        "smtpConfigured": smtp_ready,
        "notificationMode": "live_email" if smtp_ready else "mock_email",
        "passwordResetMode": "hosted_email_link" if hosted_auth else ("email" if smtp_ready else "manual_token"),
        "matchingScheduler": scheduler_state,
        "serverTime": now_iso(),
    }


def send_match_email(user, deal, matched_interest, message):
    settings = smtp_settings()
    if not smtp_is_configured():
        return {"channel": "email", "status": "mocked", "error": None}
    subject = f"New deal match in {user['zipCode']}: {deal['sourceStore'] or deal['title']}"
    email_message = EmailMessage()
    email_message["Subject"] = subject
    email_message["From"] = settings["email_from"]
    email_message["To"] = user["email"]
    email_message.set_content(
        "\n".join(
            [
                f"Hi there,",
                "",
                f"We found a new deal that matches your favorite: {matched_interest}",
                "",
                f"Business: {deal['sourceStore'] or deal['title']}",
                f"Deal: {deal['description']}",
                f"Zip code: {deal['zipCode']}",
                f"Address: {deal.get('address') or 'Address coming soon'}",
                "",
                message,
            ]
        )
    )
    with smtplib.SMTP(settings["host"], settings["port"], timeout=20) as server:
        server.starttls()
        server.login(settings["username"], settings["password"])
        server.send_message(email_message)
    return {"channel": "email", "status": "sent", "error": None}


def send_password_reset_email(email, token):
    settings = smtp_settings()
    if not smtp_is_configured():
        return {"status": "mocked", "token": token}
    reset_link = f"{app_base_url()}/?resetToken={token}"
    email_message = EmailMessage()
    email_message["Subject"] = "Reset your Local Deal Alert password"
    email_message["From"] = settings["email_from"]
    email_message["To"] = email
    email_message.set_content(
        "\n".join(
            [
                "We received a request to reset your password.",
                "",
                f"Open this link to continue: {reset_link}",
                "",
                f"If you need to enter the token manually, use: {token}",
                "",
                f"This reset link expires in {PASSWORD_RESET_TTL_MINUTES} minutes.",
            ]
        )
    )
    with smtplib.SMTP(settings["host"], settings["port"], timeout=20) as server:
        server.starttls()
        server.login(settings["username"], settings["password"])
        server.send_message(email_message)
    return {"status": "sent", "token": None}


def log_notification(entry):
    with NOTIFICATION_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def log_match_run(entry):
    with MATCH_RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def ensure_mock_grocery_deals():
    if supabase_is_configured():
        rows = supabase_rest_request("deals?select=id&deal_type=eq.grocery") or []
        if rows:
            return len(rows)
        payload = [
            {
                "deal_type": deal["dealType"],
                "company_id": None,
                "title": deal["title"],
                "description": deal["description"],
                "zip_code": deal["zipCode"],
                "address": None,
                "sale_price": deal["salePrice"],
                "regular_price": deal["regularPrice"],
                "unit": deal["unit"],
                "category": deal["category"],
                "source_store_name": deal["sourceStore"],
                "status": "active",
            }
            for deal in MOCK_GROCERY_DEALS
        ]
        supabase_rest_request("deals", method="POST", payload=payload, expect_repr=True)
        rows = supabase_rest_request("deals?select=id&deal_type=eq.grocery") or []
        return len(rows)
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) AS c FROM deals WHERE deal_type = 'grocery'").fetchone()["c"]
    if existing:
        conn.close()
        return existing
    timestamp = now_iso()
    for deal in MOCK_GROCERY_DEALS:
        conn.execute(
            """
            INSERT INTO deals (
                id, deal_type, created_by_user_id, title, description, zip_code,
                address, sale_price, regular_price, unit, category, source_store, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                str(uuid.uuid4()),
                deal["dealType"],
                None,
                deal["title"],
                deal["description"],
                deal["zipCode"],
                deal["salePrice"],
                deal["regularPrice"],
                deal["unit"],
                deal["category"],
                deal["sourceStore"],
                timestamp,
                timestamp,
            ),
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) AS c FROM deals WHERE deal_type = 'grocery'").fetchone()["c"]
    conn.close()
    return count


def ensure_mock_pizza_deals():
    if supabase_is_configured():
        encoded_category = quote("Demo Pizza", safe="")
        rows = supabase_rest_request(f"deals?select=id&category=eq.{encoded_category}") or []
        if rows:
            return len(rows)
        payload = [
            {
                "deal_type": "company",
                "company_id": None,
                "title": deal["title"],
                "description": deal["description"],
                "zip_code": deal["zipCode"],
                "address": deal["address"],
                "sale_price": None,
                "regular_price": None,
                "unit": "offer",
                "category": "Demo Pizza",
                "source_store_name": deal["sourceStore"],
                "status": "active",
            }
            for deal in MOCK_PIZZA_DEALS
        ]
        supabase_rest_request("deals", method="POST", payload=payload, expect_repr=True)
        rows = supabase_rest_request(f"deals?select=id&category=eq.{encoded_category}") or []
        return len(rows)
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) AS c FROM deals WHERE category = 'Demo Pizza'").fetchone()["c"]
    if existing:
        conn.close()
        return existing
    timestamp = now_iso()
    for deal in MOCK_PIZZA_DEALS:
        conn.execute(
            """
            INSERT INTO deals (
                id, deal_type, created_by_user_id, title, description, zip_code,
                address, sale_price, regular_price, unit, category, source_store, status,
                created_at, updated_at
            ) VALUES (?, 'company', NULL, ?, ?, ?, ?, NULL, NULL, 'offer', 'Demo Pizza', ?, 'active', ?, ?)
            """,
            (
                str(uuid.uuid4()),
                deal["title"],
                deal["description"],
                deal["zipCode"],
                deal["address"],
                deal["sourceStore"],
                timestamp,
                timestamp,
            ),
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) AS c FROM deals WHERE category = 'Demo Pizza'").fetchone()["c"]
    conn.close()
    return count


def supabase_all_deals():
    rows = supabase_rest_request(
        "deals?select=id,deal_type,company_id,title,description,zip_code,address,sale_price,regular_price,unit,category,source_store_name,status,ends_at,created_at,updated_at&status=eq.active&order=created_at.desc"
    ) or []
    return [supabase_deal_to_dict(row) for row in rows]


def supabase_company_deals_for_user(user_id):
    encoded_user_id = quote(str(user_id).strip(), safe="")
    rows = supabase_rest_request(
        "deals"
        "?select=id,deal_type,company_id,title,description,zip_code,address,sale_price,regular_price,unit,category,source_store_name,status,ends_at,created_at,updated_at"
        f"&deal_type=eq.company&company_id=eq.{encoded_user_id}&status=neq.archived&order=updated_at.desc"
    ) or []
    status_rank = {"active": 1, "draft": 2, "expired": 3}
    rows.sort(key=lambda row: (status_rank.get(str(row.get("status") or "").lower(), 4), -(parse_iso(row.get("updated_at") or now_iso()).timestamp())))
    return [supabase_deal_to_dict(row) for row in rows]


def create_supabase_company_deal(user_id, company_name, zip_code, address, deal_description, status, ends_at):
    rows = supabase_rest_request(
        "deals",
        method="POST",
        payload=[
            {
                "deal_type": "company",
                "company_id": user_id,
                "source_store_name": company_name,
                "title": company_name,
                "description": deal_description,
                "zip_code": zip_code,
                "address": address,
                "unit": "offer",
                "category": "Local Business",
                "status": status,
                "ends_at": ends_at,
            }
        ],
        expect_repr=True,
    ) or []
    if not rows:
        raise ValueError("Supabase deal creation returned no data")
    return rows[0]


def supabase_all_users():
    profiles = supabase_rest_request(
        "profiles?select=id,account_type,email,phone_number,zip_code,created_at,updated_at&order=created_at.desc"
    ) or []
    company_profiles = supabase_rest_request(
        "company_profiles?select=id,company_name"
    ) or []
    interests = supabase_rest_request(
        "alert_interests?select=user_id,normalized_label,created_at&order=created_at.asc"
    ) or []
    company_names = {row.get("id"): row.get("company_name") for row in company_profiles}
    interests_by_user = {}
    for row in interests:
        interests_by_user.setdefault(row.get("user_id"), []).append(row.get("normalized_label") or "")
    users = []
    for profile in profiles:
        users.append(
            {
                "id": profile.get("id"),
                "accountType": normalize_account_type(profile.get("account_type")),
                "email": profile.get("email"),
                "phoneNumber": profile.get("phone_number") or "",
                "zipCode": profile.get("zip_code") or "",
                "companyName": company_names.get(profile.get("id")),
                "alertInterests": normalize_alert_interests(interests_by_user.get(profile.get("id"), [])),
                "createdAt": profile.get("created_at") or now_iso(),
                "updatedAt": profile.get("updated_at") or now_iso(),
            }
        )
    return users


def supabase_notifications():
    rows = supabase_rest_request(
        "notifications?select=id,user_id,deal_id,matched_interest,channel,status,message,created_at&order=created_at.desc"
    ) or []
    user_facing_notifications = []
    for row in rows:
        status = row.get("status")
        if status == "queued" and not smtp_is_configured():
            status = "mocked"
        user_facing_notifications.append(
            {
                "userId": row.get("user_id"),
                "dealId": row.get("deal_id"),
                "matchedInterest": row.get("matched_interest"),
                "channel": row.get("channel"),
                "status": status,
                "message": row.get("message"),
                "createdAt": row.get("created_at"),
            }
        )
    return user_facing_notifications


def insert_supabase_notification(entry):
    payload = dict(entry)
    stored_status = payload.get("status")
    if stored_status == "mocked":
        payload["status"] = "queued"
    supabase_rest_request("notifications", method="POST", payload=[payload], expect_repr=True)


def update_supabase_company_deal(deal_id, company_name, zip_code, address, deal_description, status, ends_at):
    encoded_deal_id = quote(str(deal_id).strip(), safe="")
    rows = supabase_rest_request(
        f"deals?id=eq.{encoded_deal_id}",
        method="PATCH",
        payload={
            "source_store_name": company_name,
            "title": company_name,
            "description": deal_description,
            "zip_code": zip_code,
            "address": address,
            "status": status,
            "ends_at": ends_at,
            "category": "Local Business",
            "unit": "offer",
        },
        expect_repr=True,
    ) or []
    if not rows:
        raise ValueError("Company deal not found")
    return rows[0]


def archive_supabase_company_deal(deal_id):
    encoded_deal_id = quote(str(deal_id).strip(), safe="")
    rows = supabase_rest_request(
        f"deals?id=eq.{encoded_deal_id}",
        method="PATCH",
        payload={"status": "archived"},
        expect_repr=True,
    ) or []
    if not rows:
        raise ValueError("Company deal not found")
    return rows[0]


def all_deals():
    if supabase_is_configured():
        return supabase_all_deals()
    conn = get_db()
    sync_company_deal_statuses(conn)
    rows = conn.execute(
        """
        SELECT id, deal_type, created_by_user_id, title, description, zip_code,
               address, sale_price, regular_price, unit, category, source_store, status, ends_at,
               created_at, updated_at
        FROM deals
        WHERE status = 'active'
        ORDER BY created_at DESC
        """
    ).fetchall()
    conn.commit()
    conn.close()
    return [deal_row_to_dict(row) for row in rows]


def company_deals_for_user(user_id):
    if supabase_is_configured():
        return supabase_company_deals_for_user(user_id)
    conn = get_db()
    sync_company_deal_statuses(conn)
    rows = conn.execute(
        """
        SELECT id, deal_type, created_by_user_id, title, description, zip_code,
               address, sale_price, regular_price, unit, category, source_store, status, ends_at,
               created_at, updated_at
        FROM deals
        WHERE deal_type = 'company'
          AND created_by_user_id = ?
          AND status != 'archived'
        ORDER BY
          CASE status
            WHEN 'active' THEN 1
            WHEN 'draft' THEN 2
            WHEN 'expired' THEN 3
            ELSE 4
          END,
          updated_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.commit()
    conn.close()
    return [deal_row_to_dict(row) for row in rows]


def company_deal_for_user_by_id(user_id, deal_id):
    return next((deal for deal in company_deals_for_user(user_id) if deal["id"] == deal_id), None)


def safe_supabase_company_deal_payload(user_id, created_or_updated):
    if not created_or_updated:
        return None
    deal_id = str(created_or_updated.get("id") or "").strip()
    if not deal_id:
        return None
    if created_or_updated.get("deal_type") and created_or_updated.get("zip_code") is not None:
        return supabase_deal_to_dict(created_or_updated)
    try:
        return company_deal_for_user_by_id(user_id, deal_id)
    except Exception:
        return None


def all_users():
    if supabase_is_configured():
        return supabase_all_users()
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return [user_to_dict(row) for row in rows]


def all_notifications():
    if supabase_is_configured():
        return supabase_notifications()
    conn = get_db()
    rows = conn.execute(
        "SELECT user_id, deal_id, matched_interest, channel, status, message, created_at FROM notifications ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [
        {
            "userId": row["user_id"],
            "dealId": row["deal_id"],
            "matchedInterest": row["matched_interest"],
            "channel": row["channel"],
            "status": row["status"],
            "message": row["message"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def notifications_for_user(user):
    if not user:
        return []
    account_type = normalize_account_type(user["account_type"] if "account_type" in user.keys() else user.get("account_type"))
    if account_type != "user":
        return []
    user_id = str((user["id"] if "id" in user.keys() else user.get("id")) or "").strip()
    if not user_id:
        return []
    return [item for item in all_notifications() if item.get("userId") == user_id]


def notification_dedupe_keys(notifications):
    return {
        (
            item.get("userId"),
            item.get("dealId"),
            item.get("matchedInterest"),
            item.get("channel"),
        )
        for item in notifications
    }


def matching_interest_for_deal(interests, deal):
    haystack = normalized_haystack(deal["title"], deal["description"], deal.get("sourceStore"))
    return next((interest for interest in interests if interest in haystack), None)


def build_match_message(user, deal, matched_interest):
    if deal["dealType"] == "grocery":
        return f"{deal['title']} matches {matched_interest} in zip {user['zipCode']}."
    return f"{deal['title']} has {deal['description']} at area {user['zipCode']}."


def run_matching_job(trigger="manual"):
    started_at = now_iso()
    previous_state = scheduler_state_snapshot()
    update_scheduler_state(
        lastTrigger=trigger,
        lastStartedAt=started_at,
        lastCompletedAt=previous_state.get("lastCompletedAt", ""),
        lastRunError="",
        lastRunNotifications=0,
    )
    try:
        sent = match_and_notify()
        completed_at = now_iso()
        state = update_scheduler_state(
            lastTrigger=trigger,
            lastCompletedAt=completed_at,
            lastSucceededAt=completed_at,
            lastRunNotifications=sent,
            lastRunError="",
            runCount=int(previous_state.get("runCount") or 0) + 1,
        )
        log_match_run(
            {
                "trigger": trigger,
                "startedAt": started_at,
                "completedAt": completed_at,
                "notificationsSent": sent,
                "status": "ok",
            }
        )
        return sent, state
    except Exception as exc:
        completed_at = now_iso()
        state = update_scheduler_state(
            lastTrigger=trigger,
            lastCompletedAt=completed_at,
            lastRunNotifications=0,
            lastRunError=str(exc),
            runCount=int(previous_state.get("runCount") or 0) + 1,
        )
        log_match_run(
            {
                "trigger": trigger,
                "startedAt": started_at,
                "completedAt": completed_at,
                "notificationsSent": 0,
                "status": "failed",
                "error": str(exc),
            }
        )
        raise


def match_and_notify():
    if supabase_is_configured():
        users = [user for user in all_users() if user["accountType"] == "user"]
        deals = all_deals()
        existing_notifications = notification_dedupe_keys(all_notifications())
        sent = 0
        for user in users:
            if not normalize_email(user.get("email")) or not user.get("zipCode"):
                continue
            interests = [item.strip().lower() for item in user["alertInterests"] if item.strip()]
            if not interests:
                continue
            for deal in deals:
                if deal["zipCode"] != user["zipCode"]:
                    continue
                matched = matching_interest_for_deal(interests, deal)
                if not matched:
                    continue
                dedupe_key = (user["id"], deal["id"], matched, "email")
                if dedupe_key in existing_notifications:
                    continue
                message = build_match_message(user, deal, matched)
                try:
                    delivery = send_match_email(user, deal, matched, message)
                    insert_supabase_notification(
                        {
                            "user_id": user["id"],
                            "deal_id": deal["id"],
                            "matched_interest": matched,
                            "channel": delivery["channel"],
                            "status": delivery["status"],
                            "message": message,
                            "created_at": now_iso(),
                        }
                    )
                    log_notification(
                        {
                            "userId": user["id"],
                            "dealId": deal["id"],
                            "matchedInterest": matched,
                            "status": delivery["status"],
                            "channel": delivery["channel"],
                            "message": message,
                            "createdAt": now_iso(),
                        }
                    )
                    existing_notifications.add(dedupe_key)
                    sent += 1
                except Exception as exc:
                    insert_supabase_notification(
                        {
                            "user_id": user["id"],
                            "deal_id": deal["id"],
                            "matched_interest": matched,
                            "channel": "email",
                            "status": "failed",
                            "message": message,
                            "error_message": str(exc),
                            "created_at": now_iso(),
                        }
                    )
        return sent
    conn = get_db()
    users = [user_to_dict(row) for row in conn.execute("SELECT * FROM users WHERE account_type = 'user'")]
    deals = all_deals()
    existing_notifications = notification_dedupe_keys(all_notifications())
    sent = 0
    for user in users:
        if not normalize_email(user.get("email")) or not user.get("zipCode"):
            continue
        interests = [item.strip().lower() for item in user["alertInterests"] if item.strip()]
        if not interests:
            continue
        for deal in deals:
            if deal["zipCode"] != user["zipCode"]:
                continue
            matched = matching_interest_for_deal(interests, deal)
            if not matched:
                continue
            dedupe_key = (user["id"], deal["id"], matched, "email")
            if dedupe_key in existing_notifications:
                continue
            message = build_match_message(user, deal, matched)
            try:
                delivery = send_match_email(user, deal, matched, message)
                conn.execute(
                    """
                    INSERT INTO notifications (id, user_id, deal_id, matched_interest, channel, status, message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), user["id"], deal["id"], matched, delivery["channel"], delivery["status"], message, now_iso()),
                )
                conn.commit()
                log_notification(
                    {
                        "userId": user["id"],
                        "email": user["email"],
                        "dealId": deal["id"],
                        "matchedInterest": matched,
                        "status": delivery["status"],
                        "message": message,
                        "createdAt": now_iso(),
                    }
                )
                existing_notifications.add(dedupe_key)
                sent += 1
            except (smtplib.SMTPException, OSError) as exc:
                try:
                    conn.execute(
                        """
                        INSERT INTO notifications (id, user_id, deal_id, matched_interest, channel, status, message, created_at)
                        VALUES (?, ?, ?, ?, 'email', 'failed', ?, ?)
                        """,
                        (str(uuid.uuid4()), user["id"], deal["id"], matched, message, now_iso()),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass
                log_notification(
                    {
                        "userId": user["id"],
                        "email": user["email"],
                        "dealId": deal["id"],
                        "matchedInterest": matched,
                        "status": "failed",
                        "error": str(exc),
                        "message": message,
                        "createdAt": now_iso(),
                    }
                )
            except sqlite3.IntegrityError:
                pass
    conn.close()
    return sent


class AppHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.end_headers()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                return self.serve_static("index.html")
            if parsed.path.startswith("/static/"):
                return self.serve_static(parsed.path.replace("/static/", "", 1))
            if parsed.path == "/api/deals":
                return json_response(self, {"deals": all_deals()})
            if parsed.path == "/api/company-deals":
                conn = get_db()
                try:
                    cleanup_auth_artifacts(conn)
                    auth_user, _ = get_authenticated_user(self, conn)
                    if auth_user["account_type"] != "company":
                        return json_response(self, {"error": "Company account required"}, HTTPStatus.FORBIDDEN)
                finally:
                    conn.close()
                return json_response(self, {"deals": company_deals_for_user(auth_user["id"])})
            if parsed.path == "/api/system-status":
                return json_response(self, system_status())
            if parsed.path == "/api/session":
                conn = get_db()
                try:
                    cleanup_auth_artifacts(conn)
                    user_row, token = get_authenticated_user(self, conn)
                    payload = {"ok": True, "sessionToken": token, "user": user_to_dict(user_row)}
                finally:
                    conn.close()
                return json_response(self, payload)
            if parsed.path == "/api/users":
                conn = get_db()
                try:
                    cleanup_auth_artifacts(conn)
                    get_authenticated_user(self, conn)
                    users = all_users()
                finally:
                    conn.close()
                return json_response(self, {"users": users})
            if parsed.path == "/api/notifications":
                conn = get_db()
                try:
                    cleanup_auth_artifacts(conn)
                    user_row, _ = get_authenticated_user(self, conn)
                    notifications = notifications_for_user(user_row)
                finally:
                    conn.close()
                return json_response(self, {"notifications": notifications})
            return json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except AuthError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.UNAUTHORIZED)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/signup":
                body = read_json(self)
                validate_signup(body)
                return self.handle_signup(body)
            if parsed.path == "/api/login":
                return self.handle_login(read_json(self))
            if parsed.path == "/api/password-reset/request":
                return self.handle_password_reset_request(read_json(self))
            if parsed.path == "/api/password-reset/confirm":
                return self.handle_password_reset_confirm(read_json(self))
            if parsed.path == "/api/account/password":
                return self.handle_change_password(read_json(self))
            if parsed.path == "/api/logout":
                return self.handle_logout()
            if parsed.path == "/api/company-deals":
                return self.handle_company_deal(read_json(self))
            if parsed.path == "/api/ingest":
                conn = get_db()
                try:
                    get_authenticated_user(self, conn)
                finally:
                    conn.close()
                count = ensure_mock_grocery_deals()
                return json_response(self, {"ok": True, "dealsIngested": count, **system_status()})
            if parsed.path == "/api/match":
                conn = get_db()
                try:
                    get_authenticated_user(self, conn)
                finally:
                    conn.close()
                sent, _ = run_matching_job("manual")
                return json_response(self, {"ok": True, "notificationsSent": sent, **system_status()})
            return json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except AuthError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.UNAUTHORIZED)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_PUT(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/users/") and parsed.path.endswith("/interests"):
                user_id = parsed.path.split("/")[3]
                return self.handle_update_interests(user_id, read_json(self))
            if parsed.path.startswith("/api/company-deals/"):
                deal_id = parsed.path.split("/")[3]
                return self.handle_update_company_deal(deal_id, read_json(self))
            return json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except AuthError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.UNAUTHORIZED)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/company-deals/"):
                deal_id = parsed.path.split("/")[3]
                return self.handle_delete_company_deal(deal_id, read_json(self))
            return json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except AuthError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.UNAUTHORIZED)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def serve_static(self, name):
        target = STATIC_DIR / name
        if not target.exists():
            return json_response(self, {"error": "File not found"}, HTTPStatus.NOT_FOUND)
        content = target.read_bytes()
        content_type = "text/html; charset=utf-8"
        if target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def handle_signup(self, body):
        hosted_auth_guard()
        account_type = normalize_account_type(body.get("accountType"))
        email = normalize_email(body.get("email"))
        phone_number = normalize_phone_number(body.get("phoneNumber"))
        zip_code = normalize_zip_code(body.get("zipCode"))
        company_name = normalize_company_name(body.get("companyName")) if account_type == "company" else None
        conn = get_db()
        cleanup_auth_artifacts(conn)
        timestamp = now_iso()
        user_id = str(uuid.uuid4())
        try:
            conn.execute(
                """
                INSERT INTO users (id, account_type, email, password, phone_number, zip_code, company_name, alert_interests, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
                """,
                (
                    user_id,
                    account_type,
                    email,
                    hash_password(body["password"]),
                    phone_number,
                    zip_code,
                    company_name,
                    timestamp,
                    timestamp,
                ),
            )
        except sqlite3.IntegrityError:
            conn.close()
            return json_response(self, {"error": "An account with that email already exists"}, HTTPStatus.CONFLICT)
        session_token = create_session(conn, user_id)
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return json_response(
            self,
            {
                "message": f"{account_type.title()} account created.",
                "sessionToken": session_token,
                "user": user_to_dict(row),
            },
            HTTPStatus.CREATED,
        )

    def handle_login(self, body):
        hosted_auth_guard()
        email = normalize_email(body.get("email"))
        conn = get_db()
        cleanup_auth_artifacts(conn)
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if not row or not verify_password(row["password"], body.get("password", "")):
            conn.close()
            return json_response(self, {"error": "Invalid email or password"}, HTTPStatus.UNAUTHORIZED)
        if not row["password"].startswith("pbkdf2_sha256$"):
            conn.execute("UPDATE users SET password = ?, updated_at = ? WHERE id = ?", (hash_password(body["password"]), now_iso(), row["id"]))
        session_token = create_session(conn, row["id"])
        conn.commit()
        refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        conn.close()
        return json_response(self, {"ok": True, "sessionToken": session_token, "user": user_to_dict(refreshed)})

    def handle_password_reset_request(self, body):
        hosted_auth_guard()
        email = normalize_email(body.get("email"))
        if not email:
            return json_response(self, {"error": "Email is required"}, HTTPStatus.BAD_REQUEST)
        conn = get_db()
        cleanup_auth_artifacts(conn)
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            conn.close()
            return json_response(
                self,
                {
                    "ok": True,
                    "message": "If that email exists, password reset instructions have been prepared.",
                    **system_status(),
                },
            )
        token = create_password_reset_token(conn, row["id"])
        delivery = send_password_reset_email(email, token)
        conn.commit()
        conn.close()
        payload = {
            "ok": True,
            "message": "Password reset instructions sent." if delivery["status"] == "sent" else "Password reset token created for prototype mode.",
            **system_status(),
        }
        if delivery["token"]:
            payload["resetToken"] = delivery["token"]
        return json_response(self, payload)

    def handle_password_reset_confirm(self, body):
        hosted_auth_guard()
        token = str(body.get("token") or "").strip()
        new_password = str(body.get("newPassword") or "")
        if not token:
            return json_response(self, {"error": "Reset token is required"}, HTTPStatus.BAD_REQUEST)
        try:
            validate_password_strength(new_password)
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        conn = get_db()
        try:
            cleanup_auth_artifacts(conn)
            reset_row = get_valid_password_reset_row(conn, token)
            conn.execute(
                "UPDATE users SET password = ?, updated_at = ? WHERE id = ?",
                (hash_password(new_password), now_iso(), reset_row["user_id"]),
            )
            revoke_all_sessions(conn, reset_row["user_id"])
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
                (now_iso(), hash_token(token)),
            )
            session_token = create_session(conn, reset_row["user_id"])
            conn.commit()
            user_row = conn.execute("SELECT * FROM users WHERE id = ?", (reset_row["user_id"],)).fetchone()
        except ValueError as exc:
            conn.close()
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        conn.close()
        return json_response(
            self,
            {
                "ok": True,
                "message": "Password updated. You are now logged in.",
                "sessionToken": session_token,
                "user": user_to_dict(user_row),
            },
        )

    def handle_change_password(self, body):
        hosted_auth_guard()
        current_password = str(body.get("currentPassword") or "")
        new_password = str(body.get("newPassword") or "")
        if not current_password:
            return json_response(self, {"error": "Current password is required"}, HTTPStatus.BAD_REQUEST)
        try:
            validate_password_strength(new_password)
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        conn = get_db()
        cleanup_auth_artifacts(conn)
        auth_user, current_token = get_authenticated_user(self, conn)
        if not verify_password(auth_user["password"], current_password):
            conn.close()
            return json_response(self, {"error": "Current password is incorrect"}, HTTPStatus.UNAUTHORIZED)
        conn.execute(
            "UPDATE users SET password = ?, updated_at = ? WHERE id = ?",
            (hash_password(new_password), now_iso(), auth_user["id"]),
        )
        revoke_all_sessions(conn, auth_user["id"])
        session_token = create_session(conn, auth_user["id"])
        conn.commit()
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (auth_user["id"],)).fetchone()
        conn.close()
        return json_response(
            self,
            {
                "ok": True,
                "message": "Password changed. You are still signed in.",
                "sessionToken": session_token,
                "user": user_to_dict(user_row),
            },
        )

    def handle_logout(self):
        conn = get_db()
        try:
            cleanup_auth_artifacts(conn)
            _, token = get_authenticated_user(self, conn)
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (now_iso(), hash_token(token)),
            )
            conn.commit()
        finally:
            conn.close()
        return json_response(self, {"ok": True})

    def handle_update_interests(self, user_id, body):
        conn = get_db()
        cleanup_auth_artifacts(conn)
        auth_user, _ = get_authenticated_user(self, conn)
        if auth_user["id"] != user_id or auth_user["account_type"] != "user":
            conn.close()
            return json_response(self, {"error": "Not authorized"}, HTTPStatus.FORBIDDEN)
        alert_interests = normalize_alert_interests(body.get("alertInterests", []))
        if supabase_is_configured():
            replace_supabase_alert_interests(user_id, alert_interests)
            supabase_user = get_supabase_user(self.headers.get("Authorization", "").replace("Bearer ", "", 1).strip())
            row = ensure_local_user_from_supabase(conn, supabase_user) if supabase_user else conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET alert_interests = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(alert_interests), now_iso(), user_id),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        else:
            conn.execute(
                "UPDATE users SET alert_interests = ?, updated_at = ? WHERE id = ? AND account_type = 'user'",
                (json.dumps(alert_interests), now_iso(), user_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if not row:
            return json_response(self, {"error": "User not found"}, HTTPStatus.NOT_FOUND)
        return json_response(self, {"user": user_to_dict(row)})

    def handle_company_deal(self, body):
        conn = get_db()
        cleanup_auth_artifacts(conn)
        auth_user, _ = get_authenticated_user(self, conn)
        if auth_user["account_type"] != "company":
            conn.close()
            return json_response(self, {"error": "Company account required"}, HTTPStatus.FORBIDDEN)
        owner = conn.execute("SELECT * FROM users WHERE id = ? AND account_type = 'company'", (auth_user["id"],)).fetchone()
        if not owner:
            conn.close()
            return json_response(self, {"error": "Company account not found"}, HTTPStatus.NOT_FOUND)
        zip_code = normalize_zip_code(body.get("zipCode"))
        company_name = normalize_company_name(body.get("companyName") or owner["company_name"])
        address = str(body.get("address") or "").strip()
        deal_description = str(body.get("dealDescription") or "").strip()
        status = normalize_company_deal_status(body.get("status"))
        try:
            ends_at = normalize_ends_on(body.get("expiresOn"))
        except ValueError as exc:
            conn.close()
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if not ends_at:
            ends_at = default_company_deal_ends_at()
        if not zip_code or not re.fullmatch(r"\d{5}", zip_code):
            conn.close()
            return json_response(self, {"error": "Zip code must be 5 digits"}, HTTPStatus.BAD_REQUEST)
        if not address:
            conn.close()
            return json_response(self, {"error": "Street address is required"}, HTTPStatus.BAD_REQUEST)
        if not deal_description:
            conn.close()
            return json_response(self, {"error": "Deal description is required"}, HTTPStatus.BAD_REQUEST)
        if supabase_is_configured():
            created = create_supabase_company_deal(auth_user["id"], company_name, zip_code, address, deal_description, status, ends_at)
            deal_id = created["id"]
            deal_payload = safe_supabase_company_deal_payload(auth_user["id"], created)
        else:
            timestamp = now_iso()
            deal_id = str(uuid.uuid4())
            sync_company_deal_statuses(conn)
            conn.execute(
                """
                INSERT INTO deals (
                    id, deal_type, created_by_user_id, title, description, zip_code,
                    address, sale_price, regular_price, unit, category, source_store, status, ends_at, created_at, updated_at
                ) VALUES (?, 'company', ?, ?, ?, ?, ?, NULL, NULL, 'offer', 'Local Business', ?, ?, ?, ?, ?)
                """,
                (
                    deal_id,
                    auth_user["id"],
                    company_name,
                    deal_description,
                    zip_code,
                    address,
                    company_name,
                    status,
                    ends_at,
                    timestamp,
                    timestamp,
                ),
            )
            archive_duplicate_company_deals(conn, auth_user["id"])
            sync_company_deal_statuses(conn)
            conn.commit()
            row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
            deal_payload = deal_row_to_dict(row) if row else None
        conn.close()
        return json_response(self, {"dealId": deal_id, "deal": deal_payload, "message": "Company deal created."}, HTTPStatus.CREATED)

    def handle_update_company_deal(self, deal_id, body):
        conn = get_db()
        cleanup_auth_artifacts(conn)
        auth_user, _ = get_authenticated_user(self, conn)
        if auth_user["account_type"] != "company":
            conn.close()
            return json_response(self, {"error": "Company account required"}, HTTPStatus.FORBIDDEN)
        owner = conn.execute("SELECT * FROM users WHERE id = ? AND account_type = 'company'", (auth_user["id"],)).fetchone()
        if supabase_is_configured():
            deal = next((item for item in supabase_company_deals_for_user(auth_user["id"]) if item["id"] == deal_id), None)
            if not owner or not deal or deal["createdByUserId"] != auth_user["id"]:
                conn.close()
                return json_response(self, {"error": "Company deal not found"}, HTTPStatus.NOT_FOUND)
        else:
            sync_company_deal_statuses(conn)
            deal = conn.execute("SELECT * FROM deals WHERE id = ? AND deal_type = 'company'", (deal_id,)).fetchone()
            if not owner or not deal or deal["created_by_user_id"] != auth_user["id"]:
                conn.close()
                return json_response(self, {"error": "Company deal not found"}, HTTPStatus.NOT_FOUND)
        if supabase_is_configured():
            company_name = normalize_company_name(body.get("companyName") or owner["company_name"])
            zip_code = normalize_zip_code(body.get("zipCode") or deal["zipCode"])
            address = str(body.get("address") or deal["address"] or "").strip()
            deal_description = str(body.get("dealDescription") or deal["description"] or "").strip()
            status = normalize_company_deal_status(body.get("status") or deal["status"])
            try:
                ends_at = normalize_ends_on(body.get("expiresOn")) if "expiresOn" in body else deal["expiresAt"]
            except ValueError as exc:
                conn.close()
                return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            if not zip_code or not re.fullmatch(r"\d{5}", zip_code):
                conn.close()
                return json_response(self, {"error": "Zip code must be 5 digits"}, HTTPStatus.BAD_REQUEST)
            if not address:
                conn.close()
                return json_response(self, {"error": "Street address is required"}, HTTPStatus.BAD_REQUEST)
            if not deal_description:
                conn.close()
                return json_response(self, {"error": "Deal description is required"}, HTTPStatus.BAD_REQUEST)
            updated = update_supabase_company_deal(deal_id, company_name, zip_code, address, deal_description, status, ends_at)
            updated_payload = safe_supabase_company_deal_payload(auth_user["id"], updated)
            conn.close()
            return json_response(self, {"dealId": deal_id, "deal": updated_payload, "message": "Company deal updated."})
        company_name = normalize_company_name(body.get("companyName") or owner["company_name"])
        zip_code = normalize_zip_code(body.get("zipCode") or deal["zip_code"])
        address = str(body.get("address") or deal["address"] or "").strip()
        deal_description = str(body.get("dealDescription") or deal["description"] or "").strip()
        status = normalize_company_deal_status(body.get("status") or deal["status"])
        try:
            ends_at = normalize_ends_on(body.get("expiresOn")) if "expiresOn" in body else deal["ends_at"]
        except ValueError as exc:
            conn.close()
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if not zip_code or not re.fullmatch(r"\d{5}", zip_code):
            conn.close()
            return json_response(self, {"error": "Zip code must be 5 digits"}, HTTPStatus.BAD_REQUEST)
        if not address:
            conn.close()
            return json_response(self, {"error": "Street address is required"}, HTTPStatus.BAD_REQUEST)
        if not deal_description:
            conn.close()
            return json_response(self, {"error": "Deal description is required"}, HTTPStatus.BAD_REQUEST)
        conn.execute(
            """
            UPDATE deals
            SET title = ?, description = ?, zip_code = ?, address = ?, source_store = ?, status = ?, ends_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                company_name,
                deal_description,
                zip_code,
                address,
                company_name,
                status,
                ends_at,
                now_iso(),
                deal_id,
            ),
        )
        archive_duplicate_company_deals(conn, auth_user["id"])
        sync_company_deal_statuses(conn)
        conn.commit()
        updated_row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        conn.close()
        return json_response(self, {"dealId": deal_id, "deal": deal_row_to_dict(updated_row) if updated_row else None, "message": "Company deal updated."})

    def handle_delete_company_deal(self, deal_id, body):
        conn = get_db()
        cleanup_auth_artifacts(conn)
        auth_user, _ = get_authenticated_user(self, conn)
        if auth_user["account_type"] != "company":
            conn.close()
            return json_response(self, {"error": "Company account required"}, HTTPStatus.FORBIDDEN)
        if supabase_is_configured():
            deal = next((item for item in supabase_company_deals_for_user(auth_user["id"]) if item["id"] == deal_id), None)
            if not deal or deal["createdByUserId"] != auth_user["id"]:
                conn.close()
                return json_response(self, {"error": "Company deal not found"}, HTTPStatus.NOT_FOUND)
            archive_supabase_company_deal(deal_id)
            conn.close()
            return json_response(self, {"dealId": deal_id, "message": "Company deal removed."})
        deal = conn.execute("SELECT * FROM deals WHERE id = ? AND deal_type = 'company'", (deal_id,)).fetchone()
        if not deal or deal["created_by_user_id"] != auth_user["id"]:
            conn.close()
            return json_response(self, {"error": "Company deal not found"}, HTTPStatus.NOT_FOUND)
        conn.execute("UPDATE deals SET status = 'archived', updated_at = ? WHERE id = ?", (now_iso(), deal_id))
        conn.commit()
        conn.close()
        return json_response(self, {"dealId": deal_id, "message": "Company deal removed."})


def main():
    init_db()
    ensure_mock_pizza_deals()
    stop_event = threading.Event()
    scheduler_thread = None
    if matching_scheduler_is_enabled():
        interval_seconds = matching_scheduler_interval_seconds()
        update_scheduler_state(enabled=True, intervalSeconds=interval_seconds)

        def scheduler_loop():
            while not stop_event.wait(interval_seconds):
                try:
                    run_matching_job("automatic")
                except Exception:
                    continue

        scheduler_thread = threading.Thread(target=scheduler_loop, name="matching-scheduler", daemon=True)
        scheduler_thread.start()
    else:
        update_scheduler_state(enabled=False, intervalSeconds=0)
    host = app_host()
    port = app_port()
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Phase 1 prototype running at http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        if scheduler_thread:
            scheduler_thread.join(timeout=2)


if __name__ == "__main__":
    main()
