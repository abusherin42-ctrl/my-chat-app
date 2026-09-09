from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

messages = []


class ChatMessage(BaseModel):
    sender: str
    receiver: str
    message: str


@app.get("/")
def home():
    return {
        "status": "My Chat Server is Online! 🚀"
    }


@app.post("/send")
def send_message(data: ChatMessage):

    messages.append({
        "sender": data.sender,
        "receiver": data.receiver,
        "message": data.message
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

    return resultclient.py
