const form = document.getElementById('research-form');
const topicInput = document.getElementById('topic-input');
const btnStart = document.getElementById('btn-start');
const timeline = document.getElementById('timeline');
const statusBar = document.getElementById('status-bar');
const statusIndicator = statusBar.querySelector('.status-indicator');
const statusPhase = statusBar.querySelector('.status-phase');
const statusMessage = statusBar.querySelector('.status-message');
const statusDetail = statusBar.querySelector('.status-detail');
const progressBar = document.getElementById('progress-bar');
const progressFill = progressBar.querySelector('.progress-fill');
const progressText = progressBar.querySelector('.progress-text');
const tabs = document.querySelectorAll('.tab');
const tabPanes = document.querySelectorAll('.tab-pane');
const btnHistory = document.getElementById('btn-history');
const historyModal = document.getElementById('history-modal');
const btnCloseModal = document.getElementById('btn-close-modal');

let currentReportPath = null;
let allFindings = {};
let completedQuestions = [];
let researchPlan = [];
let currentPhase = null;

// --- Tab switching ---
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tabPanes.forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
    });
});

// --- History modal ---
btnHistory.addEventListener('click', async () => {
    historyModal.classList.remove('hidden');
    const resp = await fetch('/api/research/history');
    const reports = await resp.json();
    const list = document.getElementById('history-list');
    if (reports.length === 0) {
        list.innerHTML = '<div class="empty-state">暂无历史报告</div>';
    } else {
        list.innerHTML = reports.map(r => `
            <div class="history-item">
                <span>${r.filename}</span>
                <span class="report-date">${new Date(r.created_at).toLocaleString('zh-CN')}</span>
                <a href="/api/reports/${r.filename}" target="_blank">查看</a>
            </div>
        `).join('');
    }
});

btnCloseModal.addEventListener('click', () => historyModal.classList.add('hidden'));
historyModal.addEventListener('click', (e) => {
    if (e.target === historyModal) historyModal.classList.add('hidden');
});

// --- Start research ---
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const topic = topicInput.value.trim();
    if (!topic) return;

    resetUI();
    const maxIter = document.getElementById('max-iterations').value || 3;

    const params = new URLSearchParams({ topic, max_iterations: maxIter });
    const es = new EventSource(`/api/research/stream?${params}`);

    es.addEventListener('phase_start', (e) => {
        const { node, phase } = JSON.parse(e.data);
        currentPhase = phase;
        addLogEntry(phase, getPhaseLabel(node), true);
    });

    es.addEventListener('progress', (e) => {
        const { phase, message, detail, metadata } = JSON.parse(e.data);
        updateStatusBar(phase, message, detail);
        addLogEntry(phase, message, false);
    });

    es.addEventListener('message', (e) => {
        const msg = JSON.parse(e.data);
        if (msg.content) {
            addLogEntry(msg.phase, msg.content, true);
        }
    });

    es.addEventListener('plan', (e) => {
        const { questions } = JSON.parse(e.data);
        researchPlan = questions;
        renderPlan();
    });

    es.addEventListener('search_update', (e) => {
        const { completed_questions } = JSON.parse(e.data);
        completedQuestions = completed_questions || [];
        renderPlan();
    });

    es.addEventListener('findings_update', (e) => {
        const { findings, completed_questions, total } = JSON.parse(e.data);
        allFindings = findings;
        completedQuestions = completed_questions || [];
        renderFindings();
        renderPlan();
    });

    es.addEventListener('gaps', (e) => {
        const { gaps, iteration } = JSON.parse(e.data);
        if (gaps && gaps.length > 0) {
            addLogEntry('gap', `第 ${iteration} 轮：发现 ${gaps.length} 个知识缺口，继续深入...`, true);
        } else {
            addLogEntry('gap', '信息已充分，准备生成报告', true);
        }
    });

    es.addEventListener('report_chunk', (e) => {
        const { content } = JSON.parse(e.data);
        renderReport(content);
        addLogEntry('report', '研究报告生成中...', true);
    });

    es.addEventListener('report_done', (e) => {
        const { path } = JSON.parse(e.data);
        currentReportPath = path;
        addLogEntry('done', `报告已保存: ${path}`, true);
    });

    es.addEventListener('tool_start', (e) => {
        const { tool, input } = JSON.parse(e.data);
        addLogEntry('search', `调用: ${tool}`, true);
    });

    es.addEventListener('tool_end', (e) => {
        const { tool } = JSON.parse(e.data);
        addLogEntry('search', `${tool} 完成`, true);
    });

    es.addEventListener('done', (e) => {
        const { report_path } = JSON.parse(e.data);
        addLogEntry('done', '研究完成', true);
        if (report_path) currentReportPath = report_path;
        btnStart.disabled = false;
        statusBar.classList.add('hidden');
        progressBar.classList.add('hidden');
        currentPhase = null;
        es.close();
    });

    es.addEventListener('error', (e) => {
        let msg = '连接错误';
        try { msg = JSON.parse(e.data).message || msg; } catch (_) {}
        addLogEntry('error', msg, true);
        btnStart.disabled = false;
        statusBar.classList.add('hidden');
    });

    es.onerror = () => {
        btnStart.disabled = false;
        statusBar.classList.add('hidden');
    };

    btnStart.disabled = true;
    statusBar.classList.remove('hidden');
    progressBar.classList.remove('hidden');
});

// --- UI helpers ---
function resetUI() {
    timeline.innerHTML = '';
    allFindings = {};
    completedQuestions = [];
    researchPlan = [];
    currentReportPath = null;
    currentPhase = null;
    statusBar.className = 'status-bar hidden';
    document.getElementById('tab-plan').innerHTML = '<div class="empty-state">等待研究计划生成...</div>';
    document.getElementById('tab-findings').innerHTML = '<div class="empty-state">等待发现提取...</div>';
    document.getElementById('tab-report').innerHTML = '<div class="empty-state">等待报告生成...</div>';
    tabs.forEach(t => t.classList.remove('active'));
    tabPanes.forEach(p => p.classList.remove('active'));
    document.querySelector('[data-tab="plan"]').classList.add('active');
    document.getElementById('tab-plan').classList.add('active');
    progressFill.style.width = '0%';
    progressText.textContent = '';
}

function updateStatusBar(phase, message, detail) {
    const phaseLabels = {
        planning: '规划中', search: '搜索中', extract: '提取中',
        gap: '分析缺口', report: '生成报告',
    };
    statusBar.className = `status-bar active-${phase}`;
    statusPhase.textContent = phaseLabels[phase] || phase;
    statusMessage.textContent = message;
    statusDetail.textContent = detail || '';
}

let lastLogPhase = null;
let lastLogEntry = null;

function addLogEntry(phase, text, isNewEntry = true) {
    const icons = {
        planning: '📋', search: '🔍', extract: '💡', gap: '📊',
        report: '📝', error: '✕', done: '✓',
    };
    const now = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    // 同一阶段的连续进度更新，原地替换最后一条
    if (!isNewEntry && lastLogPhase === phase && lastLogEntry) {
        lastLogEntry.innerHTML = `<span class="entry-time">${now}</span><span class="entry-icon">${icons[phase] || '•'}</span><span class="entry-text">${text}</span>`;
        lastLogEntry.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        return;
    }

    lastLogPhase = phase;
    const entry = document.createElement('div');
    entry.className = `timeline-entry phase-${phase}`;
    entry.innerHTML = `<span class="entry-time">${now}</span><span class="entry-icon">${icons[phase] || '•'}</span><span class="entry-text">${text}</span>`;
    timeline.appendChild(entry);
    lastLogEntry = entry;
    timeline.scrollTop = timeline.scrollHeight;
}

function getPhaseLabel(node) {
    const labels = {
        planning: '📋 规划阶段：分解研究主题',
        search: '🔍 搜索阶段：收集信息',
        extract: '💡 提取阶段：分析关键发现',
        gap_analysis: '📊 缺口分析：评估信息完整性',
        report: '📝 报告生成：撰写研究报告',
    };
    return labels[node] || `阶段: ${node}`;
}

function renderPlan() {
    const el = document.getElementById('tab-plan');
    if (!researchPlan.length) {
        el.innerHTML = '<div class="empty-state">等待研究计划生成...</div>';
        return;
    }
    el.innerHTML = researchPlan.map(q => {
        const done = completedQuestions.includes(q);
        return `<div class="plan-item ${done ? 'done' : ''}">
            <span class="status-icon">${done ? '✓' : '○'}</span>
            <span class="plan-text">${q}</span>
        </div>`;
    }).join('');
}

function renderFindings() {
    const el = document.getElementById('tab-findings');
    const entries = Object.entries(allFindings);
    if (!entries.length) {
        el.innerHTML = '<div class="empty-state">等待发现提取...</div>';
        return;
    }
    el.innerHTML = entries.map(([q, findings]) => `
        <div class="finding-group">
            <h3>${q}</h3>
            <ul>${findings.map(f => `<li>${f}</li>`).join('')}</ul>
        </div>
    `).join('');
}

function renderReport(content) {
    const el = document.getElementById('tab-report');
    el.innerHTML = `<div class="report-content">${marked.parse(content)}</div>`;
    // Switch to report tab
    tabs.forEach(t => t.classList.remove('active'));
    tabPanes.forEach(p => p.classList.remove('active'));
    document.querySelector('[data-tab="report"]').classList.add('active');
    document.getElementById('tab-report').classList.add('active');
}
