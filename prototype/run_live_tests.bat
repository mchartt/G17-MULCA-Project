@echo off
rem Double-click: the cross-channel live tests (LIVE_TESTS.md). Uses the .env files the bots already use.
cd /d "%~dp0"
if exist "..\..\muca-server\.venv\Scripts\python.exe" (
  "..\..\muca-server\.venv\Scripts\python.exe" run_live_tests.py
) else (
  python run_live_tests.py
)
pause
