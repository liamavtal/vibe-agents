"""Shim for editable installs with older pip versions."""
from setuptools import setup, find_packages

setup(
    name="vibe-agents",
    version="0.6.0",
    packages=find_packages(include=["cli*", "backend*"]),
    entry_points={
        "console_scripts": [
            "vibe=cli.main:main",
        ],
    },
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn>=0.27.0",
        "python-dotenv>=1.0.0",
        "websockets>=12.0",
        "pydantic>=2.5.3",
        "rich>=13.0.0",
    ],
    python_requires=">=3.9",
)
