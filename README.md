# 🤖 Vibe Agents

A multi-agent AI coding platform. Describe what you want, watch AI agents collaborate to build it.

**Like ChatDev, but actually works.**

## Features

- **5 Specialized Agents** - Planner, Coder, Reviewer, Tester, Debugger
- **Visual UI** - Watch agents discuss and build in real-time
- **Code Execution** - Actually runs and tests generated code
- **Auto-Debug Loop** - Automatically fixes errors (up to 3 attempts)
- **Uses Claude Max** - No separate API key needed

## Quick Start

```bash
# 1. Clone
git clone https://github.com/liamavtal/vibe-agents.git
cd vibe-agents

# 2. Setup Python
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt

# 3. Run
uvicorn backend.main:app --reload

# 4. Open browser
open http://localhost:8000
```

## How It Works

```
You: "Build me a calculator"
         │
         ▼
┌─────────────────┐
│  📋 Planner     │  Designs architecture, creates task list
└────────┬────────┘
         ▼
┌─────────────────┐
│  💻 Coder       │  Implements each task
└────────┬────────┘
         ▼
┌─────────────────┐
│  🔍 Verifier    │  Runs code in sandbox, checks for errors
└────────┬────────┘
         │
    Error? ──Yes──▶ 🔧 Debugger (auto-fix loop)
         │
         ▼
┌─────────────────┐
│  👀 Reviewer    │  Code review for bugs & security
└────────┬────────┘
         ▼
┌─────────────────┐
│  🧪 Tester      │  Generates and runs tests
└────────┬────────┘
         ▼
   ✅ Complete!
```

## Architecture

```
vibe-agents/
├── backend/
│   ├── agents/           # AI agent definitions
│   │   ├── base.py       # Base agent (uses Claude CLI)
│   │   ├── planner.py    # Breaks down tasks
│   │   ├── coder.py      # Writes code
│   │   ├── reviewer.py   # Reviews code
│   │   ├── tester.py     # Writes tests
│   │   └── debugger.py   # Fixes bugs
│   ├── orchestrator/     # Coordinates agents
│   │   └── engine.py     # Main workflow engine
│   ├── sandbox/          # Code execution
│   │   └── executor.py   # Safe subprocess execution
│   ├── api/              # FastAPI routes
│   └── main.py           # Entry point
├── frontend/
│   ├── index.html        # Main UI
│   ├── styles.css        # Dark theme styling
│   └── app.js            # WebSocket client
└── projects/             # Generated projects saved here
```

## The Pipeline

| Phase | Agent | What It Does |
|-------|-------|--------------|
| 1. Planning | Planner | Analyzes request, creates task breakdown |
| 2. Coding | Coder | Implements each task, writes files |
| 3. Verification | - | Runs code in sandbox, checks syntax |
| 4. Debugging | Debugger | Auto-fixes errors (if any) |
| 5. Review | Reviewer | Checks for bugs, security issues |
| 6. Testing | Tester | Generates and runs test suite |

## Key Improvements Over ChatDev

| Issue | ChatDev | Vibe Agents |
|-------|---------|-------------|
| Code execution | ❌ None | ✅ Subprocess sandbox |
| Error handling | ❌ Fails silently | ✅ Auto-debug loop |
| Testing | ❌ No tests | ✅ Generated test suite |
| Model flexibility | ❌ One model | ✅ Uses your Claude Max |
| UI | Basic logs | ✅ Real-time visual UI |

## Requirements

- Python 3.9+
- Node.js 18+ (for frontend dev)
- Claude Code CLI (for agent execution)

## Tech Stack

- **Backend**: Python, FastAPI, WebSockets
- **Frontend**: Vanilla JS, CSS (no build step)
- **Agents**: Claude CLI (uses your Claude Max subscription)
- **Sandbox**: Subprocess with timeout/resource limits

## License

MIT

---

Built with Claude Code 🤖
