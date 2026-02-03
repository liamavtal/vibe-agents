# 🤖 Vibe Agents

A multi-agent AI coding platform. Describe what you want, watch AI agents collaborate to build it.

## What This Is

Vibe Agents is like ChatDev, but better:
- **Visual UI** - Watch agents discuss and build in real-time
- **Multiple specialized agents** - Planner, Coder, Reviewer each do their job
- **Actually works** - Verification loops and code review built-in

## Quick Start

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Make Sure Claude CLI Is Available

This uses your **Claude Code Max** subscription - no separate API key needed!

```bash
# Verify claude is installed
claude --version
```

### 3. Run It

```bash
# From project root
uvicorn backend.main:app --reload
```

### 4. Open the UI

Go to http://localhost:8000

## How It Works

```
You: "Build me a todo app"
         │
         ▼
┌─────────────────┐
│    Planner      │  ← Designs architecture, creates task list
└────────┬────────┘
         ▼
┌─────────────────┐
│     Coder       │  ← Implements each task
└────────┬────────┘
         ▼
┌─────────────────┐
│    Reviewer     │  ← Checks for bugs, security issues
└────────┬────────┘
         ▼
   Generated Code
```

## Project Structure

```
vibe-agents/
├── backend/
│   ├── agents/           # AI agent definitions
│   │   ├── base.py       # Base agent class
│   │   ├── planner.py    # Breaks down tasks
│   │   ├── coder.py      # Writes code
│   │   └── reviewer.py   # Reviews code
│   ├── orchestrator/     # Coordinates agents
│   ├── api/              # FastAPI routes
│   └── main.py           # Entry point
├── frontend/
│   ├── index.html        # Main UI
│   ├── styles.css        # Styling
│   └── app.js            # WebSocket client
└── projects/             # Generated projects saved here
```

## Roadmap

- [x] Basic agent system
- [x] Visual UI
- [ ] Code execution sandbox
- [ ] Verification loops (lint, type check)
- [ ] More agent types (Tester, Debugger)
- [ ] Project templates
- [ ] Export to GitHub

## License

MIT
