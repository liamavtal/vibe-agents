/**
 * Vibe Agents - Phase 6: UI Polish
 *
 * Features:
 * - Multiple concurrent sessions (tabs) over a single WebSocket
 * - Per-tab isolated state (feed, files, phase, project, streaming)
 * - Session multiplexing via session_id in all messages
 * - Tab persistence across reconnects
 * - SVG agent avatars with colored chat bubbles
 * - Phase timeline, tool cards, dialogue dividers
 * - Project browser sidebar with REST API
 * - Syntax highlighting (highlight.js)
 * - Dark/light theme toggle with persistence
 * - Keyboard shortcuts (Ctrl+Enter, Ctrl+N, Ctrl+D, Ctrl+L)
 * - Toast notifications for background events
 * - File tree panel with file type icons
 * - Copy-to-clipboard for code
 */

// ==================== TabSession ====================

class TabSession {
    constructor(id) {
        this.id = id;
        this.title = 'New Session';
        this.status = 'idle';
        this.projectId = null;
        this.projectName = null;

        // Feed DOM element (persists when tab is inactive)
        this.feedEl = document.createElement('div');
        this.feedEl.className = 'session-feed-content';
        this.feedEl.innerHTML = `
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

        // Code state
        this.files = {};
        this.testFiles = {};
        this.currentFile = null;

        // Processing state
        this.isProcessing = false;
        this.currentStreamEl = null;
        this.currentStreamAgent = null;

        // Phase state
        this.phaseIndex = -1;
    }
}

// ==================== VibeAgents ====================

class VibeAgents {
    constructor() {
        this.ws = null;
        this.useFullPipeline = false;
        this.sidebarOpen = false;

        // Session management
        this.sessions = new Map();
        this.activeSessionId = null;
        this._reconnectQueue = null;

        // Theme
        this.theme = localStorage.getItem('vibe-agents-theme') || 'dark';

        // Phase names
        this.phases = ['Planning', 'Coding', 'Reviewing', 'Testing'];

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
        this.phaseTimeline = document.getElementById('phase-timeline');
        this.projectSidebar = document.getElementById('project-sidebar');
        this.projectList = document.getElementById('project-list');
        this.projectsToggle = document.getElementById('projects-toggle');
        this.sidebarCloseBtn = document.getElementById('sidebar-close');
        this.projectBadge = document.getElementById('active-project-badge');

        // Tab bar
        this.tabList = document.getElementById('tab-list');
        this.tabNewBtn = document.getElementById('tab-new-btn');

        // Phase 6 elements
        this.themeToggle = document.getElementById('theme-toggle');
        this.copyCodeBtn = document.getElementById('copy-code-btn');
        this.fileTree = document.getElementById('file-tree');
        this.toastContainer = document.getElementById('toast-container');
        this.shortcutHint = document.getElementById('shortcut-hint');

        // Agent Theater elements
        this.theaterPanel = document.getElementById('theater-panel');
        this.theaterToggleBtn = document.getElementById('theater-toggle');
        this.theaterCloseBtn = document.getElementById('theater-close');
        this.theaterAgents = document.querySelectorAll('.theater-agent');
        this.theaterOpen = false;
        this.mainEl = document.querySelector('.main');

        this.init();
    }

    // ==================== Session Helpers ====================

    getActiveSession() {
        return this.sessions.get(this.activeSessionId);
    }

    getSession(sessionId) {
        return this.sessions.get(sessionId) || this.getActiveSession();
    }

    // ==================== Agent Character Avatars ====================

    getAgentAvatar(agent) {
        const avatars = {
            Router: '/static/avatars/router.png',
            Planner: '/static/avatars/planner.png',
            Coder: '/static/avatars/coder.png',
            Reviewer: '/static/avatars/reviewer.png',
            Tester: '/static/avatars/tester.png',
            Debugger: '/static/avatars/debugger.png'
        };
        return avatars[agent] || '/static/avatars/coder.png';
    }

    getAgentSVG(agent) {
        // Return an img tag with the character avatar
        const src = this.getAgentAvatar(agent);
        return `<img src="${src}" alt="${agent}" class="agent-character" />`;
    }

    getAgentColor(agent) {
        const colors = {
            Router: 'var(--router-color)',
            Planner: 'var(--planner-color)',
            Coder: 'var(--coder-color)',
            Reviewer: 'var(--reviewer-color)',
            Tester: 'var(--tester-color)',
            Debugger: 'var(--debugger-color)'
        };
        return colors[agent] || 'var(--text-secondary)';
    }

    getAgentRole(agent) {
        const roles = {
            Router: 'Coordinator',
            Planner: 'Architect',
            Coder: 'Developer',
            Reviewer: 'Code Reviewer',
            Tester: 'QA Engineer',
            Debugger: 'Debug Specialist'
        };
        return roles[agent] || 'Agent';
    }

    // ==================== Init & Connection ====================

    init() {
        this.connect();

        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        this.clearBtn.addEventListener('click', () => this.clearConversation());

        this.modeToggle.addEventListener('change', (e) => {
            this.useFullPipeline = e.target.checked;
            this.updateModeUI();
        });

        this.projectsToggle.addEventListener('click', () => this.toggleSidebar());
        this.sidebarCloseBtn.addEventListener('click', () => this.toggleSidebar(false));
        this.tabNewBtn.addEventListener('click', () => this.requestNewSession());

        // Theme toggle
        this.applyTheme(this.theme);
        if (this.themeToggle) {
            this.themeToggle.addEventListener('click', () => this.toggleTheme());
        }

        // Copy code button
        if (this.copyCodeBtn) {
            this.copyCodeBtn.addEventListener('click', () => this.copyCurrentCode());
        }

        // Agent Theater toggle
        if (this.theaterToggleBtn) {
            this.theaterToggleBtn.addEventListener('click', () => this.toggleTheater());
        }
        if (this.theaterCloseBtn) {
            this.theaterCloseBtn.addEventListener('click', () => this.toggleTheater(false));
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcut(e));

        // Show shortcut hint briefly on first load
        this.showShortcutHint();
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

    // ==================== Theme Toggle ====================

    applyTheme(theme) {
        this.theme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('vibe-agents-theme', theme);
    }

    toggleTheme() {
        const newTheme = this.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme(newTheme);
        this.showToast('info', `Switched to ${newTheme} theme`);
    }

    // ==================== Keyboard Shortcuts ====================

    handleKeyboardShortcut(e) {
        const ctrl = e.ctrlKey || e.metaKey;

        if (ctrl && e.key === 'Enter') {
            e.preventDefault();
            this.sendMessage();
        } else if (ctrl && e.key === 'n') {
            e.preventDefault();
            this.requestNewSession();
        } else if (ctrl && e.key === 'd') {
            e.preventDefault();
            this.toggleTheme();
        } else if (ctrl && e.key === 'l') {
            e.preventDefault();
            this.clearConversation();
        } else if (ctrl && e.key === 'Tab') {
            e.preventDefault();
            this.cycleTab(e.shiftKey ? -1 : 1);
        } else if (ctrl && e.key === 't') {
            e.preventDefault();
            this.toggleTheater();
        }
    }

    cycleTab(direction) {
        const ids = Array.from(this.sessions.keys());
        if (ids.length <= 1) return;
        const currentIdx = ids.indexOf(this.activeSessionId);
        const nextIdx = (currentIdx + direction + ids.length) % ids.length;
        this.switchTab(ids[nextIdx]);
    }

    showShortcutHint() {
        if (!this.shortcutHint) return;
        const shown = sessionStorage.getItem('vibe-agents-hint-shown');
        if (shown) return;

        this.shortcutHint.hidden = false;
        sessionStorage.setItem('vibe-agents-hint-shown', '1');
        setTimeout(() => {
            this.shortcutHint.hidden = true;
        }, 5000);
    }

    // ==================== Toast Notifications ====================

    showToast(level, text, duration = 3000) {
        if (!this.toastContainer) return;

        const toast = document.createElement('div');
        toast.className = `toast ${level}`;

        const iconSvg = this._getToastIcon(level);
        toast.innerHTML = `
            <span class="toast-icon">${iconSvg}</span>
            <span class="toast-text">${this.escapeHtml(text)}</span>
        `;

        this.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('exiting');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    _getToastIcon(level) {
        const icons = {
            success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            warning: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
            info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
        };
        return icons[level] || icons.info;
    }

    // ==================== Agent Theater ====================

    toggleTheater(show = null) {
        if (!this.theaterPanel) return;

        this.theaterOpen = show !== null ? show : !this.theaterOpen;
        this.theaterPanel.hidden = !this.theaterOpen;

        // Update main layout
        if (this.mainEl) {
            if (this.theaterOpen) {
                this.mainEl.classList.add('has-theater');
            } else {
                this.mainEl.classList.remove('has-theater');
            }
        }

        // Update toggle button state
        if (this.theaterToggleBtn) {
            this.theaterToggleBtn.classList.toggle('active', this.theaterOpen);
        }
    }

    setTheaterAgentActive(agentName, active = true, message = null) {
        if (!this.theaterAgents) return;

        this.theaterAgents.forEach(el => {
            if (el.dataset.agent === agentName) {
                if (active) {
                    el.classList.add('active');
                    // Set speech bubble text
                    const bubble = el.querySelector('.agent-speech-bubble');
                    if (bubble && message) {
                        bubble.textContent = message.length > 50 ? message.substring(0, 50) + '...' : message;
                    } else if (bubble) {
                        bubble.textContent = 'Thinking...';
                    }
                } else {
                    el.classList.remove('active');
                }
            }
        });
    }

    updateTheaterBubble(agentName, text) {
        const bubble = document.getElementById(`bubble-${agentName}`);
        if (bubble) {
            bubble.textContent = text.length > 60 ? text.substring(0, 60) + '...' : text;
        }
    }

    clearTheaterAgents() {
        if (!this.theaterAgents) return;
        this.theaterAgents.forEach(el => el.classList.remove('active'));
        if (this.arrowLeft) this.arrowLeft.hidden = true;
        if (this.arrowRight) this.arrowRight.hidden = true;
    }


    // ==================== Copy to Clipboard ====================

    copyCurrentCode() {
        const session = this.getActiveSession();
        if (!session || !session.currentFile) {
            this.showToast('warning', 'No file selected');
            return;
        }

        const content = session.files[session.currentFile] ||
                        session.testFiles[session.currentFile] || '';

        if (!content) {
            this.showToast('warning', 'No code to copy');
            return;
        }

        navigator.clipboard.writeText(content).then(() => {
            this.showToast('success', 'Code copied to clipboard');
            if (this.copyCodeBtn) {
                this.copyCodeBtn.classList.add('copied');
                const span = this.copyCodeBtn.querySelector('span:last-child');
                if (span) span.textContent = 'Copied!';
                setTimeout(() => {
                    this.copyCodeBtn.classList.remove('copied');
                    if (span) span.textContent = 'Copy';
                }, 2000);
            }
        }).catch(() => {
            this.showToast('error', 'Failed to copy');
        });
    }

    // ==================== File Tree ====================

    getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            js: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f0db4f" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 8v8"/><path d="M8 16c0-2 4-2 4-4s-4-2-4-4"/></svg>',
            ts: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3178c6" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>',
            py: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3572A5" stroke-width="2"><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2z"/><path d="M8 12l3 3 5-5"/></svg>',
            html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#e34c26" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
            css: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#563d7c" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/></svg>',
            json: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>',
            md: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
            test: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--tester-color)" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
        };
        const defaultIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
        return icons[ext] || defaultIcon;
    }

    renderFileTree() {
        const session = this.getActiveSession();
        if (!session || !this.fileTree) return;

        const allFiles = { ...session.files };
        const testFiles = { ...session.testFiles };
        const hasFiles = Object.keys(allFiles).length > 0 || Object.keys(testFiles).length > 0;

        if (!hasFiles) {
            this.fileTree.innerHTML = '<div class="file-tree-empty">No files yet</div>';
            return;
        }

        let html = '';

        Object.keys(allFiles).forEach(path => {
            const filename = path.split('/').pop();
            const isActive = session.currentFile === path;
            const isTest = filename.includes('.test.') || filename.includes('.spec.');
            html += `
                <div class="file-tree-item ${isActive ? 'active' : ''} ${isTest ? 'test-file' : ''}"
                     data-path="${this.escapeHtml(path)}" data-test="false" title="${this.escapeHtml(path)}">
                    <span class="file-tree-icon">${this.getFileIcon(filename)}</span>
                    <span class="file-tree-name">${this.escapeHtml(filename)}</span>
                </div>
            `;
        });

        Object.keys(testFiles).forEach(path => {
            const filename = path.split('/').pop();
            const isActive = session.currentFile === path;
            html += `
                <div class="file-tree-item test-file ${isActive ? 'active' : ''}"
                     data-path="${this.escapeHtml(path)}" data-test="true" title="${this.escapeHtml(path)}">
                    <span class="file-tree-icon">${this.getFileIcon('test')}</span>
                    <span class="file-tree-name">${this.escapeHtml(filename)}</span>
                </div>
            `;
        });

        this.fileTree.innerHTML = html;

        this.fileTree.querySelectorAll('.file-tree-item').forEach(item => {
            item.addEventListener('click', () => {
                const path = item.dataset.path;
                const isTest = item.dataset.test === 'true';
                this.selectFile(path, isTest);
            });
        });
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('Connected to Vibe Agents');
            this.setStatus('ready', 'Connected');

            if (this.sessions.size === 0) {
                this.requestNewSession();
            } else {
                // Reconnect: get new server sessions for each existing tab
                this._reconnectQueue = Array.from(this.sessions.keys());
                this._reconnectQueue.forEach(() => this.requestNewSession());
            }
        };

        this.ws.onclose = () => {
            console.log('Disconnected, reconnecting...');
            this.setStatus('error', 'Disconnected');
            setTimeout(() => this.connect(), 2000);
        };

        this.ws.onerror = (err) => console.error('WebSocket error:', err);

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
    }

    requestNewSession() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'new_session' }));
        }
    }

    // ==================== Tab Management ====================

    createTab(sessionId) {
        const session = new TabSession(sessionId);
        this.sessions.set(sessionId, session);
        this._bindExampleButtons(session.feedEl);

        if (!this.activeSessionId) {
            this.switchTab(sessionId);
        }

        this.renderTabs();
        this._saveTabState();
    }

    switchTab(sessionId) {
        if (!this.sessions.has(sessionId)) return;

        const oldSession = this.getActiveSession();
        const newSession = this.sessions.get(sessionId);

        // Detach old feed
        if (oldSession && oldSession.feedEl.parentNode) {
            oldSession.feedEl.parentNode.removeChild(oldSession.feedEl);
        }

        this.activeSessionId = sessionId;

        // Attach new feed
        this.agentFeed.innerHTML = '';
        this.agentFeed.appendChild(newSession.feedEl);

        // Restore phase timeline
        this.restorePhaseTimeline(newSession);

        // Restore file tabs, file tree, and code view
        this.renderFileTabs();
        if (newSession.currentFile) {
            this.selectFile(newSession.currentFile);
        } else {
            this.codeView.innerHTML = '<code>// Your generated code will appear here</code>';
            if (this.fileTree) {
                this.renderFileTree();
            }
        }

        // Restore project badge
        this.showProjectBadge(newSession.projectName);

        // Restore processing state
        if (newSession.isProcessing) {
            this.sendBtn.disabled = true;
            this.sendBtn.querySelector('.btn-text').hidden = true;
            this.sendBtn.querySelector('.btn-loading').hidden = false;
            this.setStatus('active', 'Working...');
        } else {
            this.sendBtn.disabled = false;
            this.sendBtn.querySelector('.btn-text').hidden = false;
            this.sendBtn.querySelector('.btn-loading').hidden = true;
            this.setStatus('ready', newSession.projectName ? `Project: ${newSession.projectName}` : 'Ready');
        }

        this.renderTabs();
        this._saveTabState();
        this.scrollFeed(newSession);
    }

    closeTab(sessionId) {
        if (this.sessions.size <= 1) return;

        const session = this.sessions.get(sessionId);
        if (!session) return;

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'close_session', session_id: sessionId }));
        }

        if (sessionId === this.activeSessionId) {
            const ids = Array.from(this.sessions.keys());
            const idx = ids.indexOf(sessionId);
            const nextId = ids[idx + 1] || ids[idx - 1];
            this.switchTab(nextId);
        }

        this.sessions.delete(sessionId);
        this.renderTabs();
        this._saveTabState();
    }

    renderTabs() {
        this.tabList.innerHTML = '';

        for (const [id, session] of this.sessions) {
            const tab = document.createElement('div');
            tab.className = `session-tab ${id === this.activeSessionId ? 'active' : ''}`;
            tab.dataset.sessionId = id;

            const statusDot = document.createElement('span');
            statusDot.className = `tab-status ${session.status}`;

            const title = document.createElement('span');
            title.className = 'tab-title';
            title.textContent = session.projectName || session.title;

            tab.appendChild(statusDot);
            tab.appendChild(title);

            if (this.sessions.size > 1) {
                const closeBtn = document.createElement('button');
                closeBtn.className = 'tab-close';
                closeBtn.innerHTML = '&times;';
                closeBtn.title = 'Close tab';
                closeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.closeTab(id);
                });
                tab.appendChild(closeBtn);
            }

            tab.addEventListener('click', () => this.switchTab(id));
            this.tabList.appendChild(tab);
        }
    }

    updateTabStatus(sessionId, status) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.status = status;
            this.renderTabs();
        }
    }

    _saveTabState() {
        try {
            const state = {
                tabCount: this.sessions.size,
                tabs: Array.from(this.sessions.values()).map(s => ({
                    title: s.title,
                    projectId: s.projectId,
                    projectName: s.projectName
                }))
            };
            localStorage.setItem('vibe-agents-tabs', JSON.stringify(state));
        } catch (e) { /* ignore */ }
    }

    _loadTabState() {
        try {
            const saved = localStorage.getItem('vibe-agents-tabs');
            return saved ? JSON.parse(saved) : null;
        } catch (e) {
            return null;
        }
    }

    _bindExampleButtons(container) {
        container.querySelectorAll('.example-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt;
                if (prompt) {
                    this.input.value = prompt;
                    this.input.focus();
                }
            });
        });
    }

    // ==================== Project Sidebar ====================

    toggleSidebar(forceState) {
        const shouldOpen = forceState !== undefined ? forceState : !this.sidebarOpen;
        this.sidebarOpen = shouldOpen;

        if (shouldOpen) {
            this.projectSidebar.hidden = false;
            this.projectsToggle.classList.add('active');
            document.querySelector('.main').classList.add('has-sidebar');
            this.loadProjects();
        } else {
            this.projectSidebar.hidden = true;
            this.projectsToggle.classList.remove('active');
            document.querySelector('.main').classList.remove('has-sidebar');
        }
    }

    async loadProjects() {
        try {
            const resp = await fetch('/api/projects');
            if (!resp.ok) return;
            const data = await resp.json();
            this.renderProjectList(data.projects || []);
        } catch (e) {
            console.error('Failed to load projects:', e);
        }
    }

    renderProjectList(projects) {
        const session = this.getActiveSession();
        const activeProjectId = session ? session.projectId : null;

        if (!projects.length) {
            this.projectList.innerHTML = '<div class="project-list-empty">No projects yet. Start building!</div>';
            return;
        }

        this.projectList.innerHTML = projects.map(p => {
            const isActive = p.id === activeProjectId;
            const timeAgo = this._timeAgo(p.updated_at);
            const desc = p.description ? this.escapeHtml(p.description).substring(0, 60) : '';

            return `
                <div class="project-card ${isActive ? 'active' : ''}" data-project-id="${p.id}">
                    <div class="project-card-name">${this.escapeHtml(p.name)}</div>
                    ${desc ? `<div class="project-card-desc">${desc}</div>` : ''}
                    <div class="project-card-meta">
                        <span class="project-card-files">${p.file_count || 0} files</span>
                        <span>${timeAgo}</span>
                        <div class="project-card-actions">
                            <button class="project-card-btn resume" data-action="resume" data-id="${p.id}">Resume</button>
                            <button class="project-card-btn delete" data-action="delete" data-id="${p.id}">Del</button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        this.projectList.querySelectorAll('.project-card-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                const id = parseInt(btn.dataset.id, 10);
                if (action === 'resume') this.resumeProject(id);
                if (action === 'delete') this.deleteProject(id);
            });
        });

        this.projectList.querySelectorAll('.project-card').forEach(card => {
            card.addEventListener('click', () => {
                const id = parseInt(card.dataset.projectId, 10);
                this.resumeProject(id);
            });
        });
    }

    async resumeProject(projectId) {
        const session = this.getActiveSession();
        if (!this.ws || !session || session.isProcessing) return;

        this.setStatus('active', 'Resuming project...');
        this.ws.send(JSON.stringify({
            type: 'resume',
            project_id: projectId,
            session_id: session.id
        }));
    }

    async deleteProject(projectId) {
        try {
            const resp = await fetch(`/api/projects/${projectId}`, { method: 'DELETE' });
            if (resp.ok) {
                const session = this.getActiveSession();
                if (session && session.projectId === projectId) {
                    session.projectId = null;
                    session.projectName = null;
                    this.showProjectBadge(null);
                }
                this.loadProjects();
            }
        } catch (e) {
            console.error('Failed to delete project:', e);
        }
    }

    showProjectBadge(name) {
        if (name) {
            this.projectBadge.textContent = name;
            this.projectBadge.hidden = false;
        } else {
            this.projectBadge.hidden = true;
        }
    }

    _timeAgo(timestamp) {
        if (!timestamp) return '';
        const seconds = Math.floor(Date.now() / 1000 - timestamp);
        if (seconds < 60) return 'just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    }

    // ==================== Status & Active Agent ====================

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

    // ==================== Phase Timeline ====================

    setPhase(phaseName, session) {
        const idx = this.phases.indexOf(phaseName);
        if (idx === -1) return;

        session.phaseIndex = idx;

        // Only update the shared timeline if this is the active session
        if (session.id === this.activeSessionId) {
            this.phaseTimeline.hidden = false;

            const steps = this.phaseTimeline.querySelectorAll('.phase-step');
            const connectors = this.phaseTimeline.querySelectorAll('.phase-connector');

            steps.forEach((step, i) => {
                step.classList.remove('active', 'completed');
                if (i < idx) step.classList.add('completed');
                else if (i === idx) step.classList.add('active');
            });

            connectors.forEach((conn, i) => {
                conn.classList.toggle('filled', i < idx);
            });
        }
    }

    restorePhaseTimeline(session) {
        if (session.phaseIndex >= 0) {
            this.phaseTimeline.hidden = false;
            const steps = this.phaseTimeline.querySelectorAll('.phase-step');
            const connectors = this.phaseTimeline.querySelectorAll('.phase-connector');

            steps.forEach((step, i) => {
                step.classList.remove('active', 'completed');
                if (i < session.phaseIndex) step.classList.add('completed');
                else if (i === session.phaseIndex) step.classList.add('active');
            });

            connectors.forEach((conn, i) => {
                conn.classList.toggle('filled', i < session.phaseIndex);
            });
        } else {
            this.phaseTimeline.hidden = true;
            this.phaseTimeline.querySelectorAll('.phase-step').forEach(s => s.classList.remove('active', 'completed'));
            this.phaseTimeline.querySelectorAll('.phase-connector').forEach(c => c.classList.remove('filled'));
        }
    }

    resetPhaseTimeline(session) {
        session.phaseIndex = -1;
        if (session.id === this.activeSessionId) {
            this.restorePhaseTimeline(session);
        }
    }

    // ==================== Send / Clear ====================

    sendMessage() {
        const message = this.input.value.trim();
        const session = this.getActiveSession();
        if (!message || !this.ws || !session || session.isProcessing) return;

        this.addUserMessage(message, session);
        this.input.value = '';

        session.isProcessing = true;
        this.setStatus('active', 'Thinking...');
        this.sendBtn.disabled = true;
        this.sendBtn.querySelector('.btn-text').hidden = true;
        this.sendBtn.querySelector('.btn-loading').hidden = false;

        session.currentStreamEl = null;
        session.currentStreamAgent = null;

        if (this.useFullPipeline) {
            this.ws.send(JSON.stringify({ type: 'build', prompt: message, session_id: session.id }));
        } else {
            this.ws.send(JSON.stringify({ type: 'chat', message: message, session_id: session.id }));
        }

        this.updateTabStatus(session.id, 'working');
    }

    clearConversation() {
        const session = this.getActiveSession();
        if (!session) return;

        if (this.ws) {
            this.ws.send(JSON.stringify({ type: 'clear', session_id: session.id }));
        }

        session.files = {};
        session.testFiles = {};
        session.currentFile = null;
        session.currentStreamEl = null;
        session.currentStreamAgent = null;
        session.projectId = null;
        session.projectName = null;
        session.title = 'New Session';

        this.showProjectBadge(null);
        this.resetPhaseTimeline(session);

        session.feedEl.innerHTML = `
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
        this._bindExampleButtons(session.feedEl);

        this.fileTabs.innerHTML = '';
        this.codeView.innerHTML = '<code>// Your generated code will appear here</code>';
        if (this.fileTree) {
            this.fileTree.innerHTML = '<div class="file-tree-empty">No files yet</div>';
        }
        this.setStatus('ready', 'Ready to chat');

        this.renderTabs();
        if (this.sidebarOpen) this.loadProjects();
    }

    // ==================== Message Router ====================

    handleMessage(message) {
        const { type, data, session_id } = message;

        // ---- Session lifecycle events ----

        if (type === 'session_created') {
            const newId = message.session_id;
            if (this._reconnectQueue && this._reconnectQueue.length > 0) {
                // Remap existing tab to new server session
                const oldId = this._reconnectQueue.shift();
                const session = this.sessions.get(oldId);
                if (session) {
                    this.sessions.delete(oldId);
                    session.id = newId;
                    this.sessions.set(newId, session);
                    if (this.activeSessionId === oldId) this.activeSessionId = newId;
                }
                if (this._reconnectQueue.length === 0) this._reconnectQueue = null;
                this.renderTabs();
            } else {
                this.createTab(newId);
            }
            return;
        }

        if (type === 'session_closed' || type === 'sessions_list') return;

        // ---- Route to correct session ----

        const session = session_id ? this.getSession(session_id) : this.getActiveSession();
        if (!session) return;

        const isActive = session.id === this.activeSessionId;

        switch (type) {
            case 'routing':
                if (isActive) this.setStatus('active', data.message || 'Analyzing...');
                break;

            case 'route_decision':
                this.showRouteDecision(data, session);
                break;

            case 'chat_response':
                this.handleChatResponse(data, session);
                break;

            case 'status':
                if (isActive) this.setStatus('active', data);
                break;

            case 'phase':
                this.handlePhase(data, session);
                break;

            case 'agent_message':
                this.handleAgentMessage(data, session);
                break;

            case 'plan_ready':
                this.showPlan(data, session);
                break;

            case 'task_start':
                this.addTaskIndicator(data, session);
                break;

            case 'file_created':
            case 'file_updated':
                this.addFileEvent(data, type === 'file_updated', session);
                if (data.path && data.code) {
                    session.files[data.path] = data.code;
                    if (isActive) this.renderFileTabs();
                }
                break;

            case 'execution_result':
                this.showExecutionResult(data, session);
                break;

            case 'debug_attempt':
                this.addDebugAttempt(data, session);
                break;

            case 'debug_success':
                this.addSystemMessage('success', typeof data === 'string' ? data : JSON.stringify(data), session);
                break;

            case 'fix_applied':
            case 'fix_suggested':
                this.addFixMessage(data, session);
                break;

            case 'review_complete':
                this.showReview(data, session);
                break;

            case 'test_created':
                this.addTestMessage(data, session);
                break;

            case 'test_result':
            case 'test_complete':
                this.showTestResult(data, session);
                break;

            case 'warning':
            case 'debug_failed':
            case 'debug_exhausted':
                this.addSystemMessage('warning', typeof data === 'string' ? data : JSON.stringify(data), session);
                break;

            case 'error':
                this.addSystemMessage('error', typeof data === 'string' ? data : JSON.stringify(data), session);
                this.resetUI(session);
                break;

            case 'build_complete':
                this.handleBuildComplete(data, session);
                break;

            case 'project_active':
                this.handleProjectActive(data, session);
                break;

            case 'project_resumed':
                this.handleProjectResumed(data, session);
                break;

            case 'dialogue_start':
                this.addDialogueDivider(data.topic || 'Agent Discussion', session);
                break;

            case 'dialogue_exchange':
                if (isActive) this.setStatus('active', `${data.from} \u2192 ${data.to} (round ${data.round})`);
                break;

            case 'dialogue_resolved':
                this.addSystemMessage('success', `${data.topic}: ${data.result} (${data.rounds} round${data.rounds > 1 ? 's' : ''})`, session);
                break;

            case 'dialogue_end':
            case 'cleared':
                break;

            default:
                console.log('Unknown message type:', type, data);
        }
    }

    // ==================== Project Events ====================

    handleProjectActive(data, session) {
        session.projectId = data.id;
        session.projectName = data.name;
        session.title = data.name;

        if (session.id === this.activeSessionId) {
            this.showProjectBadge(data.name);
        }
        this.renderTabs();
        if (this.sidebarOpen) this.loadProjects();
    }

    handleProjectResumed(data, session) {
        const project = data.project || data;
        session.projectId = project.id;
        session.projectName = project.name;
        session.title = project.name;

        if (session.id === this.activeSessionId) {
            this.showProjectBadge(project.name);
        }

        const context = data.context || '';
        this.addSystemMessage('success',
            `Resumed project: ${project.name}` +
            (project.file_count ? ` (${project.file_count} files)` : ''),
            session
        );

        if (context) {
            this.addAssistantMessage(`Project context restored:\n${context}`, session);
        }

        if (session.id === this.activeSessionId) {
            this.setStatus('ready', `Project: ${project.name}`);
        }
        this.renderTabs();
        if (this.sidebarOpen) this.loadProjects();
    }

    // ==================== Phase Handling ====================

    handlePhase(phase, session) {
        if (session.currentStreamAgent) {
            this.finalizeAgentStream(session.currentStreamAgent, session);
        }

        this.setPhase(phase, session);

        const el = document.createElement('div');
        el.className = 'phase-indicator';
        el.textContent = phase;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    // ==================== Agent Message Handling ====================

    handleAgentMessage(data, session) {
        const { agent, type: msgType, content } = data;
        const isActive = session.id === this.activeSessionId;

        switch (msgType) {
            case 'thinking':
                if (isActive) {
                    this.showActiveAgent(agent);
                    this.setStatus('active', `${agent}: ${content}`);
                    // Activate agent in theater
                    this.setTheaterAgentActive(agent, true);
                }
                this.startAgentStream(agent, session);
                break;

            case 'streaming':
                this.appendStreamText(agent, content, session);
                // Update theater speech bubble with latest text
                if (session.currentStreamEl) {
                    const fullText = session.currentStreamEl.textContent || '';
                    this.updateTheaterBubble(agent, fullText);
                }
                break;

            case 'tool_use':
                this.addToolUseCard(agent, content, session);
                break;

            case 'tool_result':
                if (isActive) this.setStatus('active', `${agent}: Processing tool result...`);
                break;

            case 'done':
                this.finalizeAgentStream(agent, session);
                // Deactivate agent in theater after a delay
                setTimeout(() => this.setTheaterAgentActive(agent, false), 500);
                break;

            case 'response':
                break;

            case 'cost':
                try {
                    const costData = typeof content === 'string' ? JSON.parse(content) : content;
                    if (costData.cost_usd && isActive) {
                        this.setStatus('active', `${agent}: Done ($${costData.cost_usd.toFixed(4)})`);
                    }
                } catch (e) { /* ignore */ }
                break;

            case 'error':
                this.addSystemMessage('error', `${agent}: ${content}`, session);
                break;

            case 'warning':
                this.addSystemMessage('warning', `${agent}: ${content}`, session);
                break;

            default:
                this.addAgentBubble(agent, content, msgType, session);
                break;
        }
    }

    // ==================== Agent Stream (Chat Bubble) ====================

    startAgentStream(agent, session) {
        if (session.currentStreamAgent === agent && session.currentStreamEl) {
            return;
        }

        if (session.currentStreamAgent && session.currentStreamAgent !== agent) {
            this.finalizeAgentStream(session.currentStreamAgent, session);
        }

        const el = document.createElement('div');
        el.className = `agent-message ${agent.toLowerCase()} streaming`;

        const avatarWrap = document.createElement('div');
        avatarWrap.className = 'agent-avatar-wrap';
        avatarWrap.style.color = this.getAgentColor(agent);
        avatarWrap.innerHTML = this.getAgentSVG(agent);

        const bubble = document.createElement('div');
        bubble.className = 'agent-bubble';

        const header = document.createElement('div');
        header.className = 'agent-header';
        header.innerHTML = `
            <span class="agent-name ${agent.toLowerCase()}">${agent}</span>
            <span class="agent-role">${this.getAgentRole(agent)}</span>
            <span class="streaming-indicator"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>
        `;

        const contentEl = document.createElement('div');
        contentEl.className = 'agent-content streaming-content';
        contentEl.textContent = '';

        bubble.appendChild(header);
        bubble.appendChild(contentEl);
        el.appendChild(avatarWrap);
        el.appendChild(bubble);

        const welcome = session.feedEl.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        session.feedEl.appendChild(el);
        session.currentStreamEl = contentEl;
        session.currentStreamAgent = agent;
        this.scrollFeed(session);
    }

    appendStreamText(agent, text, session) {
        if (!session.currentStreamEl || session.currentStreamAgent !== agent) {
            this.startAgentStream(agent, session);
        }
        session.currentStreamEl.textContent += text;
        this.scrollFeed(session);
    }

    finalizeAgentStream(agent, session) {
        if (session.currentStreamEl && session.currentStreamAgent === agent) {
            const rawText = session.currentStreamEl.textContent;
            session.currentStreamEl.innerHTML = this.formatContent(rawText);

            const parent = session.currentStreamEl.closest('.agent-message');
            if (parent) {
                parent.classList.remove('streaming');
                const indicator = parent.querySelector('.streaming-indicator');
                if (indicator) indicator.remove();
            }

        }

        session.currentStreamEl = null;
        session.currentStreamAgent = null;
    }

    // ==================== Agent Bubble (non-streaming) ====================

    addAgentBubble(agent, content, msgType, session) {
        const el = document.createElement('div');
        el.className = `agent-message ${agent.toLowerCase()}`;

        const avatarWrap = document.createElement('div');
        avatarWrap.className = 'agent-avatar-wrap';
        avatarWrap.style.color = this.getAgentColor(agent);
        avatarWrap.innerHTML = this.getAgentSVG(agent);

        const bubble = document.createElement('div');
        bubble.className = 'agent-bubble';

        const header = document.createElement('div');
        header.className = 'agent-header';
        header.innerHTML = `
            <span class="agent-name ${agent.toLowerCase()}">${agent}</span>
            <span class="agent-role">${this.getAgentRole(agent)}</span>
        `;

        const contentEl = document.createElement('div');
        contentEl.className = `agent-content ${msgType || ''}`;
        contentEl.innerHTML = this.formatContent(this.truncate(content, 800));

        bubble.appendChild(header);
        bubble.appendChild(contentEl);
        el.appendChild(avatarWrap);
        el.appendChild(bubble);

        const welcome = session.feedEl.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    // ==================== Tool Activity Cards ====================

    addToolUseCard(agent, content, session) {
        let toolData;
        try {
            toolData = typeof content === 'string' ? JSON.parse(content) : content;
        } catch (e) {
            toolData = { tool: 'Unknown', input: {} };
        }

        const input = toolData.input || {};
        const tool = toolData.tool || 'Unknown';
        const toolLower = tool.toLowerCase();
        const isActive = session.id === this.activeSessionId;

        if (tool === 'Bash') {
            this._addBashTerminal(agent, input.command || '', session);
            return;
        }

        if (tool === 'Write') {
            this._addFileCard(agent, input.file || 'file', input.size, session);
            return;
        }

        let description = '';
        if (tool === 'Read') description = `Reading ${input.file || 'file'}`;
        else if (tool === 'Edit') description = `Editing ${input.file || 'file'}`;
        else if (tool === 'Glob') description = `Finding: ${input.pattern || '*'}`;
        else if (tool === 'Grep') description = `Searching: ${input.pattern || ''}`;
        else description = `Using ${tool}`;

        const el = document.createElement('div');
        el.className = `tool-activity ${toolLower}`;
        el.innerHTML = `
            <span class="tool-icon">${this._getToolIcon(tool)}</span>
            <span class="tool-agent">${agent}</span>
            <span class="tool-description">${this.escapeHtml(description)}</span>
        `;

        session.feedEl.appendChild(el);
        this.scrollFeed(session);
        if (isActive) this.setStatus('active', `${agent}: ${description}`);
    }

    _addBashTerminal(agent, command, session) {
        const el = document.createElement('div');
        el.className = 'tool-terminal';
        el.innerHTML = `
            <div class="tool-terminal-header">
                <div class="tool-terminal-dots"><span></span><span></span><span></span></div>
                <span>${agent} - Terminal</span>
            </div>
            <div class="tool-terminal-cmd">${this.escapeHtml(command.substring(0, 200))}</div>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
        if (session.id === this.activeSessionId) this.setStatus('active', `${agent}: Running command...`);
    }

    _addFileCard(agent, filename, size, session) {
        const el = document.createElement('div');
        el.className = 'tool-file-card';
        el.innerHTML = `
            <span class="tool-file-icon">${this._getToolIcon('Write')}</span>
            <span class="tool-file-name">${this.escapeHtml(filename)}</span>
            ${size ? `<span class="tool-file-size">${size} chars</span>` : ''}
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
        if (session.id === this.activeSessionId) this.setStatus('active', `${agent}: Creating ${filename}`);
    }

    _getToolIcon(tool) {
        const icons = {
            Read: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--planner-color)" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`,
            Write: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--coder-color)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>`,
            Edit: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--reviewer-color)" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
            Bash: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--warning)" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
            Glob: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
            Grep: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`
        };
        return icons[tool] || `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>`;
    }

    // ==================== Route Decision ====================

    showRouteDecision(data, session) {
        if (data.action === 'CONVERSATION') return;

        const el = document.createElement('div');
        el.className = 'route-decision';
        el.innerHTML = `
            <span class="route-action">${data.action}</span>
            <span class="route-confidence">${Math.round((data.confidence || 0) * 100)}%</span>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    // ==================== Chat Response ====================

    handleChatResponse(data, session) {
        if (session.currentStreamAgent) {
            this.finalizeAgentStream(session.currentStreamAgent, session);
        }

        this.resetUI(session);

        // For conversation responses, update the last Router bubble instead of creating new message
        if (data.type === 'conversation') {
            const routerBubbles = session.feedEl.querySelectorAll('.agent-message.router');
            const lastRouterBubble = routerBubbles[routerBubbles.length - 1];
            if (lastRouterBubble) {
                const contentEl = lastRouterBubble.querySelector('.agent-content');
                if (contentEl) {
                    contentEl.innerHTML = this.formatContent(data.response || '');
                    this.scrollFeed(session);
                    if (session.id === this.activeSessionId) {
                        this.showActiveAgent(null);
                    }
                    if (this.sidebarOpen) this.loadProjects();
                    return;
                }
            }
            // Fallback if no Router bubble found
            this.addAssistantMessage(data.response, session, 'Router');
        } else if (data.type === 'code') {
            if (data.success) {
                if (data.files && data.files.length > 0) {
                    this.addAssistantMessage(
                        data.response ||
                        `Created ${data.files.length} file(s): ${data.files.join(', ')}`,
                        session
                    );
                } else {
                    this.addAssistantMessage(data.response || 'Code task completed.', session);
                }
            } else {
                this.addAssistantMessage(data.response || 'Something went wrong.', session);
            }
        } else if (data.type === 'build') {
            this.handleBuildComplete(data, session);
        } else if (data.type === 'fix') {
            this.addAssistantMessage(data.response || 'Fix applied.', session);
        } else if (data.type === 'review') {
            this.addAssistantMessage(data.response || 'Review completed.', session);
        } else if (data.type === 'test') {
            this.addAssistantMessage(data.response || 'Tests completed.', session);
        } else if (data.type === 'error') {
            this.addSystemMessage('error', data.error, session);
        } else {
            this.addAssistantMessage(
                data.response || JSON.stringify(data, null, 2),
                session
            );
        }

        if (session.id === this.activeSessionId) {
            this.showActiveAgent(null);
        }

        if (this.sidebarOpen) this.loadProjects();
    }

    // ==================== User / Assistant Messages ====================

    addUserMessage(text, session) {
        const welcome = session.feedEl.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        const el = document.createElement('div');
        el.className = 'chat-message user-message';
        el.innerHTML = `
            <div class="message-header">
                <span class="message-sender">You</span>
            </div>
            <div class="message-content">${this.escapeHtml(text)}</div>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    addAssistantMessage(text, session, agentName = 'Router') {
        const el = document.createElement('div');
        el.className = 'chat-message assistant-message';
        el.innerHTML = `
            <div class="message-header">
                <span class="message-sender">${agentName}</span>
            </div>
            <div class="message-content">${this.formatContent(text)}</div>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    // ==================== Dialogue Divider ====================

    addDialogueDivider(text, session) {
        const el = document.createElement('div');
        el.className = 'dialogue-divider';
        el.textContent = text || 'Agent Discussion';
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    // ==================== Build / Plan / Review / Test ====================

    handleBuildComplete(result, session) {
        if (session.currentStreamAgent) {
            this.finalizeAgentStream(session.currentStreamAgent, session);
        }

        const isActive = session.id === this.activeSessionId;

        // Clear all active agents in theater
        this.clearTheaterAgents();

        // Mark all phases complete
        if (session.phaseIndex >= 0 && isActive) {
            this.phaseTimeline.querySelectorAll('.phase-step').forEach(s => {
                s.classList.remove('active');
                s.classList.add('completed');
            });
            this.phaseTimeline.querySelectorAll('.phase-connector').forEach(c => {
                c.classList.add('filled');
            });
        }

        this.resetUI(session);

        if (result.success) {
            if (isActive) this.setStatus('ready', 'Build Complete!');
            const files = result.files || [];
            if (files.length > 0) {
                this.addSystemMessage('success',
                    `${result.project || 'Project'} built! ${files.length} file(s) created: ${files.join(', ')}`,
                    session
                );
            } else {
                this.addSystemMessage('success', `${result.project || 'Project'} built!`, session);
            }

            // Toast for background builds
            if (!isActive) {
                this.showToast('success', `Build complete: ${result.project || 'Project'}`);
            }

            if (result.project_id) {
                session.projectId = result.project_id;
                session.projectName = result.project;
                session.title = result.project;
                if (isActive) this.showProjectBadge(result.project);
                this.renderTabs();
            }
        } else {
            if (isActive) this.setStatus('error', 'Build Failed');
            this.addSystemMessage('error', result.error || 'Build failed', session);
        }

        if (this.sidebarOpen) this.loadProjects();
    }

    showPlan(plan, session) {
        const el = document.createElement('div');
        el.className = 'plan-card';
        el.innerHTML = `
            <div class="plan-header">
                <span class="plan-title">${this.escapeHtml(plan.project_name || 'Project')}</span>
                <span class="plan-tech">${this.escapeHtml(plan.tech_stack?.language || 'Python')}</span>
            </div>
            <div class="plan-summary">${this.escapeHtml(plan.summary || '')}</div>
            <div class="plan-tasks">
                <strong>Tasks:</strong>
                <ol>
                    ${(plan.tasks || []).map(t => `<li>${this.escapeHtml(t.title || t.description || 'Task')}</li>`).join('')}
                </ol>
            </div>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    showReview(review, session) {
        const el = document.createElement('div');
        const status = review.status || 'complete';
        el.className = `review-card ${status}`;

        let issuesHtml = '';
        if (review.issues && review.issues.length > 0) {
            issuesHtml = `
                <div class="review-issues">
                    ${review.issues.map(i => `
                        <div class="issue ${this.escapeHtml(i.severity || 'info')}">
                            <span class="issue-severity">${this.escapeHtml(i.severity || 'info')}</span>
                            <span class="issue-text">${this.escapeHtml(i.issue || i.description || '')}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        el.innerHTML = `
            <div class="review-header">
                Review: <strong>${this.escapeHtml(status.toUpperCase())}</strong>
            </div>
            <div class="review-summary">${this.escapeHtml(review.summary || '')}</div>
            ${issuesHtml}
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    showTestResult(data, session) {
        const el = document.createElement('div');
        const isSuccess = data.success !== false;
        el.className = `test-result ${isSuccess ? 'success' : 'failed'}`;
        el.innerHTML = `
            <div class="test-header">
                ${isSuccess ? 'Tests Passed' : 'Tests Failed'}
            </div>
            <pre class="test-output">${this.escapeHtml(data.output || data.summary || '')}</pre>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    showExecutionResult(data, session) {
        const el = document.createElement('div');
        el.className = `execution-result ${data.success ? 'success' : 'error'}`;
        el.innerHTML = `
            <div class="execution-header">
                ${data.success ? 'Execution Successful' : 'Execution Failed'}
            </div>
            ${data.stdout ? `<pre class="execution-output">${this.escapeHtml(data.stdout)}</pre>` : ''}
            ${data.stderr ? `<pre class="execution-error">${this.escapeHtml(data.stderr)}</pre>` : ''}
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    // ==================== Minor Event Cards ====================

    addTaskIndicator(data, session) {
        const el = document.createElement('div');
        el.className = 'task-indicator';
        el.innerHTML = `
            <div class="task-progress">
                <div class="task-progress-bar" style="width: ${(data.task_number / data.total) * 100}%"></div>
            </div>
            <span class="task-label">Task ${data.task_number}/${data.total}: ${this.escapeHtml(data.title)}</span>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    addFileEvent(data, isUpdate, session) {
        const action = isUpdate ? 'Updated' : 'Created';
        const el = document.createElement('div');
        el.className = 'tool-file-card';
        el.innerHTML = `
            <span class="tool-file-icon">${this._getToolIcon(isUpdate ? 'Edit' : 'Write')}</span>
            <span class="tool-file-name">${this.escapeHtml(data.path)}</span>
            <span class="tool-file-size">${action}</span>
        `;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);
    }

    addDebugAttempt(data, session) {
        this.addAgentBubble('Debugger',
            `Debug attempt ${data.attempt}/${data.max} - Analyzing and fixing issues...`,
            'thinking', session
        );
    }

    addFixMessage(data, session) {
        this.addAgentBubble('Debugger',
            `Fix applied to ${data.file || 'code'}: ${data.diagnosis || 'Applied fix'}`,
            'response', session
        );
    }

    addTestMessage(data, session) {
        this.addAgentBubble('Tester',
            `Tests created: ${data.path || 'test suite'} - ${data.description || 'Test suite generated'}`,
            'response', session
        );
    }

    // ==================== System Messages ====================

    addSystemMessage(level, text, session) {
        const el = document.createElement('div');
        el.className = `system-message ${level}`;
        const textStr = typeof text === 'string' ? text : JSON.stringify(text);
        el.textContent = textStr;
        session.feedEl.appendChild(el);
        this.scrollFeed(session);

        // Show toast for background sessions (not active tab)
        if (session.id !== this.activeSessionId && (level === 'success' || level === 'error')) {
            const tabTitle = session.projectName || session.title;
            this.showToast(level, `[${tabTitle}] ${textStr.substring(0, 80)}`);
        }
    }

    // ==================== Reset UI ====================

    resetUI(session) {
        session.isProcessing = false;
        this.updateTabStatus(session.id, 'idle');

        if (session.id === this.activeSessionId) {
            this.sendBtn.disabled = false;
            this.sendBtn.querySelector('.btn-text').hidden = false;
            this.sendBtn.querySelector('.btn-loading').hidden = true;
            this.setStatus('ready', session.projectName ? `Project: ${session.projectName}` : 'Ready');
        }
    }

    // ==================== File Tabs ====================

    renderFileTabs() {
        const session = this.getActiveSession();
        if (!session) return;

        this.fileTabs.innerHTML = '';

        Object.keys(session.files).forEach(path => {
            const tab = document.createElement('button');
            tab.className = 'file-tab';
            tab.textContent = path.split('/').pop();
            tab.title = path;
            tab.onclick = () => this.selectFile(path);
            this.fileTabs.appendChild(tab);
        });

        Object.keys(session.testFiles).forEach(path => {
            const tab = document.createElement('button');
            tab.className = 'file-tab test-file';
            tab.textContent = path.split('/').pop();
            tab.title = path;
            tab.onclick = () => this.selectFile(path, true);
            this.fileTabs.appendChild(tab);
        });

        // Also update file tree
        this.renderFileTree();
    }

    selectFile(path, isTest = false) {
        const session = this.getActiveSession();
        if (!session) return;

        session.currentFile = path;
        const content = isTest ?
            (session.testFiles[path] || '// Empty') :
            (session.files[path] || '// Empty');

        // Update file tabs active state
        document.querySelectorAll('.file-tab').forEach(tab => {
            tab.classList.toggle('active', tab.title === path);
        });

        // Update file tree active state
        if (this.fileTree) {
            this.fileTree.querySelectorAll('.file-tree-item').forEach(item => {
                item.classList.toggle('active', item.dataset.path === path);
            });
        }

        // Render code with syntax highlighting
        const extension = path.split('.').pop();
        const langMap = {
            js: 'javascript', ts: 'typescript', py: 'python',
            html: 'html', css: 'css', json: 'json', md: 'markdown',
            sh: 'bash', yml: 'yaml', yaml: 'yaml', jsx: 'javascript',
            tsx: 'typescript', rb: 'ruby', go: 'go', rs: 'rust',
            java: 'java', c: 'c', cpp: 'cpp', h: 'c'
        };
        const language = langMap[extension] || extension;

        const codeEl = document.createElement('code');
        codeEl.className = `language-${language}`;
        codeEl.textContent = content;

        this.codeView.innerHTML = '';
        this.codeView.appendChild(codeEl);

        // Apply highlight.js if available
        if (window.hljs) {
            try {
                window.hljs.highlightElement(codeEl);
            } catch (e) { /* ignore highlight errors */ }
        }
    }

    // ==================== Formatting Utilities ====================

    formatContent(text) {
        if (!text) return '';
        text = this.escapeHtml(text);

        // Code blocks with optional language
        text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            const langClass = lang ? `language-${lang}` : '';
            if (window.hljs && lang) {
                try {
                    const result = window.hljs.highlight(code, { language: lang, ignoreIllegals: true });
                    return `<pre class="code-block"><code class="hljs ${langClass}">${result.value}</code></pre>`;
                } catch (e) { /* fall through */ }
            }
            return `<pre class="code-block"><code class="${langClass}">${code}</code></pre>`;
        });

        text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
        text = text.replace(/\n/g, '<br>');
        return text;
    }

    truncate(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrollFeed(session) {
        if (!session || session.id === this.activeSessionId) {
            this.agentFeed.scrollTop = this.agentFeed.scrollHeight;
        }
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.app = new VibeAgents();
});
