from flask_babel import Babel, gettext as _
from datetime import timedelta
from flask import Flask, flash, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from db_config import get_db_connection

import socket
print("FLASK RUNNING ON:", socket.gethostname())

app = Flask(__name__)
app.secret_key = "yojanasetu_secret_key"
app.permanent_session_lifetime = timedelta(minutes=60)

from translations_ui import translations_ui

@app.context_processor
def inject_translator():
    lang = session.get("lang","en")
    return dict(t=lambda key: translations_ui[lang].get(key,key))


app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en','hi']

def get_locale():
    return session.get('lang', 'en')

babel = Babel(app, locale_selector=get_locale)

@app.route("/set-language/<lang>")
def set_language(lang):
    session['lang'] = lang
    return redirect(request.referrer or "/")


# ---------- HOME ----------
@app.route("/")
def home():
    income = session.get("income")
    conn = get_db_connection()
    cursor = conn.cursor()  
    cursor.execute("""
        SELECT id, scheme_name, description, min_income, max_income, official_url
        FROM schemes WHERE is_active=TRUE
        ORDER BY id DESC LIMIT 3""")
    popular_schemes = cursor.fetchall()

    for s in popular_schemes:
        s["eligible"] = income is not None and s["min_income"] <= income <= s["max_income"]

    # FIX : fetch recent schemes (latest 4 by id) for the home template
    cursor.execute("""
        SELECT id, scheme_name
        FROM schemes WHERE is_active=TRUE
        ORDER BY id DESC LIMIT 4""")
    recent_schemes = cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()
    return render_template("home.html",
    popular_schemes=popular_schemes,recent_schemes=recent_schemes)


# ---------- ELIGIBILITY ----------
@app.route("/check-eligibility", methods=["GET", "POST"])
def check_eligibility():
    if request.method == "POST":
        income = int(request.form["income"])
        category = request.form["category"].lower()
        session["income"] = income
        session.permanent = True  # FIX : make session persist per app lifetime setting

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT scheme_name, description, official_url
            FROM schemes
            WHERE is_active=TRUE
              AND %s BETWEEN min_income AND max_income
              AND (category=%s OR category='all')
        """, (income, category))

        schemes = cursor.fetchall()
        conn.commit()
        cursor.close()
        conn.close()

        return render_template("results.html", schemes=schemes)

    return render_template("eligibility_form.html")


# ---------- ALL SCHEMES ----------
@app.route("/all-schemes")
def all_schemes():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            scheme_name,
            description,
            category
        FROM schemes
    """)
    schemes = cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()

    return render_template(
        "all_schemes.html",
        schemes=schemes)


# ---------- CATEGORY ----------
@app.route("/category/<cat>")
def category(cat):
    conn = get_db_connection()
    cursor = conn.cursor()
    # LOWER() on both sides so Health/health/HEALTH all match
    cursor.execute(
        "SELECT * FROM schemes WHERE LOWER(category)=LOWER(%s) AND is_active=TRUE ORDER BY id DESC",
        (cat,))
    schemes = cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()
    return render_template("schemes.html", schemes=schemes, cat=cat)


# ---------- SCHEME DETAIL ----------
@app.route("/scheme/<name>")  # FIX : changed from /admin/scheme/<name> so navbar links work
def scheme_detail(name):
    scheme_name = name.replace('-', ' ')
    conn = get_db_connection()
    cursor = conn.cursor()  
    cursor.execute("""
        SELECT scheme_name, description, category,
               min_income, max_income, official_url
        FROM schemes
        WHERE scheme_name = %s
    """, (scheme_name,))
    scheme = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()
    return render_template("scheme_detail.html", scheme=scheme)


# ---------- ADMIN ----------
@app.route("/admin/add-scheme", methods=["GET", "POST"])
def add_scheme():
    if session.get("user_id") != 1:
        return "Access Denied", 403  # FIX : return proper HTTP status code

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            INSERT INTO schemes
            (scheme_name, description, min_income, max_income, category, official_url)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            request.form["scheme_name"],
            request.form["description"],
            int(request.form["min_income"]),
            int(request.form["max_income"]),
            request.form["category"].strip().lower(),
            request.form["official_url"]))
        conn.commit()

    cursor.execute("SELECT * FROM schemes")
    schemes = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("add_scheme.html", schemes=schemes)


@app.route("/admin/delete/<int:id>")
def delete_scheme(id):
    if session.get("user_id") != 1:  # FIX : protect delete route too
        return "Access Denied", 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM schemes WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("add_scheme"))  # FIX : use url_for instead of hardcoded path


@app.route("/admin/edit/<int:id>", methods=["GET", "POST"])
def edit_scheme(id):
    conn = get_db_connection()          # FIX 11: conn/cursor must be created before both branches
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            UPDATE schemes SET
            scheme_name=%s, description=%s,
            min_income=%s, max_income=%s, category=%s, official_url=%s
            WHERE id=%s
        """, (
            request.form["scheme_name"],
            request.form["description"],
            int(request.form["min_income"]),
            int(request.form["max_income"]),
            request.form["category"],
            request.form["official_url"],
            id
        ))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("add_scheme"))  # FIX 12: was /add_scheme which raises 404

    cursor.execute("SELECT * FROM schemes WHERE id=%s", (id,))
    scheme = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template("edit_scheme.html", scheme=scheme)


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, password FROM users WHERE email=%s",
            (request.form["email"],)
        )
        user = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if user and check_password_hash(user["password"], request.form["password"]):
            session.permanent = True   # FIX 13: persist session
            session["user_id"] = user["id"]
            return redirect(url_for("home"))  # FIX 14: use url_for
        flash("Invalid credentials", "danger")

    return render_template("login.html")


# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users (email, password)
            VALUES (%s, %s)
        """, (
            request.form["email"],
            generate_password_hash(request.form["password"])
        ))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("login"))  # FIX 15: use url_for

    return render_template("register.html")


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))  # FIX 16: url_for takes function name, not path string


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)