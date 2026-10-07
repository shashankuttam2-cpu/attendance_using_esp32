import { api } from '../api.js';
import { showToast } from '../components/toast.js';

const BRANCH_MAP = {
    'A': 'Computer Science (CSE)',
    'B': 'Electronics (ECE)',
    'C': 'Industrial (IPE)',
    'D': 'Mechanical (ME)',
    'E': 'Instrumentation (ICE)',
    'F': 'Electrical (EE)',
    'G': 'Civil (CE)',
};

export default {
    async render(container) {
        container.innerHTML = `
            <div class="mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 class="text-3xl font-bold text-white flex items-center gap-3">
                        <i class="fas fa-chart-pie text-highlight"></i>
                        Attendance Analytics & Defaulter Tracker
                    </h2>
                    <p class="text-gray-400 mt-1">
                        Identify students below the mandatory 75% attendance threshold and dispatch official warning notices.
                    </p>
                </div>
                <div class="flex items-center gap-3">
                    <button id="btn-bulk-email-defaulters" class="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg border border-red-500 flex items-center gap-2 text-sm font-semibold shadow-sm transition-colors">
                        <i class="fas fa-paper-plane"></i> Email All Defaulters
                    </button>
                    <button id="btn-export-defaulters-csv" class="px-4 py-2 bg-cardbg hover:bg-gray-700 text-white rounded-lg border border-gray-600 flex items-center gap-2 text-sm font-semibold transition-colors">
                        <i class="fas fa-file-csv text-green-400"></i> Export CSV
                    </button>
                </div>
            </div>

            <!-- Top Summary Cards -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <!-- Card 1: Monitored Students -->
                <div class="bg-cardbg rounded-xl border border-gray-700/80 p-5 shadow-lg">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold uppercase tracking-wider text-gray-400">Students Monitored</span>
                        <div class="w-9 h-9 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center text-lg">
                            <i class="fas fa-users"></i>
                        </div>
                    </div>
                    <div id="stat-total-students" class="text-2xl font-bold text-white mt-2">--</div>
                    <span class="text-[11px] text-gray-400 mt-1 block">Active college roster count</span>
                </div>

                <!-- Card 2: Total Defaulters (< 75%) -->
                <div class="bg-cardbg rounded-xl border border-gray-700/80 p-5 shadow-lg">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold uppercase tracking-wider text-amber-400">Defaulters (&lt; 75%)</span>
                        <div class="w-9 h-9 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center text-lg">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                    </div>
                    <div id="stat-total-defaulters" class="text-2xl font-bold text-amber-400 mt-2">--</div>
                    <span id="stat-defaulter-pct" class="text-[11px] text-amber-300 mt-1 block">-- % of monitored pool</span>
                </div>

                <!-- Card 3: Critical Defaulters (< 60%) -->
                <div class="bg-cardbg rounded-xl border border-gray-700/80 p-5 shadow-lg">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold uppercase tracking-wider text-red-400">Critical (&lt; 60%)</span>
                        <div class="w-9 h-9 rounded-lg bg-red-500/10 text-red-400 flex items-center justify-center text-lg">
                            <i class="fas fa-skull-crossbones"></i>
                        </div>
                    </div>
                    <div id="stat-critical-defaulters" class="text-2xl font-bold text-red-400 mt-2">--</div>
                    <span class="text-[11px] text-red-300 mt-1 block">Immediate examination bar risk</span>
                </div>

                <!-- Card 4: College Average % -->
                <div class="bg-cardbg rounded-xl border border-gray-700/80 p-5 shadow-lg">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold uppercase tracking-wider text-emerald-400">College Avg %</span>
                        <div class="w-9 h-9 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center text-lg">
                            <i class="fas fa-chart-line"></i>
                        </div>
                    </div>
                    <div id="stat-avg-pct" class="text-2xl font-bold text-emerald-400 mt-2">-- %</div>
                    <span class="text-[11px] text-gray-400 mt-1 block">Overall attendance average</span>
                </div>
            </div>

            <!-- Filter Controls & Data Table -->
            <div class="bg-cardbg rounded-xl border border-gray-700/80 p-6 shadow-lg">
                <div class="flex flex-col md:flex-row items-center justify-between gap-4 mb-5 border-b border-gray-700/80 pb-4">
                    <!-- Search Input -->
                    <div class="relative w-full md:w-72">
                        <i class="fas fa-search absolute left-3 top-3 text-gray-400 text-xs"></i>
                        <input type="text" id="analytics-search" placeholder="Search by name or roll number..." class="w-full bg-darkbg border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-xs text-gray-200 focus:outline-none focus:border-highlight" />
                    </div>

                    <!-- Dropdown Filters -->
                    <div class="flex flex-wrap items-center gap-3 w-full md:w-auto">
                        <div>
                            <label class="text-[10px] font-semibold text-gray-400 uppercase block mb-0.5">Threshold</label>
                            <select id="filter-threshold" class="bg-darkbg border border-gray-700 rounded-lg px-2.5 py-1.5 text-xs text-amber-300 font-bold">
                                <option value="75" selected>75% Standard</option>
                                <option value="80">80% Strict</option>
                                <option value="60">60% Critical Only</option>
                                <option value="50">50% Emergency</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-[10px] font-semibold text-gray-400 uppercase block mb-0.5">Branch</label>
                            <select id="filter-branch" class="bg-darkbg border border-gray-700 rounded-lg px-2.5 py-1.5 text-xs text-white">
                                <option value="ALL">All Branches</option>
                                <option value="A">Branch A (CSE)</option>
                                <option value="B">Branch B (ECE)</option>
                                <option value="C">Branch C (IPE)</option>
                                <option value="D">Branch D (ME)</option>
                                <option value="E">Branch E (ICE)</option>
                                <option value="F">Branch F (EE)</option>
                                <option value="G">Branch G (CE)</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-[10px] font-semibold text-gray-400 uppercase block mb-0.5">Year</label>
                            <select id="filter-year" class="bg-darkbg border border-gray-700 rounded-lg px-2.5 py-1.5 text-xs text-white">
                                <option value="ALL">All Years</option>
                                <option value="1">1st Year</option>
                                <option value="2">2nd Year</option>
                                <option value="3">3rd Year</option>
                                <option value="4">4th Year</option>
                            </select>
                        </div>
                    </div>
                </div>

                <!-- Table -->
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-gray-800/60 text-gray-400 text-xs uppercase tracking-wider border-b border-gray-700">
                                <th class="py-3 px-3">Roll Number</th>
                                <th class="py-3 px-3">Student Name</th>
                                <th class="py-3 px-3">Branch & Section</th>
                                <th class="py-3 px-3">Held / Attended</th>
                                <th class="py-3 px-3">Attendance %</th>
                                <th class="py-3 px-3">Status</th>
                                <th class="py-3 px-3 text-center">Action</th>
                            </tr>
                        </thead>
                        <tbody id="defaulters-tbody" class="divide-y divide-gray-700/60 text-xs">
                            <tr>
                                <td colspan="7" class="py-8 text-center text-gray-500">
                                    <i class="fas fa-spinner fa-spin text-xl mb-2"></i>
                                    <p>Calculating student attendance percentages...</p>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        let defaultersData = null;

        const loadAnalyticsData = async () => {
            const threshold = document.getElementById('filter-threshold').value;
            const branch = document.getElementById('filter-branch').value;
            const year = document.getElementById('filter-year').value;

            try {
                const res = await api.getDefaulters(threshold, branch === 'ALL' ? '' : branch, '', year === 'ALL' ? '' : year);
                defaultersData = res;

                // Update summary stats
                document.getElementById('stat-total-students').textContent = res.summary.total_students;
                document.getElementById('stat-total-defaulters').textContent = res.summary.total_defaulters;
                document.getElementById('stat-critical-defaulters').textContent = res.summary.critical_defaulters;
                document.getElementById('stat-avg-pct').textContent = `${res.summary.college_avg_percentage}%`;

                const defPct = res.summary.total_students > 0 
                    ? ((res.summary.total_defaulters / res.summary.total_students) * 100).toFixed(1) 
                    : 0;
                document.getElementById('stat-defaulter-pct').textContent = `${defPct}% of monitored pool`;

                renderDefaultersTable(res.defaulters);
            } catch (err) {
                console.error("Failed to load defaulters analytics:", err);
                document.getElementById('defaulters-tbody').innerHTML = `
                    <tr>
                        <td colspan="7" class="py-6 text-center text-red-400">
                            Failed to load analytics: ${err.message}
                        </td>
                    </tr>
                `;
            }
        };

        const renderDefaultersTable = (list) => {
            const tbody = document.getElementById('defaulters-tbody');
            const searchQuery = (document.getElementById('analytics-search')?.value || '').toLowerCase().trim();

            const filtered = (list || []).filter(s => 
                s.roll_no.toLowerCase().includes(searchQuery) ||
                s.name.toLowerCase().includes(searchQuery) ||
                (s.section && s.section.toLowerCase().includes(searchQuery))
            );

            if (filtered.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" class="py-8 text-center text-gray-500">
                            🎉 No defaulter students found for this filter criteria! All students have attendance above threshold.
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = filtered.map(s => {
                const isCritical = s.percentage < 60.0;
                const statusBadge = isCritical
                    ? `<span class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-red-900/60 text-red-300 border border-red-700/50 flex items-center gap-1 w-fit"><i class="fas fa-exclamation-circle"></i> Critical (&lt;60%)</span>`
                    : `<span class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-900/60 text-amber-300 border border-amber-700/50 flex items-center gap-1 w-fit"><i class="fas fa-exclamation-triangle"></i> Warning (&lt;75%)</span>`;

                const pctBadgeClass = isCritical 
                    ? "bg-red-500/20 text-red-400 border-red-500/40" 
                    : "bg-amber-500/20 text-amber-300 border-amber-500/40";

                return `
                    <tr class="hover:bg-darkbg/50 transition-colors">
                        <td class="py-3 px-3 font-mono font-semibold text-gray-200">${s.roll_no}</td>
                        <td class="py-3 px-3 font-medium text-white">${s.name}</td>
                        <td class="py-3 px-3">
                            <span class="text-xs text-yellow-300 font-semibold">Branch ${s.branch_code}</span>
                            <div class="text-[10px] text-gray-400">Sec ${s.section} • ${s.year_label}</div>
                        </td>
                        <td class="py-3 px-3 font-mono">
                            <span class="text-emerald-400 font-bold">${s.attended}</span> / <span class="text-gray-400">${s.total_held}</span>
                            <div class="text-[10px] text-red-400">${s.absent} missed</div>
                        </td>
                        <td class="py-3 px-3">
                            <span class="px-2.5 py-1 rounded-md text-xs font-bold font-mono border ${pctBadgeClass}">
                                ${s.percentage}%
                            </span>
                        </td>
                        <td class="py-3 px-3">${statusBadge}</td>
                        <td class="py-3 px-3 text-center">
                            <button data-roll="${s.roll_no}" data-name="${s.name}" class="btn-send-single-warning text-amber-400 hover:text-amber-300 bg-amber-900/30 hover:bg-amber-900/50 px-2.5 py-1 rounded border border-amber-700/50 text-[11px] font-semibold transition-colors flex items-center gap-1 mx-auto">
                                <i class="fas fa-envelope"></i> Send Notice
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            // Attach single warning button handlers
            tbody.querySelectorAll('.btn-send-single-warning').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const rollNo = btn.getAttribute('data-roll');
                    const name = btn.getAttribute('data-name');
                    
                    if (!confirm(`Dispatch official Attendance Warning Notice to ${name} (${rollNo})?`)) return;

                    btn.disabled = true;
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';

                    try {
                        const res = await api.sendDefaulterWarningEmail([rollNo]);
                        showToast(res.message || `Sent warning notice to ${name}!`, "success");
                    } catch (err) {
                        showToast(`Failed to send email: ${err.message}`, "error");
                    } finally {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-envelope"></i> Send Notice';
                    }
                });
            });
        };

        // Attach Bulk Email Handler
        document.getElementById('btn-bulk-email-defaulters').addEventListener('click', async () => {
            if (!defaultersData || !defaultersData.defaulters || defaultersData.defaulters.length === 0) {
                showToast("No defaulter students found to email.", "info");
                return;
            }

            const count = defaultersData.defaulters.length;
            if (!confirm(`Are you sure you want to dispatch official Warning Notices to ALL ${count} defaulter students?`)) return;

            const btn = document.getElementById('btn-bulk-email-defaulters');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Dispatching Bulk Notices...';

            try {
                const rollNos = defaultersData.defaulters.map(d => d.roll_no);
                const res = await api.sendDefaulterWarningEmail(rollNos);
                showToast(res.message || `Dispatched warning notices to ${count} students!`, "success");
            } catch (err) {
                showToast(`Bulk email error: ${err.message}`, "error");
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-paper-plane"></i> Email All Defaulters';
            }
        });

        // Export CSV Handler
        document.getElementById('btn-export-defaulters-csv').addEventListener('click', () => {
            if (!defaultersData || !defaultersData.defaulters || defaultersData.defaulters.length === 0) {
                showToast("No defaulters data available to export.", "info");
                return;
            }

            let csvStr = "Roll Number,Student Name,Branch,Section,Year,Total Classes,Attended,Absent,Attendance Percentage,Status\n";
            defaultersData.defaulters.forEach(d => {
                csvStr += `"${d.roll_no}","${d.name}","${d.branch_code}","${d.section}","${d.year_label}",${d.total_held},${d.attended},${d.absent},${d.percentage}%,"${d.status}"\n`;
            });

            const blob = new Blob([csvStr], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `IERT_Defaulter_Students_Report_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showToast("Exported defaulter student list as CSV!", "success");
        });

        // Event listeners for filters
        document.getElementById('filter-threshold').addEventListener('change', loadAnalyticsData);
        document.getElementById('filter-branch').addEventListener('change', loadAnalyticsData);
        document.getElementById('filter-year').addEventListener('change', loadAnalyticsData);
        document.getElementById('analytics-search').addEventListener('input', () => {
            if (defaultersData) renderDefaultersTable(defaultersData.defaulters);
        });

        // Initial Load
        await loadAnalyticsData();
    }
};
