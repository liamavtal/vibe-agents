/**
 * Vibe Agents - Frontend Application
 * Handles WebSocket communication and UI updates
 */

class VibeAgents {
    constructor() {
        this.ws = null;
        this.files = {};
        this.currentFile = null;

        // DOM elements
        this.form = document.getElementById('build-form');
        this.input = document.getElementById('prompt-input');
        this.buildBtn = document.getElementById('build-btn');
        this.agentFeed = document.getElementById('agent-feed');
        this.fileTabs = document.getElementById('file-tabs');
        this.codeView = document.getElementById('code-view');
        this.statusIndicator = document.getElementById('status-indicator');
        this.statusText = document.getElementById('status-text');

        this.init();
    }

    init() {
        // Connect WebSocket
        this.connect();

        // Handle form submission
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.startBuild();
        });
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('Connected to Vibe Agents');
            this.setStatus('ready', 'Connected');
        };

        this.ws.onclose = () => {
            console.log('Disconnected, reconnecting...');
            this.setStatus('error', 'Disconnected');
            setTimeout(() => this.connect(), 2000);
        };

        this.ws.onerror = (err) => {
            console.error('WebSocket error:', err);
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
    }

    setStatus(state, text) {
        this.statusIndicator.className = 'status-indicator';
        if (state === 'active') {
            this.statusIndicator.classList.add('active');
        }
        this.statusText.textContent = text;
    }

    startBuild() {
        const prompt = this.input.value.trim();
        if (!prompt || !this.ws) return;

        // Clear previous state
        this.files = {};
        this.currentFile = null;
        this.agentFeed.innerHTML = '';
        this.fileTabs.innerHTML = '';
        this.codeView.innerHTML = '<code>// Building...</code>';

        // Update UI
        this.setStatus('active', 'Building...');
        this.buildBtn.disabled = true;
        this.buildBtn.querySelector('.btn-text').hidden = true;
        this.buildBtn.querySelector('.btn-loading').hidden = false;

        // Send build request
        this.ws.send(JSON.stringify({
            type: 'build',
            prompt: prompt
        }));
    }

    handleMessage(message) {
        const { type, data } = message;

        switch (type) {
            case 'status':
                this.setStatus('active', data);
                break;

            case 'phase':
                this.addPhaseIndicator(data);
                break;

            case 'agent_message':
                this.addAgentMessage(data);
                break;

            case 'plan_ready':
                this.showPlan(data);
                break;

            case 'task_start':
                this.addTaskIndicator(data);
                break;

            case 'file_created':
            case 'file_updated':
                this.addFileMessage(data);
                break;

            case 'file_saved':
                this.addSystemMessage(`Saved: ${data}`);
                break;

            case 'review_complete':
                this.showReview(data);
                break;

            case 'error':
                this.addErrorMessage(data);
                break;

            case 'build_complete':
                this.handleBuildComplete(data);
                break;

            case 'complete':
                this.setStatus('ready', 'Complete!');
                break;
        }
    }

    addPhaseIndicator(phase) {
        const el = document.createElement('div');
        el.className = 'phase-indicator';
        el.textContent = phase;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addAgentMessage(data) {
        const { agent, type: msgType, content } = data;

        const el = document.createElement('div');
        el.className = `agent-message ${agent.toLowerCase()}`;

        const header = document.createElement('div');
        header.className = 'agent-header';
        header.innerHTML = `
            <span class="agent-name ${agent.toLowerCase()}">${agent}</span>
            <span class="agent-role">${this.getAgentRole(agent)}</span>
        `;

        const contentEl = document.createElement('div');
        contentEl.className = `agent-content ${msgType}`;
        contentEl.textContent = this.truncate(content, 500);

        el.appendChild(header);
        el.appendChild(contentEl);
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addTaskIndicator(data) {
        const el = document.createElement('div');
        el.className = 'agent-message';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--accent)">📋 Task ${data.task_number}/${data.total}</span>
            </div>
            <div class="agent-content">${data.title}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addFileMessage(data) {
        const el = document.createElement('div');
        el.className = 'agent-message';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--success)">📄 File Created</span>
            </div>
            <div class="agent-content">${data.path}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addSystemMessage(text) {
        const el = document.createElement('div');
        el.className = 'agent-message';
        el.innerHTML = `<div class="agent-content" style="color: var(--text-secondary)">${text}</div>`;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addErrorMessage(error) {
        const el = document.createElement('div');
        el.className = 'agent-message';
        el.style.borderLeftColor = 'var(--error)';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--error)">❌ Error</span>
            </div>
            <div class="agent-content">${error}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    showPlan(plan) {
        const el = document.createElement('div');
        el.className = 'agent-message planner';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name planner">📋 Plan Created</span>
            </div>
            <div class="agent-content">
                <strong>${plan.project_name}</strong><br>
                ${plan.summary}<br><br>
                <strong>Tasks:</strong>
                <ul style="margin-top: 0.5rem; padding-left: 1.5rem;">
                    ${plan.tasks.map(t => `<li>${t.title}</li>`).join('')}
                </ul>
            </div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    showReview(review) {
        const el = document.createElement('div');
        el.className = 'agent-message reviewer';
        const statusColor = review.status === 'approved' ? 'var(--success)' : 'var(--warning)';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name reviewer">🔍 Code Review</span>
                <span style="color: ${statusColor}; font-weight: 600;">${review.status.toUpperCase()}</span>
            </div>
            <div class="agent-content">${review.summary}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    handleBuildComplete(result) {
        // Re-enable button
        this.buildBtn.disabled = false;
        this.buildBtn.querySelector('.btn-text').hidden = false;
        this.buildBtn.querySelector('.btn-loading').hidden = true;

        if (result.success) {
            this.setStatus('ready', 'Build Complete!');
            this.files = result.files || {};
            this.renderFileTabs();

            // Show first file
            const firstFile = Object.keys(this.files)[0];
            if (firstFile) {
                this.selectFile(firstFile);
            }

            this.addSystemMessage(`✅ Project "${result.project_name}" built successfully!`);
        } else {
            this.setStatus('error', 'Build Failed');
            this.addErrorMessage(result.error || 'Unknown error');
        }
    }

    renderFileTabs() {
        this.fileTabs.innerHTML = '';
        Object.keys(this.files).forEach(path => {
            const tab = document.createElement('button');
            tab.className = 'file-tab';
            tab.textContent = path.split('/').pop();
            tab.title = path;
            tab.onclick = () => this.selectFile(path);
            this.fileTabs.appendChild(tab);
        });
    }

    selectFile(path) {
        this.currentFile = path;
        const content = this.files[path] || '// Empty file';

        // Update tabs
        document.querySelectorAll('.file-tab').forEach(tab => {
            tab.classList.toggle('active', tab.title === path);
        });

        // Update code view
        this.codeView.innerHTML = `<code>${this.escapeHtml(content)}</code>`;
    }

    getAgentRole(agent) {
        const roles = {
            'Planner': 'Technical Architect',
            'Coder': 'Software Developer',
            'Reviewer': 'Code Reviewer',
            'Tester': 'QA Engineer'
        };
        return roles[agent] || 'Agent';
    }

    truncate(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrollFeed() {
        this.agentFeed.scrollTop = this.agentFeed.scrollHeight;
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.app = new VibeAgents();
});
