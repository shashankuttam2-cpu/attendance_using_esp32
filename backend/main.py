"""
Modular Face Recognition Attendance System — FastAPI + SQLite
=============================================================
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db
from config import REPORTS_DIR

# Import routers
from routers import admin, students, attendance, timetable, roster, auth, teachers, analytics
from fastapi import Depends
from security import get_api_key

logger = logging.getLogger("attendance")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title="Face Recognition Attendance System",
    version="2.0.0",
    description="Modularized API for Face Registration & Attendance",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "Modular Face Recognition Attendance System API is running.",
    }

# Include all modular routers
app.include_router(auth.router)
app.include_router(teachers.router)
app.include_router(analytics.router)
app.include_router(admin.router, dependencies=[Depends(get_api_key)])
app.include_router(students.router, dependencies=[Depends(get_api_key)])
app.include_router(attendance.router, dependencies=[Depends(get_api_key)])
app.include_router(timetable.router, dependencies=[Depends(get_api_key)])
app.include_router(roster.router, dependencies=[Depends(get_api_key)])


# Serve the generated Excel reports
@app.get("/reports/{filename}")
async def get_report(filename: str):
    file_path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(file_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(file_path, filename=filename)

# Mount the static web dashboard
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSSIBLE_FRONTEND_PATHS = [
    os.path.join(os.path.dirname(BASE_DIR), "frontend"),
    os.path.join(BASE_DIR, "frontend"),
    r"D:\RFID\frontend",
]

for fpath in POSSIBLE_FRONTEND_PATHS:
    if os.path.isdir(fpath) and os.path.isfile(os.path.join(fpath, "index.html")):
        app.mount("/", StaticFiles(directory=fpath, html=True), name="frontend")
        break
