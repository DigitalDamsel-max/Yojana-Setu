from flask import flash
from flask import jsonify
from datetime import datetime,timedelta
from flask import Flask, flash, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from db_config import get_db_connection
from secrets import token_urlsafe
import socket
import os

from dotenv import load_dotenv
load_dotenv()

print("FLASK RUNNING ON:", socket.gethostname())

app = Flask(__name__)
app.secret_key = "yojanasetu_secret_key"
app.permanent_session_lifetime = timedelta(minutes=60)

from flask_mail import Mail, Message, Message

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")
mail = Mail(app)


@app.route("/check-db")
def check_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT email, password FROM users")
    users = cursor.fetchall()

    return str(users)


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
        age = int(request.form.get("age", 0))
        gender = request.form.get("gender", "all")
        occupation = request.form.get("occupation", "all")
        area = request.form.get("area", "all")

        session["income"] = income
        session['category'] = category
        session['age'] = age
        session['gender'] = gender
        session['occupation'] = occupation      
        session['area'] = area
        session.permanent = True
        eligible_schemes = []
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT scheme_name, description, category, official_url, min_income, max_income
            FROM schemes
            WHERE min_income <= %s
            AND max_income >= %s
            AND (LOWER(category) = %s OR LOWER(category) = 'all')
            AND (LOWER(gender) = %s OR LOWER(gender) = 'all')
        """, (income, income, category, gender.lower()))
        
        eligible_schemes = cursor.fetchall()
        conn.commit()
        cursor.close()
        conn.close()

        return render_template("results.html", schemes=eligible_schemes)

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
    cursor.execute(
        "SELECT * FROM schemes WHERE LOWER(category)=LOWER(%s) AND is_active=TRUE ORDER BY id DESC",
        (cat,))
    schemes = cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()
    return render_template("schemes.html", schemes=schemes, cat=cat)


# ---------- SCHEME DETAIL ----------
@app.route("/scheme/<name>")  
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
    documents_map = {
    "Ayushman Bharat": ["Aadhaar", "Income Certificate"],
    "PM Awas Yojana": ["Aadhaar", "Address Proof"]
    }
    scheme = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()
    docs = documents_map.get(scheme["scheme_name"], ["Aadhaar"])

    return render_template("scheme_detail.html",
        scheme=scheme,
        documents=docs
    )

# ---------- ADMIN ----------
@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM schemes")
    schemes = cursor.fetchall()

    return render_template("admin_dashboard.html", schemes=schemes)



@app.route("/admin/add-scheme", methods=["GET", "POST"])
def add_scheme():
    if session.get("role") != "admin":
        return "Access Denied", 403  # returns proper HTTP status code

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
    flash("Scheme added successfully!", "success")
    return render_template("add_scheme.html", schemes=schemes)


@app.route("/admin/delete/<int:id>")
def delete_scheme(id):
    if session.get("role") != "admin":
        return "Access Denied", 403
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM schemes WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Scheme deleted successfully!", "success")
    return redirect(url_for("admin_dashboard"))  


@app.route("/admin/edit/<int:id>", methods=["GET", "POST"])
def edit_scheme(id):
    if session.get("role") != "admin":
        return "Access Denied", 403
    
    conn = get_db_connection()
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
        flash("Scheme updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    cursor.execute("SELECT * FROM schemes WHERE id=%s", (id,))
    scheme = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("edit_scheme.html", scheme=scheme)
    

@app.route("/get_schemes", methods=["POST"])
def get_schemes():
    income = int(request.form["max_income"])
    category = request.form["category"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM schemes
        WHERE category=%s AND max_income >= %s
    """, (category, income))

    schemes = cursor.fetchall()

    return render_template("results.html", schemes=schemes)


# ---------- CHATBOT --------
print("GROQ_API_KEY =", os.getenv("GROQ_API_KEY"))
from openai import OpenAI
client = OpenAI(api_key=os.getenv("GROQ_API_KEY"),base_url="https://api.groq.com/openai/v1")

@app.route("/chatbot", methods=["POST"])
def chatbot():
    if "user_id" not in session:
        return jsonify({"reply": "Please login first"})

    msg = request.form.get("message", "").strip()

    if not msg:
        return jsonify({"reply": "Please enter a message"})

    try:
        # 🧠 Hardcoded system prompt
        SYSTEM_PROMPT = (
            "You are a helpful assistant for Indian PM Welfare schemes. "
            "Always respond politely and in formal style. "
            "Answer in 50-80 words using simple language and bullet points."
        )

        # 🤖 Groq API call
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # ✅ stable & free
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": msg}
            ]
        )
        reply = response.choices[0].message.content.strip()
        return jsonify({"reply": reply})

    except Exception as e:
        print("🔥 ERROR:", e)
        return jsonify({"reply": "⚠ Error connecting to AI"})


# ---------- CHAT PAGE ----------
@app.route("/chat")
def chat_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("chat_full.html")


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, password, role FROM users WHERE email=%s",
            (request.form["email"],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user["password"], request.form["password"]):
            session["user_id"] = user["id"]
            session["role"] = user["role"]   

            # Role-based redirect
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("home"))

        flash("Invalid credentials", "danger")

    return render_template("login.html")


# ---------- FORGOT PASSWORD ----------
@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():

    if request.method=="POST":
        email=request.form["email"]

        conn=get_db_connection()
        cursor=conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )
        user=cursor.fetchone()

        if user:
            token=token_urlsafe(32)
            expiry=datetime.now()+timedelta(hours=1)

            cursor.execute("""
            UPDATE users
            SET reset_token=%s,
                token_expiry=%s
            WHERE email=%s
            """,(token,expiry,email))

            conn.commit()
            link=url_for(
                "reset_password",
                token=token,
                _external=True
            )
            
            msg = Message(
                subject="Reset Your Yojana Setu Password",
                recipients=[email]
            )
            msg.body = f"""
            Hello,

            We received a request to reset your password for your Yojana Setu account.

            Click the link below to reset your password:

            {link}

            This link will expire in 30 minutes.

            If you did not request a password reset, please ignore this email.

            Regards,
            Yojana Setu Team
            """

            mail.send(msg)

            flash("Password reset link has been sent to your email.")
            
        else:
            flash("Email not found.")

    return render_template("forgot_password.html")


# ---------- RESET PASSWORD ----------
@app.route("/reset_password/<token>", methods=["GET","POST"])
def reset_password(token):

    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute("""
    SELECT *
    FROM users
    WHERE reset_token=%s
    """,(token,))

    user=cursor.fetchone()
    if not user:
        return "Invalid Token"

    if datetime.now()>user["token_expiry"]:
        return "Token Expired"

    if request.method=="POST":
        password=generate_password_hash(
            request.form["password"]
        )

        cursor.execute("""
        UPDATE users
        SET password=%s,
            reset_token=NULL,
            token_expiry=NULL
        WHERE id=%s
        """,(password,user["id"]))

        conn.commit()
        flash("Password Updated")
        return redirect("/login")

    return render_template("reset_password.html")


# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users (email, password)
            VALUES (%s, %s)
        """, (request.form["email"],
            generate_password_hash(request.form["password"])
        ))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("login"))  

    return render_template("register.html")


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))  


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)