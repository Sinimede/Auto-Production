@echo off
set "PYTHONPATH=%~dp0\src"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "src\pdm\app.py"
) else (
    python "src\pdm\app.py"
)
