import sqlite3
from datetime import datetime

def get_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_user_by_telegram_id(telegram_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        user = dict(row)
        # Преобразуем строковые представления дат в объекты datetime, если они заданы
        if user.get("premium_expires_at"):
            user["premium_expires_at"] = datetime.fromisoformat(user["premium_expires_at"])
        if user.get("premium_reset_at"):
            user["premium_reset_at"] = datetime.fromisoformat(user["premium_reset_at"])
        if user.get("free_reset_at"):
            user["free_reset_at"] = datetime.fromisoformat(user["free_reset_at"])
        return user
    return None

def create_user(user: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (telegram_id, premium, premium_expires_at, premium_answers_left, premium_reset_at, free_answers_left, free_reset_at, username, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user["telegram_id"],
            user.get("premium", False),
            user.get("premium_expires_at").isoformat() if user.get("premium_expires_at") else None,
            user.get("premium_answers_left", 0),
            user.get("premium_reset_at").isoformat() if user.get("premium_reset_at") else None,
            user.get("free_answers_left", 5),
            user.get("free_reset_at").isoformat() if user.get("free_reset_at") else None,
            user.get("username", ""),
            datetime.now().isoformat()
        )
    )
    conn.commit()
    conn.close()

def update_user(user: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET premium = ?, premium_expires_at = ?, premium_answers_left = ?, premium_reset_at = ?, free_answers_left = ?, free_reset_at = ? WHERE telegram_id = ?",
        (
            user.get("premium", False),
            user.get("premium_expires_at").isoformat() if user.get("premium_expires_at") else None,
            user.get("premium_answers_left", 0),
            user.get("premium_reset_at").isoformat() if user.get("premium_reset_at") else None,
            user.get("free_answers_left", 5),
            user.get("free_reset_at").isoformat() if user.get("free_reset_at") else None,
            user["telegram_id"],
        )
    )
    conn.commit()
    conn.close()
