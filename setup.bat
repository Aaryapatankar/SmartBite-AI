@echo off
REM Creates .venv and installs dependencies without starting the app.
cd /d "%~dp0"
where py >nul 2>nul && (set "PYCMD=py -3") || (set "PYCMD=python")
if not exist ".venv\Scripts\python.exe" %PYCMD% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
copy /y requirements.txt ".venv\requirements.stamp" >nul
echo Setup complete. Now run run_windows.bat
pause
exit /b 0
:fail
echo [ERROR] Setup failed. Check that Python 3.10 to 3.12 is installed and you are online.
pause
exit /b 1
