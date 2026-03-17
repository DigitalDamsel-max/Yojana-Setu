import pymysql

def get_db_connection():
    print("🔌 Connecting to MySQL (PyMySQL)...")

    conn = pymysql.connect(
        host="localhost",
        user="root",
        password="Pihu@4124",
        database="yojanasetu",
        cursorclass=pymysql.cursors.DictCursor
    )

    print("✅ MySQL CONNECTED")
    return conn