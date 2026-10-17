from fastapi import APIRouter, Form, HTTPException, UploadFile, File, BackgroundTasks
from typing import Optional
from datetime import datetime
from datetime import date
from utils import get_ist_now
import json
from database import get_db
from config import BRANCH_METADATA, FACE_MATCH_TOLERANCE, ENFORCE_BEACON_AUTH, COLLEGE_WIFI_SSID
from utils import get_year_label, verify_beacon_token, log_security_event
from schemas import AttendanceUpdate, AttendanceManualCreate, StudentProfileUpdate
from services.face_engine import extract_face_encoding, match_encoding, compute_match_confidence, global_face_index
from services.timetable_service import get_class_info_from_db, check_attendance_window
from services.report_service import generate_attendance_excel, send_email_with_attachment
import logging
logger = logging.getLogger('attendance')

router = APIRouter(tags=['attendance'])

@router.post('/verify')
async def verify_attendance(
    background_tasks: BackgroundTasks,
    photo: UploadFile = File(..., description="Selfie photo for live verification"),
    roll_no: str | None = Form(None, description="Optional Roll Number for faster 1-to-1 matching"),
    device_id: str | None = Form(None, description="Optional Device UUID for hardware binding verification"),
    beacon_token: str | None = Form(None, description="Cryptographic rolling token from classroom beacon"),
    wifi_ssid: str | None = Form(None, description="Current connected Wi-Fi SSID from mobile client")
):
    """
    Verify a student's identity and mark attendance.
    If roll_no is provided, it performs a 1-to-1 verification against the registered encoding.
    Enforces hardware device lock (Anti-Proxy), anti-rogue beacon verification, and strict time windows.
    """
    clean_roll = roll_no.strip().upper() if roll_no and roll_no.strip() else None
    clean_dev = device_id.strip() if device_id and device_id.strip() else None

    # ── 1. Anti-Rogue ESP32 & Beacon Authentication Check ──
    if beacon_token and beacon_token.strip():
        is_beacon_valid, beacon_reason = verify_beacon_token(beacon_token)
        if not is_beacon_valid:
            await log_security_event(
                event_type="ROGUE_BEACON_DETECTED",
                roll_no=clean_roll or "",
                device_id=clean_dev or "",
                details=f"Unauthorized ESP32 beacon signature! {beacon_reason}. Token: '{beacon_token}'",
                severity="CRITICAL"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Classroom Beacon Security Alert: Unauthorized / Cloned ESP32 beacon detected ({beacon_reason}). Attendance must be marked using official classroom beacon."
            )
    elif ENFORCE_BEACON_AUTH:
        await log_security_event(
            event_type="BEACON_MISSING",
            roll_no=clean_roll or "",
            device_id=clean_dev or "",
            details="Rejected: ENFORCE_BEACON_AUTH active but no beacon token received.",
            severity="WARNING"
        )
        raise HTTPException(
            status_code=403,
            detail="Classroom Beacon Required: Official classroom beacon was not detected. Please move closer to the classroom beacon."
        )

    # ── 2. Strict Time Window Check (Server Time) ──
    now = get_ist_now()
    student_section = None
    student_branch = None
    student_year = None

    if clean_roll:
        db_s = await get_db()
        try:
            cur_s = await db_s.execute(
                "SELECT section, branch_code, year FROM students WHERE roll_no = ?", (clean_roll,)
            )
            stu_row = await cur_s.fetchone()
            if stu_row:
                student_section = stu_row["section"] or None
                student_branch = stu_row["branch_code"] or None
                student_year = stu_row["year"] or None
        finally:
            await db_s.close()

    class_info = await get_class_info_from_db(
        now,
        section=student_section,
        branch_code=student_branch,
        year=student_year,
    )

    if not class_info:
        # No timetable configured — use a fallback "Open Session" so face scan always works
        logger.info("No timetable entry found for current time. Using fallback open session.")
        class_info = {
            "subject": "General Attendance",
            "hour": now.hour,
            "start_minute": 0,
            "end_hour": None,
            "end_minute": None,
            "allowed_window_minutes": 1440,  # 24 hours — always open
            "section": student_section or "",
            "branch_code": student_branch or "",
            "branch_name": "",
            "year": student_year or 0,
        }

    is_allowed, time_err, window_end_str = check_attendance_window(class_info, now)
    if not is_allowed:
        raise HTTPException(
            status_code=403,
            detail=time_err,
        )

    try:
        photo_bytes = await photo.read()
        unknown_encoding = await extract_face_encoding(photo_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    current_subject = class_info.get("subject", "Class")

    # --- Load students for matching ---
    db = await get_db()
    try:
        if roll_no and roll_no.strip():
            # ── 1-to-1 Direct Identity Verification (Anti-Proxy Architecture) ──
            clean_roll = roll_no.strip().upper()
            cursor = await db.execute(
                "SELECT roll_no, name, face_encoding, device_id, branch_code, section, year FROM students WHERE roll_no = ?",
                (clean_roll,),
            )
            student = await cursor.fetchone()
            if not student:
                raise HTTPException(
                    status_code=404,
                    detail=f"Student with Roll Number '{clean_roll}' is not enrolled on this server.",
                )

            # Device Binding Security Check (1 Student = 1 Phone Lock)
            registered_dev = (student["device_id"] or "").strip()
            incoming_dev = (device_id or "").strip()

            # Check if incoming device belongs to another student
            if incoming_dev:
                dev_cur = await db.execute(
                    "SELECT roll_no, name FROM students WHERE device_id = ? AND roll_no != ?",
                    (incoming_dev, clean_roll),
                )
                dev_conflict = await dev_cur.fetchone()
                if dev_conflict:
                    await log_security_event(
                        event_type="PROXY_DEVICE_MISMATCH",
                        roll_no=clean_roll or "",
                        device_id=incoming_dev,
                        details=f"Proxy attempt! Phone is bound to {dev_conflict['name']} ({dev_conflict['roll_no']}) while attempting attendance for {student['name']}.",
                        severity="HIGH"
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=f"Device Security Alert! This phone is bound to {dev_conflict['name']} ({dev_conflict['roll_no']}). Proxy attendance for {student['name']} is strictly blocked.",
                    )

            known_encoding = json.loads(student["face_encoding"])
            is_match, distance, confidence = match_encoding(known_encoding, unknown_encoding)
            logger.info(
                "1-to-1 Verification: roll=%s, name=%s, distance=%.4f (threshold=%.2f, confidence=%.1f%%)",
                clean_roll,
                student["name"],
                distance,
                FACE_MATCH_TOLERANCE,
                confidence,
            )
            
            if is_match:
                matched_roll_no = student["roll_no"]
                matched_name = student["name"]
                matched_section = student["section"] or ""
                matched_branch = student["branch_code"] or ""
                matched_year = student["year"] or 1
                match_distance = distance
                match_confidence = confidence
            else:
                await log_security_event(
                    event_type="FACE_MISMATCH",
                    roll_no=clean_roll or "",
                    device_id=incoming_dev,
                    details=f"Face mismatch! (Distance: {distance:.4f} > {FACE_MATCH_TOLERANCE}) for {student['name']}.",
                    severity="HIGH"
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Face mismatch! (Distance: {distance:.4f} > {FACE_MATCH_TOLERANCE}). This does not appear to be {student['name']}. Proxy attendance blocked.",
                )
        else:
            # ── 1:N Global Search Verification ──
            cursor = await db.execute("SELECT roll_no, name, face_encoding, device_id, branch_code, section, year FROM students")
            all_students = await cursor.fetchall()

            if not all_students:
                raise HTTPException(
                    status_code=404,
                    detail="No students enrolled. Please register first.",
                )

            best_match = None
            best_distance = FACE_MATCH_TOLERANCE
            
            for stu in all_students:
                known_encoding = json.loads(stu["face_encoding"])
                is_match, distance, _ = match_encoding(known_encoding, unknown_encoding)
                if is_match and distance < best_distance:
                    best_distance = distance
                    best_match = stu

            if best_match:
                matched_roll_no = best_match["roll_no"]
                matched_name = best_match["name"]
                matched_section = best_match["section"] or ""
                matched_branch = best_match["branch_code"] or ""
                matched_year = best_match["year"] or 1
                student = best_match
                match_distance = best_distance
                match_confidence = compute_match_confidence(best_distance, FACE_MATCH_TOLERANCE)
                
                registered_dev = (student["device_id"] or "").strip()
                incoming_dev = (device_id or "").strip()

                if incoming_dev:
                    dev_cur = await db.execute(
                        "SELECT roll_no, name FROM students WHERE device_id = ? AND roll_no != ?",
                        (incoming_dev, matched_roll_no),
                    )
                    dev_conflict = await dev_cur.fetchone()
                    if dev_conflict:
                        await log_security_event(
                            event_type="PROXY_DEVICE_MISMATCH",
                            roll_no=matched_roll_no,
                            device_id=incoming_dev,
                            details=f"Proxy attempt! Phone bound to {dev_conflict['name']} ({dev_conflict['roll_no']}) while verifying {student['name']}.",
                            severity="HIGH"
                        )
                        raise HTTPException(
                            status_code=403,
                            detail=f"Device Security Alert! This phone is bound to {dev_conflict['name']} ({dev_conflict['roll_no']}). Proxy attendance for {student['name']} is strictly blocked.",
                        )
            else:
                await log_security_event(
                    event_type="FACE_NOT_RECOGNIZED",
                    roll_no=clean_roll or "",
                    device_id=incoming_dev,
                    details="Face not recognized among registered college roster.",
                    severity="WARNING"
                )
                raise HTTPException(
                    status_code=404,
                    detail="Face not recognized among registered students. Please ensure good lighting and look directly at the camera.",
                )

        if registered_dev and incoming_dev and registered_dev != incoming_dev:
            logger.warning(
                "Device Mismatch: student=%s, registered_device=%s, incoming_device=%s",
                matched_roll_no,
                registered_dev,
                incoming_dev,
            )
            await log_security_event(
                event_type="BOUND_DEVICE_MISMATCH",
                roll_no=matched_roll_no,
                device_id=incoming_dev,
                details=f"Student {student['name']} ({matched_roll_no}) registered device '{registered_dev}' != incoming device '{incoming_dev}'.",
                severity="HIGH"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Device Security Alert! Attendance for {student['name']} ({matched_roll_no}) is bound to another phone. Proxy attendance from different devices is strictly blocked.",
            )

        # Auto-bind device on first verify if unassigned
        if not registered_dev and incoming_dev:
            await db.execute("UPDATE students SET device_id = ? WHERE roll_no = ?", (incoming_dev, matched_roll_no))
            await db.commit()

        # --- Prevent duplicate attendance for the same student in THIS subject on today ---
        today = date.today().isoformat()
        dup_cursor = await db.execute(
            "SELECT id FROM attendance WHERE roll_no = ? AND date = ? AND subject = ?",
            (matched_roll_no, today, current_subject),
        )
        duplicate = await dup_cursor.fetchone()
        if duplicate:
            return {
                "status": "already_marked",
                "message": f"Attendance for '{matched_name}' ({matched_roll_no}) is already marked for {current_subject} today.",
                "roll_no": matched_roll_no,
                "name": matched_name,
                "subject": current_subject,
                "section": matched_section,
                "branch_code": matched_branch,
                "year": matched_year,
                "confidence": match_confidence,
                "distance": round(match_distance, 3),
            }

        # --- Mark attendance ---
        now_time_str = now.strftime("%H:%M:%S")
        # Enqueue the write operation to background queue
        background_tasks.add_task(
            save_attendance_background,
            matched_roll_no, today, now_time_str, current_subject, matched_section, matched_branch, matched_year
        )
    finally:
        await db.close()

    return {
        "status": "success",
        "message": f"Attendance marked for '{matched_name}' (Roll No: {matched_roll_no}) in {current_subject}.",
        "roll_no": matched_roll_no,
        "name": matched_name,
        "subject": current_subject,
        "section": matched_section,
        "branch_code": matched_branch,
        "year": matched_year,
        "date": today,
        "time": now_time_str,
        "confidence": match_confidence,
        "distance": round(match_distance, 3),
    }

@router.get('/attendance')
async def get_attendance(
    roll_no: str | None = None,
    date_filter: str | None = None,
    subject_filter: str | None = None,
    branch_filter: str | None = None,
    section_filter: str | None = None,
):
    """
    Retrieve attendance records, optionally filtered by student, date, subject, branch, and section.
    """
    db = await get_db()
    try:
        query = """
            SELECT a.id, a.roll_no, s.name, a.date, a.time, a.subject, a.status,
                   COALESCE(NULLIF(s.branch_code, ''), NULLIF(a.branch_code, ''), '') as branch_code,
                   COALESCE(NULLIF(s.section, ''), NULLIF(a.section, ''), '') as section,
                   COALESCE(s.class_roll_no, '') as class_roll_no
            FROM attendance a 
            JOIN students s ON a.roll_no = s.roll_no 
            WHERE 1=1
        """
        params: list = []

        if roll_no:
            query += " AND a.roll_no = ?"
            params.append(roll_no.strip().upper())
        if date_filter:
            query += " AND a.date = ?"
            params.append(date_filter.strip())
        if subject_filter:
            query += " AND (a.subject = ? OR a.subject LIKE ?)"
            params.extend([subject_filter.strip(), f"%{subject_filter.strip()}%"])
        if branch_filter:
            query += " AND (s.branch_code = ? OR a.branch_code = ?)"
            params.extend([branch_filter.strip().upper(), branch_filter.strip().upper()])
        if section_filter:
            query += " AND (s.section = ? OR a.section = ?)"
            params.extend([section_filter.strip().upper(), section_filter.strip().upper()])

        query += " ORDER BY a.date DESC, a.time DESC"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    finally:
        await db.close()

    records = [
        {
            "id": row["id"],
            "roll_no": row["roll_no"],
            "name": row["name"],
            "date": row["date"],
            "time": row["time"],
            "subject": row["subject"] or "",
            "status": row["status"],
            "branch_code": row["branch_code"],
            "branch_name": BRANCH_METADATA.get(row["branch_code"], {}).get("name", ""),
            "section": row["section"],
            "class_roll_no": row["class_roll_no"],
        }
        for row in rows
    ]

    return {"status": "success", "count": len(records), "records": records}

@router.put('/attendance/{record_id:int}')
async def update_attendance_record(record_id: int, payload: AttendanceUpdate):
    """Update an individual attendance record (subject, status, date, time, section, branch)."""
    db = await get_db()
    try:
        cur = await db.execute("SELECT id, roll_no FROM attendance WHERE id = ?", (record_id,))
        rec = await cur.fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail=f"Attendance record with ID {record_id} not found.")

        updates = []
        params = []
        if payload.status is not None and payload.status.strip():
            updates.append("status = ?")
            params.append(payload.status.strip())
        if payload.subject is not None and payload.subject.strip():
            updates.append("subject = ?")
            params.append(payload.subject.strip())
        if payload.date is not None and payload.date.strip():
            updates.append("date = ?")
            params.append(payload.date.strip())
        if payload.time is not None and payload.time.strip():
            updates.append("time = ?")
            params.append(payload.time.strip())
        if payload.section is not None:
            updates.append("section = ?")
            params.append(payload.section.strip().upper())
        if payload.branch_code is not None:
            updates.append("branch_code = ?")
            params.append(payload.branch_code.strip().upper())

        if updates:
            params.append(record_id)
            await db.execute(f"UPDATE attendance SET {', '.join(updates)} WHERE id = ?", params)
            await db.commit()

        return {"status": "success", "message": f"Attendance record #{record_id} updated successfully."}
    finally:
        await db.close()

@router.delete('/attendance/{record_id:int}')
async def delete_attendance_record(record_id: int):
    """Delete an individual attendance record by ID."""
    db = await get_db()
    try:
        cur = await db.execute("DELETE FROM attendance WHERE id = ?", (record_id,))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Attendance record with ID {record_id} not found.")
        return {"status": "success", "message": f"Attendance record #{record_id} deleted successfully."}
    finally:
        await db.close()

@router.post('/attendance/manual')
async def add_manual_attendance(payload: AttendanceManualCreate):
    """Manually add an attendance record for a student."""
    clean_roll = payload.roll_no.strip().upper()
    db = await get_db()
    try:
        # Check student exists in students table
        cur = await db.execute("SELECT roll_no, name, branch_code, section, year FROM students WHERE roll_no = ?", (clean_roll,))
        stu = await cur.fetchone()
        if not stu:
            # Check college roster
            r_cur = await db.execute("SELECT primary_roll_no, name, branch_code, section, year FROM college_roster WHERE primary_roll_no LIKE ? OR name LIKE ?", (f"%{clean_roll}%", f"%{clean_roll}%"))
            r_stu = await r_cur.fetchone()
            if not r_stu:
                raise HTTPException(status_code=404, detail=f"Student with roll number '{clean_roll}' not found in students or college roster.")
            student_name = r_stu["name"]
            sec = payload.section or r_stu["section"] or ""
            b_code = payload.branch_code or r_stu["branch_code"] or ""
            yr = r_stu["year"] or 1
        else:
            student_name = stu["name"]
            sec = payload.section or stu["section"] or ""
            b_code = payload.branch_code or stu["branch_code"] or ""
            yr = stu["year"] or 1

        rec_date = payload.date.strip() if payload.date else get_ist_now().strftime("%Y-%m-%d")
        rec_time = payload.time.strip() if payload.time else get_ist_now().strftime("%H:%M:%S")
        status_val = payload.status.strip() if payload.status else "Present"
        subj_val = payload.subject.strip()

        await db.execute(
            """
            INSERT OR IGNORE INTO attendance (roll_no, date, time, status, subject, section, branch_code, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_roll, rec_date, rec_time, status_val, subj_val, sec, b_code, yr)
        )
        await db.commit()
        return {
            "status": "success",
            "message": f"Manual attendance marked for '{student_name}' ({clean_roll}) in {subj_val} as {status_val}.",
        }
    finally:
        await db.close()

async def save_attendance_background(roll_no: str, today: str, time_str: str, subject: str, section: str, branch: str, year: int):
    """Background task to safely save attendance to DB without blocking the API response."""
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR IGNORE INTO attendance (roll_no, date, time, subject, status, section, branch_code, year)
               VALUES (?, ?, ?, ?, 'Present', ?, ?, ?)""",
            (roll_no, today, time_str, subject, section, branch, year)
        )
        await db.commit()
        logger.info("Attendance saved in background: roll=%s, date=%s, subject=%s", roll_no, today, subject)
    except Exception as e:
        logger.error("Background attendance save failed: %s", e)
    finally:
        await db.close()


