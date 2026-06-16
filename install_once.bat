@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Installation complete.
echo Run start_offline.bat for offline use.
echo Run start_qr.bat to open the app on a phone via QR.
pause

endlocal
