# Book Management System

A beginner-friendly multipage library app using Flask, SQLAlchemy, SQLite, Bootstrap, HTML, CSS, and JavaScript.

## Features

- Dashboard with book, author, PDF, and credit totals
- Browse and search the collection by title or author
- Add and edit books with credit costs (no monetary prices)
- Delete a book
- Per-user credit balances, admin assignments, and claim history
- Student signup with registration number, name, email, course, year, and specialization
- Pending admin approval before student login
- Admin dashboard for reviewing, editing, approving, and rejecting signup requests
- Optional email notices for new requests and approved access
- Admin dashboard for assigning credits
- Admin PDF uploads, grouped by subject and limited to 16 MB
- Subject folders with curated third-year textbook and course links
- In-page PDF reader with page navigation and zoom
- Homepage reading picks link only to verified Project Gutenberg public-domain editions
- Input validation and useful error messages
- SQLAlchemy ORM with SQLite persistence
- Responsive Bootstrap layout, subtle transitions, and reduced-motion support
- REST API endpoints returning JSON

## Project structure

```text
Book Management System/
├── main.py
├── db.py                 # SQLAlchemy model and data access
├── books.db             # Created automatically on first run
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── books.html
│   ├── book_form.html
│   ├── credits.html
│   ├── login.html
│   ├── change_password.html
│   ├── admin.html
│   ├── admin_user_form.html
│   ├── signup.html
│   └── pdf_reader.html
└── static/
   ├── style.css
   ├── resources.css
   ├── theme.css
   ├── auth.css
   ├── reader.css
   ├── signup.js
   ├── pdf_reader.js
   └── script.js
```

## Run on Windows

1. Open this folder in VS Code.
2. Open the terminal in this folder.
3. (Recommended) Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

5. (Recommended) Create a private `.env` from `.env.example` and set a stable `SHELFWISE_SECRET_KEY`. The local development fallback is stable across restarts but must not be used for a network deployment.

6. Create the initial admin account. The password prompt is hidden:

   ```powershell
   python -m flask --app main create-admin
   ```

7. Start the application:

   ```powershell
   python main.py
   ```

8. Open <http://127.0.0.1:5000> in your browser and sign in with the admin credentials.

`.env` is ignored by Git. Production startup refuses to run without `SHELFWISE_SECRET_KEY`; set `SHELFWISE_ENV=production` and `SHELFWISE_COOKIE_SECURE=1` when serving over HTTPS. The `books.db` file is created automatically; the original three sample book rows remain in the collection but are no longer shown on the homepage.

## Pages

- `/` — collection overview
- `/books` — searchable catalog
- `/books/new` — add a title
- `/books/<id>/edit` — update a title
- `/resources` — browse PDF folders by subject
- `/resources/<subject>` — open the PDFs in a subject folder
- `/admin/resources/upload` — upload a PDF into a subject folder (admin-only POST)
- `/reader/<subject>/<id>` — read a PDF inside the app
- `/credits` — review the signed-in user's credit balance and activity
- `/signup` — request student access
- `/admin` — review requests, edit profiles, approve/reject users, and assign credits (admin only)
- `/login` — sign in with a college registration number

Study PDFs are stored in the project's `documents/` directory, with subject folders and document metadata recorded in the SQLite database. The source semester folder can be re-imported with `db.import_pdf_library(source_root, destination_root)`; matching file paths update existing records instead of creating duplicates.

Admins can upload PDFs from `/resources`. Uploads are limited to 16 MB, checked for a `.pdf` extension and PDF signature, sanitized with `secure_filename`, stored under `documents/<subject-slug>/`, and indexed in `study_documents` so the in-page reader can open them. Existing local PDFs remain in place.

Students choose their own password during signup. Passwords must be at least 12 characters and are stored as hashes. New registrations remain pending and cannot sign in until approved. Admins can update profile details, approve or reject requests, and assign credits. Course options are BCA, BBA, BCom, BSc, BA, BTech, MCA, MBA, and Other; specializations adapt to the selected course.

Email is optional and is sent only when SMTP settings are configured. Set these environment variables in the server's shell; never commit the SMTP password:

```powershell
$env:SHELFWISE_ADMIN_EMAIL = "admin@example.edu"
$env:SHELFWISE_SMTP_HOST = "smtp.example.edu"
$env:SHELFWISE_SMTP_PORT = "587"
$env:SHELFWISE_SMTP_USERNAME = "sender@example.edu"
$env:SHELFWISE_SMTP_PASSWORD = "use-an-app-password"
$env:SHELFWISE_SMTP_FROM = "sender@example.edu"
```

New signup notifications go to `SHELFWISE_ADMIN_EMAIL`. Approval emails go to the student's signup email. Without SMTP configuration, requests still appear in the admin queue and the UI reports that email was not sent.

Each student has an independent wallet. Only admins can assign credits; admins can claim catalog books without a deduction. Credit assignment is a local library action, not a payment system. Existing monetary values remain stored in the legacy database column but are not shown in the app or returned by the book API. Forms use CSRF tokens, passwords are hashed, and student/admin routes require a signed-in session. The homepage only links to verified Project Gutenberg records; links open only after the user chooses them. The PDF reader loads PDF.js from a CDN, so the first reader load needs an internet connection.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/books` | List all books |
| GET | `/api/books/1` | Get a book by ID |
| POST | `/api/books` | Create a book (admin only) |
| PUT | `/api/books/1` | Replace a book's title, author, and credit cost (admin only) |
| DELETE | `/api/books/1` | Delete a book (admin only) |

POST and PUT JSON body example. API writes require an authenticated admin session and the session CSRF token in `X-CSRF-Token`:

```json
{
  "title": "Python Basics",
   "author": "Amit Sharma",
   "credits": 10
}
```

## Important notes

- Keep the terminal running while using the application.
- Stop the server with `Ctrl+C`.
- SQLite records persist after restarting Flask.
- The Flask debug server is for local learning only. Use a production WSGI server and HTTPS before deploying to a network.
- The included `Procfile` runs `gunicorn wsgi:app`; Gunicorn is intended for Linux-based deployments, not Windows development.
