@echo off
setlocal

echo ============================================================
echo  Auto Production -- Build executavel
echo ============================================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado no PATH.
    pause
    exit /b 1
)

:: Instalar PyInstaller se necessario
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo A instalar PyInstaller...
    pip install pyinstaller
)

:: Limpar builds anteriores
if exist dist\AutoProduction rmdir /s /q dist\AutoProduction
if exist build\AutoProduction rmdir /s /q build\AutoProduction
if exist AutoProduction.spec del AutoProduction.spec

echo A construir executavel...
echo.

pyinstaller ^
    --onedir ^
    --windowed ^
    --name "AutoProduction" ^
    --distpath "dist" ^
    --workpath "build" ^
    --hidden-import win32com.client ^
    --hidden-import win32com.shell ^
    --hidden-import win32com.shell.shell ^
    --hidden-import pywintypes ^
    --hidden-import win32api ^
    --hidden-import win32con ^
    --hidden-import pythoncom ^
    --hidden-import ezdxf ^
    --hidden-import ezdxf.addons ^
    --hidden-import openpyxl ^
    --hidden-import openpyxl.styles ^
    --hidden-import openpyxl.utils ^
    --collect-submodules win32com ^
    --collect-submodules ezdxf ^
    tools\exporter\main.py

if errorlevel 1 (
    echo.
    echo ERRO: Build falhou. Ver mensagens acima.
    pause
    exit /b 1
)

:: Copiar Templates para junto do executavel
echo A copiar Templates...
xcopy /E /I /Y Templates dist\AutoProduction\Templates >nul

echo.
echo ============================================================
echo  Build concluido!
echo  Executavel em: dist\AutoProduction\AutoProduction.exe
echo ============================================================
echo.

:: Abrir a pasta com o resultado
explorer dist\AutoProduction

pause
