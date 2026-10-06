// Game Sub — overlay dịch thoại game bằng OCR màn hình (bản C++ / Qt 6).
#include <QApplication>
#include <QTimer>
#include "app.h"
#include "config.h"
#include "i18n.h"
#include "winapp.h"
#include <windows.h>
#include <shobjidl.h>

int main(int argc, char** argv) {
    SetCurrentProcessExplicitAppUserModelID(L"GameSub");       // taskbar nhóm đúng icon app
    QApplication q(argc, argv);
    q.setQuitOnLastWindowClosed(false); q.setApplicationName("Game Sub");
    Config cfg;
    if (cfg.b("run_as_admin") && !winapp::selfElevated() && winapp::relaunchAsAdmin()) return 0;
    i18n::init(appDir() + "/locales");
    i18n::setLang(cfg.str("ui_lang"));
    App app(q);
    if (const int i = int(q.arguments().indexOf("--shot")); i > 0 && i + 1 < q.arguments().size())
        QTimer::singleShot(1500, &app, [&app, &q, i] { app.shots(q.arguments()[i + 1]); });
    if (q.arguments().contains("--selftest")) {
        int rc = 1;
        QTimer::singleShot(500, &app, [&] { rc = app.selfTest(); app.quit(); });
        q.exec(); return rc;
    }
    return q.exec();
}
