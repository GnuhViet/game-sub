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

rem ---- đóng gói: exe + DLL Qt (chỉ module cần) + runtime llvm-mingw + locales; giữ data\ và engines\ đã có
set OUT=dist\GameSub
if not exist %OUT% mkdir %OUT%
copy /y build\GameSub.exe %OUT%\ >nul
robocopy build\locales %OUT%\locales /MIR /NFL /NDL /NJH /NJS /NP >nul
windeployqt --release --no-translations --no-system-d3d-compiler --no-opengl-sw --no-compiler-runtime --skip-plugin-types qmltooling,generic,networkinformation,iconengines --dir %OUT% %OUT%\GameSub.exe >nul || exit /b 1
for %%f in (libc++.dll libunwind.dll) do copy /y %LLVM%\bin\%%f %OUT%\ >nul
powershell -NoProfile -Command "Compress-Archive -Force %OUT% dist\GameSub.zip"
echo Xong: cpp\%OUT%\GameSub.exe  ^|  zip: cpp\dist\GameSub.zip
