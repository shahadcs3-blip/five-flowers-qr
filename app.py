import io
import os
import secrets
import zipfile
from functools import wraps

import psycopg
import qrcode
from flask import Flask, redirect, render_template, request, send_file, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "fiveflowers123")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing. Add it in Render Environment variables.")


def db():
    return psycopg.connect(DATABASE_URL)


def initialize():
    with db() as con:
        with con.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS qr_codes (
                    number INTEGER PRIMARY KEY,
                    token TEXT UNIQUE NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT FALSE,
                    first_used_at TIMESTAMPTZ
                )
            """)
            for number in range(71, 83):
                cur.execute("""
                    INSERT INTO qr_codes(number, token)
                    VALUES (%s, %s)
                    ON CONFLICT (number) DO NOTHING
                """, (number, secrets.token_urlsafe(18)))


initialize()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.get("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("dashboard"))
        error = "Incorrect password"
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@admin_required
def dashboard():
    with db() as con:
        with con.cursor() as cur:
            cur.execute("SELECT number, used, first_used_at FROM qr_codes ORDER BY number")
            rows = cur.fetchall()
    return render_template("dashboard.html", rows=rows)


@app.get("/scan/<token>")
def scan(token):
    with db() as con:
        with con.cursor() as cur:
            cur.execute("""
                UPDATE qr_codes
                SET used = TRUE, first_used_at = NOW()
                WHERE token = %s AND used = FALSE
                RETURNING number, first_used_at
            """, (token,))
            accepted = cur.fetchone()
            if accepted:
                return render_template("result.html", allowed=True, number=accepted[0], first_used_at=accepted[1], invalid=False)
            cur.execute("SELECT number, first_used_at FROM qr_codes WHERE token = %s", (token,))
            existing = cur.fetchone()
    if existing:
        return render_template("result.html", allowed=False, number=existing[0], first_used_at=existing[1], invalid=False)
    return render_template("result.html", allowed=False, number="—", first_used_at=None, invalid=True), 404


@app.get("/download")
@admin_required
def download():
    base_url = request.host_url.rstrip("/")
    with db() as con:
        with con.cursor() as cur:
            cur.execute("SELECT number, token FROM qr_codes ORDER BY number")
            rows = cur.fetchall()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for number, token in rows:
            image = qrcode.make(f"{base_url}/scan/{token}")
            image_bytes = io.BytesIO()
            image.save(image_bytes, format="PNG")
            archive.writestr(f"QR_{number}.png", image_bytes.getvalue())
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="QR_71_to_82.zip", mimetype="application/zip")


@app.post("/reset/<int:number>")
@admin_required
def reset(number):
    with db() as con:
        with con.cursor() as cur:
            cur.execute("UPDATE qr_codes SET used = FALSE, first_used_at = NULL WHERE number = %s", (number,))
    return redirect(url_for("dashboard"))


@app.post("/reset-all")
@admin_required
def reset_all():
    with db() as con:
        with con.cursor() as cur:
            cur.execute("UPDATE qr_codes SET used = FALSE, first_used_at = NULL")
    return redirect(url_for("dashboard"))
