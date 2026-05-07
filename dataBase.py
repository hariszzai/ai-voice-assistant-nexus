# database.py
import sqlite3
import json
import os

DB_PATH = "nexus.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    # runs once on startup — creates all tables if they don't exist
    conn = get_connection()
    cursor = conn.cursor()

    # reminders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            message TEXT NOT NULL
        )
    """)

    # conversation history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # user profile table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY,
            name TEXT DEFAULT '',
            city TEXT DEFAULT 'Delhi'
        )
    """)

    # voice settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_settings (
            id INTEGER PRIMARY KEY,
            voice TEXT DEFAULT 'en-US-BrianNeural',
            speed TEXT DEFAULT '20'
        )
    """)

    # insert default rows if tables are empty
    cursor.execute("INSERT OR IGNORE INTO user_profile (id, name, city) VALUES (1, '', 'Delhi')")
    cursor.execute("INSERT OR IGNORE INTO voice_settings (id, voice, speed) VALUES (1, 'en-US-BrianNeural', '20')")

    conn.commit()
    conn.close()

# ── REMINDERS ──────────────────────────────────────────────────────────────────

def save_reminder(time, message):
    conn = get_connection()
    conn.execute("INSERT INTO reminders (time, message) VALUES (?, ?)", (time, message))
    conn.commit()
    conn.close()

def load_reminders():
    conn = get_connection()
    rows = conn.execute("SELECT id, time, message FROM reminders").fetchall()
    conn.close()
    return [{"id": r[0], "time": r[1], "message": r[2]} for r in rows]

def delete_reminder(reminder_id):
    conn = get_connection()
    conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

# ── CONVERSATION HISTORY ───────────────────────────────────────────────────────

def save_message(session_id, role, content):
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversation_history (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    conn.commit()
    conn.close()

def load_history(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM conversation_history WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def clear_history(session_id):
    conn = get_connection()
    conn.execute("DELETE FROM conversation_history WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

# ── USER PROFILE ───────────────────────────────────────────────────────────────

def save_profile(name, city):
    conn = get_connection()
    conn.execute("UPDATE user_profile SET name = ?, city = ? WHERE id = 1", (name, city))
    conn.commit()
    conn.close()

def load_profile():
    conn = get_connection()
    row = conn.execute("SELECT name, city FROM user_profile WHERE id = 1").fetchone()
    conn.close()
    return {"name": row[0], "city": row[1]} if row else {"name": "", "city": "Delhi"}

# ── VOICE SETTINGS ─────────────────────────────────────────────────────────────

def save_voice_settings(voice, speed):
    conn = get_connection()
    conn.execute("UPDATE voice_settings SET voice = ?, speed = ? WHERE id = 1", (voice, speed))
    conn.commit()
    conn.close()

def load_voice_settings():
    conn = get_connection()
    row = conn.execute("SELECT voice, speed FROM voice_settings WHERE id = 1").fetchone()
    conn.close()
    return {"voice": row[0], "speed": row[1]} if row else {"voice": "en-US-BrianNeural", "speed": "20"}