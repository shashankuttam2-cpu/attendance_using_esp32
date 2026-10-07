import { renderNavbar } from './components/navbar.js';
import dashboardPage from './pages/dashboard.js';
import studentsPage from './pages/students.js';
import attendancePage from './pages/attendance.js';
import classroomPage from './pages/classroom.js?v=1.2';
import timetablePage from './pages/timetable.js';
import analyticsPage from './pages/analytics.js';
import { renderTeachersPage } from './pages/teachers.js';
import { api } from './api.js';
import { showToast } from './components/toast.js';

const routes = {
    '#dashboard': dashboardPage,
    '#analytics': analyticsPage,
    '#timetable': timetablePage,
    '#students': studentsPage,
    '#attendance': attendancePage,
    '#classroom': classroomPage,
    '#teachers': { render: (container) => renderTeachersPage(container) }
};

let lastAlertedId = null;

async function pollLiveClassAlerts() {
    try {
        let teacherEmail = '';
        try {
            const rawUser = localStorage.getItem('currentUser');
            if (rawUser) {
                const u = JSON.parse(rawUser);
                if (u && u.email) teacherEmail = u.email;
            }
        } catch (_) {}

        const res = await api.getLiveAlerts(teacherEmail);
        if (res && res.has_active_alert && res.alerts && res.alerts.length > 0) {
            const alert = res.alerts[0];
            const alertKey = `${alert.subject}_${alert.window_end}`;
            if (lastAlertedId !== alertKey) {
                lastAlertedId = alertKey;
                showToast(alert.alert_title + ' ' + alert.alert_message, 'info');
            }
        }
    } catch (_) {}
}

async function syncUserProfile() {
    try {
        const res = await api.getCurrentUser();
        if (res && res.user) {
            localStorage.setItem('currentUser', JSON.stringify(res.user));
        }
    } catch (_) {}
}

function router() {
    let hash = window.location.hash || '#dashboard';
    if (!window.location.hash) {
        history.replaceState(null, '', '#dashboard');
    }

    const [path, query] = hash.split('?');
    if (path === '#register') {
        window.location.hash = '#students';
        return;
    }
    const page = routes[path] || routes['#dashboard'];
    
    const appDiv = document.getElementById('app');
    if (!appDiv) return;
    
    if (window.currentIntervals) {
        window.currentIntervals.forEach(clearInterval);
    }
    window.currentIntervals = [];

    appDiv.innerHTML = '<div class="flex items-center justify-center h-full"><div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-highlight"></div></div>';
    
    (async () => {
        try {
            await syncUserProfile();
            await page.render(appDiv, query);
            renderNavbar(path);
        } catch (error) {
            console.error(error);
            appDiv.innerHTML = `<div class="text-red-500 p-4 bg-red-500 bg-opacity-20 rounded-lg">Error loading page: ${error.message}</div>`;
        }
    })();
}

document.addEventListener('DOMContentLoaded', async () => {
    await syncUserProfile();
    renderNavbar(window.location.hash || '#dashboard');
    window.addEventListener('hashchange', router);
    router();
    
    // Poll for live class alert notifications every 30 seconds
    pollLiveClassAlerts();
    setInterval(pollLiveClassAlerts, 30000);
});

window.handleLogout = async () => {
    if(confirm("Are you sure you want to log out?")) {
        try {
            await fetch('/api/auth/logout', {method: 'POST'});
        } catch (_) {}
        localStorage.removeItem('currentUser');
        window.location.href = '/login.html';
    }
};


