// Kiểm tra các luồng chính của app (GameSub.exe --selftest, đặt GAMESUB_DATA=thư mục tạm để không đụng dữ liệu thật).
// In PASS/FAIL từng mục ra selftest.txt trong thư mục dữ liệu; mã thoát 0 = qua hết.
#include "app.h"
#include "capture.h"
#include "dialogs.h"
#include "i18n.h"
#include "importer.h"
#include "overlay.h"
#include "region.h"
#include "scanwin.h"
#include <QApplication>
#include <QDateTime>
#include <QEventLoop>
#include <QFile>
#include <QJsonArray>
#include <QTextStream>
#include <QTimer>

static void pump(int ms) {
    QEventLoop l; QTimer::singleShot(ms, &l, &QEventLoop::quit); l.exec();
}

int App::selfTest() {
    QFile out(dataDir() + "/selftest.txt"); out.open(QIODevice::WriteOnly | QIODevice::Text);
    QTextStream ts(&out); int fails = 0, total = 0;
    auto check = [&](const char* name, bool ok, const QString& info = {}) {
        ++total; if (!ok) ++fails;
        ts << (ok ? "PASS " : "FAIL ") << name << (info.isEmpty() ? "" : "  — " + info) << "\n"; ts.flush();
    };

    // 1) bộ sub: khớp gần đúng (OCR sai chữ I/l) + giữ tên nhân vật
    db_->addSubs("vh.csv", {{"Rover, you finally woke up.", QString::fromUtf8("Rover, cuối cùng anh cũng tỉnh rồi.")},
                            {"Let's head to Jinzhou.", QString::fromUtf8("Đi Jinzhou thôi.")}});
    rebuildIndex();
    onText("Yangyang", "Rover, you finaIly woke up.");
    check("sub match", !history_.empty() && history_.back()->vi == QString::fromUtf8("Rover, cuối cùng anh cũng tỉnh rồi.") && history_.back()->tag.startsWith(tx("app.subtitle_pack_p_match", {{"p", ""}}).left(6)),
          history_.empty() ? "" : history_.back()->vi + " | " + history_.back()->tag);
    check("speaker", !history_.empty() && history_.back()->speaker == "Yangyang");
    const auto n = history_.size(); onText("", "Rover, you finally woke up"); check("dedupe", history_.size() == n);
    onText("", "Let's head to Jinzhou."); check("2nd line", history_.size() == n + 1 && history_.back()->vi == QString::fromUtf8("Đi Jinzhou thôi."));
    onAction("prev"); check("prev", pos_ == int(history_.size()) - 2); onAction("next"); check("next", pos_ == int(history_.size()) - 1);
    // 2) tắt dịch -> chỉ câu gốc
    onAction("translate"); check("translate off", !cfg_.b("translate") && history_.back()->notr && history_.back()->vi.isEmpty());
    onAction("translate"); check("translate on", cfg_.b("translate") && !history_.back()->vi.isEmpty());
    // 3) hết thoại -> xóa
    onText("", "  ..  "); check("clear on empty", cleared_ && ov_->src().isEmpty());
    // 4) glossary / sổ từ
    onPhrase("keep", "Jinzhou"); bool hasTerm = false; for (const Term& t : db_->glossary()) hasTerm |= t.term == "Jinzhou";
    check("glossary keep", hasTerm);
    onPhrase("vocab", "finally"); check("vocab add", db_->hasVocab("finally"));
    check("meta shows glossary", meta("Jinzhou").contains(tx("app.keep_as_is")));
    // 5) khóa / click-through
    onAction("lock"); check("lock", cfg_.b("locked") && ov_->passthroughWanted());
    onAction("lock"); check("unlock", !cfg_.b("locked") && !ov_->passthroughWanted());
    onAction("clickthrough"); check("click-through on", cfg_.b("click_through") && ov_->passthroughWanted());
    onAction("clickthrough"); check("click-through off", !cfg_.b("click_through"));
    // 6) xem vùng
    const Region r{100, 100, 400, 80}; cfg_.setRegion("region", &r);
    onAction("show_region"); check("show region", flash_.size() == 1); onAction("show_region"); check("show region off", flash_.empty());
    // 7) từ điển offline
    QFile d(dataDir() + "/d.tsv"); d.open(QIODevice::WriteOnly); d.write("finally\tcu\xe1\xbb\x91i c\xc3\xb9ng\nwake\tth\xe1\xbb\xa9\x63 d\xe1\xba\xady\n"); d.close();
    dicts_.load({dataDir() + "/d.tsv"}); cfg_.set("dict_mode", "offline");
    lookup("wakes", QPoint(300, 300), true);
    check("offline lookup (lemma wakes->wake)", pop_->isVisible() && pop_->raw.contains(QString::fromUtf8("thức dậy")), pop_->raw);
    pop_->closePop();
    // 8) nhập sub CSV
    QFile c(dataDir() + "/subs.csv"); c.open(QIODevice::WriteOnly);
    c.write("en,vi\n\"Hello, world\",\"Xin ch\xc3\xa0o, th\xe1\xba\xbf gi\xe1\xbb\x9bi\"\nGood night,Ch\xc3\xba\x63 ng\xe1\xbb\xa7 ngon\n"); c.close();
    try {
        const auto t = importer::readTable(dataDir() + "/subs.csv"); const auto cols = importer::guessCols(t.hdr, t.rows);
        const auto pairs = importer::extractPairs(t.rows, cols.first, cols.second);
        check("import csv", pairs.size() == 2 && pairs[0].first == "Hello, world" && pairs[0].second == QString::fromUtf8("Xin chào, thế giới"));
    } catch (const std::exception& e) { check("import csv", false, e.what()); }
    if (QFile::exists(dataDir() + "/subs.xlsx")) {       // tests: sinh bằng openpyxl (chuỗi dùng chung + chuỗi trong ô + số)
        try {
            const auto t = importer::readTable(dataDir() + "/subs.xlsx"); const auto cols = importer::guessCols(t.hdr, t.rows);
            const auto pairs = importer::extractPairs(t.rows, cols.first, cols.second);
            check("import xlsx", pairs.size() == 3 && pairs[1].first == "Good night" && pairs[1].second == QString::fromUtf8("Chúc ngủ ngon") && pairs[2].first == "42",
                  QString("%1 dòng, cột %2/%3, hdr %4").arg(pairs.size()).arg(cols.first).arg(cols.second).arg(t.hdr.join("|")));
        } catch (const std::exception& e) { check("import xlsx", false, e.what()); }
    }
    // 9) mở Cài đặt -> OK không đổi gì
    cfg_.set("dict_mode", "auto");
    const QJsonObject before = cfg_.raw();
    { SettingsDialog s(cfg_, {}); s.apply(); }
    QJsonObject after = cfg_.raw(); after.remove("toolbar_known"); QJsonObject b2 = before; b2.remove("toolbar_known");
    QStringList diff; for (auto it = b2.begin(); it != b2.end(); ++it) if (after.value(it.key()) != it.value()) diff << it.key();
    check("settings round-trip", diff.isEmpty(), diff.join(","));
    // 10) dịch máy qua mạng (Google) — cần Internet
    cfg_.set("dialog_engine", "google");
    onText("", "This is a completely new sentence for the network test.");
    for (int i = 0; i < 100 && history_.back()->busy; ++i) pump(100);
    check("google translate (network)", !history_.back()->busy && !history_.back()->vi.isEmpty() && !history_.back()->alert, history_.back()->vi + " | " + history_.back()->tag);
    // 11) chụp & dịch 1 vùng: khớp bộ sub
    scan_ = {"Good night", "", ""}; db_->addSubs("subs.csv", {{"Good night", QString::fromUtf8("Chúc ngủ ngon")}}); rebuildIndex(); scanTranslate();
    check("scan translate (sub)", scan_.vi == QString::fromUtf8("Chúc ngủ ngon"));
    scanWin_->hide();

    ts << QString("%1/%2 PASS\n").arg(total - fails).arg(total);
    return fails ? 1 : 0;
}
