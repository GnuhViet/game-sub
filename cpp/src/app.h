#pragma once
// Bộ điều khiển: OCR -> bộ sub / dịch máy -> overlay, tra từ, hành động toolbar / hotkey / khay (giống app.py).
#include <QObject>
#include <QPointer>
#include <QSet>
#include <QSystemTrayIcon>
#include <QTimer>
#include <deque>
#include <memory>
#include "config.h"
#include "db.h"
#include "dictionary.h"
#include "matcher.h"
#include "spacing.h"
#include "translator.h"

class CaptureWorker;
class Hotkeys;
class Overlay;
class RegionFlash;
class RegionSelector;
class ScanWindow;
class WordPopup;
class QAction;
class QApplication;

struct Line { int id = 0; QString speaker, src, vi, tag; bool busy = false, alert = false, notr = false; };
struct ScanCtx { QString src, vi, note; };

class App : public QObject {
    Q_OBJECT
public:
    explicit App(QApplication& q);
    ~App() override;
    void quit();
public slots:
    void onAction(const QString& k);
private:
    void rebuildIndex();
    void knownWords();
    void registerHotkeys();
    void tray();
    void onText(const QString& speaker, const QString& text);
    void resolve(const std::shared_ptr<Line>& line, bool machine = false);
    QString note(const QString& n);
    void render(const Line* line = nullptr);
    void checkElevation();
    void autoHide();
    void onError(const QString& msg);
    // tra từ
    QString curSrc() const;
    QString curVi() const;
    void hoverFrom(bool scan, const QString& w, const QPoint& p);
    void clickFrom(bool scan, const QString& w, const QPoint& p);
    void onHover(const QString& w, const QPoint& p);
    QString meta(const QString& word);
    void lookup(const QString& word, const QPoint& pos, bool pinned = false);
    void explain(const QString& word, const QString& sentence, const QPoint* pos = nullptr, bool pinned = true);
    void fetch(const QString& key, std::function<void(StrFn, StrFn)> fn, StrFn show, StrFn error);
    void onLang(const QString& code);
    void onPhrase(const QString& act, const QString& phrase);
    void toast(const QString& msg);
    // vùng
    void showRegions();
    void flashOff();
    void selectRegion(const QString& kind);
    void scanCapture(const Region& r);
    void scanTranslate(bool machine = false);
    void openSettings();
    void restart();
    void pushCaptureSettings();

    QApplication& q_;
    Config cfg_;
    std::unique_ptr<DB> db_;
    SubIndex index_;
    Spacer spacer_;
    Dictionaries dicts_;
    std::unique_ptr<Translator> tr_;
    std::deque<std::shared_ptr<Line>> history_;
    int pos_ = -1, seq_ = 0;
    QString last_;
    bool cleared_ = false, autoHidden_ = false, lookupScan_ = false;
    QSet<QString> noted_, inflight_, elevWarned_;
    Overlay* ov_; WordPopup* pop_; ScanWindow* scanWin_;
    ScanCtx scan_;
    std::vector<RegionFlash*> flash_;
    QTimer flashT_, hoverT_, idleT_, elevT_;
    QString pendingWord_; QPoint pendingPos_;
    CaptureWorker* worker_;
    Hotkeys* hk_;
    QSystemTrayIcon* tray_ = nullptr;
    QAction *ctAction_ = nullptr, *lockAction_ = nullptr;
    QPointer<RegionSelector> sel_;
};
