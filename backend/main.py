"""
Vibe Agents - Multi-Agent Coding Platform

Run with: uvicorn backend.main:app --reload
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api import router

# Load environment variables
load_dotenv()

# Note: Uses Claude CLI, no API key needed - uses your Claude Max subscription

# Create FastAPI app
app = FastAPI(
    title="Vibe Agents",
    description="Multi-agent vibe coding platform",
    version="0.1.0"
)

# Include API routes
app.include_router(router, prefix="/api")

# Serve frontend static files
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
async def root():
    """Serve the main UI."""
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Vibe Agents API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
