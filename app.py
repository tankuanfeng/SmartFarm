import os
import re
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

PROJECT_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = PROJECT_DIR / "instance"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    DATABASE=str(INSTANCE_DIR / "smartfarm.sqlite3"),
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
)
CSRFProtect(app)
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


def get_db():
    if "db" not in g:
        database_path = Path(app.config["DATABASE"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        g.db = connection
    return g.db


def init_db():
    database = get_db()
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    database.commit()


@app.before_request
def ensure_database():
    if request.endpoint in {"register", "login", "dashboard", "logout"}:
        init_db()


@app.teardown_appcontext
def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def normalize_email(value):
    value = value.strip()
    if not value or len(value) > 254:
        return None
    try:
        result = validate_email(
            value,
            allow_display_name=False,
            check_deliverability=False,
        )
    except EmailNotValidError:
        return None
    return result.normalized.lower()


def password_error(value):
    if not 8 <= len(value) <= 64:
        return "密码长度需为 8–64 位。"
    if re.fullmatch(r"[A-Za-z0-9]+", value) is None:
        return "密码只能包含英文字母和数字。"
    if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
        return "密码必须同时包含至少一个英文字母和一个数字。"
    return None


def identifier_conflict(database, user_id, email):
    if database.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
        return "user_id"
    if database.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return "email"
    cross_match = database.execute(
        """
        SELECT 1 FROM users
        WHERE email = ? COLLATE NOCASE OR id = ? COLLATE NOCASE
        """,
        (user_id, email),
    ).fetchone()
    return "general" if cross_match else None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def render_auth_page(template, page_title, values=None, errors=None, status=200):
    return (
        render_template(
            template,
            page_title=page_title,
            values=values or {},
            errors=errors or {},
        ),
        status,
    )


@app.get("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    values = {"user_id": "", "email": ""}
    errors = {}
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        values = {
            "user_id": user_id,
            "email": request.form.get("email", "").strip(),
        }

        if not user_id or len(user_id) > 64:
            errors["user_id"] = "用户 ID 不能为空，且不能超过 64 个字符。"
        if email is None:
            errors["email"] = "请输入有效的邮箱地址。"
        password_message = password_error(password)
        if password_message:
            errors["password"] = password_message
        if password != password_confirmation:
            errors["password_confirmation"] = "两次输入的密码不一致。"

        if not errors:
            database = get_db()
            conflict = identifier_conflict(database, user_id, email)
            if conflict == "user_id":
                errors["user_id"] = "这个用户 ID 已被使用。"
            elif conflict == "email":
                errors["email"] = "这个邮箱已被使用。"
            elif conflict == "general":
                errors["general"] = "用户 ID 与邮箱不能与其他账号重叠。"
            else:
                try:
                    database.execute(
                        """
                        INSERT INTO users (id, email, password_hash)
                        VALUES (?, ?, ?)
                        """,
                        (user_id, email, generate_password_hash(password)),
                    )
                    database.commit()
                except sqlite3.IntegrityError:
                    database.rollback()
                    conflict = identifier_conflict(database, user_id, email)
                    if conflict == "user_id":
                        errors["user_id"] = "这个用户 ID 已被使用。"
                    elif conflict == "email":
                        errors["email"] = "这个邮箱已被使用。"
                    elif conflict == "general":
                        errors["general"] = "用户 ID 与邮箱不能与其他账号重叠。"
                    else:
                        raise
                else:
                    session.clear()
                    session["user_id"] = user_id
                    return redirect(url_for("dashboard"))

    return render_auth_page(
        "register.html",
        "创建账号",
        values=values,
        errors=errors,
        status=400 if errors else 200,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    values = {"identifier": ""}
    errors = {}
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        values["identifier"] = identifier
        if len(password) > 64:
            user = None
            password_matches = check_password_hash(DUMMY_PASSWORD_HASH, password[:64])
        else:
            normalized_email = normalize_email(identifier) if len(identifier) <= 254 else None
            database = get_db()
            user = database.execute(
                """
                SELECT id, password_hash FROM users
                WHERE id = ? OR email = ?
                """,
                (identifier, normalized_email or ""),
            ).fetchone()
            stored_hash = user["password_hash"] if user is not None else DUMMY_PASSWORD_HASH
            password_matches = check_password_hash(stored_hash, password)

        if user is None or not password_matches:
            errors["general"] = "账号或密码不正确，请重试。"
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

    return render_auth_page(
        "login.html",
        "欢迎回来",
        values=values,
        errors=errors,
        status=400 if errors else 200,
    )


@app.get("/dashboard")
@login_required
def dashboard():
    user = get_db().execute(
        "SELECT id, email FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    if user is None:
        session.clear()
        flash("账号状态已失效，请重新登录。", "error")
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=user)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.after_request
def prevent_auth_page_caching(response):
    if request.endpoint in {"login", "register", "dashboard"}:
        response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    app.run(debug=True)
