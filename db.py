import re
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, create_engine, delete, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload, sessionmaker

DB_PATH = Path(__file__).resolve().parent / "books.db"
engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (CheckConstraint("price >= 0", name="check_book_price_nonnegative"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    credit: Mapped["BookCredit"] = relationship(back_populates="book", uselist=False, cascade="all, delete-orphan")


class SubjectFolder(Base):
    __tablename__ = "subject_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    documents: Mapped[list["StudyDocument"]] = relationship(back_populates="folder")
    links: Mapped[list["StudyLink"]] = relationship(back_populates="folder")


class StudyDocument(Base):
    __tablename__ = "study_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    folder_id: Mapped[int] = mapped_column(ForeignKey("subject_folders.id"), nullable=False)
    folder: Mapped[SubjectFolder] = relationship(back_populates="documents")


class StudyLink(Base):
    __tablename__ = "study_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    folder_id: Mapped[int] = mapped_column(ForeignKey("subject_folders.id"), nullable=False)
    folder: Mapped[SubjectFolder] = relationship(back_populates="links")


class BookCredit(Base):
    __tablename__ = "book_credits"

    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    credit_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    book: Mapped[Book] = relationship(back_populates="credit")


class CreditWallet(Base):
    __tablename__ = "credit_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'user')", name="check_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    registration_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    course: Mapped[str] = mapped_column(String(40), nullable=False, default="BCA")
    year_of_study: Mapped[int | None] = mapped_column(Integer, nullable=True)
    specialization: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved")
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    access_role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")
    can_delete_resources: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete_users: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class UserCreditWallet(Base):
    __tablename__ = "user_credit_wallets"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserCreditTransaction(Base):
    __tablename__ = "user_credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class UserBookClaim(Base):
    __tablename__ = "user_book_claims"
    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_user_book_claim"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    credits_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class UserSubjectAccess(Base):
    __tablename__ = "user_subject_access"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("subject_folders.id"), primary_key=True)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_registration_number: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class FeaturedRead(Base):
    __tablename__ = "featured_reads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    format_label: Mapped[str] = mapped_column(String, nullable=False, default="Public-domain novel")


FEATURED_PUBLIC_DOMAIN_READS = [
    ("Frankenstein; or, The Modern Prometheus", "Mary Wollstonecraft Shelley", "A gothic novel about ambition, responsibility, and the boundaries of science.", "https://www.gutenberg.org/ebooks/84"),
    ("The Adventures of Sherlock Holmes", "Arthur Conan Doyle", "Twelve classic detective stories featuring Holmes and Dr. Watson.", "https://www.gutenberg.org/ebooks/1661"),
    ("Alice's Adventures in Wonderland", "Lewis Carroll", "A playful fantasy novel full of wordplay, logic puzzles, and memorable characters.", "https://www.gutenberg.org/ebooks/11"),
]


RECOMMENDED_RESOURCES = [
    ("Cyber Security", "cyber-security", "Security Engineering, 3rd Edition", "https://www.cl.cam.ac.uk/~rja14/book.html", "Ross Anderson's author-hosted textbook and lectures, including material taught in Cambridge undergraduate security courses.", "Textbook"),
    ("Digital Image Processing", "digital-image-processing", "HIPR2: Image Processing Reference", "https://homepages.inf.ed.ac.uk/rbf/HIPR2/", "University of Edinburgh reference with worksheets, interactive experiments, and an image library.", "Course reference"),
    ("Digital Image Processing", "digital-image-processing", "Computer Vision: Algorithms and Applications, 2nd Edition", "https://szeliski.org/Book/", "Richard Szeliski's university-level text covers image formation, filtering, features, and vision; the author provides a personal-use download.", "Textbook"),
    ("Internet of Things", "internet-of-things", "MQTT Version 5.0 Specification", "https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html", "The OASIS standard for a lightweight publish/subscribe messaging protocol used in IoT systems.", "Technical standard"),
    ("Internet of Things", "internet-of-things", "Arduino Education: Higher Education and IoT", "https://www.arduino.cc/education/", "Official education resources with practical learning material for connected devices and IoT projects.", "Lab resource"),
    ("ML & Neural Network", "ml-neural-network", "Dive into Deep Learning", "https://d2l.ai/", "Interactive open textbook with math, executable notebooks, neural networks, optimization, computer vision, and NLP chapters.", "Textbook"),
    ("Natural Language Processing", "natural-language-processing", "Speech and Language Processing, 3rd Edition Draft", "https://web.stanford.edu/~jurafsky/slp3/", "Current author-hosted draft covering language models, embeddings, neural networks, transformers, parsing, and speech.", "Textbook"),
    ("Natural Language Processing", "natural-language-processing", "Natural Language Processing with Python", "https://www.nltk.org/book/", "Python 3 text covering text processing, classification, information extraction, and parsing; licensed CC BY-NC-ND.", "Textbook"),
]


def _as_dict(book):
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "credits": book.credit.credit_cost if book.credit else 10,
        "claimed": book.credit.claimed if book.credit else False,
    }


def init_db():
    Base.metadata.create_all(engine)
    _migrate_user_profile_schema()
    with SessionLocal.begin() as session:
        if session.scalar(select(Book.id).limit(1)) is None:
            session.add_all([
                Book(title="Python Basics", author="Amit Sharma", price=350.00),
                Book(title="Learning Flask", author="Neha Verma", price=450.00),
                Book(title="Data Science for Beginners", author="Riya Singh", price=525.00),
            ])
        wallet = session.get(CreditWallet, 1)
        if wallet is None:
            session.add(CreditWallet(id=1, balance=0))
        for book in session.scalars(select(Book).options(selectinload(Book.credit))).all():
            if book.credit is None:
                book.credit = BookCredit(credit_cost=10, claimed=False)
        for folder_name, folder_slug, title, url, description, kind in RECOMMENDED_RESOURCES:
            folder = session.scalar(select(SubjectFolder).where(SubjectFolder.slug == folder_slug))
            if folder is None:
                folder = SubjectFolder(name=folder_name, slug=folder_slug)
                session.add(folder)
                session.flush()
            if session.scalar(select(StudyLink.id).where(StudyLink.url == url)) is None:
                session.add(StudyLink(
                    title=title,
                    url=url,
                    kind=kind,
                    description=description,
                    folder=folder,
                ))
        for title, author, description, url in FEATURED_PUBLIC_DOMAIN_READS:
            if session.scalar(select(FeaturedRead.id).where(FeaturedRead.url == url)) is None:
                session.add(FeaturedRead(
                    title=title,
                    author=author,
                    description=description,
                    url=url,
                ))


def _migrate_user_profile_schema():
    additions = {
        "full_name": "VARCHAR(120) NOT NULL DEFAULT ''",
        "email": "VARCHAR(254)",
        "course": "VARCHAR(40) NOT NULL DEFAULT 'BCA'",
        "year_of_study": "INTEGER",
        "specialization": "VARCHAR(80) NOT NULL DEFAULT ''",
        "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'approved'",
        "access_role": "VARCHAR(20) NOT NULL DEFAULT 'student'",
        "can_delete_resources": "BOOLEAN NOT NULL DEFAULT 0",
        "can_delete_users": "BOOLEAN NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        role_column_was_missing = "access_role" not in columns
        for column_name, definition in additions.items():
            if column_name not in columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {definition}"))
        if role_column_was_missing:
            connection.execute(text(
                "UPDATE users SET access_role = CASE role "
                "WHEN 'admin' THEN 'main_admin' ELSE 'student' END"
            ))
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        missing_columns = additions.keys() - columns
        if missing_columns:
            raise RuntimeError(f"User schema migration incomplete: {sorted(missing_columns)}")
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email "
            "ON users(email) WHERE email IS NOT NULL"
        ))


def get_user_by_registration(registration_number):
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.registration_number == registration_number))
        return _user_dict(user, include_password_hash=True) if user else None


def get_user_by_id(user_id):
    with SessionLocal() as session:
        user = session.get(User, user_id)
        return _user_dict(user) if user else None


def _user_dict(user, include_password_hash=False):
    result = {
        "id": user.id,
        "registration_number": user.registration_number,
        "full_name": user.full_name,
        "email": user.email,
        "course": user.course,
        "year_of_study": user.year_of_study,
        "specialization": user.specialization,
        "approval_status": user.approval_status,
        "role": user.access_role,
        "can_delete_resources": user.can_delete_resources,
        "can_delete_users": user.can_delete_users,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
    }
    if include_password_hash:
        result["password_hash"] = user.password_hash
    return result


def create_user(
    registration_number,
    password_hash,
    role="user",
    must_change_password=True,
    full_name="",
    email=None,
    course="BCA",
    year_of_study=None,
    specialization="",
    approval_status="approved",
):
    role_aliases = {"admin": "main_admin", "user": "student"}
    access_role = role_aliases.get(role, role)
    if access_role not in {"student", "sub_admin", "main_admin"}:
        raise ValueError("Invalid access role")
    storage_role = "admin" if access_role == "main_admin" else "user"
    with SessionLocal.begin() as session:
        user = User(
            registration_number=registration_number,
            password_hash=password_hash,
            role=storage_role,
            access_role=access_role,
            must_change_password=must_change_password,
            full_name=full_name,
            email=email,
            course=course,
            year_of_study=year_of_study,
            specialization=specialization,
            approval_status=approval_status,
            is_active=approval_status == "approved",
        )
        session.add(user)
        session.flush()
        session.add(UserCreditWallet(user_id=user.id, balance=0))
        user_id = user.id
    return get_user_by_id(user_id)


def list_users():
    with SessionLocal() as session:
        users = session.scalars(select(User).order_by(User.registration_number)).all()
        access_rows = session.execute(select(UserSubjectAccess.user_id, UserSubjectAccess.folder_id)).all()
        subject_ids = {}
        for user_id, folder_id in access_rows:
            subject_ids.setdefault(user_id, []).append(folder_id)
        return [
            {**_user_dict(user), "subject_folder_ids": subject_ids.get(user.id, [])}
            for user in users
        ]


def pending_user_count():
    with SessionLocal() as session:
        return session.scalar(
            select(func.count(User.id)).where(User.approval_status == "pending")
        ) or 0


def email_in_use(email, except_user_id=None):
    statement = select(User.id).where(User.email == email)
    if except_user_id is not None:
        statement = statement.where(User.id != except_user_id)
    with SessionLocal() as session:
        return session.scalar(statement.limit(1)) is not None


def update_student_profile(user_id, full_name, email, course, year_of_study, specialization):
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is None or user.access_role not in {"student", "sub_admin"}:
            return False
        user.full_name = full_name
        user.email = email
        user.course = course
        user.year_of_study = year_of_study
        user.specialization = specialization
        return True


def set_user_approval(user_id, approval_status):
    if approval_status not in {"pending", "approved", "rejected"}:
        raise ValueError("Invalid approval status")
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is None or user.access_role != "student":
            return False
        user.approval_status = approval_status
        user.is_active = approval_status == "approved"
        return True


def update_user_password(user_id, password_hash):
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is None:
            return False
        user.password_hash = password_hash
        user.must_change_password = False
        return True


def user_wallet(user_id):
    with SessionLocal() as session:
        wallet = session.get(UserCreditWallet, user_id)
        transactions = session.scalars(
            select(UserCreditTransaction)
            .where(UserCreditTransaction.user_id == user_id)
            .order_by(UserCreditTransaction.created_at.desc(), UserCreditTransaction.id.desc())
            .limit(12)
        ).all()
        return wallet.balance if wallet else 0, transactions


def featured_reads():
    with SessionLocal() as session:
        return session.scalars(select(FeaturedRead).order_by(FeaturedRead.id)).all()


def check_database_connection():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def grant_subject_access(user_id, folder_ids, assigned_by_id):
    folder_ids = set(folder_ids)
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is None or user.access_role != "sub_admin":
            return False
        valid_folder_ids = set(session.scalars(select(SubjectFolder.id)).all())
        if not folder_ids.issubset(valid_folder_ids):
            return False
        session.execute(delete(UserSubjectAccess).where(UserSubjectAccess.user_id == user_id))
        session.add_all([
            UserSubjectAccess(user_id=user_id, folder_id=folder_id, assigned_by_id=assigned_by_id)
            for folder_id in folder_ids
        ])
        return True


def assigned_subject_folder_ids(user_id):
    with SessionLocal() as session:
        return set(session.scalars(
            select(UserSubjectAccess.folder_id).where(UserSubjectAccess.user_id == user_id)
        ).all())


def update_user_access_role(user_id, access_role, can_delete_resources=False, can_delete_users=False):
    if access_role not in {"student", "sub_admin"}:
        raise ValueError("Only student and sub-admin roles can be assigned here")
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is None or user.access_role == "main_admin":
            return False
        if user.approval_status != "approved":
            return False
        user.access_role = access_role
        user.role = "user"
        user.can_delete_resources = access_role == "sub_admin" and can_delete_resources
        user.can_delete_users = access_role == "sub_admin" and can_delete_users
        if access_role != "sub_admin":
            session.execute(delete(UserSubjectAccess).where(UserSubjectAccess.user_id == user_id))
        return True


def add_audit_log(actor_id, actor_registration_number, action, target_type, target_id=None, details=""):
    with SessionLocal.begin() as session:
        session.add(AuditLog(
            actor_id=actor_id,
            actor_registration_number=actor_registration_number,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details[:500],
        ))


def recent_audit_logs(limit=50):
    with SessionLocal() as session:
        entries = session.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
        ).all()
        return [
            {
                "id": entry.id,
                "actor_registration_number": entry.actor_registration_number,
                "action": entry.action,
                "target_type": entry.target_type,
                "target_id": entry.target_id,
                "details": entry.details,
                "created_at": entry.created_at,
            }
            for entry in entries
        ]


def delete_user_account(user_id, actor_id, actor_registration_number):
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is None:
            return False
        if user.access_role == "main_admin":
            other_main_admins = session.scalar(
                select(func.count(User.id)).where(
                    User.access_role == "main_admin",
                    User.id != user_id,
                )
            ) or 0
            if other_main_admins == 0:
                return False
        target_registration = user.registration_number
        session.add(AuditLog(
            actor_id=actor_id,
            actor_registration_number=actor_registration_number,
            action="user_deleted",
            target_type="user",
            target_id=user_id,
            details=f"Deleted account {target_registration}",
        ))
        session.execute(delete(UserCreditTransaction).where(UserCreditTransaction.user_id == user_id))
        session.execute(
            text("UPDATE user_credit_transactions SET assigned_by_id = NULL WHERE assigned_by_id = :user_id"),
            {"user_id": user_id},
        )
        session.execute(delete(UserBookClaim).where(UserBookClaim.user_id == user_id))
        session.execute(delete(UserSubjectAccess).where(UserSubjectAccess.user_id == user_id))
        session.execute(
            text("UPDATE user_subject_access SET assigned_by_id = NULL WHERE assigned_by_id = :user_id"),
            {"user_id": user_id},
        )
        session.execute(text("UPDATE audit_logs SET actor_id = NULL WHERE actor_id = :user_id"), {"user_id": user_id})
        session.execute(delete(UserCreditWallet).where(UserCreditWallet.user_id == user_id))
        session.delete(user)
        return True


def add_user_credits(user_id, amount, description="Credits added", assigned_by_id=None):
    with SessionLocal.begin() as session:
        wallet = session.get(UserCreditWallet, user_id)
        if wallet is None:
            wallet = UserCreditWallet(user_id=user_id, balance=0)
            session.add(wallet)
        wallet.balance += amount
        session.add(UserCreditTransaction(
            user_id=user_id,
            amount=amount,
            description=description,
            assigned_by_id=assigned_by_id,
        ))
        return wallet.balance


def claimed_book_ids(user_id):
    with SessionLocal() as session:
        return set(session.scalars(
            select(UserBookClaim.book_id).where(UserBookClaim.user_id == user_id)
        ).all())


def claim_book_for_user(book_id, user_id, is_admin=False):
    with SessionLocal.begin() as session:
        book = session.get(Book, book_id)
        if book is None:
            return "missing"
        prior_claim = session.scalar(select(UserBookClaim.id).where(
            UserBookClaim.user_id == user_id,
            UserBookClaim.book_id == book_id,
        ))
        if prior_claim is not None:
            return "claimed"
        cost = 0 if is_admin else book.credit.credit_cost
        if not is_admin:
            wallet = session.get(UserCreditWallet, user_id)
            if wallet is None or wallet.balance < cost:
                return "insufficient"
            wallet.balance -= cost
            session.add(UserCreditTransaction(
                user_id=user_id,
                amount=-cost,
                description=f"Claimed {book.title}",
            ))
        session.add(UserBookClaim(user_id=user_id, book_id=book_id, credits_spent=cost))
        return "ok"


def import_pdf_library(source_root, destination_root):
    source_root = Path(source_root).resolve()
    destination_root = Path(destination_root).resolve()
    imported = 0

    if not source_root.is_dir():
        raise FileNotFoundError(f"PDF source folder does not exist: {source_root}")

    with SessionLocal.begin() as session:
        for source_file in sorted(source_root.rglob("*")):
            if not source_file.is_file() or source_file.suffix.lower() != ".pdf":
                continue

            relative_path = source_file.relative_to(source_root)
            folder_name = relative_path.parts[0] if len(relative_path.parts) > 1 else "Unsorted"
            folder_slug = re.sub(r"[^a-z0-9]+", "-", folder_name.lower()).strip("-") or "subject"
            folder = session.scalar(select(SubjectFolder).where(SubjectFolder.slug == folder_slug))
            if folder is None:
                folder = SubjectFolder(name=folder_name, slug=folder_slug)
                session.add(folder)
                session.flush()

            target_file = destination_root / relative_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)

            storage_path = relative_path.as_posix()
            document = session.scalar(
                select(StudyDocument).where(StudyDocument.storage_path == storage_path)
            )
            if document is None:
                document = StudyDocument(
                    title=source_file.stem.replace("_", " "),
                    original_filename=source_file.name,
                    storage_path=storage_path,
                    file_size=source_file.stat().st_size,
                    folder=folder,
                )
                session.add(document)
                imported += 1
            else:
                document.title = source_file.stem.replace("_", " ")
                document.original_filename = source_file.name
                document.file_size = source_file.stat().st_size
                document.folder = folder

    return imported


def get_all_books():
    with SessionLocal() as session:
        books = session.scalars(
            select(Book).options(selectinload(Book.credit)).order_by(Book.id.desc())
        ).all()
        return [_as_dict(book) for book in books]


def get_book(book_id):
    with SessionLocal() as session:
        book = session.get(Book, book_id)
        return _as_dict(book) if book else None


def create_book(title, author, credit_cost=10):
    with SessionLocal.begin() as session:
        book = Book(title=title, author=author, price=0)
        book.credit = BookCredit(credit_cost=credit_cost)
        session.add(book)
        session.flush()
        book_id = book.id
    return get_book(book_id)


def update_book(book_id, title, author, credit_cost=None):
    with SessionLocal.begin() as session:
        book = session.get(Book, book_id)
        if book is None:
            return None
        book.title = title
        book.author = author
        if credit_cost is not None:
            book.credit.credit_cost = credit_cost
    return get_book(book_id)


def delete_book(book_id):
    with SessionLocal.begin() as session:
        book = session.get(Book, book_id)
        if book is None:
            return False
        session.execute(delete(UserBookClaim).where(UserBookClaim.book_id == book_id))
        session.delete(book)
        return True


def get_wallet():
    with SessionLocal() as session:
        wallet = session.get(CreditWallet, 1)
        transactions = session.scalars(
            select(CreditTransaction)
            .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
            .limit(12)
        ).all()
        return wallet.balance if wallet else 0, transactions


def add_credits(amount):
    with SessionLocal.begin() as session:
        wallet = session.get(CreditWallet, 1)
        if wallet is None:
            wallet = CreditWallet(id=1, balance=0)
            session.add(wallet)
        wallet.balance += amount
        session.add(CreditTransaction(amount=amount, description="Credits added to wallet"))
        return wallet.balance


def claim_book(book_id):
    with SessionLocal.begin() as session:
        book = session.get(Book, book_id)
        if book is None:
            return "missing"
        if book.credit.claimed:
            return "claimed"
        wallet = session.get(CreditWallet, 1)
        if wallet is None or wallet.balance < book.credit.credit_cost:
            return "insufficient"
        wallet.balance -= book.credit.credit_cost
        book.credit.claimed = True
        session.add(CreditTransaction(
            amount=-book.credit.credit_cost,
            description=f"Claimed {book.title}",
        ))
        return "ok"
