from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Request
from typing import Optional
from datetime import datetime, date
import json
from database import get_db
from config import BRANCH_METADATA, FACE_MATCH_TOLERANCE, TIMETABLE, ATTENDANCE_WINDOW_MINUTES
from utils import get_year_label, get_ist_now
from schemas import AttendanceUpdate, AttendanceManualCreate, StudentProfileUpdate
from services.timetable_service import get_class_info_from_db, check_attendance_window, get_all_live_classes_from_db
import logging
logger = logging.getLogger('attendance')

router = APIRouter(tags=['timetable'])

@router.get('/timetable')
async def view_timetable(
    section: str | None = None,
    branch_code: str | None = None,
    year: int | None = None,
):
    """Return the timetable filtered by section/branch (or full schedule for admin) with strict attendance windows."""
    clean_sec = section.strip().upper() if section and section.strip() else None
    clean_branch = branch_code.strip().upper() if branch_code and branch_code.strip() else None

    # Infer branch & year from section if missing
    if clean_sec and len(clean_sec) >= 2:
        if not clean_branch:
            clean_branch = clean_sec[0]
        if not year and clean_sec[1].isdigit():
            year = int(clean_sec[1])

    now = get_ist_now()
    current_class = await get_class_info_from_db(now, section=clean_sec, branch_code=clean_branch, year=year)
    all_live_classes = await get_all_live_classes_from_db(now)

    if not current_class and not clean_sec and not clean_branch and all_live_classes:
        current_class = all_live_classes[0]

    window_status = None
    if current_class:
        is_allowed, reason, window_end_str = check_attendance_window(current_class, now)
        window_status = {
            "is_open": is_allowed,
            "window_end": window_end_str,
            "message": "Window open for attendance" if is_allowed else reason,
        }

    schedule = []
    try:
        db = await get_db()
        try:
            where_clauses = []
            params = []

            # If section is provided: Show (1) classes specifically for this section, OR
            # (2) classes for 'All Sections' (empty / ALL) matching branch
            if clean_sec:
                if clean_branch and year:
                    where_clauses.append(
                        """
                        (
                            UPPER(section) = ?
                            OR (
                                (section IS NULL OR section = '' OR UPPER(section) = 'ALL' OR UPPER(section) = 'ALL SECTIONS')
                                AND (branch_code IS NULL OR branch_code = '' OR UPPER(branch_code) = 'ALL' OR UPPER(branch_code) = 'ALL BRANCHES' OR UPPER(branch_code) = ?)
                                AND (year IS NULL OR year = 0 OR year = ?)
                            )
                        )
                        """
                    )
                    params.extend([clean_sec, clean_branch, year])
                elif clean_branch:
                    where_clauses.append(
                        """
                        (
                            UPPER(section) = ?
                            OR (
                                (section IS NULL OR section = '' OR UPPER(section) = 'ALL' OR UPPER(section) = 'ALL SECTIONS')
                                AND (branch_code IS NULL OR branch_code = '' OR UPPER(branch_code) = 'ALL' OR UPPER(branch_code) = 'ALL BRANCHES' OR UPPER(branch_code) = ?)
                            )
                        )
                        """
                    )
                    params.extend([clean_sec, clean_branch])
                else:
                    where_clauses.append(
                        """
                        (
                            UPPER(section) = ?
                            OR (section IS NULL OR section = '' OR UPPER(section) = 'ALL' OR UPPER(section) = 'ALL SECTIONS')
                        )
                        """
                    )
                    params.append(clean_sec)
            elif clean_branch:
                if year:
                    where_clauses.append(
                        """
                        (
                            (UPPER(branch_code) = ? OR branch_code IS NULL OR branch_code = '' OR UPPER(branch_code) = 'ALL')
                            AND (year = ? OR year = 0)
                        )
                        """
                    )
                    params.extend([clean_branch, year])
                else:
                    where_clauses.append("(UPPER(branch_code) = ? OR branch_code IS NULL OR branch_code = '' OR UPPER(branch_code) = 'ALL')")
                    params.append(clean_branch)

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
                SELECT id, day, hour, start_minute, end_hour, end_minute, allowed_window_minutes, subject, teacher_email, 
                       COALESCE(section, '') as section, COALESCE(branch_code, '') as branch_code,
                       COALESCE(branch_name, '') as branch_name, COALESCE(year, 0) as year
                FROM timetable
                {where_sql}
                ORDER BY
                    CASE day
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                        ELSE 8
                    END,
                    hour ASC,
                    start_minute ASC
            """
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            for r in rows:
                h = r["hour"]
                sm = r["start_minute"]
                wm = r["allowed_window_minutes"]
                eh = r["end_hour"]
                em = r["end_minute"]
                we_h = h + (sm + wm) // 60
                we_m = (sm + wm) % 60
                
                if eh is not None and em is not None:
                    time_lbl = f"{h:02d}:{sm:02d} - {eh:02d}:{em:02d}"
                    att_window = f"{h:02d}:{sm:02d} - {eh:02d}:{em:02d} (Strict)"
                else:
                    time_lbl = f"{h:02d}:{sm:02d} - {h:02d}:59"
                    att_window = f"{h:02d}:{sm:02d} - {we_h:02d}:{we_m:02d} ({wm} min window)"

                b_code = r["branch_code"] or ""
                b_name = r["branch_name"] or BRANCH_METADATA.get(b_code, {}).get("name", "")
                sec = r["section"] or ""
                y_val = r["year"] or (int(sec[1]) if len(sec) >= 2 and sec[1].isdigit() else 0)
                schedule.append({
                    "id": r["id"],
                    "day": r["day"],
                    "hour": h,
                    "start_minute": sm,
                    "allowed_window_minutes": wm,
                    "end_hour": eh,
                    "end_minute": em,
                    "time_label": time_lbl,
                    "attendance_window": att_window,
                    "subject": r["subject"],
                    "teacher_email": r["teacher_email"],
                    "branch_code": b_code,
                    "branch_name": b_name,
                    "year": y_val,
                    "year_label": get_year_label(y_val, sec) if y_val else "All Years",
                    "section": sec or "All Sections",
                })
        finally:
            await db.close()
    except Exception as exc:
        logger.warning("Error loading timetable from DB: %s", exc)

    # Only fall back to default general timetable if NO student filter was applied
    if not schedule and not clean_sec and not clean_branch:
        schedule = [
            {
                "id": None,
                "day": day,
                "hour": hour,
                "start_minute": info.get("start_minute", 0),
                "allowed_window_minutes": info.get("allowed_window_minutes", ATTENDANCE_WINDOW_MINUTES),
                "time_label": f"{hour:02d}:{info.get('start_minute', 0):02d} – {hour:02d}:59",
                "attendance_window": f"{hour:02d}:{info.get('start_minute', 0):02d} – {hour:02d}:{info.get('start_minute', 0) + info.get('allowed_window_minutes', ATTENDANCE_WINDOW_MINUTES):02d} ({info.get('allowed_window_minutes', ATTENDANCE_WINDOW_MINUTES)} min window)",
                "subject": info["subject"],
                "teacher_email": info["teacher_email"],
                "branch_code": info.get("branch_code", ""),
                "branch_name": info.get("branch_name", ""),
                "year": info.get("year", 0),
                "year_label": get_year_label(info.get("year"), info.get("section")) if info.get("year") else "All Years",
                "section": info.get("section", "All Sections"),
            }
            for (day, hour), info in sorted(
                TIMETABLE.items(),
                key=lambda item: (
                    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"].index(item[0][0]),
                    item[0][1],
                ),
            )
        ]

    return {
        "status": "success",
        "current_slot": {
            "day": now.strftime("%A"),
            "hour": now.hour,
            "time": now.strftime("%H:%M:%S"),
            "class": current_class,
            "live_classes": all_live_classes,
            "window_status": window_status,
        },
        "timetable": schedule,
    }

@router.post('/timetable')
async def add_timetable_entry(
    day: str = Form(..., description="Day of week (e.g. Monday, Tuesday)"),
    hour: int = Form(..., ge=0, le=23, description="Class start hour (0-23)"),
    start_minute: int = Form(0, ge=0, le=59, description="Start minute (0-59, default 0)"),
    end_hour: int | None = Form(None, ge=0, le=23, description="Class end hour (0-23)"),
    end_minute: int | None = Form(None, ge=0, le=59, description="Class end minute (0-59)"),
    allowed_window_minutes: int = Form(10, ge=1, le=240, description="Allowed attendance window in minutes (default 10)"),
    subject: str = Form(..., description="Subject name"),
    teacher_email: str = Form(..., description="Teacher email address"),
    branch_code: str | None = Form("", description="Optional branch code (A to G)"),
    year: int | None = Form(0, description="Optional year (1, 2, 3, 4)"),
    section: str | None = Form("", description="Optional section (e.g. A1, B2)"),
):
    """Add or update a class in the timetable with branch, year, section, and strict allowed attendance window."""
    clean_day = day.strip().capitalize()
    clean_subject = subject.strip()
    clean_email = teacher_email.strip()
    clean_section = (section or "").strip().upper()
    if clean_section in ("ALL", "ALL SECTIONS", "ALL SECTION"):
        clean_section = ""
    clean_branch = (branch_code or "").strip().upper()
    
    # Infer branch & year from section if not explicitly provided
    if clean_section and not clean_branch and len(clean_section) >= 1:
        clean_branch = clean_section[0]
    final_year = year if (year and year > 0) else (int(clean_section[1]) if len(clean_section) >= 2 and clean_section[1].isdigit() else 0)
    branch_name = BRANCH_METADATA.get(clean_branch, {}).get("name", "")

    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO timetable (day, hour, start_minute, end_hour, end_minute, allowed_window_minutes, subject, teacher_email, section, branch_code, branch_name, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day, hour, section) DO UPDATE SET
                start_minute = excluded.start_minute,
                end_hour = excluded.end_hour,
                end_minute = excluded.end_minute,
                allowed_window_minutes = excluded.allowed_window_minutes,
                subject = excluded.subject,
                teacher_email = excluded.teacher_email,
                section = excluded.section,
                branch_code = excluded.branch_code,
                branch_name = excluded.branch_name,
                year = excluded.year
            """,
            (clean_day, hour, start_minute, end_hour, end_minute, allowed_window_minutes, clean_subject, clean_email, clean_section, clean_branch, branch_name, final_year),
        )
        await db.commit()

        # Keep memory cache updated
        TIMETABLE[(clean_day, hour)] = {
            "subject": clean_subject,
            "teacher_email": clean_email,
            "start_minute": start_minute,
            "end_hour": end_hour,
            "end_minute": end_minute,
            "allowed_window_minutes": allowed_window_minutes,
            "section": clean_section,
            "branch_code": clean_branch,
            "branch_name": branch_name,
            "year": final_year,
        }
    finally:
        await db.close()

    yr_label = f" ({get_year_label(final_year, clean_section)})" if final_year else ""
    return {
        "status": "success",
        "message": f"Class '{clean_subject}' for {branch_name or clean_branch or 'General'}{yr_label} (Section: {clean_section or 'All Sections'}) on {clean_day} at {hour:02d}:{start_minute:02d} saved successfully.",
    }

from pydantic import BaseModel
from typing import List, Optional

class TimetableBatchItem(BaseModel):
    day: str
    hour: int
    start_minute: Optional[int] = 0
    end_hour: Optional[int] = None
    end_minute: Optional[int] = None
    allowed_window_minutes: Optional[int] = 10
    subject: str
    teacher_email: str
    branch_code: Optional[str] = ""
    year: Optional[int] = 0
    section: Optional[str] = ""

class TimetableBatchRequest(BaseModel):
    entries: List[TimetableBatchItem]

@router.post('/timetable/batch')
async def add_bulk_timetable_entries(payload: TimetableBatchRequest):
    """Bulk insert or update a complete weekly timetable schedule for faculty/sections."""
    if not payload.entries:
        raise HTTPException(status_code=400, detail="No schedule entries provided in batch payload.")

    db = await get_db()
    saved_count = 0
    try:
        for entry in payload.entries:
            clean_day = entry.day.strip().capitalize()
            clean_subject = entry.subject.strip()
            clean_email = entry.teacher_email.strip()
            clean_section = (entry.section or "").strip().upper()
            if clean_section in ("ALL", "ALL SECTIONS", "ALL SECTION"):
                clean_section = ""
            clean_branch = (entry.branch_code or "").strip().upper()
            if clean_section and not clean_branch and len(clean_section) >= 1:
                clean_branch = clean_section[0]
            final_year = entry.year if (entry.year and entry.year > 0) else (int(clean_section[1]) if len(clean_section) >= 2 and clean_section[1].isdigit() else 0)
            branch_name = BRANCH_METADATA.get(clean_branch, {}).get("name", "")

            await db.execute(
                """
                INSERT INTO timetable (day, hour, start_minute, end_hour, end_minute, allowed_window_minutes, subject, teacher_email, section, branch_code, branch_name, year)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day, hour, section) DO UPDATE SET
                    start_minute = excluded.start_minute,
                    end_hour = excluded.end_hour,
                    end_minute = excluded.end_minute,
                    allowed_window_minutes = excluded.allowed_window_minutes,
                    subject = excluded.subject,
                    teacher_email = excluded.teacher_email,
                    section = excluded.section,
                    branch_code = excluded.branch_code,
                    branch_name = excluded.branch_name,
                    year = excluded.year
                """,
                (clean_day, entry.hour, entry.start_minute or 0, entry.end_hour, entry.end_minute, entry.allowed_window_minutes or 10, clean_subject, clean_email, clean_section, clean_branch, branch_name, final_year)
            )

            TIMETABLE[(clean_day, entry.hour)] = {
                "subject": clean_subject,
                "teacher_email": clean_email,
                "start_minute": entry.start_minute or 0,
                "end_hour": entry.end_hour,
                "end_minute": entry.end_minute,
                "allowed_window_minutes": entry.allowed_window_minutes or 10,
                "section": clean_section,
                "branch_code": clean_branch,
                "branch_name": branch_name,
                "year": final_year,
            }
            saved_count += 1

        await db.commit()
    finally:
        await db.close()

    return {
        "status": "success",
        "message": f"Successfully uploaded and saved {saved_count} weekly timetable entries!",
        "count": saved_count
    }

@router.get('/timetable/live-alerts')
async def get_live_class_alerts(teacher_email: Optional[str] = None, section: Optional[str] = None):
    """Real-time query for active class notifications & attendance window alerts."""
    now = get_ist_now()
    all_live = await get_all_live_classes_from_db(now)
    
    alerts = []
    for cls in all_live:
        # Filter by teacher email if specified
        if teacher_email and teacher_email.strip():
            if cls.get("teacher_email", "").lower() != teacher_email.strip().lower():
                continue
        # Filter by section if specified
        if section and section.strip():
            sec_cls = cls.get("section", "").upper()
            if sec_cls and sec_cls not in ("ALL", "ALL SECTIONS") and sec_cls != section.strip().upper():
                continue

        win_status = cls.get("window_status", {})
        if win_status.get("is_open"):
            sec_str = f" (Section {cls['section']})" if cls.get('section') else ""
            alerts.append({
                "id": cls.get("id"),
                "subject": cls.get("subject"),
                "teacher_email": cls.get("teacher_email"),
                "section": cls.get("section", "All"),
                "timing_12h": cls.get("timing_12h"),
                "window_end": win_status.get("window_end"),
                "alert_title": f"🔔 Class Alert: {cls.get('subject')}{sec_str} is LIVE!",
                "alert_message": f"Attendance window for {cls.get('subject')} is active now until {win_status.get('window_end')}.",
                "present_count": cls.get("present_count", 0)
            })

    return {
        "status": "success",
        "has_active_alert": len(alerts) > 0,
        "alerts": alerts,
        "server_time": now.strftime("%I:%M:%S %p")
    }

@router.delete('/timetable/{item_id}')
async def delete_timetable_entry(item_id: int):
    """Delete a class from the timetable."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT day, hour, subject FROM timetable WHERE id = ?", (item_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Timetable entry not found.")

        day, hour, subject = row["day"], row["hour"], row["subject"]
        await db.execute("DELETE FROM timetable WHERE id = ?", (item_id,))
        await db.commit()

        if (day, hour) in TIMETABLE:
            del TIMETABLE[(day, hour)]
    finally:
        await db.close()

    return {
        "status": "success",
        "message": f"Class '{subject}' deleted from timetable.",
    }

import io
import csv
import re
from fastapi.responses import PlainTextResponse
from config import API_KEY

def parse_pdf_timetable(file_bytes: bytes) -> list:
    """Parse timetable schedule entries from PDF document bytes using pdfplumber / PyPDF2 fallback."""
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        logger.warning(f"pdfplumber extraction warning ({e}), attempting PyPDF2 fallback...")
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        except Exception as e2:
            raise HTTPException(status_code=400, detail=f"Failed to read PDF file: {e2}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from uploaded PDF file. Please ensure it is a text PDF, not a scanned image.")

    entries = []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    lines = text.splitlines()
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        
        found_day = None
        for d in days:
            if re.search(r'\b' + d + r'\b', line_str, re.IGNORECASE):
                found_day = d
                break
        
        if not found_day:
            continue
        
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', line_str, re.IGNORECASE)
        hour = 9
        start_min = 0
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3).lower() if time_match.group(3) else None
            if ampm == 'pm' and h < 12:
                h += 12
            elif ampm == 'am' and h == 12:
                h = 0
            if 0 <= h <= 23:
                hour = h
                start_min = m

        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line_str)
        teacher_email = email_match.group(0) if email_match else "faculty@iert.ac.in"
        
        sec_match = re.search(r'\b([A-G][1-4])\b', line_str, re.IGNORECASE)
        section = sec_match.group(1).upper() if sec_match else ""
        
        sub_text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', line_str)
        sub_text = re.sub(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', '', sub_text, flags=re.IGNORECASE)
        sub_text = re.sub(r'\b([A-G][1-4])\b', '', sub_text, flags=re.IGNORECASE)
        sub_text = re.sub(r'\d{1,2}(?::\d{2})?\s*(?:am|pm)?', '', sub_text, flags=re.IGNORECASE)
        subject = sub_text.strip(" -:\t,") or "Lecture Session"

        entries.append({
            "day": found_day,
            "hour": hour,
            "start_minute": start_min,
            "allowed_window_minutes": 10,
            "subject": subject,
            "teacher_email": teacher_email,
            "section": section,
            "branch_code": section[0] if section else "",
            "year": int(section[1]) if len(section) >= 2 and section[1].isdigit() else 0
        })

    return entries

@router.get('/timetable/sample-template')
async def download_sample_timetable_csv():
    """Return a downloadable sample CSV template for weekly timetables."""
    sample_csv = "Day,Hour,StartMinute,EndHour,EndMinute,AllowedWindowMinutes,Subject,TeacherEmail,Section,BranchCode,Year\n"
    sample_csv += "Monday,9,0,10,0,10,Mathematics,gupta@college.edu,A1,A,1\n"
    sample_csv += "Monday,10,0,11,0,10,Physics,verma@college.edu,A1,A,1\n"
    sample_csv += "Tuesday,11,0,12,0,10,Basic Electronics,sharma@college.edu,B2,B,2\n"
    sample_csv += "Wednesday,14,0,15,0,10,Data Structures,singh@college.edu,A1,A,1\n"
    sample_csv += "Thursday,9,0,10,0,10,Chemistry,patel@college.edu,C1,C,1\n"
    sample_csv += "Friday,10,0,11,0,10,Computer Networks,kumar@college.edu,A1,A,1\n"

    return PlainTextResponse(
        content=sample_csv,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="iert_weekly_timetable_template.csv"'}
    )

@router.post('/timetable/upload-file')
async def upload_timetable_file(request: Request, file: UploadFile = File(...)):
    """
    Bulk Upload Weekly Timetable Schedule from CSV, Excel (.xlsx/.xls), or PDF file.
    Access Control: Restricted to Teacher or Admin accounts only.
    """
    admin_cookie = request.cookies.get("admin_session")
    teacher_cookie = request.cookies.get("teacher_session")
    api_key_header = request.headers.get("X-API-Key")

    if not admin_cookie and not teacher_cookie and api_key_header != API_KEY:
        raise HTTPException(
            status_code=403, 
            detail="Access Denied: Only Teachers and Administrators are authorized to upload timetable files."
        )

    filename = file.filename.lower()
    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    parsed_entries = []

    # 1. PDF File Parsing
    if filename.endswith(".pdf"):
        parsed_entries = parse_pdf_timetable(content_bytes)

    # 2. Excel (.xlsx / .xls) File Parsing
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
            sheet = wb.active
            rows = list(sheet.iter_rows(values_only=True))
            if not rows or len(rows) < 2:
                raise HTTPException(status_code=400, detail="Excel sheet has no data rows.")
            
            header = [str(c).strip().lower() if c else "" for c in rows[0]]
            for r in rows[1:]:
                if not any(r):
                    continue
                row_dict = {header[i]: str(r[i]).strip() if i < len(r) and r[i] is not None else "" for i in range(len(header))}
                day = row_dict.get("day", "").capitalize()
                subj = row_dict.get("subject", "")
                if not day or not subj:
                    continue

                hour_str = row_dict.get("hour", "9").split(".")[0]
                hour = int(hour_str) if hour_str.isdigit() else 9
                
                sm_str = row_dict.get("startminute", row_dict.get("start_minute", "0")).split(".")[0]
                sm = int(sm_str) if sm_str.isdigit() else 0

                wm_str = row_dict.get("allowedwindowminutes", row_dict.get("allowed_window_minutes", "10")).split(".")[0]
                wm = int(wm_str) if wm_str.isdigit() else 10

                email = row_dict.get("teacheremail", row_dict.get("teacher_email", row_dict.get("email", "")))
                sec = row_dict.get("section", "").upper()
                branch = row_dict.get("branchcode", row_dict.get("branch_code", row_dict.get("branch", ""))).upper()
                
                yr_str = row_dict.get("year", "0").split(".")[0]
                yr = int(yr_str) if yr_str.isdigit() else 0

                parsed_entries.append({
                    "day": day,
                    "hour": hour,
                    "start_minute": sm,
                    "allowed_window_minutes": wm,
                    "subject": subj,
                    "teacher_email": email,
                    "section": sec,
                    "branch_code": branch,
                    "year": yr
                })
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse Excel file: {e}")

    # 3. CSV File Parsing
    elif filename.endswith(".csv") or filename.endswith(".txt"):
        try:
            csv_str = content_bytes.decode("utf-8-sig", errors="ignore")
            reader = csv.DictReader(io.StringIO(csv_str))
            for row in reader:
                norm_row = {k.strip().lower().replace(" ", "").replace("_", ""): v.strip() for k, v in row.items() if k}
                day = norm_row.get("day", "").capitalize()
                subj = norm_row.get("subject", "")
                if not day or not subj:
                    continue

                hour = int(norm_row.get("hour", "9")) if norm_row.get("hour", "").isdigit() else 9
                sm = int(norm_row.get("startminute", "0")) if norm_row.get("startminute", "").isdigit() else 0
                wm = int(norm_row.get("allowedwindowminutes", "10")) if norm_row.get("allowedwindowminutes", "").isdigit() else 10
                email = norm_row.get("teacheremail", norm_row.get("email", ""))
                sec = norm_row.get("section", "").upper()
                branch = norm_row.get("branchcode", norm_row.get("branch", "")).upper()
                yr = int(norm_row.get("year", "0")) if norm_row.get("year", "").isdigit() else 0

                parsed_entries.append({
                    "day": day,
                    "hour": hour,
                    "start_minute": sm,
                    "allowed_window_minutes": wm,
                    "subject": subj,
                    "teacher_email": email,
                    "section": sec,
                    "branch_code": branch,
                    "year": yr
                })
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {e}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload .csv, .xlsx, .xls, or .pdf files.")

    if not parsed_entries:
        raise HTTPException(status_code=400, detail="No valid timetable schedule entries found in uploaded file.")

    batch_req = TimetableBatchRequest(entries=[TimetableBatchItem(**e) for e in parsed_entries])
    res = await add_bulk_timetable_entries(batch_req)
    
    return {
        "status": "success",
        "message": f"Successfully uploaded '{file.filename}'! Parsed and saved {len(parsed_entries)} weekly timetable schedule entries.",
        "parsed_count": len(parsed_entries),
        "filename": file.filename
    }


