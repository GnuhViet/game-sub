#include "ocr.h"
#include "config.h"
#include "i18n.h"
#include <QDir>
#include <QFileInfo>
#include <QProcess>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Globalization.h>
#include <winrt/Windows.Graphics.Imaging.h>
#include <winrt/Windows.Media.Ocr.h>
#include <winrt/Windows.Storage.Streams.h>

using namespace winrt;
namespace WO = Windows::Media::Ocr;
namespace WI = Windows::Graphics::Imaging;

void initWinrtThread() {
    try { init_apartment(apartment_type::multi_threaded); } catch (...) {}
}

namespace {
class WindowsOcr : public OcrEngine {
public:
    explicit WindowsOcr(const QString& lang) {
        if (!lang.isEmpty()) {
            Windows::Globalization::Language l(lang.toStdWString());
            if (WO::OcrEngine::IsLanguageSupported(l)) eng_ = WO::OcrEngine::TryCreateFromLanguage(l);
        }
        if (!eng_) eng_ = WO::OcrEngine::TryCreateFromUserProfileLanguages();
        if (!eng_) throw std::runtime_error(tx("ocr.windows_ocr_has_no_lang", {{"lang", lang}}).toStdString());
        maxDim_ = int(WO::OcrEngine::MaxImageDimension());
    }
    QString name() const override { return "windows"; }
    QStringList recognize(const QImage& src) override {
        QImage img = src.format() == QImage::Format_RGB32 ? src : src.convertToFormat(QImage::Format_RGB32);   // bộ nhớ = BGRA8
        if (std::max(img.width(), img.height()) > maxDim_) img = img.scaled(maxDim_, maxDim_, Qt::KeepAspectRatio, Qt::SmoothTransformation).convertToFormat(QImage::Format_RGB32);
        Windows::Storage::Streams::DataWriter dw;
        dw.WriteBytes(array_view<const uint8_t>(img.constBits(), uint32_t(img.sizeInBytes())));
        auto bmp = WI::SoftwareBitmap::CreateCopyFromBuffer(dw.DetachBuffer(), WI::BitmapPixelFormat::Bgra8, img.width(), img.height());
        QStringList out;
        for (const auto& line : eng_.RecognizeAsync(bmp).get().Lines()) out << QString::fromWCharArray(line.Text().c_str());
        return out;
    }
private:
    WO::OcrEngine eng_{nullptr};
    int maxDim_ = 10000;
};

class TesseractOcr : public OcrEngine {
public:
    TesseractOcr(const QString& exe, const QString& lang) : exe_(exe), lang_(lang == "en-US" || lang == "en" ? "eng" : lang) {}
    QString name() const override { return "tesseract"; }
    QStringList recognize(const QImage& img) override {
        if (!dir_.isValid()) return {};
        const QString png = dir_.filePath("ocr.png"); img.save(png);
        QProcess p; p.start(exe_, {png, "stdout", "-l", lang_});
        if (!p.waitForFinished(30000)) { p.kill(); return {}; }
        QStringList out;
        for (const QString& l : QString::fromUtf8(p.readAllStandardOutput()).split('\n')) if (!l.trimmed().isEmpty()) out << l.trimmed();
        return out;
    }
private:
    QString exe_, lang_;
    QTemporaryDir dir_;
};
}  // namespace

QString tesseractExe() {
    const QString own = appDir() + "/engines/tesseract/tesseract.exe";
    if (QFileInfo::exists(own)) return own;
    const QString path = QStandardPaths::findExecutable("tesseract");
    if (!path.isEmpty()) return path;
    for (const char* env : {"ProgramFiles", "ProgramFiles(x86)"}) {
        const QString p = qEnvironmentVariable(env) + "/Tesseract-OCR/tesseract.exe";
        if (QFileInfo::exists(p)) return p;
    }
    return {};
}

std::unique_ptr<OcrEngine> createOcr(const QString& name, const QString& lang, QString* error) {
    try {
        if (name == "tesseract") {
            const QString exe = tesseractExe();
            if (exe.isEmpty()) throw std::runtime_error(tx("ocr.tesseract_not_installed_settings_ocr").toStdString());
            return std::make_unique<TesseractOcr>(exe, lang);
        }
        if (name == "rapidocr") throw std::runtime_error(tx("ocr.rapidocr_not_in_cpp").toStdString());
        return std::make_unique<WindowsOcr>(lang);
    } catch (const std::exception& e) {
        if (error) *error = QString::fromStdString(e.what());
    } catch (const hresult_error& e) {
        if (error) *error = QString::fromWCharArray(e.message().c_str());
    }
    return nullptr;
}
