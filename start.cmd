@echo off
rem One-command start on Windows: .\start.cmd [start|stop|status] [--yes] [--check]
rem Bypass applies to this one script run only; Windows blocks .ps1 files by default.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
