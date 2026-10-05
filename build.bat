@echo off
cd /d %~dp0
if not exist .venv (py -3 -m venv .venv)
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --windowed --name WuWaSub --collect-submodules winrt main.py
echo Xong: dist\WuWaSub\WuWaSub.exe
pause
