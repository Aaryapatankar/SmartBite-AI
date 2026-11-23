@echo off
setlocal enableextensions
cd /d "%~dp0"
title SmartBite AI Launcher
echo ==== SmartBite AI launcher ====

REM 1. Detect Python
set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD where python >nul 2>nul && set "PYCMD=python"
if not defined PYCMD goto nopython
for /f "tokens=2" %%v in ('%PYCMD% --version 2^>^&1') do set "PYVER=%%v"
echo Detected Python %PYVER%
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do set "PYMAJ=%%a" & set "PYMIN=%%b"
if %PYMAJ% LSS 3 goto badpython
if %PYMAJ% EQU 3 if %PYMIN% LSS 10 goto badpython
if %PYMAJ% EQU 3 if %PYMIN% GTR 12 echo [WARNING] Python 3.10 to 3.12 is recommended. Newer versions may fail to install chromadb.

REM 2. Create virtual environment if missing
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment .venv ...
  %PYCMD% -m venv .venv
  if errorlevel 1 goto fail
)
set "VPY=%CD%\.venv\Scripts\python.exe"

REM 3. Install dependencies only when requirements.txt changed
fc /b requirements.txt ".venv\requirements.stamp" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies. The first run can take several minutes ...
  "%VPY%" -m pip install --upgrade pip
  "%VPY%" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
  copy /y requirements.txt ".venv\requirements.stamp" >nul
)

REM 4. Environment configuration
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example
)
findstr /r /c:"^GEMINI_API_KEY=..*" .env >nul 2>nul
if errorlevel 1 (
  echo [NOTE] GEMINI_API_KEY is empty in .env. Recipes, nutrition, budget and meal planning work.
  echo        The AI assistant and AI recipe generation need a key from https://aistudio.google.com/apikey
)

REM 5. Start backend
echo Starting backend on http://127.0.0.1:8000 ...
start "SmartBite Backend" cmd /k ""%VPY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
set /a TRIES=0
:waitbackend
curl -s http://127.0.0.1:8000/api/health >nul 2>nul
if not errorlevel 1 goto backendok
set /a TRIES+=1
if %TRIES% GEQ 40 goto backendfail
timeout /t 2 /nobreak >nul
goto waitbackend
:backendok
echo Backend is running.

REM 6. Start frontend and open browser
echo Starting frontend on http://localhost:8501 ...
start "SmartBite Frontend" cmd /k ""%VPY%" -m streamlit run frontend\app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false"
timeout /t 6 /nobreak >nul
start "" http://localhost:8501
echo.
echo SmartBite AI is running. To stop it, run stop_windows.bat or close the two console windows.
pause
exit /b 0

:nopython
echo [ERROR] Python was not found. Install Python 3.10 to 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
goto fail
:badpython
echo [ERROR] Python 3.10 or newer is required. Found %PYVER%.
goto fail
:backendfail
echo [ERROR] The backend did not start. Look at the "SmartBite Backend" window for the error message.
goto fail
:fail
echo.
echo Launch failed. See the message above.
pause
exit /b 1
