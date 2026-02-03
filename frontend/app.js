/**
 * Vibe Agents - Frontend Application
 * Real-time multi-agent coding platform UI
 */

class VibeAgents {
    constructor() {
        this.ws = null;
        this.files = {};
        this.testFiles = {};
        this.currentFile = null;
        this.buildStartTime = null;

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
        this.connect();
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.startBuild();
        });

        // Example prompts
        this.addExamplePrompts();
    }

    addExamplePrompts() {
        const examples = [
            "Create a simple calculator with add, subtract, multiply, divide",
            "Build a todo list app with local storage",
            "Make a password generator with customizable length and characters",
            "Create a countdown timer with start, pause, reset"
        ];

        const welcomeDiv = this.agentFeed.querySelector('.welcome-message');
        if (welcomeDiv) {
            const examplesHtml = `
                <p style="margin-top: 1rem; font-size: 0.875rem;">Try one of these:</p>
                <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">
                    ${examples.map(ex => `
                        <button class="example-btn" onclick="app.useExample('${ex}')">${ex.substring(0, 40)}...</button>
                    `).join('')}
                </div>
            `;
            welcomeDiv.innerHTML += examplesHtml;
        }
    }

    useExample(text) {
        this.input.value = text;
        this.input.focus();
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
        } else if (state === 'error') {
            this.statusIndicator.style.background = 'var(--error)';
        }
        this.statusText.textContent = text;
    }

    startBuild() {
        const prompt = this.input.value.trim();
        if (!prompt || !this.ws) return;

        // Clear previous state
        this.files = {};
        this.testFiles = {};
        this.currentFile = null;
        this.buildStartTime = Date.now();
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

        this.addSystemMessage(`🚀 Starting build: "${prompt}"`);
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
                this.addFileMessage(data, type === 'file_updated');
                break;

            case 'file_saved':
                // Silent - just update internal state
                break;

            case 'executing':
                this.addExecutionMessage(data);
                break;

            case 'execution_result':
                this.showExecutionResult(data);
                break;

            case 'lint_error':
                this.addLintError(data);
                break;

            case 'installing_deps':
                this.addSystemMessage(`📦 Installing dependencies: ${data.join(', ')}`);
                break;

            case 'debug_attempt':
                this.addDebugAttempt(data);
                break;

            case 'debug_success':
                this.addSuccessMessage(data);
                break;

            case 'debug_failed':
            case 'debug_exhausted':
                this.addWarningMessage(data);
                break;

            case 'fix_applied':
                this.addFixMessage(data);
                break;

            case 'review_complete':
                this.showReview(data);
                break;

            case 'test_created':
                this.addTestMessage(data);
                break;

            case 'test_result':
                this.showTestResult(data);
                break;

            case 'warning':
                this.addWarningMessage(data);
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
        const phaseIcons = {
            'Planning': '📋',
            'Coding': '💻',
            'Verifying': '🔍',
            'Reviewing': '👀',
            'Testing': '🧪',
            'Debugging': '🔧'
        };

        const el = document.createElement('div');
        el.className = 'phase-indicator';
        el.innerHTML = `${phaseIcons[phase] || '▶'} ${phase}`;
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
            <span class="agent-avatar">${this.getAgentEmoji(agent)}</span>
            <span class="agent-name ${agent.toLowerCase()}">${agent}</span>
            <span class="agent-role">${this.getAgentRole(agent)}</span>
        `;

        const contentEl = document.createElement('div');
        contentEl.className = `agent-content ${msgType}`;

        // Format content - truncate and highlight code blocks
        let displayContent = this.truncate(content, 800);
        displayContent = this.formatContent(displayContent);
        contentEl.innerHTML = displayContent;

        el.appendChild(header);
        el.appendChild(contentEl);
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addTaskIndicator(data) {
        const el = document.createElement('div');
        el.className = 'task-indicator';
        el.innerHTML = `
            <div class="task-progress">
                <div class="task-progress-bar" style="width: ${(data.task_number / data.total) * 100}%"></div>
            </div>
            <span class="task-label">📋 Task ${data.task_number}/${data.total}: ${data.title}</span>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addFileMessage(data, isUpdate = false) {
        const icon = isUpdate ? '📝' : '📄';
        const action = isUpdate ? 'Updated' : 'Created';

        const el = document.createElement('div');
        el.className = 'agent-message file-message';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--success)">${icon} ${action}: ${data.path}</span>
            </div>
            ${data.explanation ? `<div class="agent-content">${data.explanation}</div>` : ''}
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addExecutionMessage(data) {
        const el = document.createElement('div');
        el.className = 'agent-message';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--accent)">⚡ Executing</span>
            </div>
            <div class="agent-content">Running ${data.file} (${data.language})</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    showExecutionResult(data) {
        const el = document.createElement('div');
        el.className = `execution-result ${data.success ? 'success' : 'error'}`;
        el.innerHTML = `
            <div class="execution-header">
                ${data.success ? '✅ Execution Successful' : '❌ Execution Failed'}
            </div>
            ${data.stdout ? `<pre class="execution-output">${this.escapeHtml(data.stdout)}</pre>` : ''}
            ${data.stderr ? `<pre class="execution-error">${this.escapeHtml(data.stderr)}</pre>` : ''}
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addLintError(data) {
        const el = document.createElement('div');
        el.className = 'agent-message lint-error';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--warning)">⚠️ Lint Error: ${data.file}</span>
            </div>
            <pre class="agent-content" style="color: var(--error)">${this.escapeHtml(data.error)}</pre>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addDebugAttempt(data) {
        const el = document.createElement('div');
        el.className = 'agent-message debug-attempt';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--warning)">🔧 Debug Attempt ${data.attempt}/${data.max}</span>
            </div>
            <div class="agent-content">Analyzing error...</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addFixMessage(data) {
        const el = document.createElement('div');
        el.className = 'agent-message fix-applied';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--success)">✨ Fix Applied: ${data.file}</span>
            </div>
            <div class="agent-content">${data.diagnosis}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addTestMessage(data) {
        const el = document.createElement('div');
        el.className = 'agent-message';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--tester-color)">🧪 Tests Created: ${data.path}</span>
            </div>
            <div class="agent-content">${data.description || 'Test suite generated'}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    showTestResult(data) {
        const el = document.createElement('div');
        el.className = `test-result ${data.success ? 'success' : 'failed'}`;
        el.innerHTML = `
            <div class="test-header">
                ${data.success ? '✅ Tests Passed' : '❌ Tests Failed'}
            </div>
            <pre class="test-output">${this.escapeHtml(data.output)}</pre>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addSystemMessage(text) {
        const el = document.createElement('div');
        el.className = 'system-message';
        el.innerHTML = text;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addSuccessMessage(text) {
        const el = document.createElement('div');
        el.className = 'system-message success';
        el.innerHTML = `✅ ${text}`;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addWarningMessage(text) {
        const el = document.createElement('div');
        el.className = 'system-message warning';
        el.innerHTML = `⚠️ ${text}`;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addErrorMessage(error) {
        const el = document.createElement('div');
        el.className = 'system-message error';
        el.innerHTML = `❌ Error: ${error}`;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    showPlan(plan) {
        const el = document.createElement('div');
        el.className = 'plan-card';
        el.innerHTML = `
            <div class="plan-header">
                <span class="plan-title">📋 ${plan.project_name}</span>
                <span class="plan-tech">${plan.tech_stack?.language || 'Python'}</span>
            </div>
            <div class="plan-summary">${plan.summary}</div>
            <div class="plan-tasks">
                <strong>Tasks:</strong>
                <ol>
                    ${plan.tasks.map(t => `<li>${t.title}</li>`).join('')}
                </ol>
            </div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    showReview(review) {
        const el = document.createElement('div');
        el.className = `review-card ${review.status}`;
        const statusIcon = review.status === 'approved' ? '✅' : '⚠️';

        let issuesHtml = '';
        if (review.issues && review.issues.length > 0) {
            issuesHtml = `
                <div class="review-issues">
                    ${review.issues.map(i => `
                        <div class="issue ${i.severity}">
                            <span class="issue-severity">${i.severity}</span>
                            <span class="issue-text">${i.issue}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        el.innerHTML = `
            <div class="review-header">
                ${statusIcon} Code Review: <strong>${review.status.toUpperCase()}</strong>
            </div>
            <div class="review-summary">${review.summary}</div>
            ${issuesHtml}
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    handleBuildComplete(result) {
        const duration = this.buildStartTime ?
            ((Date.now() - this.buildStartTime) / 1000).toFixed(1) : '?';

        // Re-enable button
        this.buildBtn.disabled = false;
        this.buildBtn.querySelector('.btn-text').hidden = false;
        this.buildBtn.querySelector('.btn-loading').hidden = true;

        if (result.success) {
            this.setStatus('ready', 'Build Complete!');
            this.files = result.files || {};
            this.testFiles = result.test_files || {};
            this.renderFileTabs();

            // Show first file
            const firstFile = Object.keys(this.files)[0];
            if (firstFile) {
                this.selectFile(firstFile);
            }

            this.addSystemMessage(`
                ✅ <strong>${result.project_name}</strong> built successfully in ${duration}s!
                <br>Files: ${Object.keys(this.files).length} | Tests: ${Object.keys(this.testFiles).length}
            `);
        } else {
            this.setStatus('error', 'Build Failed');
            this.addErrorMessage(result.error || 'Unknown error');

            // Still show partial files if any
            if (result.partial_files) {
                this.files = result.partial_files;
                this.renderFileTabs();
            }
        }
    }

    renderFileTabs() {
        this.fileTabs.innerHTML = '';

        // Code files
        Object.keys(this.files).forEach(path => {
            const tab = document.createElement('button');
            tab.className = 'file-tab';
            tab.textContent = path.split('/').pop();
            tab.title = path;
            tab.onclick = () => this.selectFile(path);
            this.fileTabs.appendChild(tab);
        });

        // Test files
        Object.keys(this.testFiles).forEach(path => {
            const tab = document.createElement('button');
            tab.className = 'file-tab test-file';
            tab.textContent = `🧪 ${path.split('/').pop()}`;
            tab.title = path;
            tab.onclick = () => this.selectFile(path, true);
            this.fileTabs.appendChild(tab);
        });
    }

    selectFile(path, isTest = false) {
        this.currentFile = path;
        const content = isTest ?
            (this.testFiles[path] || '// Empty') :
            (this.files[path] || '// Empty');

        // Update tabs
        document.querySelectorAll('.file-tab').forEach(tab => {
            tab.classList.toggle('active', tab.title === path);
        });

        // Update code view with syntax highlighting hint
        const extension = path.split('.').pop();
        this.codeView.innerHTML = `<code class="language-${extension}">${this.escapeHtml(content)}</code>`;
    }

    getAgentEmoji(agent) {
        const emojis = {
            'Planner': '📋',
            'Coder': '💻',
            'Reviewer': '👀',
            'Tester': '🧪',
            'Debugger': '🔧'
        };
        return emojis[agent] || '🤖';
    }

    getAgentRole(agent) {
        const roles = {
            'Planner': 'Technical Architect',
            'Coder': 'Software Developer',
            'Reviewer': 'Code Reviewer',
            'Tester': 'QA Engineer',
            'Debugger': 'Debug Specialist'
        };
        return roles[agent] || 'Agent';
    }

    formatContent(text) {
        // Convert markdown code blocks to styled elements
        text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>');
        // Convert inline code
        text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
        // Convert newlines
        text = text.replace(/\n/g, '<br>');
        return text;
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
