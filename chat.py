import sqlite3
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

DATABASE = "chats.db"

class ChatCreate(BaseModel):
    name: str
    creator_id: int
    is_group: bool

class ChatUpdate(BaseModel):
    chat_id: int
    name: Optional[str] = None
    avatar_url: Optional[str] = None

# создание таблицы чатов
def create_chats_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            creator_id INTEGER NOT NULL,
            is_group BOOLEAN NOT NULL,
            avatar_url TEXT
        )
    """)
    conn.commit()
    conn.close()

create_chats_table()

@router.post("/create")
def create_chat(chat: ChatCreate):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chats (name, creator_id, is_group) VALUES (?, ?, ?)",
                   (chat.name, chat.creator_id, chat.is_group))
    conn.commit()
    conn.close()
    return {"message": "Чат создан"}

@router.post("/update")
def update_chat(chat: ChatUpdate):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("UPDATE chats SET name = ?, avatar_url = ? WHERE id = ?",
                   (chat.name, chat.avatar_url, chat.chat_id))
    conn.commit()
    conn.close()
    return {"message": "Чат обновлен"}
