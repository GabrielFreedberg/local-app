# v1

Local first iteration of a grocery and local business deal alert app. It runs as a small Python HTTP server with a static HTML/CSS/JS frontend and SQLite persistence.

The app is intentionally self-contained: grocery data, SMS delivery, and email delivery can all run in mock mode so the complete workflow is testable without external services.

## Current Features

- Create user accounts with phone number, email, password, and zip code
- Create company accounts with company name, phone number, email, password, and zip code
- Log in with email and password
- Show role-specific screens after login
- Land user accounts on a scrollable deal feed
- Let users search all grocery and company-submitted deals
- Let users save alert interests such as `rice`, `beer`, `chicken`, or `avocados`
- Let users remove saved alert interests from the favorites list
- Let companies submit local deals
- Notify users only when a deal matches both their zip code and one of their alert interests
- Ingest mock grocery deals for local testing
- Record SMS and email notifications in SQLite and `notification_log.jsonl`
- Send real email through SMTP when configured

## Mocked Services

- Grocery store and deal data
- SMS confirmation and SMS delivery
- Email delivery when SMTP settings are missing
- Cloud infrastructure

## Project Structure

```text
app.py
static/
  index.html
  app.js
  styles.css
prototype.db
notification_log.jsonl
README.md
```

## Run Locally

```bash
python3 app.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Suggested Walkthrough

1. Open the app.
2. Create a user account in zip code `80205`.
3. Add alert interests such as `beer`, `avocados`, or `chicken`.
4. Click `Ingest Mock Deals`.
5. Search for a deal keyword.
6. Click `Match + Notify`.
7. Review notifications in the dashboard and `notification_log.jsonl`.
8. Create a company account.
9. Submit a company deal that matches a user's zip code and alert interests.
10. Confirm the matching user receives a mocked email notification.

## Real Email Setup

Set these environment variables before starting the app if you want SMTP delivery:

```bash
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-username"
export SMTP_PASSWORD="your-password"
export EMAIL_FROM="you@example.com"
export SMTP_USE_TLS="true"
```

If these values are missing, email notifications are logged as mocked sends.

## Data Files

- `prototype.db` stores users, deals, company deals, and notifications.
- `notification_log.jsonl` stores a readable append-only notification log.

Delete these files only if you want to reset local app data.

## Next Steps

- Replace mock grocery data with live grocery API integration
- Replace mocked SMS with a real SMS provider
- Move password storage to a secure password hashing flow
- Add session handling instead of local-only user persistence
- Move from local SQLite to production storage
- Add scheduled ingestion and matching jobs
