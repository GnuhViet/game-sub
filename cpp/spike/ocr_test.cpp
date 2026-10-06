// Thử: gọi Windows OCR (WinRT) từ C++ biên dịch bằng llvm-mingw.  ocr_test <ảnh.png>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Globalization.h>
#include <winrt/Windows.Graphics.Imaging.h>
#include <winrt/Windows.Media.Ocr.h>
#include <winrt/Windows.Storage.h>
#include <winrt/Windows.Storage.Streams.h>
#include <cstdio>
#include <string>

using namespace winrt;
using namespace Windows::Graphics::Imaging;
using namespace Windows::Media::Ocr;

int wmain(int argc, wchar_t** argv) {
    init_apartment();
    if (argc < 2) { std::puts("usage: ocr_test <image>"); return 2; }
    auto file = Windows::Storage::StorageFile::GetFileFromPathAsync(argv[1]).get();
    auto stream = file.OpenAsync(Windows::Storage::FileAccessMode::Read).get();
    auto bmp = BitmapDecoder::CreateAsync(stream).get().GetSoftwareBitmapAsync().get();
    auto eng = OcrEngine::TryCreateFromLanguage(Windows::Globalization::Language(L"en-US"));
    if (!eng) eng = OcrEngine::TryCreateFromUserProfileLanguages();
    if (!eng) { std::puts("no OCR engine"); return 1; }
    auto res = eng.RecognizeAsync(bmp).get();
    for (auto const& line : res.Lines()) std::printf("%ls\n", line.Text().c_str());
    return 0;
}
