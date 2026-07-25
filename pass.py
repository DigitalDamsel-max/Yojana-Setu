from werkzeug.security import generate_password_hash
import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Pihu@4124",
    database="yojanasetu"
)

cursor = conn.cursor()

hashed = generate_password_hash("admin123", method="pbkdf2:sha256")

cursor.execute(
    "UPDATE users SET password=%s WHERE email=%s",
    (hashed, "admin@gmail.com")
)

conn.commit()

print("Updated:", cursor.rowcount)

cursor.close()
conn.close()