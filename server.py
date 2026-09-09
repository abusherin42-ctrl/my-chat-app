from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

messages = []
users = []


class RegisterUser(BaseModel):
    username: str


class ChatMessage(BaseModel):
    sender: str
    receiver: str
    message: str


@app.get("/")
def home():
    return {
        "status": "My Chat Server is Online! 🚀"
    }


@app.post("/register")
def register_user(data: RegisterUser):

    username = data.username.strip()

    if not username:
        return {
            "success": False,
            "message": "Username cannot be empty"
        }

    if username not in users:
        users.append(username)

    return {
        "success": True,
        "username": username
    }


@app.get("/users")
def get_users():

    return {
        "users": users
    }


@app.post("/send")
def send_message(data: ChatMessage):

    messages.append({
        "sender": data.sender,
        "receiver": data.receiver,
        "message": data.message,
        "time": datetime.now().isoformat()
    })

    return {
        "success": True,
        "message": "Message sent! ✅"
    }


@app.get("/messages/{username}")
def get_messages(username: str):

    result = []

    for msg in messages:

        if (
            msg["receiver"] == username
            or msg["sender"] == username
        ):
            result.append(msg)

    return result
