@echo off
cd /d "%~dp0"
echo ===================================================
echo  Iniciando Centro de Mando / Dashboard Web MAS
echo ===================================================
timeout /t 1 /nobreak >nul
start "" "http://localhost:8000/web_dashboard.html"
if exist ".venv\Scripts\python.exe" (
    echo Usando entorno virtual: .venv\Scripts\python.exe
    ".venv\Scripts\python.exe" GUI\rpi_dashboard_service.py --standalone
) else (
    echo Usando Python del sistema...
    python GUI\rpi_dashboard_service.py --standalone
)
pause
