import hmac
import os
import re
import secrets
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import AuditLog, Book, FeaturedRead, SessionLocal, StudyDocument, SubjectFolder, add_audit_log, add_user_credits, assigned_subject_folder_ids, check_database_connection, claim_book_for_user, claimed_book_ids, create_book, create_user, delete_book, delete_user_account, email_in_use, featured_reads, get_all_books, get_book, get_user_by_id, get_user_by_registration, grant_subject_access, init_db, list_users, pending_user_count, recent_audit_logs, set_user_approval, update_book, update_student_profile, update_user_access_role, update_user_password, user_wallet

load_dotenv()

app = Flask(__name__)
runtime_environment = os.environ.get("SHELFWISE_ENV", "development").strip().lower()
secret_key = os.environ.get("SHELFWISE_SECRET_KEY", "").strip()
if not secret_key:
    if runtime_environment in {"production", "prod"}:
        raise RuntimeError("SHELFWISE_SECRET_KEY is required in production.")
    secret_key = "shelfwise-local-development-only-not-for-production"
app.config["SECRET_KEY"] = secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SHELFWISE_COOKIE_SECURE") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["DOCUMENTS_DIR"] = Path(app.root_path) / "documents"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
init_db()


def _bootstrap_admin():
    registration_number = os.environ.get("SHELFWISE_ADMIN_REGISTRATION_NUMBER", "").strip().upper()
    password = os.environ.get("SHELFWISE_ADMIN_PASSWORD", "")
    if not registration_number or not password:
        return
    if get_user_by_registration(registration_number) is None:
        create_user(
            registration_number,
            generate_password_hash(password),
            role="main_admin",
            must_change_password=False,
        )


_bootstrap_admin()

ADMIN_ENDPOINTS = {
    "admin_panel",
    "admin_approve_user",
    "admin_reject_user",
    "admin_delete_resource",
    "admin_delete_user",
    "upload_document",
    "new_book_page",
    "edit_book_page",
    "delete_book_page",
    "api_create_book",
    "api_update_book",
    "api_delete_book",
}
MAIN_ADMIN_ENDPOINTS = {
    "admin_user_edit",
    "admin_assign_credits",
    "admin_change_user_role",
    "admin_set_subject_access",
    "admin_audit_log",
}


def _csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


@app.before_request
def require_session_and_csrf():
    if request.method == "POST":
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="Invalid or missing request token.")

    if request.endpoint in {"login", "signup", "static"}:
        return None

    user_id = session.get("user_id")
    current_user = get_user_by_id(user_id) if user_id else None
    if current_user is None or not current_user["is_active"]:
        session.clear()
        return redirect(url_for("login"))

    g.current_user = current_user
    if current_user["must_change_password"] and request.endpoint not in {"change_password", "logout"}:
        return redirect(url_for("change_password"))
    if request.endpoint in ADMIN_ENDPOINTS and current_user["role"] not in {"main_admin", "sub_admin"}:
        abort(403)
    if request.endpoint in MAIN_ADMIN_ENDPOINTS and current_user["role"] != "main_admin":
        abort(403)
    return None


@app.context_processor
def template_context():
    current_user = getattr(g, "current_user", None)
    return {
        "current_user": current_user,
        "csrf_token": _csrf_token,
        "database_connected": check_database_connection(),
        "pending_signup_count": pending_user_count() if current_user and current_user["role"] in {"main_admin", "sub_admin"} else 0,
    }


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(error):
    if request.path == url_for("upload_document"):
        flash("PDF uploads are limited to 16 MB.", "danger")
        return redirect(url_for("resources_page"))
    return jsonify({"error": "Request body exceeds the 16 MB limit."}), 413


@app.cli.command("create-admin")
def create_admin_command():
    """Create the initial admin using hidden interactive password prompts."""
    from getpass import getpass

    registration_number = click.prompt("Admin registration number").strip().upper()
    password = getpass("Admin password (12+ characters): ")
    confirmation = getpass("Confirm admin password: ")
    if len(password) < 12 or password != confirmation:
        raise click.ClickException("Passwords must match and be at least 12 characters.")
    if get_user_by_registration(registration_number):
        raise click.ClickException("That registration number is already in use.")
    create_user(registration_number, generate_password_hash(password), role="main_admin", must_change_password=False)
    click.echo("Admin account created.")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))
    if request.method == "POST":
        registration_number = request.form.get("registration_number", "").strip().upper()
        password = request.form.get("password", "")
        user = get_user_by_registration(registration_number)
        if user and check_password_hash(user["password_hash"], password):
            if user["approval_status"] == "pending":
                flash("Your account is waiting for admin approval.", "warning")
                return render_template("login.html")
            elif not user["is_active"]:
                flash("Your account is not active. Contact the administrator.", "danger")
                return render_template("login.html")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session.permanent = True
                if user["must_change_password"]:
                    return redirect(url_for("change_password"))
                return redirect(url_for("home"))
        flash("Registration number or password is incorrect.", "danger")
    return render_template("login.html")


COURSE_SPECIALIZATIONS = {
    "BCA": ["Web Development", "Data Science", "AI and Machine Learning", "Cybersecurity", "Cloud Computing", "General"],
    "BBA": ["Marketing", "Finance", "Human Resources", "Business Analytics", "Entrepreneurship", "General"],
    "BCom": ["Accounting and Finance", "Taxation", "Banking", "Business Analytics", "General"],
    "BSc": ["Computer Science", "Mathematics", "Physics", "Biotechnology", "General"],
    "BA": ["English", "Economics", "Psychology", "Political Science", "General"],
    "BTech": ["Computer Science", "AI and Machine Learning", "Data Science", "Cybersecurity", "Electronics", "General"],
    "MCA": ["Web Development", "Data Science", "AI and Machine Learning", "Cybersecurity", "General"],
    "MBA": ["Marketing", "Finance", "Human Resources", "Business Analytics", "Operations", "General"],
    "Other": ["General"],
}


def _validated_student_profile(form):
    registration_number = form.get("registration_number", "").strip().upper()
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip().lower()
    course = form.get("course", "").strip()
    specialization = form.get("specialization", "").strip()
    try:
        year_of_study = int(form.get("year_of_study", ""))
    except ValueError:
        year_of_study = 0
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9/-]{2,29}", registration_number):
        return None, "Enter a valid college registration number."
    if len(full_name) < 2 or len(full_name) > 120:
        return None, "Enter your full name."
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        return None, "Enter a valid email address."
    if course not in COURSE_SPECIALIZATIONS:
        return None, "Choose a course from the list."
    if year_of_study not in range(1, 7):
        return None, "Choose your current year of study."
    if specialization not in COURSE_SPECIALIZATIONS[course]:
        return None, "Choose a specialization for your course."
    return {
        "registration_number": registration_number,
        "full_name": full_name,
        "email": email,
        "course": course,
        "year_of_study": year_of_study,
        "specialization": specialization,
    }, None


def _send_system_email(to_address, subject, body):
    host = os.environ.get("SHELFWISE_SMTP_HOST", "").strip()
    username = os.environ.get("SHELFWISE_SMTP_USERNAME", "").strip()
    password = os.environ.get("SHELFWISE_SMTP_PASSWORD", "")
    sender = os.environ.get("SHELFWISE_SMTP_FROM", username).strip()
    try:
        port = int(os.environ.get("SHELFWISE_SMTP_PORT", "587"))
    except ValueError:
        return False
    if not all([host, username, password, sender, to_address]):
        return False
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        app.logger.warning("Unable to send Shelfwise notification email.")
        return False


@app.route("/signup", methods=["GET", "POST"])
def signup():
    profile = None
    if request.method == "POST":
        profile, error = _validated_student_profile(request.form)
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "")
        if error:
            flash(error, "danger")
        elif get_user_by_registration(profile["registration_number"]):
            flash("That registration number already has an account.", "danger")
        elif email_in_use(profile["email"]):
            flash("That email address is already associated with an account.", "danger")
        elif len(password) < 12:
            flash("Use at least 12 characters for your password.", "danger")
        elif password != confirmation:
            flash("The passwords do not match.", "danger")
        else:
            user = create_user(
                profile["registration_number"],
                generate_password_hash(password),
                role="user",
                must_change_password=False,
                full_name=profile["full_name"],
                email=profile["email"],
                course=profile["course"],
                year_of_study=profile["year_of_study"],
                specialization=profile["specialization"],
                approval_status="pending",
            )
            admin_email = os.environ.get("SHELFWISE_ADMIN_EMAIL", "").strip()
            _send_system_email(
                admin_email,
                "Shelfwise signup awaiting approval",
                f"A new student account is awaiting approval.\n\n"
                f"Name: {user['full_name']}\nRegistration: {user['registration_number']}\n"
                f"Course: {user['course']}\nYear: {user['year_of_study']}\n"
                f"Specialization: {user['specialization']}\nSign in to Shelfwise to review the request.",
            )
            flash("Signup submitted. You can sign in after an admin approves your account.", "success")
            return redirect(url_for("login"))
    return render_template(
        "signup.html",
        courses=COURSE_SPECIALIZATIONS,
        form_data=request.form if request.method == "POST" else {},
    )


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "")
        if len(password) < 12:
            flash("Use at least 12 characters for your new password.", "danger")
        elif password != confirmation:
            flash("The passwords do not match.", "danger")
        elif not update_user_password(g.current_user["id"], generate_password_hash(password)):
            abort(404)
        else:
            flash("Password updated.", "success")
            return redirect(url_for("home"))
    return render_template("change_password.html")


@app.route("/admin")
def admin_panel():
    all_users = [
        {**user, "balance": user_wallet(user["id"])[0]}
        for user in list_users()
    ]
    is_main_admin = g.current_user["role"] == "main_admin"
    can_delete_users = is_main_admin or g.current_user["can_delete_users"]
    if is_main_admin:
        users = all_users
    elif can_delete_users:
        users = [user for user in all_users if user["role"] == "student"]
    else:
        users = [
            user for user in all_users
            if user["role"] == "student" and user["approval_status"] == "pending"
        ]
    with SessionLocal() as session:
        subject_folders = session.scalars(select(SubjectFolder).order_by(SubjectFolder.name)).all()
    return render_template(
        "admin.html",
        users=users,
        pending_count=pending_user_count(),
        can_manage_roles=is_main_admin,
        can_delete_users=can_delete_users,
        subject_folders=subject_folders if is_main_admin else [],
        audit_logs=recent_audit_logs(50) if is_main_admin else [],
    )


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
def admin_user_edit(user_id):
    user = get_user_by_id(user_id)
    if user is None or user["role"] not in {"student", "sub_admin"}:
        abort(404)
    form_data = user
    if request.method == "POST":
        form_data = request.form
        profile, error = _validated_student_profile(request.form)
        if error:
            flash(error, "danger")
        elif email_in_use(profile["email"], except_user_id=user_id):
            flash("That email address is already associated with another account.", "danger")
        elif update_student_profile(
            user_id,
            profile["full_name"],
            profile["email"],
            profile["course"],
            profile["year_of_study"],
            profile["specialization"],
        ):
            flash("Student profile updated.", "success")
            return redirect(url_for("admin_panel"))
    return render_template(
        "admin_user_form.html",
        user=user,
        form_data=form_data,
        courses=COURSE_SPECIALIZATIONS,
    )


@app.post("/admin/users/<int:user_id>/approve")
def admin_approve_user(user_id):
    user = get_user_by_id(user_id)
    if user is None or user["role"] != "student" or user["approval_status"] != "pending":
        flash("That account is not awaiting approval.", "warning")
    elif set_user_approval(user_id, "approved"):
        sent = _send_system_email(
            user["email"],
            "Your Shelfwise account is approved",
            f"Hello {user['full_name']},\n\nYour account has been approved. "
            "You can now sign in with your college registration number and the password you chose during signup.",
        )
        flash(
            "Account approved and email sent." if sent else "Account approved. Email was not sent; check the SMTP settings.",
            "success" if sent else "warning",
        )
        add_audit_log(g.current_user["id"], g.current_user["registration_number"], "user_approved", "user", user_id, user["registration_number"])
    return redirect(url_for("admin_panel"))


@app.post("/admin/users/<int:user_id>/reject")
def admin_reject_user(user_id):
    user = get_user_by_id(user_id)
    if user is None or user["role"] != "student" or user["approval_status"] != "pending":
        flash("That account is not awaiting approval.", "warning")
    elif set_user_approval(user_id, "rejected"):
        flash("Signup request rejected.", "success")
        add_audit_log(g.current_user["id"], g.current_user["registration_number"], "user_rejected", "user", user_id, user["registration_number"])
    else:
        flash("That student account could not be found.", "danger")
    return redirect(url_for("admin_panel"))


@app.post("/admin/users/<int:user_id>/credits")
def admin_assign_credits(user_id):
    user = get_user_by_id(user_id)
    try:
        amount = int(request.form.get("amount", ""))
    except ValueError:
        amount = 0
    if user is None or user["role"] != "student" or user["approval_status"] != "approved":
        flash("Approved student account not found.", "danger")
    elif amount < 1 or amount > 100000:
        flash("Assign between 1 and 100,000 credits.", "danger")
    else:
        add_user_credits(
            user_id,
            amount,
            description=f"Assigned by admin {g.current_user['registration_number']}",
            assigned_by_id=g.current_user["id"],
        )
        add_audit_log(g.current_user["id"], g.current_user["registration_number"], "credits_assigned", "user", user_id, f"{amount} credits")
        flash(f"{amount} credits assigned to {user['registration_number']}.", "success")
    return redirect(url_for("admin_panel"))


@app.post("/admin/users/<int:user_id>/role")
def admin_change_user_role(user_id):
    user = get_user_by_id(user_id)
    new_role = request.form.get("role", "")
    can_delete_resources = request.form.get("can_delete_resources") == "on"
    can_delete_users = request.form.get("can_delete_users") == "on"
    if user is None or user["role"] == "main_admin":
        flash("Main admin roles cannot be changed here.", "danger")
    elif user["approval_status"] != "approved":
        flash("Only approved accounts can be promoted or demoted.", "warning")
    elif new_role not in {"student", "sub_admin"}:
        flash("Choose student or sub-admin.", "danger")
    elif update_user_access_role(user_id, new_role, can_delete_resources, can_delete_users):
        add_audit_log(
            g.current_user["id"],
            g.current_user["registration_number"],
            "role_changed",
            "user",
            user_id,
            f"{user['role']} -> {new_role}; can_delete_resources={can_delete_resources}; can_delete_users={can_delete_users}",
        )
        flash(f"{user['registration_number']} is now {new_role}.", "success")
    return redirect(url_for("admin_panel"))


@app.post("/admin/subadmins/<int:user_id>/subjects")
def admin_set_subject_access(user_id):
    try:
        folder_ids = {int(folder_id) for folder_id in request.form.getlist("folder_ids")}
    except ValueError:
        abort(400)
    user = get_user_by_id(user_id)
    if user is None or user["role"] != "sub_admin":
        flash("Sub-admin account not found.", "danger")
    elif grant_subject_access(user_id, folder_ids, g.current_user["id"]):
        add_audit_log(
            g.current_user["id"],
            g.current_user["registration_number"],
            "subject_access_changed",
            "user",
            user_id,
            f"Assigned {len(folder_ids)} subject folder(s)",
        )
        flash("Subject-folder access updated.", "success")
    else:
        flash("One or more selected folders are invalid.", "danger")
    return redirect(url_for("admin_panel"))


@app.post("/admin/users/<int:user_id>/delete")
def admin_delete_user(user_id):
    user = get_user_by_id(user_id)
    if g.current_user["role"] == "sub_admin" and not g.current_user["can_delete_users"]:
        abort(403)
    if user is None or user_id == g.current_user["id"] or user["role"] == "main_admin":
        flash("That account cannot be deleted here.", "danger")
    elif delete_user_account(user_id, g.current_user["id"], g.current_user["registration_number"]):
        flash(f"{user['registration_number']} was deleted.", "success")
    else:
        flash("The last main-admin account cannot be deleted.", "danger")
    return redirect(url_for("admin_panel"))


@app.route("/admin/audit")
def admin_audit_log():
    return render_template("audit_log.html", audit_logs=recent_audit_logs(200))


@app.route("/")
def home():
    with SessionLocal() as session:
        total_books = session.scalar(select(func.count(Book.id))) or 0
        author_count = session.scalar(select(func.count(func.distinct(Book.author)))) or 0
        document_count = session.scalar(select(func.count(StudyDocument.id))) or 0
    is_admin = g.current_user["role"] in {"main_admin", "sub_admin"}
    balance = "Unlimited" if is_admin else user_wallet(g.current_user["id"])[0]
    return render_template(
        "dashboard.html",
        total_books=total_books,
        author_count=author_count,
        document_count=document_count,
        credit_balance=balance,
        featured_reads=featured_reads(),
    )


@app.route("/books")
def books_page():
    query = request.args.get("q", "").strip()
    statement = select(Book).options(selectinload(Book.credit)).order_by(Book.id.desc())
    if query:
        pattern = f"%{query}%"
        statement = statement.where(or_(Book.title.ilike(pattern), Book.author.ilike(pattern)))
    with SessionLocal() as session:
        books = session.scalars(statement).all()
        total_books = session.scalar(select(func.count(Book.id))) or 0
    return render_template(
        "books.html",
        books=books,
        query=query,
        total_books=total_books,
        claimed_ids=claimed_book_ids(g.current_user["id"]),
        is_admin=g.current_user["role"] in {"main_admin", "sub_admin"},
    )


@app.route("/resources")
def resources_page():
    with SessionLocal() as session:
        folders = session.scalars(
            select(SubjectFolder)
            .options(selectinload(SubjectFolder.documents), selectinload(SubjectFolder.links))
            .order_by(SubjectFolder.name)
        ).all()
    upload_folders = folders
    if g.current_user["role"] == "sub_admin":
        allowed_ids = assigned_subject_folder_ids(g.current_user["id"])
        upload_folders = [folder for folder in folders if folder.id in allowed_ids]
    elif g.current_user["role"] == "student":
        upload_folders = []
    return render_template("resources.html", folders=folders, upload_folders=upload_folders)


@app.post("/admin/resources/upload")
def upload_document():
    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        flash("Choose a PDF file to upload.", "danger")
        return redirect(url_for("resources_page"))

    filename = secure_filename(uploaded_file.filename)
    if not filename or Path(filename).suffix.lower() != ".pdf":
        flash("Only PDF files are accepted.", "danger")
        return redirect(url_for("resources_page"))

    if b"%PDF-" not in uploaded_file.stream.read(1024):
        flash("The selected file does not have a valid PDF signature.", "danger")
        return redirect(url_for("resources_page"))
    uploaded_file.stream.seek(0)

    try:
        folder_id = int(request.form.get("folder_id", ""))
    except ValueError:
        folder_id = 0
    with SessionLocal() as session:
        folder = session.get(SubjectFolder, folder_id)
        if folder is None:
            flash("Choose a valid subject folder.", "danger")
            return redirect(url_for("resources_page"))
        folder_name = folder.name
        folder_slug = folder.slug
    if g.current_user["role"] == "sub_admin" and folder_id not in assigned_subject_folder_ids(g.current_user["id"]):
        abort(403)

    documents_root = Path(app.config["DOCUMENTS_DIR"]).resolve()
    subject_directory = (documents_root / folder_slug).resolve()
    try:
        subject_directory.relative_to(documents_root)
    except ValueError:
        abort(400)
    subject_directory.mkdir(parents=True, exist_ok=True)
    target_path = subject_directory / filename
    storage_path = f"{folder_slug}/{filename}"
    if target_path.exists():
        flash("A file with that name already exists in this subject folder.", "warning")
        return redirect(url_for("resources_page"))
    with SessionLocal() as session:
        if session.scalar(select(StudyDocument.id).where(StudyDocument.storage_path == storage_path)):
            flash("A document with that storage path is already indexed.", "warning")
            return redirect(url_for("resources_page"))

    saved_file = False
    try:
        uploaded_file.save(target_path)
        saved_file = True
        file_size = target_path.stat().st_size
        if file_size > app.config["MAX_CONTENT_LENGTH"]:
            raise RequestEntityTooLarge()
        title = request.form.get("title", "").strip() or Path(filename).stem.replace("_", " ")
        with SessionLocal.begin() as session:
            session.add(StudyDocument(
                title=title[:250],
                original_filename=filename,
                storage_path=storage_path,
                file_size=file_size,
                folder_id=folder_id,
            ))
            session.add(AuditLog(
                actor_id=g.current_user["id"],
                actor_registration_number=g.current_user["registration_number"],
                action="pdf_uploaded",
                target_type="document",
                details=f"{filename} -> {folder_slug}",
            ))
    except RequestEntityTooLarge:
        if saved_file:
            target_path.unlink(missing_ok=True)
        flash("PDF uploads are limited to 16 MB.", "danger")
        return redirect(url_for("resources_page"))
    except IntegrityError:
        if saved_file:
            target_path.unlink(missing_ok=True)
        flash("That PDF was already added. Rename it before uploading again.", "warning")
        return redirect(url_for("resources_page"))
    except SQLAlchemyError:
        if saved_file:
            target_path.unlink(missing_ok=True)
        app.logger.exception("PDF metadata could not be indexed for subject %s", folder_slug)
        flash("The PDF could not be indexed. No upload was saved; try again.", "danger")
        return redirect(url_for("resources_page"))
    except OSError:
        if saved_file:
            target_path.unlink(missing_ok=True)
        app.logger.exception("PDF upload failed for subject %s", folder_slug)
        flash("The PDF could not be saved. Check the documents folder permissions.", "danger")
        return redirect(url_for("resources_page"))

    flash(f"{filename} uploaded to {folder_name}.", "success")
    return redirect(url_for("resources_page"))


@app.route("/resources/<slug>")
def resource_folder(slug):
    with SessionLocal() as session:
        folder = session.scalar(
            select(SubjectFolder)
            .options(selectinload(SubjectFolder.documents), selectinload(SubjectFolder.links))
            .where(SubjectFolder.slug == slug)
        )
        if folder is None:
            abort(404)
        documents = sorted(folder.documents, key=lambda document: document.title.casefold())
        links = sorted(folder.links, key=lambda link: link.title.casefold())
        folder_name = folder.name
        folder_slug = folder.slug
        folder_id = folder.id
    current_user = g.current_user
    can_delete_documents = current_user["role"] == "main_admin" or (
        current_user["role"] == "sub_admin"
        and current_user["can_delete_resources"]
        and folder_id in assigned_subject_folder_ids(current_user["id"])
    )
    return render_template(
        "resource_folder.html",
        folder_name=folder_name,
        folder_slug=folder_slug,
        documents=documents,
        links=links,
        can_delete_documents=can_delete_documents,
    )


@app.route("/reader/<slug>/<int:document_id>")
def pdf_reader(slug, document_id):
    with SessionLocal() as session:
        document = session.get(StudyDocument, document_id)
        if document is None or document.folder.slug != slug:
            abort(404)
        title = document.title
        folder_name = document.folder.name
    return render_template(
        "pdf_reader.html",
        title=title,
        folder_name=folder_name,
        pdf_url=url_for("open_resource", slug=slug, document_id=document_id),
    )


@app.route("/resources/<slug>/<int:document_id>/open")
def open_resource(slug, document_id):
    with SessionLocal() as session:
        document = session.get(StudyDocument, document_id)
        if document is None or document.folder.slug != slug:
            abort(404)
        storage_path = document.storage_path
        filename = document.original_filename
    return send_from_directory(
        app.config["DOCUMENTS_DIR"],
        storage_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=filename,
    )


@app.post("/admin/resources/<int:document_id>/delete")
def admin_delete_resource(document_id):
    user = g.current_user
    if user["role"] == "sub_admin" and not user["can_delete_resources"]:
        abort(403)

    with SessionLocal() as session:
        document = session.get(StudyDocument, document_id)
        if document is None:
            abort(404)
        storage_path = document.storage_path
        folder_id = document.folder_id
        folder_slug = document.folder.slug
        title = document.title

    if user["role"] == "sub_admin" and folder_id not in assigned_subject_folder_ids(user["id"]):
        abort(403)

    documents_root = Path(app.config["DOCUMENTS_DIR"]).resolve()
    file_path = (documents_root / storage_path).resolve()
    try:
        file_path.relative_to(documents_root)
    except ValueError:
        abort(400)

    quarantine_path = None
    if file_path.exists():
        quarantine_path = file_path.with_name(f".{file_path.name}.{secrets.token_hex(6)}.deleting")
        try:
            os.replace(file_path, quarantine_path)
        except OSError:
            flash("The PDF is currently in use and could not be removed.", "danger")
            return redirect(url_for("resource_folder", slug=folder_slug))

    try:
        with SessionLocal.begin() as session:
            document = session.get(StudyDocument, document_id)
            if document is None:
                raise LookupError("PDF record disappeared during deletion")
            session.delete(document)
            session.add(AuditLog(
                actor_id=user["id"],
                actor_registration_number=user["registration_number"],
                action="resource_deleted",
                target_type="document",
                target_id=document_id,
                details=f"{title} -> {folder_slug}",
            ))
    except Exception:
        if quarantine_path and quarantine_path.exists():
            os.replace(quarantine_path, file_path)
        app.logger.exception("PDF deletion failed for document %s", document_id)
        flash("The PDF could not be removed; the file was restored.", "danger")
        return redirect(url_for("resource_folder", slug=folder_slug))

    if quarantine_path and quarantine_path.exists():
        try:
            quarantine_path.unlink()
        except OSError:
            app.logger.exception("Deleted PDF left a cleanup file: %s", quarantine_path.name)
    flash(f"{title} was removed.", "success")
    return redirect(url_for("resource_folder", slug=folder_slug))


@app.route("/books/new", methods=["GET", "POST"])
def new_book_page():
    if request.method == "POST":
        values = _validated_form_values()
        if values is None:
            return render_template("book_form.html", book=None)
        created = create_book(*values)
        add_audit_log(g.current_user["id"], g.current_user["registration_number"], "book_created", "book", created["id"], created["title"])
        flash("Book added to your collection.", "success")
        return redirect(url_for("books_page"))
    return render_template("book_form.html", book=None)


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def edit_book_page(book_id):
    book = get_book(book_id)
    if book is None:
        flash("That book could not be found.", "danger")
        return redirect(url_for("books_page"))
    if request.method == "POST":
        values = _validated_form_values()
        if values is None:
            return render_template("book_form.html", book=book)
        update_book(book_id, *values)
        add_audit_log(g.current_user["id"], g.current_user["registration_number"], "book_updated", "book", book_id, values[0])
        flash("Book details updated.", "success")
        return redirect(url_for("books_page"))
    return render_template("book_form.html", book=book)


@app.post("/books/<int:book_id>/delete")
def delete_book_page(book_id):
    if delete_book(book_id):
        add_audit_log(g.current_user["id"], g.current_user["registration_number"], "book_deleted", "book", book_id)
        flash("Book removed from your collection.", "success")
    else:
        flash("That book could not be found.", "danger")
    return redirect(url_for("books_page"))


@app.post("/books/<int:book_id>/claim")
def claim_book_page(book_id):
    is_admin = g.current_user["role"] in {"main_admin", "sub_admin"}
    result = claim_book_for_user(book_id, g.current_user["id"], is_admin=is_admin)
    messages = {
        "ok": ("Book claimed with credits.", "success"),
        "missing": ("That book could not be found.", "danger"),
        "claimed": ("You have already claimed that book.", "info"),
        "insufficient": ("Not enough credits. Add credits to your wallet first.", "warning"),
    }
    message, category = messages[result]
    flash(message, category)
    return redirect(url_for("books_page"))


@app.route("/credits")
def credits_page():
    access_role = g.current_user["role"]
    if access_role in {"main_admin", "sub_admin"}:
        return render_template("credits.html", balance="Unlimited", transactions=[], is_admin=True, access_role=access_role)
    balance, transactions = user_wallet(g.current_user["id"])
    return render_template("credits.html", balance=balance, transactions=transactions, is_admin=False, access_role=access_role)


def _validated_form_values():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    try:
        credit_cost = int(request.form.get("credits", ""))
    except ValueError:
        credit_cost = 0
    if not title or not author or credit_cost < 1 or credit_cost > 5000:
        flash("Enter a title, author, and a credit cost between 1 and 5,000.", "danger")
        return None
    return title, author, credit_cost


@app.route("/api/books", methods=["GET"])
def api_get_books():
    return jsonify(get_all_books())


@app.route("/api/books/<int:book_id>", methods=["GET"])
def api_get_book(book_id):
    book = get_book(book_id)
    if book is None:
        return jsonify({"error": "Book not found"}), 404
    return jsonify(book)


@app.route("/api/books", methods=["POST"])
def api_create_book():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Please send a valid JSON object."}), 400

    title = data.get("title")
    author = data.get("author")
    credit_cost = data.get("credits", 10)

    if not isinstance(title, str) or not title.strip():
        return jsonify({"error": "Title is required."}), 400
    if not isinstance(author, str) or not author.strip():
        return jsonify({"error": "Author is required."}), 400

    if not isinstance(credit_cost, int) or credit_cost < 1 or credit_cost > 5000:
        return jsonify({"error": "Credits must be an integer between 1 and 5,000."}), 400

    book = create_book(title.strip(), author.strip(), credit_cost)
    return jsonify(book), 201


@app.route("/api/books/<int:book_id>", methods=["PUT"])
def api_update_book(book_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Please send a valid JSON object."}), 400

    title = data.get("title")
    author = data.get("author")
    credit_cost = data.get("credits")

    if not isinstance(title, str) or not title.strip():
        return jsonify({"error": "Title is required."}), 400
    if not isinstance(author, str) or not author.strip():
        return jsonify({"error": "Author is required."}), 400

    if credit_cost is not None and (
        not isinstance(credit_cost, int) or credit_cost < 1 or credit_cost > 5000
    ):
        return jsonify({"error": "Credits must be an integer between 1 and 5,000."}), 400

    book = update_book(book_id, title.strip(), author.strip(), credit_cost)
    if book is None:
        return jsonify({"error": "Book not found."}), 404
    return jsonify(book)


@app.route("/api/books/<int:book_id>", methods=["DELETE"])
def api_delete_book(book_id):
    deleted = delete_book(book_id)
    if not deleted:
        return jsonify({"error": "Book not found."}), 404
    return jsonify({"message": "Book deleted successfully."})


if __name__ == "__main__":
    app.run(debug=runtime_environment not in {"production", "prod"})
