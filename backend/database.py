import os
import aiosqlite
import logging
from config import DATABASE_PATH, TIMETABLE

logger = logging.getLogger("attendance.db")


async def get_db() -> aiosqlite.Connection:
    """Open and return a SQLite database connection."""
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    """Create SQLite tables if they do not already exist."""
    db = await get_db()
    try:
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                roll_no       TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                face_encoding TEXT NOT NULL,
                is_locked     INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT,
                updated_at    TEXT,
                device_id     TEXT DEFAULT '',
                branch_code   TEXT DEFAULT '',
                branch_name   TEXT DEFAULT '',
                section       TEXT DEFAULT '',
                year          INTEGER DEFAULT 1,
                class_roll_no TEXT DEFAULT ''
            )
            """
        )

        # Safe column migrations (ignore if already exists)
        for col_sql in [
            "ALTER TABLE students ADD COLUMN device_id TEXT DEFAULT ''",
            "ALTER TABLE students ADD COLUMN branch_code TEXT DEFAULT ''",
            "ALTER TABLE students ADD COLUMN branch_name TEXT DEFAULT ''",
            "ALTER TABLE students ADD COLUMN section TEXT DEFAULT ''",
            "ALTER TABLE students ADD COLUMN year INTEGER DEFAULT 1",
            "ALTER TABLE students ADD COLUMN class_roll_no TEXT DEFAULT ''",
            "ALTER TABLE students ADD COLUMN is_locked INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE students ADD COLUMN created_at TEXT",
            "ALTER TABLE students ADD COLUMN updated_at TEXT",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS college_roster (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                year            INTEGER NOT NULL,
                branch_code     TEXT NOT NULL,
                branch_name     TEXT NOT NULL,
                section         TEXT NOT NULL,
                semester        TEXT NOT NULL,
                class_roll_no   TEXT NOT NULL,
                primary_roll_no TEXT NOT NULL UNIQUE,
                name            TEXT NOT NULL
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                roll_no     TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                time        TEXT    NOT NULL,
                subject     TEXT    NOT NULL DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'Present',
                section     TEXT    NOT NULL DEFAULT '',
                branch_code TEXT    NOT NULL DEFAULT '',
                year        INTEGER DEFAULT 1,
                UNIQUE(roll_no, date, subject)
            )
            """
        )

        for col_sql in [
            "ALTER TABLE attendance ADD COLUMN year INTEGER DEFAULT 1",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS timetable (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                day                    TEXT NOT NULL,
                hour                   INTEGER NOT NULL,
                start_minute           INTEGER NOT NULL DEFAULT 0,
                end_hour               INTEGER,
                end_minute             INTEGER,
                allowed_window_minutes INTEGER DEFAULT 15,
                subject                TEXT NOT NULL,
                teacher_email          TEXT NOT NULL DEFAULT '',
                section                TEXT DEFAULT '',
                branch_code            TEXT DEFAULT '',
                branch_name            TEXT DEFAULT '',
                year                   INTEGER DEFAULT 1,
                UNIQUE(day, hour, section)
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS teachers (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                department    TEXT DEFAULT '',
                role          TEXT NOT NULL DEFAULT 'teacher',
                created_at    TEXT
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS password_otps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT NOT NULL,
                otp         TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                used        INTEGER DEFAULT 0
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS security_audit_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                roll_no     TEXT DEFAULT '',
                device_id   TEXT DEFAULT '',
                details     TEXT DEFAULT '',
                severity    TEXT DEFAULT 'WARNING'
            )
            """
        )

        # Seed default teacher accounts if teachers table is empty
        cursor = await db.execute("SELECT COUNT(*) as count FROM teachers")
        count_row = await cursor.fetchone()
        if count_row and count_row["count"] == 0:
            from security import hash_password
            from datetime import datetime
            now_iso = datetime.now().isoformat()

            default_teachers = [
                ("Admin User", "admin@college.edu", hash_password("admin123"), "Administration", "admin"),
                ("Dr. Gupta", "gupta@college.edu", hash_password("teacher123"), "Mathematics", "teacher"),
                ("Prof. Verma", "verma@college.edu", hash_password("teacher123"), "Physics", "teacher"),
                ("Er. Sharma", "sharma@college.edu", hash_password("teacher123"), "Electronics", "teacher"),
                ("Dr. Singh", "singh@college.edu", hash_password("teacher123"), "Computer Science", "teacher"),
                ("Prof. Patel", "patel@college.edu", hash_password("teacher123"), "Chemistry", "teacher"),
                ("Dr. Mehta", "mehta@college.edu", hash_password("teacher123"), "Humanities", "teacher"),
                ("Er. Kumar", "kumar@college.edu", hash_password("teacher123"), "Computer Science", "teacher"),
                ("Prof. Rao", "rao@college.edu", hash_password("teacher123"), "Electronics", "teacher"),
            ]
            await db.executemany(
                """
                INSERT INTO teachers (name, email, password_hash, department, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(t[0], t[1], t[2], t[3], t[4], now_iso) for t in default_teachers],
            )
            logger.info("Seeded default teacher accounts into SQLite database.")

        # Indexes for fast lookups
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_attendance_roll_no ON attendance(roll_no)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_section ON attendance(section, branch_code)",
            "CREATE INDEX IF NOT EXISTS idx_students_device_id ON students(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_roster_search ON college_roster(branch_code, section, year)",
            "CREATE INDEX IF NOT EXISTS idx_teachers_email ON teachers(email)",
            "CREATE INDEX IF NOT EXISTS idx_otps_email ON password_otps(email)",
            "CREATE INDEX IF NOT EXISTS idx_security_timestamp ON security_audit_logs(timestamp)",
        ]:
            try:
                await db.execute(idx)
            except Exception:
                pass

        await db.commit()
        logger.info("SQLite database initialized at: %s", DATABASE_PATH)

    finally:
        await db.close()

