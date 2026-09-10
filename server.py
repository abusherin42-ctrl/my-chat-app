from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import hashlib
import uuid
import shutil

app = FastAPI(title="My Chat Server")

DB_FILE = "chat.db"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# =========================
# DATABASE
# =========================

def get_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db


def now():
    return datetime.now(timezone.utc).isoformat()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            display_name TEXT,
            profile_image TEXT,
            about TEXT DEFAULT '',
            online INTEGER DEFAULT 0,
            last_seen TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            message TEXT DEFAULT '',
            message_type TEXT DEFAULT 'text',
            media_url TEXT,
            file_name TEXT,
            timestamp TEXT NOT NULL,
            delivered INTEGER DEFAULT 0,
            seen INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0,
            edited INTEGER DEFAULT 0
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            contact TEXT NOT NULL,
            UNIQUE(username, contact)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS typing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            is_typing INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(sender, receiver)
        )
    """)

    db.commit()
    db.close()


init_db()


# =========================
# MODELS
# =========================

class RegisterData(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


class LoginData(BaseModel):
    username: str
    password: str


class ChatMessage(BaseModel):
    sender: str
    receiver: str
    message: str
    message_type: str = "text"


class StatusData(BaseModel):
    username: str
    online: bool


class SeenData(BaseModel):
    username: str
    other_user: str


class TypingData(BaseModel):
    sender: str
    receiver: str
    is_typing: bool


class ContactData(BaseModel):
    username: str
    contact: str


class ProfileData(BaseModel):
    username: str
    display_name: Optional[str] = None
    about: Optional[str] = None


class EditMessage(BaseModel):
    message: str


# =========================
# HOME
# =========================

@app.get("/")
def home():
    return {
        "status": "My Chat Server is Online!",
        "version": "2.0"
    }


# =========================
# REGISTER
# =========================

@app.post("/register")
def register(data: RegisterData):

    username = data.username.strip()

    if not username:
        raise HTTPException(400, "Username required")

    if not data.password:
        raise HTTPException(400, "Password required")

    db = get_db()

    existing = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if existing:
        db.close()
        raise HTTPException(400, "Username already exists")

    db.execute("""
        INSERT INTO users
        (username, password, display_name, online, last_seen)
        VALUES (?, ?, ?, 0, ?)
    """, (
        username,
        hash_password(data.password),
        data.display_name or username,
        now()
    ))

    db.commit()
    db.close()

    return {
        "success": True,
        "username": username
    }


# =========================
# LOGIN
# =========================

@app.post("/login")
def login(data: LoginData):

    db = get_db()

    row = db.execute("""
        SELECT *
        FROM users
        WHERE username = ?
        AND password = ?
    """, (
        data.username,
        hash_password(data.password)
    )).fetchone()

    if not row:
        db.close()
        raise HTTPException(401, "Invalid username or password")

    db.execute("""
        UPDATE users
        SET online = 1,
            last_seen = ?
        WHERE username = ?
    """, (
        now(),
        data.username
    ))

    db.commit()
    db.close()

    return {
        "success": True,
        "username": row["username"],
        "display_name": row["display_name"],
        "profile_image": row["profile_image"],
        "about": row["about"]
    }


# =========================
# LOGOUT
# =========================

@app.post("/logout/{username}")
def logout(username: str):

    db = get_db()

    db.execute("""
        UPDATE users
        SET online = 0,
            last_seen = ?
        WHERE username = ?
    """, (
        now(),
        username
    ))

    db.commit()
    db.close()

    return {"success": True}


# =========================
# STATUS
# =========================

@app.get("/status/{username}")
def status(username: str):

    db = get_db()

    row = db.execute("""
        SELECT username, online, last_seen
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    db.close()

    if not row:
        raise HTTPException(404, "User not found")

    return {
        "username": row["username"],
        "online": bool(row["online"]),
        "last_seen": row["last_seen"]
    }


# =========================
# SEND MESSAGE
# =========================

@app.post("/send")
def send_message(data: ChatMessage):

    db = get_db()

    sender = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (data.sender,)
    ).fetchone()

    receiver = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (data.receiver,)
    ).fetchone()

    if not sender:
        db.close()
        raise HTTPException(404, "Sender not found")

    if not receiver:
        db.close()
        raise HTTPException(404, "Receiver not found")

    message_time = now()

    cursor = db.execute("""
        INSERT INTO messages
        (
            sender,
            receiver,
            message,
            message_type,
            timestamp,
            delivered
        )
        VALUES (?, ?, ?, ?, ?, 1)
    """, (
        data.sender,
        data.receiver,
        data.message,
        data.message_type,
        message_time
    ))

    message_id = cursor.lastrowid

    db.commit()
    db.close()

    return {
        "success": True,
        "id": message_id,
        "sender": data.sender,
        "receiver": data.receiver,
        "message": data.message,
        "message_type": data.message_type,
        "timestamp": message_time,
        "delivered": True,
        "seen": False
    }


# =========================
# GET MESSAGES
# =========================

@app.get("/messages/{username}")
def get_messages(username: str):

    db = get_db()

    rows = db.execute("""
        SELECT *
        FROM messages
        WHERE sender = ?
        OR receiver = ?
        ORDER BY id ASC
    """, (
        username,
        username
    )).fetchall()

    db.close()

    result = []

    for row in rows:
        result.append({
            "id": row["id"],
            "sender": row["sender"],
            "receiver": row["receiver"],
            "message": "" if row["deleted"] else row["message"],
            "message_type": row["message_type"],
            "media_url": row["media_url"],
            "file_name": row["file_name"],
            "timestamp": row["timestamp"],
            "delivered": bool(row["delivered"]),
            "seen": bool(row["seen"]),
            "deleted": bool(row["deleted"]),
            "edited": bool(row["edited"])
        })

    return result


# =========================
# SEEN
# =========================

@app.post("/seen")
def seen(data: SeenData):

    db = get_db()

    db.execute("""
        UPDATE messages
        SET seen = 1,
            delivered = 1
        WHERE sender = ?
        AND receiver = ?
    """, (
        data.other_user,
        data.username
    ))

    db.commit()
    db.close()

    return {"success": True}


# =========================
# TYPING
# =========================

@app.post("/typing")
def typing(data: TypingData):

    db = get_db()

    db.execute("""
        INSERT INTO typing
        (sender, receiver, is_typing, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(sender, receiver)
        DO UPDATE SET
        is_typing = excluded.is_typing,
        updated_at = excluded.updated_at
    """, (
        data.sender,
        data.receiver,
        1 if data.is_typing else 0,
        now()
    ))

    db.commit()
    db.close()

    return {"success": True}


@app.get("/typing/{sender}/{receiver}")
def get_typing(sender: str, receiver: str):

    db = get_db()

    row = db.execute("""
        SELECT is_typing, updated_at
        FROM typing
        WHERE sender = ?
        AND receiver = ?
    """, (
        sender,
        receiver
    )).fetchone()

    db.close()

    if not row:
        return {"is_typing": False}

    return {
        "is_typing": bool(row["is_typing"]),
        "updated_at": row["updated_at"]
    }


# =========================
# CONTACTS
# =========================

@app.post("/contacts/add")
def add_contact(data: ContactData):

    db = get_db()

    user = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (data.username,)
    ).fetchone()

    contact = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (data.contact,)
    ).fetchone()

    if not user or not contact:
        db.close()
        raise HTTPException(404, "User not found")

    db.execute("""
        INSERT OR IGNORE INTO contacts
        (username, contact)
        VALUES (?, ?)
    """, (
        data.username,
        data.contact
    ))

    db.commit()
    db.close()

    return {"success": True}


@app.get("/contacts/{username}")
def get_contacts(username: str):

    db = get_db()

    rows = db.execute("""
        SELECT contact
        FROM contacts
        WHERE username = ?
        ORDER BY contact
    """, (username,)).fetchall()

    db.close()

    return [row["contact"] for row in rows]


# =========================
# PROFILE
# =========================

@app.get("/profile/{username}")
def get_profile(username: str):

    db = get_db()

    row = db.execute("""
        SELECT username,
               display_name,
               profile_image,
               about,
               online,
               last_seen
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    db.close()

    if not row:
        raise HTTPException(404, "User not found")

    return dict(row)


@app.post("/profile/update")
def update_profile(data: ProfileData):

    db = get_db()

    db.execute("""
        UPDATE users
        SET display_name = ?,
            about = ?
        WHERE username = ?
    """, (
        data.display_name,
        data.about,
        data.username
    ))

    db.commit()
    db.close()

    return {"success": True}


# =========================
# PROFILE IMAGE
# =========================

@app.post("/profile/image")
async def upload_profile_image(
    username: str = Form(...),
    file: UploadFile = File(...)
):

    db = get_db()

    user = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if not user:
        db.close()
        raise HTTPException(404, "User not found")

    extension = Path(file.filename).suffix
    filename = f"profile_{uuid.uuid4().hex}{extension}"
    filepath = UPLOAD_DIR / filename

    with filepath.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    url = f"/uploads/{filename}"

    db.execute("""
        UPDATE users
        SET profile_image = ?
        WHERE username = ?
    """, (
        url,
        username
    ))

    db.commit()
    db.close()

    return {
        "success": True,
        "profile_image": url
    }


# =========================
# IMAGE / VIDEO / FILE / VOICE
# =========================

@app.post("/upload")
async def upload_message_file(
    sender: str = Form(...),
    receiver: str = Form(...),
    message_type: str = Form(...),
    file: UploadFile = File(...)
):

    allowed = [
        "image",
        "video",
        "file",
        "voice"
    ]

    if message_type not in allowed:
        raise HTTPException(
            400,
            "Invalid message type"
        )

    db = get_db()

    sender_user = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (sender,)
    ).fetchone()

    receiver_user = db.execute(
        "SELECT username FROM users WHERE username = ?",
        (receiver,)
    ).fetchone()

    if not sender_user or not receiver_user:
        db.close()
        raise HTTPException(404, "User not found")

    extension = Path(file.filename).suffix
    filename = f"{uuid.uuid4().hex}{extension}"
    filepath = UPLOAD_DIR / filename

    with filepath.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    media_url = f"/uploads/{filename}"
    message_time = now()

    cursor = db.execute("""
        INSERT INTO messages
        (
            sender,
            receiver,
            message,
            message_type,
            media_url,
            file_name,
            timestamp,
            delivered
        )
        VALUES (?, ?, '', ?, ?, ?, ?, 1)
    """, (
        sender,
        receiver,
        message_type,
        media_url,
        file.filename,
        message_time
    ))

    message_id = cursor.lastrowid

    db.commit()
    db.close()

    return {
        "success": True,
        "id": message_id,
        "message_type": message_type,
        "media_url": media_url,
        "file_name": file.filename,
        "timestamp": message_time
    }


# =========================
# DELETE MESSAGE
# =========================

@app.delete("/messages/{message_id}")
def delete_message(message_id: int):

    db = get_db()

    db.execute("""
        UPDATE messages
        SET deleted = 1
        WHERE id = ?
    """, (message_id,))

    db.commit()
    db.close()

    return {"success": True}


# =========================
# EDIT MESSAGE
# =========================

@app.put("/messages
