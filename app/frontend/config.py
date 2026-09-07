"""Runtime configuration for the Quiz frontend."""

import os

API_URL = os.environ.get("QUIZ_API_URL", "http://localhost:8000")
# Credential-bearing server-side calls never follow the public/media origin.
# The Flet app and FastAPI API share this process and Uvicorn's fixed port, so
# this destination is intentionally not configurable through the environment.
PRIVATE_API_ORIGIN = "http://127.0.0.1:8000"
API_TIMEOUT = float(os.environ.get("QUIZ_API_TIMEOUT", "15"))
APP_TITLE = "Incluir Quiz"
