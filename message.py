import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

router = APIRouter()

DATABASE = "chats.db"

class Message(BaseModel):
    chat_id: int
    sender_id: int
    content: str

class MessageResponse(BaseModel):
    id: int
    chat_id: int
    sender_id: int
    content: str
    timestamp: str

# Создание таблицы сообщений
def create_messages_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

create_messages_table()

@router.post("/send")
def send_message(message: Message):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (chat_id, sender_id, content) VALUES (?, ?, ?)",
                   (message.chat_id, message.sender_id, message.content))
    conn.commit()
    conn.close()
    return {"message": "Сообщение отправлено"}


@router.put("/edit")
def edit_message(message_id: int, new_content: str):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("UPDATE messages SET content = ? WHERE id = ?", (new_content, message_id))
    conn.commit()
    conn.close()
    return {"message": "Сообщение изменено"}

@router.delete("/delete")
def delete_message(message_id: int):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return {"message": "Сообщение удалено"}

@router.get("/receiving/{chat_id}", response_model=List[MessageResponse])
def get_messages(chat_id: int):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, chat_id, sender_id, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp", (chat_id,))
    messages = cursor.fetchall()
    conn.close()

    if not messages:
        raise HTTPException(status_code=404, detail="Сообщений нет")

    return [{"id": msg[0], "chat_id": msg[1], "sender_id": msg[2], "content": msg[3], "timestamp": msg[4]} for msg in messages]