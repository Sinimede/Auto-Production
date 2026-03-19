@echo off
setlocal

:: Add current directory to PYTHONPATH so 'import src' works
set PYTHONPATH=%PYTHONPATH%;.

echo A iniciar Auto Production...
python main.py

if errorlevel 1 (
    echo.
    echo ERRO: A aplicacao terminou com um erro.
    pause
)
