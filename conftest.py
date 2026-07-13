"""Test configuration — set dummy env vars before any module imports."""

import os

# Set dummy env vars so config.py can import without real credentials
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy-token-for-testing")
os.environ.setdefault("GROQ_API_KEY", "dummy-key-for-testing")
