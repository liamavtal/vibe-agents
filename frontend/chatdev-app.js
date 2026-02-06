/**
 * Vibe Agents - ChatDev Style Frontend
 * Real-time chat with ChatDev's visual style
 */

// Agent coordinates on company.png (like ChatDev's coordSet)
const agentCoords = {
    'Router': { arrow: 'right', top: '155px', left: '240px' },      // CEO on carpet
    'Planner': { arrow: 'left', top: '250px', left: '50px' },       // Designing area
    'Coder': { arrow: 'right', top: '330px', left: '180px' },       // Coding area
    'Reviewer': { arrow: 'left', top: '220px', left: '380px' },     // Documenting area
    'Tester': { arrow: 'right', top: '320px', left: '330px' },      // Testing area
    'Debugger': { arrow: 'right', top: '350px', left: '150px' }     // Coding area bottom
};

// Agent avatar images
const agentAvatars = {
    'Router': '/static/avatars/router.png',
    'Planner': '/static/avatars/planner.png',
    'Coder': '/static/avatars/coder.png',
    'Reviewer': '/static/avatars/reviewer.png',
    'Tester': '/static/avatars/tester.png',
    'Debugger': '/static/avatars/debugger.png',
    'User': '/static/avatars/coder.png'
};

class VibeAgentsChat {
    constructor() {
        this.ws = null;
        this.sessionId = null;
        this.messageCount = 0;
        this.fileCount = 0;
        this.files = {};
        this.currentFile = null;
        this.currentStreamEl = null;
        this.currentAgent = null;
        this.md = window.markdownit();

        // DOM elements
        this.dialogBody = document.getElementById('dialogBody');
        this.chatForm = document.getElementById('chat-form');
        this.chatInput = document.getElementById('chat-input');
        this.sendBtn = document.getElementById('send-btn');
        this.taskText = document.getElementById('Requesttext');
        this.statusIndicator = document.getElementById('status-indicator');
        this.statusText = document.getElementById('status-text');
        this.arrowLeft = document.getElementById('arrow-left');
        this.arrowRight = document.getElementById('arrow-right');
        this.codePanel = document.getElementById('code-panel');
        this.codeView = document.getElementById('code-view');
        this.fileTabs = document.getElementById('file-tabs');
        this.viewCodeBtn = document.getElementById('view-code-btn');
        this.closeCodeBtn = document.getElementById('close-code-panel');

        // Stats elements
        this.statAgent = document.getElementById('current_agent');
        this.statPhase = document.getElementById('current_phase');
        this.statFiles = document.getElementById('num_files');
        this.statMessages = document.getElementById('num_messages');
        this.statStatus = document.getElementById('build_status');

        this.init();
    }

    init() {
        this.connect();

        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        this.viewCodeBtn.addEventListener('click', () => this.toggleCodePanel(true));
        this.closeCodeBtn.addEventListener('click', () => this.toggleCodePanel(false));

        // Keyboard shortcut
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('Connected to Vibe Agents');
            this.setStatus('ready', 'Connected - Ready to chat');
            this.ws.send(JSON.stringify({ type: 'new_session' }));
        };

        this.ws.onclose = () => {
            console.log('Disconnected, reconnecting...');
            this.setStatus('error', 'Disconnected...');
            setTimeout(() => this.connect(), 2000);
        };

        this.ws.onerror = (err) => console.error('WebSocket error:', err);

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
    }

    setStatus(state, text) {
        this.statusIndicator.className = '';
        if (state === 'active') {
            this.statusIndicator.classList.add('active');
            this.statStatus.textContent = 'Working';
        } else if (state === 'error') {
            this.statusIndicator.classList.add('error');
            this.statStatus.textContent = 'Error';
        } else {
            this.statStatus.textContent = 'Idle';
        }
        this.statusText.textContent = text;
    }

    // ChatDev-style: Move arrow to point at active agent
    updateCompanyWorking(agentName) {
        if (agentName === 'end' || !agentName) {
            this.arrowLeft.style.display = 'none';
            this.arrowRight.style.display = 'none';
            this.statAgent.textContent = '-';
            return;
        }

        const coords = agentCoords[agentName];
        if (!coords) return;

        this.statAgent.textContent = agentName;

        if (coords.arrow === 'left') {
            this.arrowLeft.style.display = 'block';
            this.arrowLeft.style.top = coords.top;
            this.arrowLeft.style.left = coords.left;
            this.arrowRight.style.display = 'none';
        } else {
            this.arrowRight.style.display = 'block';
            this.arrowRight.style.top = coords.top;
            this.arrowRight.style.left = coords.left;
            this.arrowLeft.style.display = 'none';
        }
    }

    sendMessage() {
        const message = this.chatInput.value.trim();
        if (!message || !this.ws) return;

        // Show user message
        this.addDialog('User', message, 'user');
        this.taskText.textContent = 'Task: ' + message;
        this.chatInput.value = '';

        // Disable input while processing
        this.sendBtn.disabled = true;
        this.setStatus('active', 'Processing...');

        // Send to backend
        this.ws.send(JSON.stringify({
            type: 'chat',
            message: message,
            session_id: this.sessionId
        }));
    }

    handleMessage(message) {
        const { type, data, session_id } = message;

        if (type === 'session_created') {
            this.sessionId = message.session_id;
            return;
        }

        switch (type) {
            case 'routing':
                this.setStatus('active', data.message || 'Analyzing...');
                break;

            case 'route_decision':
                if (data.action !== 'CONVERSATION') {
                    this.addSystemMessage(`Routing: ${data.action}`);
                }
                break;

            case 'phase':
                this.statPhase.textContent = data;
                this.addSystemMessage(`Phase: ${data}`);
                break;

            case 'agent_message':
                this.handleAgentMessage(data);
                break;

            case 'chat_response':
                this.handleChatResponse(data);
                break;

            case 'file_created':
            case 'file_updated':
                this.handleFileEvent(data);
                break;

            case 'build_complete':
                this.handleBuildComplete(data);
                break;

            case 'error':
                this.addSystemMessage(`Error: ${typeof data === 'string' ? data : JSON.stringify(data)}`, 'error');
                this.resetUI();
                break;

            default:
                console.log('Message:', type, data);
        }
    }

    handleAgentMessage(data) {
        const { agent, type: msgType, content } = data;

        switch (msgType) {
            case 'thinking':
                this.updateCompanyWorking(agent);
                this.setStatus('active', `${agent} is thinking...`);
                this.startAgentStream(agent);
                break;

            case 'streaming':
                this.appendStreamText(content);
                break;

            case 'tool_use':
                this.handleToolUse(agent, content);
                break;

            case 'done':
                this.finalizeAgentStream();
                break;

            case 'error':
                this.addSystemMessage(`${agent}: ${content}`, 'error');
                break;
        }
    }

    startAgentStream(agent) {
        this.currentAgent = agent;
        this.messageCount++;
        this.statMessages.textContent = this.messageCount;

        // Create dialog container
        const dialog = document.createElement('div');
        dialog.className = 'dialog-message';

        // Character header (like ChatDev)
        const header = document.createElement('div');
        header.className = 'dialog-header';

        const character = document.createElement('div');
        character.className = 'dialog-character';

        const avatar = document.createElement('img');
        avatar.src = agentAvatars[agent] || agentAvatars['Coder'];
        avatar.alt = agent;

        const name = document.createElement('span');
        name.textContent = agent;
        name.className = `agent-${agent.toLowerCase()}`;

        character.appendChild(avatar);
        character.appendChild(name);
        header.appendChild(character);

        // Content area
        const content = document.createElement('div');
        content.className = 'dialog-content assistant';
        content.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

        dialog.appendChild(header);
        dialog.appendChild(content);
        this.dialogBody.appendChild(dialog);

        this.currentStreamEl = content;
        this.scrollToBottom();
    }

    appendStreamText(text) {
        if (!this.currentStreamEl) return;

        // Remove typing indicator if present
        const typing = this.currentStreamEl.querySelector('.typing-indicator');
        if (typing) typing.remove();

        // Append text
        const currentText = this.currentStreamEl.getAttribute('data-raw') || '';
        const newText = currentText + text;
        this.currentStreamEl.setAttribute('data-raw', newText);
        this.currentStreamEl.innerHTML = this.formatContent(newText);

        this.scrollToBottom();
    }

    finalizeAgentStream() {
        if (this.currentStreamEl) {
            const typing = this.currentStreamEl.querySelector('.typing-indicator');
            if (typing) typing.remove();

            // Apply syntax highlighting to code blocks
            this.currentStreamEl.querySelectorAll('pre code').forEach(block => {
                if (window.hljs) {
                    window.hljs.highlightElement(block);
                }
            });
        }

        this.currentStreamEl = null;
        this.currentAgent = null;
        this.updateCompanyWorking('end');
    }

    handleToolUse(agent, content) {
        let toolData;
        try {
            toolData = typeof content === 'string' ? JSON.parse(content) : content;
        } catch (e) {
            return;
        }

        const tool = toolData.tool || 'Unknown';
        const input = toolData.input || {};

        let description = '';
        if (tool === 'Write') description = `Creating ${input.file_path || 'file'}`;
        else if (tool === 'Read') description = `Reading ${input.file_path || 'file'}`;
        else if (tool === 'Edit') description = `Editing ${input.file_path || 'file'}`;
        else if (tool === 'Bash') description = `Running: ${(input.command || '').substring(0, 50)}`;
        else description = `Using ${tool}`;

        this.setStatus('active', `${agent}: ${description}`);
    }

    handleFileEvent(data) {
        if (data.path && data.code) {
            this.files[data.path] = data.code;
            this.fileCount = Object.keys(this.files).length;
            this.statFiles.textContent = this.fileCount;
            this.viewCodeBtn.classList.add('has-files');
            this.renderFileTabs();
        }
    }

    handleChatResponse(data) {
        this.finalizeAgentStream();
        this.resetUI();

        if (data.type === 'conversation' && data.response) {
            // Response already shown via streaming
        } else if (data.type === 'code' && data.files) {
            this.addSystemMessage(`Created ${data.files.length} file(s): ${data.files.join(', ')}`, 'success');
        }
    }

    handleBuildComplete(data) {
        this.finalizeAgentStream();
        this.resetUI();

        if (data.success) {
            this.addSystemMessage(`Build complete: ${data.project || 'Project'}`, 'success');
            this.statStatus.textContent = 'Complete';
        } else {
            this.addSystemMessage(`Build failed: ${data.error || 'Unknown error'}`, 'error');
        }
    }

    addDialog(agent, text, type = 'assistant') {
        this.messageCount++;
        this.statMessages.textContent = this.messageCount;

        const dialog = document.createElement('div');
        dialog.className = 'dialog-message';

        const header = document.createElement('div');
        header.className = 'dialog-header';

        const character = document.createElement('div');
        character.className = `dialog-character ${type}`;

        const avatar = document.createElement('img');
        avatar.src = agentAvatars[agent] || agentAvatars['Coder'];
        avatar.alt = agent;

        const name = document.createElement('span');
        name.textContent = agent;

        character.appendChild(avatar);
        character.appendChild(name);
        header.appendChild(character);

        const content = document.createElement('div');
        content.className = `dialog-content ${type}`;
        content.innerHTML = this.formatContent(text);

        dialog.appendChild(header);
        dialog.appendChild(content);
        this.dialogBody.appendChild(dialog);

        this.scrollToBottom();
    }

    addSystemMessage(text, level = 'info') {
        const msg = document.createElement('div');
        msg.className = `dialog-message system-${level}`;
        msg.style.cssText = `
            text-align: center;
            padding: 8px 15px;
            margin: 10px 0;
            border-radius: 20px;
            font-size: 13px;
            background: ${level === 'error' ? 'rgba(248,81,73,0.2)' : level === 'success' ? 'rgba(63,185,80,0.2)' : 'rgba(88,166,255,0.2)'};
            color: ${level === 'error' ? '#f85149' : level === 'success' ? '#3fb950' : '#58a6ff'};
        `;
        msg.textContent = text;
        this.dialogBody.appendChild(msg);
        this.scrollToBottom();
    }

    resetUI() {
        this.sendBtn.disabled = false;
        this.setStatus('ready', 'Ready');
        this.updateCompanyWorking('end');
    }

    formatContent(text) {
        if (!text) return '';

        // Escape HTML
        let escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Code blocks
        escaped = escaped.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code class="language-${lang || 'plaintext'}">${code}</code></pre>`;
        });

        // Inline code
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Line breaks
        escaped = escaped.replace(/\n/g, '<br>');

        return escaped;
    }

    scrollToBottom() {
        this.dialogBody.scrollTop = this.dialogBody.scrollHeight;
    }

    // Code panel
    toggleCodePanel(show) {
        if (show) {
            this.codePanel.classList.remove('hidden');
            this.codePanel.classList.add('visible');
        } else {
            this.codePanel.classList.remove('visible');
            this.codePanel.classList.add('hidden');
        }
    }

    renderFileTabs() {
        this.fileTabs.innerHTML = '';

        Object.keys(this.files).forEach(path => {
            const tab = document.createElement('button');
            tab.className = 'file-tab' + (this.currentFile === path ? ' active' : '');
            tab.textContent = path.split('/').pop();
            tab.onclick = () => this.selectFile(path);
            this.fileTabs.appendChild(tab);
        });

        // Select first file if none selected
        if (!this.currentFile && Object.keys(this.files).length > 0) {
            this.selectFile(Object.keys(this.files)[0]);
        }
    }

    selectFile(path) {
        this.currentFile = path;
        const content = this.files[path] || '';

        const codeEl = document.createElement('code');
        codeEl.textContent = content;

        // Detect language
        const ext = path.split('.').pop();
        const langMap = { js: 'javascript', py: 'python', ts: 'typescript', html: 'html', css: 'css', json: 'json' };
        codeEl.className = `language-${langMap[ext] || ext}`;

        this.codeView.innerHTML = '';
        this.codeView.appendChild(codeEl);

        if (window.hljs) {
            window.hljs.highlightElement(codeEl);
        }

        this.renderFileTabs();
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.app = new VibeAgentsChat();
});
