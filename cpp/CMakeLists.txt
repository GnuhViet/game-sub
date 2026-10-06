# Game Sub — bản C++ (Qt 6 Widgets + C++/WinRT cho Windows OCR). Build: cpp\build.bat
cmake_minimum_required(VERSION 3.21)
project(GameSub VERSION 0.3.0 LANGUAGES CXX RC)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets Network Sql CorePrivate)

set(CPPWINRT_INCLUDE "D:/cpp-toolchain/cppwinrt/include" CACHE PATH "header C++/WinRT (cppwinrt.exe -in local)")

file(GLOB SRC CONFIGURE_DEPENDS src/*.cpp src/*.h)
add_executable(GameSub WIN32 ${SRC} resources/resources.qrc resources/app.rc)
target_include_directories(GameSub PRIVATE src third_party)
target_include_directories(GameSub SYSTEM PRIVATE ${CPPWINRT_INCLUDE})
target_compile_definitions(GameSub PRIVATE UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN GAMESUB_VERSION="${PROJECT_VERSION}")
target_link_libraries(GameSub PRIVATE Qt6::Widgets Qt6::Network Qt6::Sql Qt6::CorePrivate
    runtimeobject ole32 oleaut32 dwmapi gdi32 user32 shell32 advapi32 kernel32)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(GameSub PRIVATE -Wall -Wno-unused-parameter)
    target_link_options(GameSub PRIVATE -municode)
endif()

# locales/*.json đặt cạnh exe (người dùng thả thêm file ngôn ngữ được) — dùng chung với bản Python
add_custom_command(TARGET GameSub POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory ${CMAKE_SOURCE_DIR}/../gamesub/locales $<TARGET_FILE_DIR:GameSub>/locales)

# test đối chiếu phần lõi với bản Python (tests/make_expected.py -> expected.json)
add_executable(core_test tests/core_test.cpp src/textnorm.cpp src/spacing.cpp src/matcher.cpp resources/resources.qrc)
target_include_directories(core_test PRIVATE src third_party)
target_link_libraries(core_test PRIVATE Qt6::Core)
