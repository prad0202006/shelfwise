# Shelfwise Project Review Capsule

## Purpose

Review the current Flask book-management and study-resource app for correctness, security, and maintainability. This capsule is a source-code handoff; it contains no credentials, account rows, or PDF contents.

## Project Structure

```text
book_management_system/
├── main.py                 # Flask routes, session/CSRF checks, auth, email
├── db.py                   # SQLAlchemy models, SQLite setup, data operations
├── wsgi.py                 # WSGI entry point with dotenv loading
├── Procfile                # Gunicorn production command
├── .gitignore              # Excludes local DB, secrets, venv, and PDFs
├── .env.example            # Configuration template; no real secrets
├── requirements.txt        # Flask and SQLAlchemy
├── README.md               # Setup and app documentation
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── books.html
│   ├── book_form.html
│   ├── credits.html
│   ├── login.html
│   ├── signup.html
│   ├── change_password.html
│   ├── admin.html
│   ├── admin_user_form.html
│   ├── resources.html
│   ├── resource_folder.html
│   └── pdf_reader.html
├── static/
│   ├── style.css
│   ├── theme.css
│   ├── auth.css
│   ├── resources.css
│   ├── reader.css
│   ├── script.js
│   ├── signup.js
│   └── pdf_reader.js
└── documents/              # Local PDF copies grouped by subject
```

Runtime/local data also exists: `.venv/`, `books.db`, `documents/`, and `__pycache__/`. Do not distribute `.venv/` or `books.db`; the database contains user account and credit data. Share PDFs only if you have permission to redistribute them.

## Stack And Runtime

- Flask 3.x, SQLAlchemy 2.x, SQLite, Jinja templates, Bootstrap 5.
- Run from this directory on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

- Create an initial admin using hidden interactive prompts:

```powershell
.\.venv\Scripts\python.exe -m flask --app main create-admin
```

- Local URL: `http://127.0.0.1:5000`.
- No dedicated automated test suite was present when this capsule was created. Ad hoc Flask test-client checks have been used during development.

## Main Flows

- `/login`: registration number and password.
- `/signup`: student profile, email, course/year/specialization, and chosen password. New accounts are inactive and pending approval.
- `/admin`: pending queue and full user list. Admins can edit profiles, approve/reject pending accounts, and assign credits.
- Approval activates the account and attempts an email to the student. New signup email is attempted to `SHELFWISE_ADMIN_EMAIL`.
- `/books`: browse/claim titles. Students spend their own credits; admin claims have no deduction.
- `/resources` and `/resources/<slug>`: subject folders, local PDFs, and curated references.
- `/admin/resources/upload`: admin-only multipart upload, 16 MB maximum, PDF signature and extension check, safe filename, storage under `documents/<subject-slug>/`, and `StudyDocument` indexing for the existing reader.
- `/reader/<slug>/<id>`: in-page PDF.js canvas reader.
- `/`: dashboard with statistics and curated public-domain Project Gutenberg picks. The three starter book rows remain in the catalog but are not listed on the homepage.
- `/api/books`: JSON CRUD; writes require an authenticated admin session and CSRF header.

## Data Model

- `Book`, `BookCredit`: catalog entries and credit costs.
- `User`: registration number, password hash, role, profile, active flag, approval status.
- `UserCreditWallet`, `UserCreditTransaction`: per-user balances and ledger.
- `UserBookClaim`: per-user claim history and credits spent.
- `SubjectFolder`, `StudyDocument`, `StudyLink`: imported PDFs and vetted study links.
- `FeaturedRead`: fixed, curated homepage reads.

`init_db()` creates missing tables and includes an additive SQLite migration for newer user profile/approval columns. Migration reflects columns within a connection and verifies them after `ALTER TABLE`; `create_all()` itself does not alter existing tables.

## Configuration

Optional email uses these environment variables; never commit the SMTP password:

- `SHELFWISE_ADMIN_EMAIL`
- `SHELFWISE_SMTP_HOST`
- `SHELFWISE_SMTP_PORT` (defaults to 587)
- `SHELFWISE_SMTP_USERNAME`
- `SHELFWISE_SMTP_PASSWORD`
- `SHELFWISE_SMTP_FROM`

The local development fallback session key is deterministic so local restarts do not invalidate sessions, but it is public and development-only. Set a stable private `SHELFWISE_SECRET_KEY`; production (`SHELFWISE_ENV=production`) refuses to start without it. `SHELFWISE_COOKIE_SECURE=1` enables the Secure cookie flag for HTTPS deployments. SMTP failures are reported in the admin UI; the pending queue works without SMTP.

## Review Checklist

- Verify signup validation, duplicate registration/email handling, pending access denial, approval/rejection, and disabled-user behavior.
- Verify profile editing, unique email handling, and authorization boundaries between student and admin roles.
- Review CSRF coverage for browser forms and JSON API writes; API clients must preserve the session cookie and send `X-CSRF-Token`.
- Review password/session handling, admin bootstrap, and deployment configuration (stable secret, HTTPS, secure cookies, rate limiting).
- Review SQLite schema upgrades against an existing `books.db`; ensure local accounts and PDF metadata are preserved.
- Review credit assignment/claim transactions, duplicate claims, and book deletion with claims.
- Verify SMTP success/failure paths without sending to real recipients during tests.
- Verify external links remain fixed/curated and do not accept arbitrary user-provided URLs.
- Check the in-page PDF reader with local files, mobile layout, and unavailable CDN behavior.
- Check upload size rejection, invalid PDF signatures, duplicate filenames, traversal-style filenames, and database failure cleanup.
- Verify `.env` is ignored and not included in shared artifacts; test WSGI/Procfile on a Linux-like deployment target.

## Reviewer Notes

- Do not print, copy, or request real passwords, SMTP credentials, session cookies, or database rows.
- Do not click outbound resource links during review; inspect their fixed URLs and target attributes in source.
- Report findings with file paths and reproducible steps. Treat `books.db` and `documents/` as user data, not disposable test fixtures.
