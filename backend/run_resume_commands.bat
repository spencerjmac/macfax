@echo off
cd /d "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\backend"
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py compute_game_value --season 2026
pause
