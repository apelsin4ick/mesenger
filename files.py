import os
import shutil
from fastapi import APIRouter, UploadFile, File

router = APIRouter()

UPLOAD_DIR = "static/uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


@router.post("/upload")
def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": "Файл загружен", "file_url": f"/{file_path}"}
