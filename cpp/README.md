# Game Sub — bản C++ (Qt 6 + C++/WinRT)

Viết lại toàn bộ app Python (`gamesub/`) bằng C++ để nhẹ hơn. Cùng tính năng, cùng giao diện, **dùng chung dữ liệu**:
`data\settings.json`, `data\gamesub.db` và `locales\*.json` đọc/ghi qua lại được giữa hai bản.

| | Python (v0.2.1) | Python (đã tối ưu RAM) | **C++** |
|---|---|---|---|
| RAM (Task Manager) | 159–180 MB | 84–99 MB | **~34 MB** |
| Gói zip | ~80 MB | ~71 MB | **~14 MB** |

Chưa có trong bản C++: **RapidOCR** (dùng Windows OCR — mặc định — hoặc Tesseract).

## Build
```
cpp\build.bat            -> cpp\dist\GameSub\GameSub.exe + cpp\dist\GameSub.zip (zip không kèm data\ / engines\)
cpp\build.bat nodeploy   -> chỉ biên dịch (cpp\build\)
```
Cần bộ công cụ **portable** ở `D:\cpp-toolchain` (đổi bằng biến môi trường `TC`). Không cài gì vào ổ C, không cần quyền admin;
không dùng nữa thì **xóa thư mục `D:\cpp-toolchain` là sạch**. Dựng lại từ đầu (dùng Python của dự án):
```
.venv\Scripts\pip install aqtinstall
aqt install-qt windows desktop 6.10.3 win64_llvm_mingw -O D:\cpp-toolchain\Qt
aqt install-tool windows desktop tools_llvm_mingw1706 qt.tools.win64_llvm_mingw1706 -O D:\cpp-toolchain\Qt
aqt install-tool windows desktop tools_cmake qt.tools.cmake -O D:\cpp-toolchain\Qt
aqt install-tool windows desktop tools_ninja qt.tools.ninja -O D:\cpp-toolchain\Qt
rem C++/WinRT: tải gói NuGet Microsoft.Windows.CppWinRT, giải nén, sinh header từ dữ liệu WinRT có sẵn trong Windows:
cppwinrt.exe -in local -out D:\cpp-toolchain\cppwinrt\include -include Windows.Media.Ocr -include Windows.Graphics.Imaging ^
             -include Windows.Globalization -include Windows.Foundation -include Windows.Storage.Streams
```
Trình biên dịch: llvm-mingw 17 (Clang), khớp với bản Qt build sẵn. Liên kết `runtimeobject` (không phải `windowsapp`:
thư viện đó chuyển cả hàm thường như `LocalFree` sang API set chỉ có trên bản Windows dành cho app Store -> exe không chạy).

## Cấu trúc (`src/`, tương ứng file Python)
| C++ | Python | |
|---|---|---|
| `main.cpp`, `app.*` | `main.py`, `app.py` | khởi động, điều phối OCR -> sub / dịch máy -> overlay, tra từ, khay, hotkey |
| `config.*` | `config.py` | `settings.json` (cùng key, mặc định, chuyển đổi cài đặt cũ) |
| `i18n.*` | `i18n.py` | `tx("key")` đọc `locales\*.json` (dùng chung) |
| `textnorm.*`, `matcher.*`, `spacing.*` | cùng tên | chuẩn hóa chữ, khớp sub (rapidfuzz-cpp), tách từ dính (wordninja viết lại) |
| `capture.*`, `ocr.*` | `capture.py`, `ocr.py` | chụp GDI + so ảnh + Windows OCR (C++/WinRT) / Tesseract (`tesseract.exe`) ở luồng riêng |
| `net.*`, `translator.*`, `dictionary.*` | `net.py`, `translator.py`, `dictionary.py` | QtNetwork bất đồng bộ (TLS Schannel), Google / Gemini (stream SSE), từ điển |
| `db.*`, `importer.*`, `engines.*` | cùng tên | SQLite (QtSql), nhập sub CSV/TSV/JSON/XLSX, tải Tesseract |
| `overlay.*`, `region.*`, `scanwin.*`, `dialogs.*`, `icons.*` | `ui_*.py`, `icons.py` | giao diện |
| `winapp.*`, `hotkeys.*` | cùng tên | Win32 |

Khác bản Python: mạng chạy bất đồng bộ trên luồng chính (không cần luồng phụ); SQLite chỉ dùng ở luồng chính;
cài đặt được chép sang luồng chụp qua `CaptureWorker::setSettings` (không đọc chung giữa các luồng).

## Kiểm tra
```
.venv\Scripts\python cpp\tests\make_expected.py      -> đáp án từ bản Python
cpp\build\core_test.exe cpp\tests\expected.json      -> so phần lõi C++ với Python (69/69)
set GAMESUB_DATA=%TEMP%\gs_test & cpp\dist\GameSub\GameSub.exe --selftest   -> 23 luồng chính, kết quả: %GAMESUB_DATA%\selftest.txt
cpp\dist\GameSub\GameSub.exe --shot <thư mục>        -> chụp overlay, popup, Cài đặt (7 tab), Glossary… ra PNG
python tools\i18n_check.py                           -> key dùng ở cả hai bản đều có trong locales
```
