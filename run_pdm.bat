@echo off
set "PYTHONPATH=%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m src.pdm.app
) else (
    python -m src.pdm.app
)
if %ERRORLEVEL% neq 0 pause
