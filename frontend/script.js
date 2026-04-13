const demoIncidents = [
    'sqlite3.OperationalError: no such table: users',
    'psycopg2.OperationalError: connection to server at "db", port 5432 failed: FATAL: password authentication failed for user "postgres"',
    'ModuleNotFoundError: No module named fastapi'
];

const errorLogEl = document.getElementById('errorLog');
const analyzeBtn = document.getElementById('analyzeBtn');
const demoBtn = document.getElementById('demoBtn');
const loading = document.getElementById('loading');
const progressPanel = document.getElementById('progressPanel');
const progressTitle = document.getElementById('progressTitle');
const resultSection = document.getElementById('resultSection');
const progressStepEls = {
    recall: document.getElementById('stageRecall'),
    reason: document.getElementById('stageReason'),
    respond: document.getElementById('stageRespond')
};

function setProgressState(stage, message, title) {
    progressPanel.classList.remove('hidden');
    progressTitle.textContent = title;
    loading.textContent = message;

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
    errorLogEl.value = demoIncidents[index % demoIncidents.length];
    errorLogEl.focus();
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

async function analyzeIncident() {
    const errorLog = errorLogEl.value.trim();
    if (!errorLog) {
        alert('Please enter an error log.');
        return;
    }

    analyzeBtn.disabled = true;
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
        analyzeBtn.disabled = false;
    }
}

analyzeBtn.addEventListener('click', analyzeIncident);

demoBtn.addEventListener('click', () => {
    const nextIndex = Math.floor(Math.random() * demoIncidents.length);
    setDemoIncident(nextIndex);
});

document.querySelectorAll('.chip').forEach((button) => {
    button.addEventListener('click', () => {
        errorLogEl.value = button.dataset.demo;
        errorLogEl.focus();
    });
});

loadSystemStatus();
setDemoIncident(0);
