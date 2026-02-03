/**
 * Vibe Agents - Frontend Application
 * Conversational AI coding platform with smart agent routing
 */

class VibeAgents {
    constructor() {
        this.ws = null;
        this.files = {};
        this.testFiles = {};
        this.currentFile = null;
        this.isProcessing = false;
        this.useFullPipeline = false;  // Toggle for full pipeline vs smart routing

        // DOM elements
        this.form = document.getElementById('chat-form');
        this.input = document.getElementById('chat-input');
        this.sendBtn = document.getElementById('send-btn');
        this.clearBtn = document.getElementById('clear-btn');
        this.modeToggle = document.getElementById('mode-toggle');
        this.agentFeed = document.getElementById('agent-feed');
        this.fileTabs = document.getElementById('file-tabs');
        this.codeView = document.getElementById('code-view');
        this.statusIndicator = document.getElementById('status-indicator');
        this.statusText = document.getElementById('status-text');
        this.panelTitle = document.getElementById('panel-title');
        this.activeAgentBadge = document.getElementById('active-agent');

        this.init();
    }

    init() {
        this.connect();

        // Form submit
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Clear button
        this.clearBtn.addEventListener('click', () => {
            this.clearConversation();
        });

        // Mode toggle
        this.modeToggle.addEventListener('change', (e) => {
            this.useFullPipeline = e.target.checked;
            this.updateModeUI();
        });

        // Example prompts
        document.querySelectorAll('.example-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt;
                if (prompt) {
                    this.input.value = prompt;
                    this.input.focus();
                }
            });
        });
    }

    updateModeUI() {
        const toggleText = this.modeToggle.parentElement.querySelector('.toggle-text');
        if (this.useFullPipeline) {
            toggleText.textContent = 'Full Pipeline';
            this.panelTitle.textContent = 'Agent Theater';
        } else {
            toggleText.textContent = 'Smart Routing';
            this.panelTitle.textContent = 'Conversation';
        }
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('Connected to Vibe Agents');
            this.setStatus('ready', 'Ready to chat');
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
        } else {
            this.statusIndicator.style.background = '';
        }
        this.statusText.textContent = text;
    }

    showActiveAgent(agent) {
        if (agent) {
            this.activeAgentBadge.textContent = agent;
            this.activeAgentBadge.hidden = false;
            this.activeAgentBadge.className = `agent-badge ${agent.toLowerCase()}`;
        } else {
            this.activeAgentBadge.hidden = true;
        }
    }

    sendMessage() {
        const message = this.input.value.trim();
        if (!message || !this.ws || this.isProcessing) return;

        // Add user message to feed
        this.addUserMessage(message);
        this.input.value = '';

        // Update UI
        this.isProcessing = true;
        this.setStatus('active', 'Thinking...');
        this.sendBtn.disabled = true;
        this.sendBtn.querySelector('.btn-text').hidden = true;
        this.sendBtn.querySelector('.btn-loading').hidden = false;

        // Send message
        if (this.useFullPipeline) {
            this.ws.send(JSON.stringify({
                type: 'build',
                prompt: message
            }));
        } else {
            this.ws.send(JSON.stringify({
                type: 'chat',
                message: message
            }));
        }
    }

    clearConversation() {
        if (this.ws) {
            this.ws.send(JSON.stringify({ type: 'clear' }));
        }
        this.files = {};
        this.testFiles = {};
        this.currentFile = null;
        this.agentFeed.innerHTML = `
            <div class="welcome-message">
                <p>Hey! I'm your AI coding assistant.</p>
                <p>Just tell me what you want to build, or ask me anything about code.</p>
                <p class="hint">I'll intelligently decide when to use specialized agents.</p>
                <div class="example-prompts">
                    <button class="example-btn" data-prompt="Build me a todo app with local storage">Todo App</button>
                    <button class="example-btn" data-prompt="Write a function to validate email addresses">Validate Email</button>
                    <button class="example-btn" data-prompt="How does this system work?">How it works</button>
                </div>
            </div>
        `;
        this.fileTabs.innerHTML = '';
        this.codeView.innerHTML = '<code>// Your generated code will appear here</code>';
        this.setStatus('ready', 'Ready to chat');

        // Re-attach example button handlers
        document.querySelectorAll('.example-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt;
                if (prompt) {
                    this.input.value = prompt;
                    this.input.focus();
                }
            });
        });
    }

    handleMessage(message) {
        const { type, data } = message;

        switch (type) {
            case 'routing':
                this.setStatus('active', data.message || 'Analyzing...');
                break;

            case 'route_decision':
                this.showRouteDecision(data);
                break;

            case 'chat_response':
                this.handleChatResponse(data);
                break;

            case 'status':
                this.setStatus('active', data);
                break;

            case 'phase':
                this.addPhaseIndicator(data);
                break;

            case 'agent_message':
                this.addAgentMessage(data);
                this.showActiveAgent(data.agent);
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
                // Store the file
                if (data.path && data.code) {
                    this.files[data.path] = data.code;
                    this.renderFileTabs();
                }
                break;

            case 'execution_result':
                this.showExecutionResult(data);
                break;

            case 'debug_attempt':
                this.addDebugAttempt(data);
                break;

            case 'debug_success':
                this.addSuccessMessage(data);
                break;

            case 'fix_applied':
            case 'fix_suggested':
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
            case 'debug_failed':
            case 'debug_exhausted':
                this.addWarningMessage(data);
                break;

            case 'error':
                this.addErrorMessage(data);
                this.resetUI();
                break;

            case 'build_complete':
                this.handleBuildComplete(data);
                break;

            case 'cleared':
                // Already handled locally
                break;

            default:
                console.log('Unknown message type:', type, data);
        }
    }

    showRouteDecision(data) {
        const actionEmojis = {
            'CONVERSATION': '💬',
            'BUILD': '🏗️',
            'CODE_ONLY': '💻',
            'FIX': '🔧',
            'REVIEW': '👀',
            'TEST': '🧪'
        };

        const emoji = actionEmojis[data.action] || '🤔';

        // Only show for non-conversation routes
        if (data.action !== 'CONVERSATION') {
            const el = document.createElement('div');
            el.className = 'route-decision';
            el.innerHTML = `
                <span class="route-action">${emoji} ${data.action}</span>
                <span class="route-confidence">${Math.round(data.confidence * 100)}% confident</span>
            `;
            this.agentFeed.appendChild(el);
            this.scrollFeed();
        }
    }

    handleChatResponse(data) {
        this.resetUI();

        if (data.type === 'conversation') {
            this.addAssistantMessage(data.response);
        } else if (data.type === 'code') {
            if (data.success && data.code) {
                this.files[data.file_path] = data.code;
                this.renderFileTabs();
                this.selectFile(data.file_path);
                this.addAssistantMessage(data.explanation || `Created ${data.file_path}`);
            } else {
                this.addAssistantMessage(data.raw_response || 'Something went wrong.');
            }
        } else if (data.type === 'build') {
            this.handleBuildComplete(data);
        } else if (data.type === 'fix') {
            this.addAssistantMessage(data.diagnosis || 'Applied fix.');
        } else if (data.type === 'review') {
            if (data.success) {
                this.showReview({
                    status: data.verdict,
                    summary: data.summary,
                    issues: data.issues
                });
            }
        } else if (data.type === 'test') {
            if (data.success && data.code) {
                this.testFiles[data.file_path] = data.code;
                this.renderFileTabs();
                this.addAssistantMessage(data.description || `Created ${data.file_path}`);
            }
        } else if (data.type === 'error') {
            this.addErrorMessage(data.error);
        } else {
            this.addAssistantMessage(JSON.stringify(data, null, 2));
        }

        this.showActiveAgent(null);
    }

    addUserMessage(text) {
        // Remove welcome message if present
        const welcome = this.agentFeed.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        const el = document.createElement('div');
        el.className = 'chat-message user-message';
        el.innerHTML = `
            <div class="message-header">
                <span class="message-sender">You</span>
            </div>
            <div class="message-content">${this.escapeHtml(text)}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addAssistantMessage(text) {
        const el = document.createElement('div');
        el.className = 'chat-message assistant-message';
        el.innerHTML = `
            <div class="message-header">
                <span class="message-sender">Vibe</span>
            </div>
            <div class="message-content">${this.formatContent(text)}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    resetUI() {
        this.isProcessing = false;
        this.sendBtn.disabled = false;
        this.sendBtn.querySelector('.btn-text').hidden = false;
        this.sendBtn.querySelector('.btn-loading').hidden = true;
        this.setStatus('ready', 'Ready');
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
            <span class="task-label">Task ${data.task_number}/${data.total}: ${data.title}</span>
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
                <span class="agent-name" style="color: var(--success)">✨ Fix: ${data.file || 'code'}</span>
            </div>
            <div class="agent-content">${data.diagnosis || 'Applied fix'}</div>
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    addTestMessage(data) {
        const el = document.createElement('div');
        el.className = 'agent-message';
        el.innerHTML = `
            <div class="agent-header">
                <span class="agent-name" style="color: var(--tester-color)">🧪 Tests: ${data.path}</span>
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
        el.innerHTML = `⚠️ ${typeof text === 'string' ? text : JSON.stringify(text)}`;
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
                ${statusIcon} Review: <strong>${review.status?.toUpperCase() || 'COMPLETE'}</strong>
            </div>
            <div class="review-summary">${review.summary || ''}</div>
            ${issuesHtml}
        `;
        this.agentFeed.appendChild(el);
        this.scrollFeed();
    }

    handleBuildComplete(result) {
        this.resetUI();

        if (result.success) {
            this.setStatus('ready', 'Complete!');
            this.files = result.files || {};
            this.testFiles = result.test_files || {};
            this.renderFileTabs();

            const firstFile = Object.keys(this.files)[0];
            if (firstFile) {
                this.selectFile(firstFile);
            }

            this.addSuccessMessage(`${result.project || 'Project'} built successfully!`);
        } else {
            this.setStatus('error', 'Failed');
            this.addErrorMessage(result.error || 'Build failed');

            if (result.partial_files) {
                this.files = result.partial_files;
                this.renderFileTabs();
            }
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

        document.querySelectorAll('.file-tab').forEach(tab => {
            tab.classList.toggle('active', tab.title === path);
        });

        const extension = path.split('.').pop();
        this.codeView.innerHTML = `<code class="language-${extension}">${this.escapeHtml(content)}</code>`;
    }

    getAgentEmoji(agent) {
        const emojis = {
            'Router': '🧠',
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
            'Router': 'Coordinator',
            'Planner': 'Architect',
            'Coder': 'Developer',
            'Reviewer': 'Code Reviewer',
            'Tester': 'QA Engineer',
            'Debugger': 'Debug Specialist'
        };
        return roles[agent] || 'Agent';
    }

    formatContent(text) {
        text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>');
        text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.app = new VibeAgents();
});
