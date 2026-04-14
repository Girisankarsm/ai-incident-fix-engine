const demoIncidents = [
    'sqlite3.OperationalError: no such table: users',
    'psycopg2.OperationalError: connection to server at "db", port 5432 failed: FATAL: password authentication failed for user "postgres"',
    'ModuleNotFoundError: No module named fastapi'
];

// Cache DOM elements
const DOM = {
    errorLog: document.getElementById('errorLog'),
    analyzeBtn: document.getElementById('analyzeBtn'),
    demoBtn: document.getElementById('demoBtn'),
    loading: document.getElementById('loading'),
    progressPanel: document.getElementById('progressPanel'),
    progressTitle: document.getElementById('progressTitle'),
    resultSection: document.getElementById('resultSection'),
    stageRecall: document.getElementById('stageRecall'),
    stageReason: document.getElementById('stageReason'),
    stageRespond: document.getElementById('stageRespond')
};

const progressStepEls = {
    recall: DOM.stageRecall,
    reason: DOM.stageReason,
    respond: DOM.stageRespond
};

function setProgressState(stage, message, title) {
    DOM.progressPanel.classList.remove('hidden');
    DOM.progressTitle.textContent = title;
    DOM.loading.textContent = message;

    Object.values(progressStepEls).forEach((element) => {
        element.classList.remove('active', 'done');
    });

    if (stage === 'recall') {
        progressStepEls.recall.classList.add('active');
    }

    if (stage === 'reason') {
        progressStepEls.recall.classList.add('done');
        progressStepEls.reason.classList.add('active');
    }

    if (stage === 'respond') {
        progressStepEls.recall.classList.add('done');
        progressStepEls.reason.classList.add('done');
        progressStepEls.respond.classList.add('active');
    }

    if (stage === 'done') {
        Object.values(progressStepEls).forEach((element) => {
            element.classList.add('done');
        });
    }
}

async function loadSystemStatus() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        document.getElementById('groqStatus').textContent = data.groq_configured ? 'Configured' : 'Fallback';
        document.getElementById('hindsightStatus').textContent = data.hindsight_configured ? 'Ready' : 'Missing key';
        document.getElementById('incidentCount').textContent = data.recent_incident_count ?? 0;
    } catch (_error) {
        document.getElementById('groqStatus').textContent = 'Unavailable';
        document.getElementById('hindsightStatus').textContent = 'Unavailable';
    }
}

function renderIncidentTimeline(incidents) {
    const timeline = document.getElementById('incidentTimeline');
    if (!incidents || incidents.length === 0) {
        timeline.className = 'timeline empty-state';
        timeline.textContent = 'No incidents analyzed yet.';
        return;
    }

    timeline.className = 'timeline';
    timeline.innerHTML = incidents.map((incident) => `
        <article class="timeline-item">
            <div class="timeline-top">
                <span class="timeline-pill ${incident.memory_used ? 'used' : 'new'}">${incident.memory_used ? 'Memory hit' : 'New issue'}</span>
                <time>${new Date(incident.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time>
            </div>
            <p>${incident.error_log}</p>
            <small>Seen before: ${incident.seen_before_count || 0} - Confidence: ${incident.confidence || 0}%</small>
        </article>
    `).join('');
}

function setDemoIncident(index = 0) {
    DOM.errorLog.value = demoIncidents[index % demoIncidents.length];
    DOM.errorLog.focus();
}

function updateResultUI(data) {
    document.getElementById('suggestedFix').textContent = data.solution;
    document.getElementById('classificationText').textContent = data.incident_summary.status;
    document.getElementById('memoryHitsText').textContent = data.incident_summary.memory_hits;
    document.getElementById('resolutionModeText').textContent = data.memory_used ? 'Memory-guided' : 'First-response';
    document.getElementById('signalMode').textContent = data.memory_used ? 'Known incident' : 'New incident';
    document.getElementById('signalConfidence').textContent = `${data.confidence || 0}%`;
    document.getElementById('heroMemoryStatus').textContent = data.memory_used
        ? 'Memory found a similar incident'
        : 'This incident is building fresh memory';
    document.getElementById('similarityStatus').textContent = data.incident_summary.similarity_band;
    document.getElementById('incidentCount').textContent = data.recent_incidents.length;
    const groqStatus = data.system_status.groq_status || (data.system_status.groq_configured ? 'ready' : 'fallback');
    document.getElementById('groqStatus').textContent =
        groqStatus === 'invalid-key' ? 'Invalid key' :
        groqStatus === 'ready' ? 'Ready' :
        'Fallback';
    document.getElementById('hindsightStatus').textContent = data.system_status.hindsight_configured ? 'Ready' : 'Missing key';

    const memoryBadge = document.getElementById('memoryBadge');
    const confidenceBadge = document.getElementById('confidenceBadge');
    const seenBadge = document.getElementById('seenBadge');
    const pastReference = document.getElementById('pastReference');

    confidenceBadge.classList.add('hidden');
    seenBadge.classList.add('hidden');
    pastReference.classList.add('hidden');

    if (data.memory_used) {
        memoryBadge.textContent = 'Hindsight Memory Used';
        memoryBadge.className = 'badge used';

        confidenceBadge.textContent = `Confidence ${data.confidence}%`;
        confidenceBadge.className = 'badge info';
        confidenceBadge.classList.remove('hidden');

        seenBadge.textContent = `Seen Before ${data.seen_before_count}x`;
        seenBadge.className = 'badge info';
        seenBadge.classList.remove('hidden');

        pastReference.classList.remove('hidden');
        document.getElementById('refError').textContent = data.past_reference.error_log;
        document.getElementById('refSolution').textContent = data.past_reference.solution;
        document.getElementById('refTimestamp').textContent = new Date(data.past_reference.timestamp).toLocaleString();
    } else {
        memoryBadge.textContent = 'New Issue Logged';
        memoryBadge.className = 'badge new';
    }



    renderIncidentTimeline(data.recent_incidents);
    resultSection.classList.remove('hidden');
    setProgressState(
        'done',
        data.memory_used
            ? 'Memory recall completed and recommendation updated from a known incident.'
            : 'Analysis completed and a new incident response has been generated.',
        'Incident recommendation ready'
    );
}

// Advanced Analysis Panel functions
function openAdvancedPanel() {
    const data = JSON.parse(sessionStorage.getItem('analysisData') || '{}');
    if (!data.error_category) {
        alert('No analysis data available. Please run an analysis first.');
        return;
    }

    const panel = document.getElementById('advancedAnalysisPanel');
    panel.classList.remove('hidden');

    // Map severity to proper labels and colors
    const severityMap = {
        'CRITICAL': { label: 'Critical', color: '#ff4444', indicator: '●' },
        'HIGH': { label: 'High', color: '#ff8844', indicator: '●' },
        'MEDIUM': { label: 'Medium', color: '#ffdd44', indicator: '●' },
        'LOW': { label: 'Low', color: '#44dd44', indicator: '●' }
    };

    const severity = data.severity || 'LOW';
    const severityInfo = severityMap[severity] || severityMap['LOW'];

    // Format category name
    const categoryLabels = {
        'DATABASE': 'Database',
        'NETWORK': 'Network',
        'IMPORT': 'Import/Module',
        'AUTHENTICATION': 'Authentication',
        'RESOURCE': 'Resource',
        'API': 'API',
        'PERMISSION': 'Permission',
        'UNKNOWN': 'Unknown'
    };

    const categoryName = categoryLabels[data.error_category] || data.error_category;

    // Populate stats with proper formatting
    document.getElementById('adv-category-inline').innerHTML = `<strong style="color: #fff;">${categoryName}</strong>`;
    document.getElementById('adv-severity-inline').innerHTML = `<strong style="color: ${severityInfo.color};">${severityInfo.indicator} ${severityInfo.label}</strong>`;
    
    const priorityScore = data.severity_score || 0;
    const priorityLabel = priorityScore >= 8 ? 'Critical' : priorityScore >= 6 ? 'High' : priorityScore >= 4 ? 'Medium' : 'Low';
    document.getElementById('adv-priority-inline').innerHTML = `<strong style="color: #fff;">${priorityLabel}</strong><br><small style="color: #a3a3a3;">Score: ${priorityScore}/10</small>`;
    
    const score = data.incident_score || {};
    
    // Get percentage values (0-1 from backend becomes 0-100%)
    const getPercentage = (value) => {
        if (typeof value !== 'number') return 0;
        return value > 1 ? value : Math.round(value * 100);
    };
    
    const complexityPercent = getPercentage(score.complexity_score);
    const complexityLabel = complexityPercent >= 80 ? 'Very High' : complexityPercent >= 60 ? 'High' : complexityPercent >= 40 ? 'Medium' : 'Low';
    document.getElementById('adv-complexity-inline').innerHTML = `<strong style="color: #fff;">${complexityLabel}</strong><br><small style="color: #a3a3a3;">Level: ${complexityPercent}%</small>`;

    // Populate detailed cards
    document.getElementById('adv-cat-detail').innerHTML = `
        <strong>${categoryName}</strong><br>
        <small style="color: #a3a3a3;">Error Classification</small>
    `;
    
    document.getElementById('adv-sev-detail').innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
            <span style="color: ${severityInfo.color}; font-size: 18px;">${severityInfo.indicator}</span>
            <strong>${severityInfo.label}</strong>
        </div>
        <small style="color: #a3a3a3;">Severity Score: ${data.severity_score || 0}/10</small>
    `;

    // Root causes with better formatting
    const causesHtml = (data.root_causes || []).length > 0
        ? `<ul style="margin: 0; padding-left: 16px;">${data.root_causes.map(c => `<li style="margin-bottom: 6px; color: #a3a3a3;">${c}</li>`).join('')}</ul>`
        : '<p style="color: #a3a3a3; margin: 0;">No root causes identified</p>';
    document.getElementById('adv-causes-inline').innerHTML = causesHtml;

    // Components with better formatting
    const componentsHtml = (data.affected_components || []).length > 0
        ? `<ul style="margin: 0; padding-left: 16px;">${data.affected_components.map(c => `<li style="margin-bottom: 6px; color: #a3a3a3;">${c}</li>`).join('')}</ul>`
        : '<p style="color: #a3a3a3; margin: 0;">No affected components</p>';
    document.getElementById('adv-components-inline').innerHTML = componentsHtml;

    // Actions with better formatting
    const actionsHtml = (data.recommended_actions || []).length > 0
        ? `<ul style="margin: 0; padding-left: 16px;">${data.recommended_actions.map(a => `<li style="margin-bottom: 6px; color: #a3a3a3;">${a}</li>`).join('')}</ul>`
        : '<p style="color: #a3a3a3; margin: 0;">No recommended actions</p>';
    document.getElementById('adv-actions-inline').innerHTML = actionsHtml;

    // Render radar chart
    setTimeout(() => renderAdvancedChart(data), 100);

    // Scroll to panel
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closeAdvancedPanel() {
    const panel = document.getElementById('advancedAnalysisPanel');
    panel.classList.add('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderAdvancedChart(data) {
    const ctx = document.getElementById('advInlineChart');
    if (!ctx) return;

    const score = data.incident_score || {};
    
    // Extract scores and normalize to 0-100 percentage
    // Backend now returns 0-1 scores, convert to 0-100
    const getPercentage = (value) => {
        if (typeof value !== 'number') return 0;
        // If value is already normalized (0-1), multiply by 100
        return Math.min(100, Math.max(0, value > 1 ? value : value * 100));
    };

    const urgency = getPercentage(score.urgency_score);
    const impact = getPercentage(score.impact_score);
    const complexity = getPercentage(score.complexity_score);
    const recovery = getPercentage(score.recovery_score);

    console.log('Incident Scores:', { urgency, impact, complexity, recovery });

    const chartData = {
        labels: ['Urgency', 'Impact', 'Complexity', 'Recovery Time'],
        datasets: [{
            label: 'Incident Metrics (%)',
            data: [urgency, impact, complexity, 100 - recovery], // Invert recovery for visibility
            borderColor: 'rgba(100, 150, 255, 0.8)',
            backgroundColor: 'rgba(100, 150, 255, 0.2)',
            borderWidth: 2.5,
            pointBackgroundColor: 'rgb(100, 150, 255)',
            pointBorderColor: '#fff',
            pointRadius: 5,
            pointHoverRadius: 7,
            fill: true,
            tension: 0.4
        }]
    };

    if (window.advancedChartInstance) {
        window.advancedChartInstance.destroy();
    }

    window.advancedChartInstance = new Chart(ctx, {
        type: 'radar',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#ffffff',
                        font: { size: 12, weight: 'bold' },
                        padding: 15,
                        boxWidth: 12
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#a3a3a3',
                    borderColor: '#404040',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + Math.round(context.parsed.r) + '%';
                        }
                    }
                }
            },
            scales: {
                r: {
                    min: 0,
                    max: 100,
                    ticks: {
                        color: '#a3a3a3',
                        font: { size: 10 },
                        stepSize: 20,
                        callback: function(value) {
                            return value + '%';
                        }
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: true,
                        circular: true
                    },
                    pointLabels: {
                        color: '#ffffff',
                        font: { size: 12, weight: 'bold' },
                        padding: 12,
                        backdropColor: 'rgba(0, 0, 0, 0.5)',
                        backdropPadding: 4
                    }
                }
            }
        }
    });
}

// Advanced Analysis Button setup
function setupAdvancedAnalysisButton(data) {
    const btn = document.getElementById('advancedAnalysisBtn');
    if (!btn) return;
    // Store the latest analysis data for the advanced dashboard
    sessionStorage.setItem('analysisData', JSON.stringify({
        error_log: data.error_log || DOM.errorLog.value,
        error_category: data.error_category || 'unknown',
        severity: data.severity || 'LOW',
        severity_score: data.severity_score || 0,
        root_causes: data.root_causes || [],
        affected_components: data.affected_components || [],
        incident_score: data.incident_score || {},
        recommended_actions: data.recommended_actions || []
    }));
}

// Patch updateResultUI to call this after rendering
const originalUpdateResultUI = updateResultUI;
updateResultUI = function(data) {
    originalUpdateResultUI(data);
    setupAdvancedAnalysisButton(data);
};

async function analyzeIncident() {
    const errorLog = DOM.errorLog.value.trim();
    if (!errorLog) {
        alert('Please enter an error log.');
        return;
    }

    DOM.analyzeBtn.disabled = true;
    DOM.analyzeBtn.setAttribute('aria-busy', 'true');
    setProgressState('recall', 'Searching Hindsight for similar incidents...', 'Recalling incident memory');
    resultSection.classList.add('hidden');

    try {
        await new Promise((resolve) => setTimeout(resolve, 250));
        setProgressState('reason', 'Comparing prior fixes and preparing the best response path...', 'Building recommendation');

        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: 'local_user',
                error_log: errorLog
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || 'Request failed');
        }

        setProgressState('respond', 'Streaming the final incident guidance into the response panel...', 'Finalizing response');
        await new Promise((resolve) => setTimeout(resolve, 200));
        updateResultUI(data);
    } catch (error) {
        alert(`Analysis failed: ${error.message}`);
        progressPanel.classList.add('hidden');
    } finally {
        DOM.analyzeBtn.disabled = false;
        DOM.analyzeBtn.setAttribute('aria-busy', 'false');
    }
}

analyzeBtn.addEventListener('click', analyzeIncident);

demoBtn.addEventListener('click', () => {
    const nextIndex = Math.floor(Math.random() * demoIncidents.length);
    setDemoIncident(nextIndex);
});

document.querySelectorAll('.chip').forEach((button) => {
    button.addEventListener('click', () => {
        DOM.errorLog.value = button.dataset.demo;
        DOM.errorLog.focus();
    });
});

loadSystemStatus();
setDemoIncident(0);