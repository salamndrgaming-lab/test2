@echo off
REM Double-click this file (Windows) to start AI Income Team. No terminal needed.
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )

if not defined PY (
  echo Python 3 isn't installed yet.
  echo Please install it from https://www.python.org/downloads/
  echo During install, tick "Add Python to PATH". Then double-click this file again.
  pause
  exit /b 1
)

%PY% bootstrap.py
echo.
echo AI Income Team has stopped.
pause
