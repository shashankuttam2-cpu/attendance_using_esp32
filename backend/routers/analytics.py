import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, List
from database import get_db
from config import BRANCH_METADATA, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL
from utils import get_year_label
from security import get_api_key

logger = logging.getLogger("attendance.analytics")

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(get_api_key)])

class WarningEmailRequest(BaseModel):
    roll_nos: List[str]
    custom_message: Optional[str] = None

@router.get("/defaulters")
async def get_defaulter_students(
    threshold: int = 75,
    branch_code: Optional[str] = None,
    section: Optional[str] = None,
    year: Optional[int] = None,
    subject: Optional[str] = None,
):
    """
    Calculate attendance percentages for registered students and identify defaulters (< threshold%).
    """
    clean_branch = branch_code.strip().upper() if branch_code and branch_code.strip() and branch_code.strip().upper() != "ALL" else None
    clean_sec = section.strip().upper() if section and section.strip() and section.strip().upper() != "ALL" else None
    clean_sub = subject.strip() if subject and subject.strip() and subject.strip().upper() != "ALL" else None

    db = await get_db()
    try:
        # 1. Fetch students matching branch/section/year filter
        where_clauses = []
        params = []
        if clean_branch:
            where_clauses.append("UPPER(branch_code) = ?")
            params.append(clean_branch)
        if clean_sec:
            where_clauses.append("UPPER(section) = ?")
            params.append(clean_sec)
        if year and year > 0:
            where_clauses.append("year = ?")
            params.append(year)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        students_cur = await db.execute(
            f"""
            SELECT roll_no, name, branch_code, branch_name, section, year, class_roll_no
            FROM students
            {where_sql}
            ORDER BY branch_code ASC, section ASC, roll_no ASC
            """,
            params
        )
        students = await students_cur.fetchall()

        if not students:
            # Fallback to college_roster if students table is empty
            roster_cur = await db.execute(
                f"""
                SELECT primary_roll_no as roll_no, name, branch_code, branch_name, section, year, class_roll_no
                FROM college_roster
                {where_sql}
                ORDER BY branch_code ASC, section ASC, primary_roll_no ASC
                """,
                params
            )
            students = await roster_cur.fetchall()

        # 2. Get total unique classes held per section/branch
        att_where = []
        att_params = []
        if clean_sub:
            att_where.append("LOWER(subject) = LOWER(?)")
            att_params.append(clean_sub)

        att_where_sql = f"WHERE {' AND '.join(att_where)}" if att_where else ""

        # Total held slots by date/subject/section
        held_cur = await db.execute(
            f"""
            SELECT section, branch_code, COUNT(DISTINCT date || '_' || subject) as held_count
            FROM attendance
            {att_where_sql}
            GROUP BY section, branch_code
            """,
            att_params
        )
        held_rows = await held_cur.fetchall()
        held_map = {(r["branch_code"] or "", r["section"] or ""): r["held_count"] for r in held_rows}

        # Overall total held classes in DB as benchmark fallback
        total_benchmark_cur = await db.execute(
            f"SELECT COUNT(DISTINCT date || '_' || subject) as total FROM attendance {att_where_sql}",
            att_params
        )
        benchmark_row = await total_benchmark_cur.fetchone()
        overall_benchmark = max(benchmark_row["total"] if benchmark_row else 10, 10)

        # 3. Get student attendance counts
        pres_cur = await db.execute(
            f"""
            SELECT roll_no, COUNT(id) as present_count
            FROM attendance
            {att_where_sql}
            GROUP BY roll_no
            """,
            att_params
        )
        pres_rows = await pres_cur.fetchall()
        pres_map = {r["roll_no"]: r["present_count"] for r in pres_rows}

        defaulter_list = []
        all_students_list = []
        critical_count = 0
        warning_count = 0
        total_pct_sum = 0

        for s in students:
            r_no = s["roll_no"]
            b_code = s["branch_code"] or ""
            sec = s["section"] or ""
            y_val = s["year"] or 1
            
            held = held_map.get((b_code, sec), held_map.get(("", sec), overall_benchmark))
            held = max(held, 10) # minimum denominator for realistic percentage

            attended = pres_map.get(r_no, 0)
            pct = round((attended / held) * 100, 1)
            total_pct_sum += pct

            status_label = "Good"
            status_color = "emerald"
            if pct < 60.0:
                status_label = "Critical Defaulter"
                status_color = "red"
                critical_count += 1
            elif pct < threshold:
                status_label = "Warning Defaulter"
                status_color = "amber"
                warning_count += 1

            student_obj = {
                "roll_no": r_no,
                "name": s["name"],
                "branch_code": b_code,
                "branch_name": s["branch_name"] or BRANCH_METADATA.get(b_code, {}).get("name", b_code),
                "section": sec or "General",
                "year": y_val,
                "year_label": get_year_label(y_val, sec),
                "total_held": held,
                "attended": attended,
                "absent": max(held - attended, 0),
                "percentage": pct,
                "status": status_label,
                "status_color": status_color,
                "is_defaulter": pct < threshold
            }

            all_students_list.append(student_obj)
            if pct < threshold:
                defaulter_list.append(student_obj)

        # Sort defaulters with lowest percentage first
        defaulter_list.sort(key=lambda x: x["percentage"])

        avg_pct = round(total_pct_sum / len(all_students_list), 1) if all_students_list else 0.0

        return {
            "status": "success",
            "threshold": threshold,
            "summary": {
                "total_students": len(all_students_list),
                "total_defaulters": len(defaulter_list),
                "critical_defaulters": critical_count,
                "warning_defaulters": warning_count,
                "college_avg_percentage": avg_pct
            },
            "defaulters": defaulter_list,
            "all_students": all_students_list
        }
    finally:
        await db.close()

@router.get("/summary-charts")
async def get_analytics_summary_charts():
    """Return branch-wise and year-wise attendance metrics for dashboard charts."""
    db = await get_db()
    try:
        branch_cur = await db.execute(
            """
            SELECT s.branch_code, COUNT(a.id) as present_total, COUNT(DISTINCT s.roll_no) as student_count
            FROM students s
            LEFT JOIN attendance a ON s.roll_no = a.roll_no
            GROUP BY s.branch_code
            """
        )
        branch_rows = await branch_cur.fetchall()
        
        branch_data = []
        for r in branch_rows:
            b_code = r["branch_code"] or "General"
            b_name = BRANCH_METADATA.get(b_code, {}).get("short", b_code)
            branch_data.append({
                "branch_code": b_code,
                "branch_name": b_name,
                "total_scans": r["present_total"],
                "student_count": r["student_count"]
            })

        return {
            "status": "success",
            "branch_metrics": branch_data
        }
    finally:
        await db.close()

@router.post("/send-warning-email")
async def send_defaulter_warning_emails(payload: WarningEmailRequest):
    """Dispatch official attendance warning email to defaulter students."""
    if not payload.roll_nos:
        raise HTTPException(status_code=400, detail="No student roll numbers provided.")

    db = await get_db()
    sent_count = 0
    try:
        for r_no in payload.roll_nos:
            s_cur = await db.execute("SELECT name, branch_code, section, year FROM students WHERE roll_no = ?", (r_no,))
            student = await s_cur.fetchone()
            if not student:
                continue

            name = student["name"]
            sec = student["section"] or "N/A"
            email = f"{r_no.lower()}@college.edu"

            subject = f"⚠️ OFFICIAL ATTENDANCE WARNING NOTICE — IERT Prayagraj ({r_no})"
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial, sans-serif; background-color: #0b1324; color: #e2e8f0; padding: 20px;">
                <div style="max-width: 500px; margin: 0 auto; background-color: #141d33; padding: 24px; border-radius: 10px; border: 1px solid #1f2d4d;">
                    <h2 style="color: #ef4444; margin-top: 0;">⚠️ ATTENDANCE WARNING NOTICE</h2>
                    <p>Dear <strong>{name}</strong> (Roll No: <code>{r_no}</code>),</p>
                    <p>This is an official automated notification from the <strong>IERT Prayagraj Academic Cell</strong>.</p>
                    <p>Your current attendance status in Section <strong>{sec}</strong> has fallen below the mandatory <strong>75% threshold</strong>.</p>
                    <div style="background-color: #7f1d1d; color: #fca5a5; padding: 12px; border-radius: 6px; font-weight: bold; margin: 16px 0;">
                        Status: CRITICAL DEFAULTER (&lt; 75% Attendance)
                    </div>
                    <p style="font-size: 13px; color: #94a3b8;">Please attend all upcoming scheduled lectures immediately to maintain your eligibility for term examinations.</p>
                    <hr style="border: none; border-top: 1px solid #1f2d4d; margin: 20px 0;" />
                    <div style="font-size: 11px; color: #64748b; text-align: center;">IERT Prayagraj &bull; Smart Attendance Portal</div>
                </div>
            </body>
            </html>
            """
            
            if SMTP_USER and SMTP_PASSWORD and SMTP_USER != "your_email@gmail.com":
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = SENDER_EMAIL or SMTP_USER
                    msg["To"] = email
                    msg.attach(MIMEText(html_body, "html"))
                    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                        server.starttls()
                        server.login(SMTP_USER, SMTP_PASSWORD)
                        server.sendmail(msg["From"], [email], msg.as_string())
                except Exception as e:
                    logger.error(f"Failed to send warning email to {email}: {e}")

            logger.info(f"Dispatched attendance warning email for {name} ({r_no})")
            sent_count += 1

    finally:
        await db.close()

    return {
        "status": "success",
        "message": f"Successfully sent attendance warning notices to {sent_count} student(s)!",
        "sent_count": sent_count
    }
