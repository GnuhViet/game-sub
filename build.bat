@echo off
cd /d %~dp0
if not exist .venv (py -3 -m venv .venv)
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name WuWaSub --collect-all winrt --hidden-import diag ^
  --exclude-module tkinter --exclude-module rapidocr_onnxruntime --exclude-module onnxruntime --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtPdf main.py
copy /y README.md dist\WuWaSub\ >nul
powershell -NoProfile -Command "Compress-Archive -Force dist\WuWaSub dist\WuWaSub.zip"
echo Xong: dist\WuWaSub\WuWaSub.exe  ^|  gui may khac: dist\WuWaSub.zip
pause
