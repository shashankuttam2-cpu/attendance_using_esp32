import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Response, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional
from config import ADMIN_USERNAME, ADMIN_PASSWORD, API_KEY
from database import get_db
from security import verify_password, hash_password
from utils import send_email_otp

router = APIRouter(tags=['auth'])

class LoginData(BaseModel):
    username: str
    password: str

@router.post('/api/auth/login')
async def login(data: LoginData, response: Response):
    username_input = data.username.strip()
    password_input = data.password.strip()

    # 1. Check SQLite teachers database table by email or username
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, email, password_hash, department, role FROM teachers WHERE LOWER(email) = LOWER(?) OR LOWER(name) = LOWER(?)",
            (username_input, username_input)
        )
        teacher = await cursor.fetchone()
        if teacher and verify_password(password_input, teacher["password_hash"]):
            user_payload = {
                "id": teacher["id"],
                "name": teacher["name"],
                "email": teacher["email"],
                "role": teacher["role"],
                "department": teacher["department"] or "Faculty",
            }
            # Set cookies for session
            cookie_key = "admin_session" if teacher["role"] == "admin" else "teacher_session"
            response.set_cookie(
                key=cookie_key,
                value=API_KEY,
                httponly=False,
                samesite="lax",
                max_age=86400 * 30,
                path="/"
            )
            return {
                "status": "success",
                "message": f"Welcome back, {teacher['name']}!",
                "user": user_payload
            }
    finally:
        await db.close()

    # 2. Fallback check for system admin credentials (.env or default config)
    if username_input == ADMIN_USERNAME and password_input == ADMIN_PASSWORD:
        user_payload = {
            "id": 0,
            "name": "System Administrator",
            "email": "admin@college.edu",
            "role": "admin",
            "department": "Administration",
        }
        response.set_cookie(
            key="admin_session",
            value=API_KEY,
            httponly=False,
            samesite="lax",
            max_age=86400 * 30,
            path="/"
        )
        return {
            "status": "success",
            "message": "Logged in successfully as Administrator",
            "user": user_payload
        }

    raise HTTPException(status_code=401, detail="Invalid email/username or password.")

@router.get('/api/auth/me')
async def get_current_user_profile(request: Request):
    admin_cookie = request.cookies.get("admin_session")
    teacher_cookie = request.cookies.get("teacher_session")

    if admin_cookie == API_KEY:
        return {
            "status": "success",
            "user": {
                "id": 0,
                "name": "System Administrator",
                "email": "admin@college.edu",
                "role": "admin",
                "department": "Administration"
            }
        }
    
    if teacher_cookie:
        return {
            "status": "success",
            "user": {
                "id": 1,
                "name": "Faculty Member",
                "email": "teacher@college.edu",
                "role": "teacher",
                "department": "Faculty"
            }
        }

    return {"status": "unauthenticated", "user": None}

class SendOTPData(BaseModel):
    email: str

class VerifyOTPData(BaseModel):
    email: str
    otp: str
    new_password: str

class ForgotPasswordData(BaseModel):
    email: str
    new_password: str
    otp: Optional[str] = None

@router.post('/api/auth/send-otp')
async def send_otp(data: SendOTPData):
    """Generate 6-digit OTP, store in database password_otps, and send via email/SMTP."""
    email_input = data.email.strip().lower()
    if not email_input:
        raise HTTPException(status_code=400, detail="Email address is required.")

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, email FROM teachers WHERE LOWER(email) = LOWER(?)",
            (email_input,)
        )
        teacher = await cursor.fetchone()
        if not teacher:
            raise HTTPException(status_code=404, detail=f"No faculty account found with email '{email_input}'.")

        # Generate 6-digit numeric OTP code
        otp_code = str(random.randint(100000, 999999))
        now = datetime.now()
        expires_at = (now + timedelta(minutes=10)).isoformat()
        created_at = now.isoformat()

        # Invalidate previous unused OTPs for this email
        await db.execute(
            "UPDATE password_otps SET used = 1 WHERE LOWER(email) = LOWER(?) AND used = 0",
            (email_input,)
        )

        # Insert new OTP record into database
        await db.execute(
            """
            INSERT INTO password_otps (email, otp, expires_at, created_at, used)
            VALUES (?, ?, ?, ?, 0)
            """,
            (email_input, otp_code, expires_at, created_at)
        )
        await db.commit()

        # Dispatch email or log fallback
        send_email_otp(teacher["email"], otp_code, teacher["name"])

        return {
            "status": "success",
            "message": f"OTP sent to '{teacher['email']}'. Valid for 10 minutes."
        }
    finally:
        await db.close()

@router.post('/api/auth/verify-otp')
async def verify_otp(data: VerifyOTPData):
    """Verify OTP code from database and update teacher password hash."""
    email_input = data.email.strip().lower()
    otp_input = data.otp.strip()
    new_pwd = data.new_password.strip()

    if not email_input or not otp_input or not new_pwd:
        raise HTTPException(status_code=400, detail="Email, OTP code, and new password are required.")

    if len(new_pwd) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters long.")

    db = await get_db()
    try:
        cursor = await db.execute("SELECT id, name FROM teachers WHERE LOWER(email) = LOWER(?)", (email_input,))
        teacher = await cursor.fetchone()
        if not teacher:
            raise HTTPException(status_code=404, detail=f"No faculty account found with email '{email_input}'.")

        # Query active OTP
        cur_otp = await db.execute(
            """
            SELECT id, expires_at, used FROM password_otps
            WHERE LOWER(email) = LOWER(?) AND otp = ? AND used = 0
            ORDER BY id DESC LIMIT 1
            """,
            (email_input, otp_input)
        )
        otp_row = await cur_otp.fetchone()
        if not otp_row:
            raise HTTPException(status_code=400, detail="Invalid OTP code. Please check your email and try again.")

        expires_at_dt = datetime.fromisoformat(otp_row["expires_at"])
        if datetime.now() > expires_at_dt:
            raise HTTPException(status_code=400, detail="OTP code has expired. Please click 'Send OTP' to get a new code.")

        # Mark OTP as used
        await db.execute("UPDATE password_otps SET used = 1 WHERE id = ?", (otp_row["id"],))

        # Update teacher password hash
        hashed = hash_password(new_pwd)
        await db.execute("UPDATE teachers SET password_hash = ? WHERE id = ?", (hashed, teacher["id"]))
        await db.commit()

        return {
            "status": "success",
            "message": f"Password reset successful for {teacher['name']}. You can now log in with your new password."
        }
    finally:
        await db.close()

@router.post('/api/auth/forgot-password')
async def forgot_password(data: ForgotPasswordData):
    """OTP-backed password reset endpoint. Strictly requires valid OTP."""
    if not data.otp or not data.otp.strip():
        raise HTTPException(status_code=400, detail="OTP code is strictly required to reset password. Please click 'Send OTP' first.")

    return await verify_otp(VerifyOTPData(email=data.email, otp=data.otp, new_password=data.new_password))

@router.post('/api/auth/logout')
async def logout(response: Response):
    response.delete_cookie("admin_session")
    response.delete_cookie("teacher_session")
    return {"status": "success", "message": "Logged out successfully"}
