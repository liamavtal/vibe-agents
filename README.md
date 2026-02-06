# Vibe Agents

A multi-agent AI coding platform. Talk naturally, watch AI agents collaborate to build it.

## Features

- **6 Specialized Agents** - Router, Planner, Coder, Reviewer, Tester, Debugger
- **Real-Time Streaming** - Watch agents think, use tools, and write code live
- **Agent Conversations** - Agents discuss and debate with each other
- **Multi-Session Tabs** - Work on multiple projects simultaneously
- **Project Persistence** - Close browser, come back, resume where you left off
- **CLI & Web UI** - Use from terminal or browser
- **Dark/Light Themes** - Toggle with keyboard shortcut
- **File Tree & Syntax Highlighting** - Professional code viewing
- **Windows Service** - Auto-starts on boot, accessible from any device
- **Uses Claude Max** - No separate API key needed (uses Claude CLI)

## Quick Start

### Option 1: CLI (Fastest)

```bash
# Clone and install
git clone https://github.com/liamavtal/vibe-agents.git
cd vibe-agents
pip install -e .

# Use it
vibe "build me a todo app"
vibe --interactive              # Chat mode
vibe --build "create a REST API" # Full pipeline
```

### Option 2: Web UI

```bash
# Clone and install
git clone https://github.com/liamavtal/vibe-agents.git
cd vibe-agents
pip install -r backend/requirements.txt

# Start server
python deploy/start.py

# Open browser to http://localhost:8000
```

### Option 3: Windows Service (For Servers)

```powershell
# Clone
git clone https://github.com/liamavtal/vibe-agents.git
cd vibe-agents

# Run installer as Administrator
powershell -ExecutionPolicy Bypass -File deploy\install-windows.ps1
```

This installs Vibe Agents as a Windows service that:
- Auto-starts on boot
- Auto-restarts on crash
- Opens firewall port
- Prints the URL to access from any device

## Requirements

- **Python 3.9+**
- **Claude CLI** - Install with: `npm install -g @anthropic-ai/claude-code`
- **Node.js 18+** - Required for Claude CLI

## CLI Commands

```bash
vibe "prompt"                    # Smart routing (auto-detects intent)
vibe --build "prompt"            # Full pipeline: plan → code → review → test
vibe --code "prompt"             # Code-only mode
vibe --fix "prompt"              # Debug/fix mode
vibe --review                    # Review current project
vibe --interactive               # Interactive chat session

vibe --server                    # Start web server
vibe --connect "prompt"          # Send to running server

vibe --projects                  # List saved projects
vibe --resume 3                  # Resume project by ID

vibe --help                      # Show all options
```

## Keyboard Shortcuts (Web UI)

| Shortcut | Action |
|----------|--------|
| `Ctrl+Enter` | Send message |
| `Ctrl+N` | New session tab |
| `Ctrl+W` | Close current tab |
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |
| `Ctrl+L` | Clear conversation |
| `Ctrl+Shift+T` | Toggle theme |
| `?` | Show shortcuts |

## How It Works

```
You: "Build me a calculator"
         │
         ▼
┌─────────────────┐
│  🔀 Router      │  Analyzes intent, picks the right mode
└────────┬────────┘
         ▼
┌─────────────────┐
│  📋 Planner     │  Reads existing code, designs architecture
└────────┬────────┘
         ▼
┌─────────────────┐
│  💻 Coder       │  Uses real tools: Write, Edit, Bash, etc.
└────────┬────────┘
         ▼
┌─────────────────┐
│  👀 Reviewer    │  Reads code, checks for bugs & security
└────────┬────────┘
         │
    Issues? ──Yes──▶ 💬 Dialogue (agents discuss fixes)
         │
         ▼
┌─────────────────┐
│  🧪 Tester      │  Writes and runs tests
└────────┬────────┘
         │
    Failing? ──Yes──▶ 🔧 Debugger (auto-fix loop)
         │
         ▼
   ✅ Complete!
```

## Architecture

```
vibe-agents/
├── backend/
│   ├── agents/              # AI agents (use Claude CLI)
│   │   ├── base.py          # Base agent with streaming
│   │   ├── router.py        # Intent detection
│   │   ├── planner.py       # Task breakdown
│   │   ├── coder.py         # Code generation (has tool access)
│   │   ├── reviewer.py      # Code review
│   │   ├── tester.py        # Test generation
│   │   └── debugger.py      # Bug fixing
│   ├── orchestrator/        # Coordinates agents
│   │   ├── engine.py        # Pipeline orchestrator
│   │   ├── conversation.py  # Chat orchestrator with routing
│   │   └── dialogue.py      # Agent-to-agent discussions
│   ├── storage/             # Persistence
│   │   ├── database.py      # SQLite (projects, memory)
│   │   ├── file_locator.py  # Smart file placement
│   │   └── project_context.py
│   ├── api/                 # FastAPI
│   │   ├── routes.py        # WebSocket + REST endpoints
│   │   └── session_manager.py # Multi-session support
│   ├── sandbox/             # Safe code execution
│   ├── health.py            # Health monitoring
│   └── main.py              # Entry point
├── frontend/
│   ├── index.html           # Main UI
│   ├── styles.css           # Dark/light themes
│   └── app.js               # WebSocket client, tabs, file tree
├── cli/
│   ├── main.py              # CLI entry point
│   ├── client.py            # WebSocket client
│   └── terminal_renderer.py # Rich terminal output
├── deploy/
│   ├── install-windows.ps1  # Windows service installer
│   ├── nssm-config.bat      # NSSM configuration
│   ├── start.py             # Cross-platform startup
│   └── start-server.bat     # Windows quick-start
└── projects/                # Generated projects saved here
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/api/ws` | WebSocket | Real-time communication |
| `/api/projects` | GET | List all projects |
| `/api/projects/:id` | GET | Get project details |
| `/api/projects/:id` | DELETE | Delete project |
| `/api/health` | GET | Basic health check |
| `/api/health/detailed` | GET | Full system diagnostics |

## Agent Tool Access

Each agent has specific tool permissions:

| Agent | Tools | Purpose |
|-------|-------|---------|
| Router | None (text only) | Intent classification |
| Planner | Read, Glob, Grep | Understand existing code |
| Coder | Read, Write, Edit, Bash, Glob, Grep | Full coding capability |
| Reviewer | Read, Glob, Grep | Code analysis |
| Tester | Read, Write, Bash, Glob, Grep | Write & run tests |
| Debugger | Read, Write, Edit, Bash, Glob, Grep | Fix issues |

## Troubleshooting

### Claude CLI not found
```bash
npm install -g @anthropic-ai/claude-code
```

### Permission errors on Windows
Run PowerShell as Administrator, then run the install script.

### Service not starting
Check logs at `C:\vibe-agents\logs\vibe-agents-stderr.log`

### Health check
```bash
curl http://localhost:8000/api/health/detailed
```

## License

MIT

---

Built with Claude Code
