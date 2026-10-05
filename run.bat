@echo off
cd /d %~dp0
if not exist .venv (
  py -3 -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe main.py
