@echo off
echo Stopping SmartBite AI ...
for %%P in (8000 8501) do for /f "tokens=5" %%I in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do taskkill /f /pid %%I >nul 2>nul
taskkill /fi "WINDOWTITLE eq SmartBite Backend*" /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq SmartBite Frontend*" /f >nul 2>nul
echo Done.
pause
