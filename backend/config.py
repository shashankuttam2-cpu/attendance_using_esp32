import os
from typing import Dict, Any, Tuple
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "attendance.db")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")

REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# 0.44 = strict anti-proxy tolerance (blocks re-photographed screens & lookalikes)
FACE_MATCH_TOLERANCE = 0.44  

# SMTP / Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "your_email@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your_app_password")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", SMTP_USER)

ATTENDANCE_WINDOW_MINUTES = 10

BRANCH_METADATA: Dict[str, Dict[str, str]] = {
    "A": {"name": "Computer Science & Engineering", "short": "CSE"},
    "B": {"name": "Electronics Engineering", "short": "ECE"},
    "C": {"name": "Industrial & Production Engineering", "short": "IPE"},
    "D": {"name": "Mechanical Engineering", "short": "ME"},
    "E": {"name": "Instrumentation & Control Engineering", "short": "ICE"},
    "F": {"name": "Electrical Engineering", "short": "EE"},
    "G": {"name": "Civil Engineering", "short": "CE"},
}

# Fallback memory timetable
TIMETABLE: Dict[Tuple[str, int], Dict[str, Any]] = {
    ("Monday", 9):  {"subject": "Mathematics",        "teacher_email": "gupta@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Monday", 10): {"subject": "Physics",             "teacher_email": "verma@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Monday", 11): {"subject": "Basic Electronics",   "teacher_email": "sharma@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Monday", 14): {"subject": "Data Structures",     "teacher_email": "singh@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Tuesday", 9):  {"subject": "Chemistry",          "teacher_email": "patel@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Tuesday", 10): {"subject": "English",            "teacher_email": "mehta@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Tuesday", 11): {"subject": "Basic Electronics",  "teacher_email": "sharma@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Tuesday", 14): {"subject": "Computer Networks",  "teacher_email": "kumar@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Wednesday", 9):  {"subject": "Mathematics",      "teacher_email": "gupta@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Wednesday", 10): {"subject": "Physics",          "teacher_email": "verma@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Wednesday", 11): {"subject": "Digital Logic",    "teacher_email": "rao@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Wednesday", 14): {"subject": "Data Structures",  "teacher_email": "singh@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Thursday", 9):  {"subject": "Chemistry",         "teacher_email": "patel@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Thursday", 10): {"subject": "English",           "teacher_email": "mehta@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Thursday", 11): {"subject": "Basic Electronics", "teacher_email": "sharma@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Thursday", 14): {"subject": "Computer Networks", "teacher_email": "kumar@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Friday", 9):  {"subject": "Mathematics",         "teacher_email": "gupta@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Friday", 10): {"subject": "Physics Lab",         "teacher_email": "verma@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Friday", 11): {"subject": "Digital Logic",       "teacher_email": "rao@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
    ("Friday", 14): {"subject": "Project Work",        "teacher_email": "singh@college.edu", "start_minute": 0, "allowed_window_minutes": 10},
}

# Application API Security Key
API_KEY = os.getenv("API_KEY", "default_secret_api_key_for_dev_only")

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

# Cryptographic Anti-Rogue ESP32 & Beacon Authentication
BEACON_SECRET_KEY = os.getenv("BEACON_SECRET_KEY", "iert_smart_classroom_beacon_secret_2026")
ENFORCE_BEACON_AUTH = os.getenv("ENFORCE_BEACON_AUTH", "false").lower() == "true"
COLLEGE_WIFI_SSID = os.getenv("COLLEGE_WIFI_SSID", "IERT_Campus_WiFi")

