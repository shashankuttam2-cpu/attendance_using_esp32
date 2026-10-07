const API_BASE_URL = "";

const API_KEY = "";

async function fetchWithHandler(url, options = {}) {
    options.credentials = "include"; options.headers = {
        ...options.headers,
        "X-API-Key": API_KEY
    };
    try {
        const response = await fetch(`${API_BASE_URL}${url}`, options);
        if (!response.ok) {
            let errorText = await response.text();
            try {
                const parsed = JSON.parse(errorText);
                if (parsed.detail) errorText = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail);
            } catch (_) {}
            if (response.status === 401 || response.status === 403) { window.location.href = "/login.html"; await new Promise(r => setTimeout(r, 5000)); } throw new Error(errorText || `API Error: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error("API Request Failed:", error);
        throw error;
    }
}

export const api = {
    // Health Check
    healthCheck: () => fetchWithHandler("/health"),

    // Student & Verification
    registerStudent: (formData) => fetchWithHandler("/register", {
        method: "POST",
        body: formData
    }),
    verifyFace: (formData) => fetchWithHandler("/verify", {
        method: "POST",
        body: formData
    }),
    getStudents: (branchCode = '', section = '', q = '') => {
        let query = [];
        if (branchCode) query.push(`branch_code=${encodeURIComponent(branchCode)}`);
        if (section) query.push(`section=${encodeURIComponent(section)}`);
        if (q) query.push(`q=${encodeURIComponent(q)}`);
        const qs = query.length ? `?${query.join('&')}` : '';
        return fetchWithHandler(`/students${qs}`);
    },
    deleteStudent: (rollNo) => fetchWithHandler(`/students/${encodeURIComponent(rollNo)}`, {
        method: "DELETE"
    }),
    updateStudent: (rollNo, data) => fetchWithHandler(`/students/${encodeURIComponent(rollNo)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    }),
    unlockStudent: (rollNo) => fetchWithHandler(`/admin/students/${encodeURIComponent(rollNo)}/unlock`, {
        method: "POST"
    }),
    lockStudent: (rollNo) => fetchWithHandler(`/admin/students/${encodeURIComponent(rollNo)}/lock`, {
        method: "POST"
    }),
    getAdminSettings: () => fetchWithHandler("/admin/settings"),
    toggleRegistration: (open) => fetchWithHandler("/admin/settings/registration", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ open })
    }),

    // College Master Roster (7 Branches & 4 Years — A1 to G4)
    getRosterBranches: () => fetchWithHandler("/roster/branches"),
    getRosterStudents: (section = '', branchCode = '', year = '', q = '', limit = 200, offset = 0) => {
        let query = [];
        if (section) query.push(`section=${encodeURIComponent(section)}`);
        if (branchCode) query.push(`branch_code=${encodeURIComponent(branchCode)}`);
        if (year) query.push(`year=${encodeURIComponent(year)}`);
        if (q) query.push(`q=${encodeURIComponent(q)}`);
        query.push(`limit=${limit}`);
        query.push(`offset=${offset}`);
        return fetchWithHandler(`/roster/students?${query.join('&')}`);
    },
    lookupRosterStudent: (rollNo) => fetchWithHandler(`/roster/lookup/${encodeURIComponent(rollNo)}`),
    getRosterStats: () => fetchWithHandler("/roster/stats"),

    // Attendance Records
    getAttendance: (rollNo = '', date = '', subject = '', branch = '', section = '') => {
        let query = [];
        if (rollNo) query.push(`roll_no=${encodeURIComponent(rollNo)}`);
        if (date) query.push(`date_filter=${encodeURIComponent(date)}`);
        if (subject) query.push(`subject_filter=${encodeURIComponent(subject)}`);
        if (branch) query.push(`branch_filter=${encodeURIComponent(branch)}`);
        if (section) query.push(`section_filter=${encodeURIComponent(section)}`);
        const qs = query.length ? `?${query.join('&')}` : '';
        return fetchWithHandler(`/attendance${qs}`);
    },
    updateAttendance: (id, data) => fetchWithHandler(`/attendance/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    }),
    deleteAttendance: (id) => fetchWithHandler(`/attendance/${id}`, {
        method: "DELETE"
    }),
    markManualAttendance: (data) => fetchWithHandler("/attendance/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    }),

    // Timetable & Strict 10-Min Window Management
    getTimetable: () => fetchWithHandler("/timetable"),
    addTimetableEntry: (formData) => fetchWithHandler("/timetable", {
        method: "POST",
        body: formData
    }),
    uploadTimetableFile: (formData) => fetchWithHandler("/timetable/upload-file", {
        method: "POST",
        body: formData
    }),
    batchAddTimetable: (data) => fetchWithHandler("/timetable/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    }),
    getLiveAlerts: (teacherEmail = '', section = '') => fetchWithHandler(`/timetable/live-alerts?${teacherEmail ? `teacher_email=${encodeURIComponent(teacherEmail)}&` : ''}${section ? `section=${encodeURIComponent(section)}` : ''}`),
    deleteTimetableEntry: (id) => fetchWithHandler(`/timetable/${id}`, {
        method: "DELETE"
    }),
    resetStudentDevice: (rollNo) => fetchWithHandler(`/admin/students/${encodeURIComponent(rollNo)}/reset-device`, {
        method: "POST"
    }),
    endClass: (formData) => fetchWithHandler("/admin/end-class", {
        method: "POST",
        body: formData
    }),

    // Auth & Teacher Management
    getCurrentUser: () => fetchWithHandler("/api/auth/me"),
    sendOTP: (email) => fetchWithHandler("/api/auth/send-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
    }),
    verifyOTP: (email, otp, new_password) => fetchWithHandler("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp, new_password })
    }),
    forgotPassword: (email, new_password, otp = null) => fetchWithHandler("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, new_password, otp })
    }),
    getTeachers: () => fetchWithHandler("/api/teachers"),
    addTeacher: (data) => fetchWithHandler("/api/teachers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    }),
    resetTeacherPassword: (id, new_password) => fetchWithHandler(`/api/teachers/${id}/reset-password`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password })
    }),
    deleteTeacher: (id) => fetchWithHandler(`/api/teachers/${id}`, {
        method: "DELETE"
    }),

    // Analytics & Defaulter Tracker
    getDefaulters: (threshold = 75, branchCode = '', section = '', year = '', subject = '') => {
        let query = [`threshold=${threshold}`];
        if (branchCode) query.push(`branch_code=${encodeURIComponent(branchCode)}`);
        if (section) query.push(`section=${encodeURIComponent(section)}`);
        if (year) query.push(`year=${encodeURIComponent(year)}`);
        if (subject) query.push(`subject=${encodeURIComponent(subject)}`);
        return fetchWithHandler(`/api/analytics/defaulters?${query.join('&')}`);
    },
    sendDefaulterWarningEmail: (rollNos, customMessage = '') => fetchWithHandler("/api/analytics/send-warning-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roll_nos: rollNos, custom_message: customMessage })
    }),
    getAnalyticsCharts: () => fetchWithHandler("/api/analytics/summary-charts")
};


