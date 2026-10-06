@echo off
rem Build dạng thư mục (exe + _internal): mở nhanh, không giải nén ra %TEMP% mỗi lần chạy.
rem PyInstaller xóa sạch thư mục đích khi build -> build vào build\out, rồi đồng bộ sang dist\GameSub chừa data\ và engines\.
cd /d %~dp0
if not exist .venv (py -3 -m venv .venv)
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name GameSub --icon gamesub\assets\icon.ico --add-data "gamesub\assets;gamesub\assets" --add-data "gamesub\locales;gamesub\locales" --distpath build\out --collect-all winrt --hidden-import diag --collect-submodules numpy --add-data ".venv\Lib\site-packages\wordninja;wordninja" --add-binary "%SystemRoot%\System32\msvcp140.dll;." --add-binary "%SystemRoot%\System32\msvcp140_1.dll;." --add-binary "%SystemRoot%\System32\vcruntime140_1.dll;." ^
  --exclude-module tkinter --exclude-module rapidocr_onnxruntime --exclude-module onnxruntime --exclude-module cv2 --exclude-module shapely --exclude-module pyclipper --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtPdf main.py || exit /b 1
copy /y README.md build\out\GameSub\ >nul & copy /y README.vi.md build\out\GameSub\ >nul & copy /y LICENSE build\out\GameSub\ >nul
robocopy build\out\GameSub dist\GameSub /MIR /XD data engines /NFL /NDL /NJH /NJS /NP >nul
powershell -NoProfile -Command "Compress-Archive -Force build\out\GameSub dist\GameSub.zip"
echo Xong: dist\GameSub\GameSub.exe  ^|  gui may khac: dist\GameSub.zip (giai nen HET roi chay GameSub.exe)
pause
