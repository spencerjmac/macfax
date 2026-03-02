@echo off
REM Simple wrapper for Task Scheduler

cd /d "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard"
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\update_simple.ps1"
