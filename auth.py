import bcrypt
import sqlite3
import datetime

import jwt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from typing import Optional

SECRET_KEY = "zzz"  # Секретный ключ для подписи токена
ALGORITHM = "HS256"  # Алгоритм шифрования
TOKEN_EXPIRATION_MINUTES = 60  # Время жизни токена

router = APIRouter()
DATABASE = "users.db"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class User(BaseModel):
    login: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

# Функция создания токена
def create_token(user_id: int):
    payload = {
        "sub": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_EXPIRATION_MINUTES)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# Функция декодирования токена
def decode_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истек")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Неверный токен")


def create_users_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


create_users_table()


@router.post("/register")
def register(user: User):
    hashed_password = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (login, password) VALUES (?, ?)",
                       (user.login, hashed_password.decode()))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    finally:
        conn.close()

    return {"message": "Регистрация успешна"}


@router.post("/login", response_model=TokenResponse)
def login(user: User):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM users WHERE login = ?", (user.login,))
    user_data = cursor.fetchone()
    conn.close()

    if user_data is None or not bcrypt.checkpw(user.password.encode(), user_data[1].encode()):
        raise HTTPException(status_code=401, detail="Неверные логин или пароль")

    # Создаем токен
    user_id = user_data[0]
    token = create_token(user_id)

    return {"access_token": token, "token_type": "bearer"}


# Защищенный эндпоинт для проверки авторизации
@router.get("/me")
def get_me(token: str = Depends(oauth2_scheme)):
    user_id = decode_token(token)
    return {"user_id": user_id}