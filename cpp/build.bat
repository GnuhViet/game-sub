@echo off
rem Build bản C++ của Game Sub -> cpp\dist\GameSub\GameSub.exe (+ cpp\dist\GameSub.zip)
rem Cần bộ công cụ portable ở D:\cpp-toolchain (đổi bằng biến TC): Qt 6.10.3 llvm-mingw, llvm-mingw 17, CMake, Ninja, C++/WinRT.
rem Không dùng nữa: xóa thư mục D:\cpp-toolchain là sạch.
setlocal
if "%TC%"=="" set TC=D:\cpp-toolchain
set QT=%TC%\Qt\6.10.3\llvm-mingw_64
set LLVM=%TC%\Qt\Tools\llvm-mingw1706_64
set PATH=%LLVM%\bin;%TC%\Qt\Tools\CMake_64\bin;%TC%\Qt\Tools\Ninja;%QT%\bin;%PATH%
cd /d %~dp0

cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=%QT% -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_RC_COMPILER=llvm-windres -DCPPWINRT_INCLUDE=%TC%/cppwinrt/include || exit /b 1
cmake --build build || exit /b 1
if "%1"=="nodeploy" exit /b 0

rem ---- đóng gói: exe + đúng các DLL / plugin Qt app dùng + runtime llvm-mingw + locales; giữ data\ và engines\ đã có
rem (không dùng windeployqt: bản llvm-mingw báo "Unable to find the platform plugin", và tự chép thì gọn hơn)
set OUT=dist\GameSub
if not exist %OUT% mkdir %OUT%
copy /y build\GameSub.exe %OUT%\ >nul
robocopy build\locales %OUT%\locales /MIR /NFL /NDL /NJH /NJS /NP >nul
for %%f in (Qt6Core Qt6Gui Qt6Widgets Qt6Network Qt6Sql) do copy /y %QT%\bin\%%f.dll %OUT%\ >nul
copy /y "%LLVM%\x86_64-w64-mingw32\bin\libc++.dll" %OUT%\ >nul
copy /y "%LLVM%\x86_64-w64-mingw32\bin\libunwind.dll" %OUT%\ >nul
for %%d in (platforms styles sqldrivers tls) do if not exist %OUT%\%%d mkdir %OUT%\%%d
copy /y %QT%\plugins\platforms\qwindows.dll %OUT%\platforms\ >nul
copy /y %QT%\plugins\styles\qmodernwindowsstyle.dll %OUT%\styles\ >nul
copy /y %QT%\plugins\sqldrivers\qsqlite.dll %OUT%\sqldrivers\ >nul
copy /y %QT%\plugins\tls\qschannelbackend.dll %OUT%\tls\ >nul
rem zip từ bản sạch: KHÔNG kèm data\ (cài đặt, API key, sổ từ…) và engines\ của máy này
robocopy %OUT% build\zip\GameSub /MIR /XD data engines /NFL /NDL /NJH /NJS /NP >nul
if exist dist\GameSub.zip del dist\GameSub.zip
powershell -NoProfile -Command "Compress-Archive -Force -Path build\zip\GameSub -DestinationPath dist\GameSub.zip"
echo Xong: cpp\%OUT%\GameSub.exe  ^|  zip: cpp\dist\GameSub.zip
