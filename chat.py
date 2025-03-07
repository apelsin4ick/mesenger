import sqlite3
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
import json
from datetime import datetime
import ssl

router = APIRouter()

DATABASE = "chats.db"

# Хранение активных WebSocket подключений
active_connections: Dict[int, WebSocket] = {}

class ChatCreate(BaseModel):
    name: str
    creator_id: int
    is_group: bool = False
    participants: List[int] = []  # Добавляем список участников

class ChatUpdate(BaseModel):
    chat_id: int
    name: Optional[str] = None
    avatar_url: Optional[str] = None

class ChatResponse(BaseModel):
    id: int
    name: str
    creator_id: int
    is_group: bool
    last_message: Optional[str] = None
    last_message_time: Optional[str] = None

# создание таблицы чатов
def create_chats_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            creator_id INTEGER NOT NULL,
            is_group BOOLEAN NOT NULL DEFAULT 0,
            avatar_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Создаем таблицу участников чата
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_participants (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chat_id, user_id),
            FOREIGN KEY (chat_id) REFERENCES chats (id)
        )
    """)

    conn.commit()
    conn.close()

create_chats_table()

# Функция для добавления участника в чат
async def add_chat_participant(chat_id: int, user_id: int):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO chat_participants (chat_id, user_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        conn.commit()
    finally:
        conn.close()

@router.get("/list", response_model=List[ChatResponse])
async def get_chats(user_id: int = None):
    if user_id is None:
        raise HTTPException(status_code=400, detail="user_id is required")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        print(f"Getting chats for user {user_id}")
        # Получаем все чаты пользователя
        cursor.execute("""
            SELECT DISTINCT c.id, c.name, c.creator_id, c.is_group,
                   m.content, m.created_at
            FROM chats c
            LEFT JOIN chat_participants cp ON c.id = cp.chat_id
            LEFT JOIN (
                SELECT chat_id, content, created_at
                FROM messages
                WHERE (chat_id, created_at) IN (
                    SELECT chat_id, MAX(created_at)
                    FROM messages
                    GROUP BY chat_id
                )
            ) m ON c.id = m.chat_id
            WHERE cp.user_id = ?
            ORDER BY COALESCE(m.created_at, cp.joined_at) DESC
        """, (user_id,))

        chats = cursor.fetchall()
        print(f"Found {len(chats)} chats for user {user_id}")

        result = [
            {
                "id": chat[0],
                "name": chat[1],
                "creator_id": chat[2],
                "is_group": bool(chat[3]),
                "last_message": chat[4] if chat[4] is not None else None,
                "last_message_time": chat[5] if chat[5] is not None else None
            }
            for chat in chats
        ]
        print(f"Returning chats: {result}")
        return result
    except Exception as e:
        print(f"Error getting chats for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/create", response_model=dict)
async def create_chat(chat: ChatCreate):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        print(f"Creating chat with name: {chat.name}, creator: {chat.creator_id}")
        cursor.execute(
            "INSERT INTO chats (name, creator_id, is_group) VALUES (?, ?, ?)",
            (chat.name, chat.creator_id, chat.is_group)
        )
        chat_id = cursor.lastrowid

        # Добавляем создателя как участника чата
        cursor.execute(
            "INSERT INTO chat_participants (chat_id, user_id) VALUES (?, ?)",
            (chat_id, chat.creator_id)
        )

        # Добавляем остальных участников
        for participant_id in chat.participants:
            if participant_id != chat.creator_id:  # Пропускаем создателя, он уже добавлен
                cursor.execute(
                    "INSERT INTO chat_participants (chat_id, user_id) VALUES (?, ?)",
                    (chat_id, participant_id)
                )

        conn.commit()

        # Получаем обновленный список чатов для всех участников
        all_participants = [chat.creator_id] + [p for p in chat.participants if p != chat.creator_id]
        for participant_id in all_participants:
            participant_chats = await get_chats(user_id=participant_id)
            if participant_id in active_connections:
                try:
                    await active_connections[participant_id].send_json({
                        "type": "chats_update",
                        "chats": participant_chats
                    })
                except Exception as e:
                    print(f"Error sending update to participant {participant_id}: {e}")

        return {"id": chat_id, "message": "Чат успешно создан"}
    except Exception as e:
        print(f"Error creating chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/update")
async def update_chat(chat: ChatUpdate):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Проверяем существование чата
    cursor.execute("SELECT id FROM chats WHERE id = ?", (chat.chat_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Чат не найден")

    cursor.execute(
        "UPDATE chats SET name = ?, avatar_url = ? WHERE id = ?",
        (chat.name, chat.avatar_url, chat.chat_id)
    )
    conn.commit()
    conn.close()

    # Отправляем уведомление об обновлении списка чатов всем подключенным пользователям
    chats = await get_chats()
    for connection in active_connections.values():
        await connection.send_json({
            "type": "chats_update",
            "chats": chats
        })

    return {"message": "Чат успешно обновлен"}

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    try:
        await websocket.accept()
        active_connections[user_id] = websocket

        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                if message["type"] == "request_update":
                    # Получаем обновленный список чатов
                    chats = await get_chats()
                    await websocket.send_json({
                        "type": "chats_update",
                        "chats": chats
                    })
                elif message["type"] == "join_chat":
                    # Пользователь присоединяется к чату
                    chat_id = message["chat_id"]
                    await add_chat_participant(chat_id, user_id)
                    await websocket.send_json({
                        "type": "chat_joined",
                        "chat_id": chat_id
                    })
                elif message["type"] == "leave_chat":
                    # Пользователь покидает чат
                    chat_id = message["chat_id"]
                    await websocket.send_json({
                        "type": "chat_left",
                        "chat_id": chat_id
                    })
            except json.JSONDecodeError:
                print(f"Invalid JSON received from user {user_id}")
                continue
            except WebSocketDisconnect:
                break  # Выходим из цикла при отключении
            except Exception as e:
                print(f"Error processing message from user {user_id}: {e}")
                continue

    except WebSocketDisconnect:
        if user_id in active_connections:
            del active_connections[user_id]
    except Exception as e:
        print(f"WebSocket error for user {user_id}: {e}")
        if user_id in active_connections:
            del active_connections[user_id]

# Функция для отправки сообщения всем подключенным пользователям чата
async def broadcast_message(chat_id: int, message: dict):
    # Получаем список пользователей в чате
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT user_id 
        FROM chat_participants 
        WHERE chat_id = ?
    """, (chat_id,))
    participants = cursor.fetchall()

    # Если чат пустой, добавляем отправителя
    if not participants and 'sender_id' in message:
        cursor.execute(
            "INSERT OR IGNORE INTO chat_participants (chat_id, user_id) VALUES (?, ?)",
            (chat_id, message['sender_id'])
        )
        conn.commit()
        participants = [(message['sender_id'],)]

    conn.close()

    # Отправляем сообщение всем участникам чата
    for participant in participants:
        user_id = participant[0]
        if user_id in active_connections:
            try:
                await active_connections[user_id].send_json({
                    "type": "message",
                    "message": {
                        **message,
                        "sender_name": message.get("sender_name", "Unknown User")
                    }
                })
            except Exception as e:
                print(f"Error sending message to user {user_id}: {e}")
                if user_id in active_connections:
                    del active_connections[user_id]
