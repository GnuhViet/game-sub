@echo off
cd /d %~dp0
if not exist .venv (py -3 -m venv .venv)
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed --name WuWaSub --collect-all winrt --hidden-import diag --collect-submodules numpy --collect-data wordninja --add-binary "%SystemRoot%\System32\msvcp140.dll;." --add-binary "%SystemRoot%\System32\msvcp140_1.dll;." --add-binary "%SystemRoot%\System32\vcruntime140_1.dll;." ^
  --exclude-module tkinter --exclude-module rapidocr_onnxruntime --exclude-module onnxruntime --exclude-module cv2 --exclude-module shapely --exclude-module pyclipper --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtPdf main.py

powershell -NoProfile -Command "Compress-Archive -Force dist\WuWaSub.exe,README.md dist\WuWaSub.zip"
echo Xong: dist\WuWaSub.exe  ^|  gui may khac: dist\WuWaSub.zip
pause
