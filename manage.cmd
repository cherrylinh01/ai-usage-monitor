@echo off
REM Windows helper:  manage.cmd setup ^| status ^| switch-account ^| new-key
REM Double-click = status
cd /d "%~dp0"
set "PY=py -3"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if "%~1"=="" (
  %PY% manage.py status
  pause
) else (
  %PY% manage.py %*
)
