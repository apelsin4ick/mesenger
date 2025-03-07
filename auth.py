import sqlite3
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
from datetime import datetime
from chat import broadcast_message

router = APIRouter()

DATABASE = "chats.db"
USERS_DATABASE = "users.db"  # База данных с пользователями

# Хранение WebSocket подключений
connections: Dict[int, WebSocket] = {}

class MessageCreate(BaseModel):
    content: str
    chat_id: int
    sender_id: int

class MessageResponse(BaseModel):
    id: int
    content: str
    sender_id: int
    chat_id: int
    created_at: str
    sender_name: str

def get_user_name(user_id: int) -> str:
    try:
        conn = sqlite3.connect(USERS_DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT login FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "Unknown User"
    except Exception as e:
        print(f"Error getting username: {e}")
        return "Unknown User"

def setup_database():
    with sqlite3.connect(DATABASE) as conn:
        # Создаем временную таблицу с правильной структурой
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            sender_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (id)
        )
        """)

        # Проверяем существование старой таблицы
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        if cursor.fetchone():
            # Копируем данные из старой таблицы в новую
            try:
                conn.execute("""
                INSERT INTO messages_new (id, content, sender_id, chat_id, created_at)
                SELECT id, content, sender_id, chat_id, COALESCE(created_at, CURRENT_TIMESTAMP)
                FROM messages
                """)
                # Удаляем старую таблицу
                conn.execute("DROP TABLE messages")
            except sqlite3.OperationalError:
                # Если что-то пошло не так, просто создаем новую таблицу
                conn.execute("DROP TABLE IF EXISTS messages")

        # Переименовываем новую таблицу
        conn.execute("ALTER TABLE messages_new RENAME TO messages")

setup_database()

# WebSocket подключение
@router.websocket("/ws/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: int):
    await websocket.accept()
    connections[user_id] = websocket

    try:
        while True:
            # Ожидаем сообщение от клиента
            message = await websocket.receive_json()

            # Сохраняем сообщение в БД
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                cursor.execute(
                    """INSERT INTO messages (chat_id, sender_id, content, created_at) 
                    VALUES (?, ?, ?, ?)""",
                    (message["chat_id"], user_id, message["content"], now)
                )

                msg_id = cursor.lastrowid

                # Отправляем сообщение всем подключенным пользователям
                new_message = {
                    "id": msg_id,
                    "chat_id": message["chat_id"],
                    "sender_id": user_id,
                    "content": message["content"],
                    "created_at": now
                }

                for connection in connections.values():
                    await connection.send_json(new_message)

    except WebSocketDisconnect:
        # Удаляем соединение при отключении
        if user_id in connections:
            del connections[user_id]

# HTTP эндпоинты
@router.post("/", response_model=MessageResponse)
async def create_message(message: MessageCreate):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        # Проверяем существование чата
        cursor.execute("SELECT id FROM chats WHERE id = ?", (message.chat_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Чат не найден")

        # Получаем имя отправителя из базы данных пользователей
        sender_name = get_user_name(message.sender_id)

        # Создаем сообщение
        cursor.execute(
            "INSERT INTO messages (content, sender_id, chat_id) VALUES (?, ?, ?)",
            (message.content, message.sender_id, message.chat_id)
        )
        message_id = cursor.lastrowid

        # Получаем созданное сообщение
        cursor.execute(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,)
        )
        message_data = cursor.fetchone()
        conn.commit()

        # Формируем ответ
        response = {
            "id": message_data[0],
            "content": message_data[1],
            "sender_id": message_data[2],
            "chat_id": message_data[3],
            "created_at": message_data[4],
            "sender_name": sender_name
        }

        # Отправляем сообщение через WebSocket
        await broadcast_message(message.chat_id, response)

        return response
    finally:
        conn.close()

@router.get("/", response_model=List[MessageResponse])
async def get_messages(chat_id: int):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT m.* FROM messages m
            WHERE m.chat_id = ?
            ORDER BY m.created_at ASC
        """, (chat_id,))
        messages = cursor.fetchall()

        return [
            {
                "id": msg[0],
                "content": msg[1],
                "sender_id": msg[2],
                "chat_id": msg[3],
                "created_at": msg[4],
                "sender_name": get_user_name(msg[2])
            }
            for msg in messages
        ]
    finally:
        conn.close()

@router.put("/edit")
async def edit_message(message_id: int, new_content: str):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Получаем информацию о сообщении
    cursor.execute("SELECT chat_id, sender_id FROM messages WHERE id = ?", (message_id,))
    message_info = cursor.fetchone()

    if not message_info:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")

    chat_id, sender_id = message_info

    # Обновляем сообщение
    cursor.execute(
        "UPDATE messages SET content = ?, created_at = ? WHERE id = ?",
        (new_content, datetime.now().isoformat(), message_id)
    )
    conn.commit()
    conn.close()

    # Отправляем обновленное сообщение через WebSocket
    for user_id, connection in connections.items():
        await connection.send_json({
            "type": "message_edit",
            "id": message_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": new_content,
            "created_at": datetime.now().isoformat()
        })

    return {"message": "Сообщение изменено"}

@router.delete("/delete")
async def delete_message(message_id: int):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Получаем информацию о сообщении
    cursor.execute("SELECT chat_id, sender_id FROM messages WHERE id = ?", (message_id,))
    message_info = cursor.fetchone()

    if not message_info:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")

    chat_id, sender_id = message_info

    # Удаляем сообщение
    cursor.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()

    # Отправляем уведомление об удалении через WebSocket
    for user_id, connection in connections.items():
        await connection.send_json({
            "type": "message_delete",
            "id": message_id,
            "chat_id": chat_id,
            "sender_id": sender_id
        })

    return {"message": "Сообщение удалено"}