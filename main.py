import sqlite3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth import router as auth_router
from chat import router as chat_router
from message import router as message_router
from files import router as files_router
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене замените на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Подключаем роутеры
app.include_router(files_router, prefix="/files")
app.include_router(auth_router, prefix="/auth")
app.include_router(chat_router, prefix="/chats")
app.include_router(message_router, prefix="/messages")

@app.get("/")
def root():
    return {"message": "Мессенджер API работает!"}

def get_db_connection(db_name="users.db"):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    return conn

if __name__ == "__main__":
    import os
    from uvicorn import run as uvicorn_run

    port = int(os.getenv("PORT", 2020))  # Получаем порт из переменных окружения
    uvicorn_run(app, host="127.0.0.1", port=port)