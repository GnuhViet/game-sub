#include "app.h"
#include "capture.h"
#include "dialogs.h"
#include "hotkeys.h"
#include "i18n.h"
#include "ocr.h"
#include "overlay.h"
#include "region.h"
#include "scanwin.h"
#include "textnorm.h"
#include "winapp.h"
#include <QAction>
#include <QApplication>
#include <QBuffer>
#include <QCursor>
#include <QDir>
#include <QInputDialog>
#include <QMenu>
#include <QMessageBox>
#include <QProcess>
#include <QPushButton>
#include <QRegularExpression>
#include <QThread>
#include <rapidfuzz_amalgamated.hpp>

static const char* WAIT_ONLINE = N_("app.looking_up_online");
static const char* WAIT_GOOGLE = N_("app.translating");
static const char* WAIT_AI = N_("app.ai_is_explaining");
static QString num(qsizetype n) { return QLocale(QLocale::English).toString(n); }

App::App(QApplication& q) : q_(q) {
    QDir().mkpath(dataDir());
    db_ = std::make_unique<DB>(migrateDb(dataDir()));
    rebuildIndex();
    dicts_.load(cfg_.list("dict_files"));
    tr_ = std::make_unique<Translator>(cfg_, db_.get());
    ov_ = new Overlay(cfg_); pop_ = new WordPopup(cfg_); scanWin_ = new ScanWindow(cfg_);
    connect(ov_, &Overlay::action, this, &App::onAction);
    connect(ov_, &Overlay::wordHover, this, [this](const QString& w, const QPoint& p) { hoverFrom(false, w, p); });
    connect(ov_, &Overlay::wordClick, this, [this](const QString& w, const QPoint& p) { clickFrom(false, w, p); });
    connect(ov_, &Overlay::phraseAction, this, [this](const QString& a, const QString& ph) { lookupScan_ = false; onPhrase(a, ph); });
    connect(scanWin_, &ScanWindow::wordHover, this, [this](const QString& w, const QPoint& p) { hoverFrom(true, w, p); });
    connect(scanWin_, &ScanWindow::wordClick, this, [this](const QString& w, const QPoint& p) { clickFrom(true, w, p); });
    connect(scanWin_, &ScanWindow::action, this, &App::onAction);
    connect(pop_, &WordPopup::act, this, &App::onPhrase);
    connect(pop_, &WordPopup::langChanged, this, &App::onLang);
    flashT_.setSingleShot(true); flashT_.setInterval(3000); connect(&flashT_, &QTimer::timeout, this, &App::flashOff);   // viền "Xem vùng đang chọn"
    hoverT_.setSingleShot(true); connect(&hoverT_, &QTimer::timeout, this, [this] { lookup(pendingWord_, pendingPos_); });
    idleT_.setSingleShot(true); connect(&idleT_, &QTimer::timeout, this, &App::autoHide);
    ov_->setClickThrough(cfg_.b("click_through"));
    worker_ = new CaptureWorker(captureSettings(cfg_));
    connect(worker_, &CaptureWorker::textReady, this, &App::onText);
    connect(worker_, &CaptureWorker::error, this, &App::onError);
    connect(worker_, &CaptureWorker::status, ov_, &Overlay::setStatus);
    worker_->start();
    hk_ = new Hotkeys; connect(hk_, &Hotkeys::triggered, this, &App::onAction); registerHotkeys();
    tray();
    elevT_.setInterval(2000); connect(&elevT_, &QTimer::timeout, this, &App::checkElevation); elevT_.start();
    ov_->show();
    QStringList hint;
    if (!cfg_.region("region").valid()) hint << tx("app.press_select_region_button_or", {{"hk", cfg_.hotkey("region")}});
    if (!index_.size()) hint << tx("app.press_folder_button_subtitle_pack");
    if (!dicts_.errors.isEmpty()) hint << tx("app.dictionary_error_e", {{"e", dicts_.errors.join("; ")}});
    ov_->showLine("", "", hint.isEmpty() ? tx("app.ready") : hint.join(' '), tx("app.n_subtitle_lines", {{"n", num(index_.size())}}));
}

App::~App() { delete ov_; delete pop_; delete scanWin_; delete hk_; flashOff(); }

// ---------------- setup
void App::rebuildIndex() {
    index_.build(db_->allSubs(), cfg_.str("gender"), cfg_.list("name_tokens"), cfg_.str("player_name")); knownWords();
}

void App::knownWords() {
    // tên riêng / từ trong bộ sub + glossary: không tách khi sửa chữ OCR dính
    QStringList words;
    auto add = [&](const QString& s) { for (auto it = textnorm::wordRe().globalMatch(s); it.hasNext();) words << it.next().captured(); };
    for (const auto& [s, v] : db_->allSubs()) add(s);
    for (const Term& g : db_->glossary()) add(g.term);
    add(cfg_.str("player_name"));
    spacer_.setKnown(words);
}

void App::registerHotkeys() {
    QList<QPair<QString, QString>> m; const QJsonObject hk = cfg_.obj("hotkeys");
    for (auto it = hk.begin(); it != hk.end(); ++it) m.append({it.key(), it->toString()});
    const QStringList errs = hk_->registerAll(m);
    if (!errs.isEmpty()) ov_->setStatus(tx("app.hotkey_conflict_keys", {{"keys", errs.join(", ")}}));
}

void App::tray() {
    q_.setWindowIcon(QIcon(":/icon.png"));
    tray_ = new QSystemTrayIcon(QIcon(":/icon.png"), this); auto* m = new QMenu;
    QList<QPair<const char*, QString>> items{{N_("tray.toggle"), "toggle"}, {N_("tray.scan"), "scan"}, {N_("tray.region"), "region"}, {N_("tray.pause"), "pause"},
                                             {N_("tray.subs"), "subs"}, {N_("tray.glossary"), "glossary"}, {N_("tray.vocab"), "vocab"}, {N_("tray.settings"), "settings"}, {nullptr, ""}};
    if (!winapp::selfElevated()) items.append(QPair<const char*, QString>(N_("tray.relaunch_admin"), "relaunch_admin"));
    items.append(QPair<const char*, QString>(N_("tray.quit"), "quit"));
    for (const auto& [txt, k] : items) {
        if (!txt) { m->addSeparator(); continue; }
        m->addAction(tx(txt), this, [this, k = k] { onAction(k); });
        if (k == "pause") {
            ctAction_ = m->addAction(tx("app.click_through_mouse_passes_through"), this, [this] { onAction("clickthrough"); });
            ctAction_->setCheckable(true); ctAction_->setChecked(cfg_.b("click_through"));
            lockAction_ = m->addAction(tx("app.lock_overlay"), this, [this] { onAction("lock"); });
            lockAction_->setCheckable(true); lockAction_->setChecked(cfg_.b("locked"));
        }
    }
    tray_->setContextMenu(m); tray_->setToolTip("Game Sub");
    connect(tray_, &QSystemTrayIcon::activated, this, [this](QSystemTrayIcon::ActivationReason r) { if (r == QSystemTrayIcon::Trigger) onAction("toggle"); });
    if (QSystemTrayIcon::isSystemTrayAvailable()) tray_->show();
}

void App::pushCaptureSettings() { worker_->setSettings(captureSettings(cfg_)); }

// ---------------- pipeline
void App::onText(const QString& speaker, const QString& raw) {
    static const QRegularExpression letters("[A-Za-z]{2,}");
    if (!letters.match(raw).hasMatch()) {                  // rỗng / chỉ ký tự rác = hết thoại
        last_.clear();
        if (cfg_.b("clear_on_empty") && !cleared_) { cleared_ = true; ov_->showLine("", "", "", ""); pop_->requestHide(); }
        if (cfg_.d("auto_hide_s") > 0 && ov_->isVisible()) idleT_.start(int(cfg_.d("auto_hide_s") * 1000));
        return;
    }
    idleT_.stop(); cleared_ = false;
    if (autoHidden_) { autoHidden_ = false; ov_->show(); }
    const QString text = cfg_.b("fix_spacing") ? spacer_.fix(raw) : raw;
    const QString n = textnorm::norm(text);
    if (!last_.isEmpty()) {
        const std::u16string a(reinterpret_cast<const char16_t*>(n.utf16()), size_t(n.size())), b(reinterpret_cast<const char16_t*>(last_.utf16()), size_t(last_.size()));
        if (rapidfuzz::fuzz::ratio(a, b) >= cfg_.d("dedupe_ratio")) return;
    }
    last_ = n; ++seq_;
    auto line = std::make_shared<Line>(); line->id = seq_; line->speaker = speaker.trimmed(); line->src = text;
    history_.push_back(line);
    while (history_.size() > 300) history_.pop_front();
    pos_ = int(history_.size()) - 1;
    resolve(line);
}

void App::resolve(const std::shared_ptr<Line>& line, bool machine) {
    if (!cfg_.b("translate") && !machine) { line->vi.clear(); line->tag = tx("app.not_translating_source_text_only"); line->notr = true; line->alert = false; render(line.get()); return; }
    if (cfg_.b("use_subs") && !machine) {
        if (auto m = index_.match(line->src, cfg_.d("fuzzy_threshold"))) {
            line->vi = m->vi; line->tag = tx("app.subtitle_pack_p_match", {{"p", QString::number(m->score, 'f', 0)}}); line->notr = line->alert = false;
            render(line.get()); return;
        }
    }
    line->tag.clear(); line->busy = true; line->notr = line->alert = false; render(line.get());    // không hiện "Đang dịch…"
    QList<CtxLine> ctx;
    if (const int n = cfg_.i("context_lines")) {
        int i = 0; while (i < int(history_.size()) && history_[i] != line) ++i;
        for (int k = std::max(0, i - n); k < i; ++k) ctx.append({history_[k]->speaker, history_[k]->src, history_[k]->vi});
    }
    std::weak_ptr<Line> wl = line;
    tr_->translate(line->src, line->speaker, ctx,
        [this, wl](const QString& t) { if (auto l = wl.lock()) { l->vi = t; render(l.get()); } },
        [this, wl](const TrResult& r) { if (auto l = wl.lock()) { l->vi = r.vi; l->tag = tr_->label(r.provider) + note(r.note); l->busy = false; render(l.get()); } },
        [this, wl](const QString& e) { if (auto l = wl.lock()) { l->tag = tx("app.translation_error_e", {{"e", e}}); l->busy = false; l->alert = true; render(l.get()); } });
}

QString App::note(const QString& n) {
    // lý do bỏ qua Gemini (lỗi key/quota…) chỉ báo 1 lần cho mỗi loại; đổi cài đặt thì báo lại
    if (n.isEmpty() || noted_.contains(n)) return {};
    noted_.insert(n); return QString::fromUtf8(" · ") + n;
}

void App::render(const Line* line) {
    if (history_.empty()) return;
    const Line& cur = *history_[pos_];
    if (line && (line != &cur || cleared_)) return;        // đã xóa (hết thoại): bản dịch về muộn không hiện lại
    const QString nav = pos_ != int(history_.size()) - 1 ? QString("  [%1/%2]").arg(pos_ + 1).arg(history_.size()) : QString();
    const bool hold = cur.busy || cur.alert || cur.notr;   // đang dịch / lỗi / tắt dịch: không lấy câu gốc làm bản dịch
    ov_->showLine(cur.speaker, cur.src, !cur.vi.isEmpty() ? cur.vi : (hold ? QString() : cur.src), cur.tag + nav, cur.alert);
}

void App::checkElevation() {
    // game chạy quyền admin mà GameSub thì không -> Windows (UIPI) chặn hotkey / giữ phím mở khóa / focus: báo 1 lần
    if (winapp::selfElevated()) { elevT_.stop(); return; }
    const auto f = winapp::foreground(); const QString tgt = cfg_.str("target_app");
    if (f.exe.isEmpty() || elevWarned_.contains(f.exe) || (!tgt.isEmpty() && f.exe != tgt) || winapp::elevated(f.pid) != 1) return;
    elevWarned_.insert(f.exe);
    ov_->setStatus(tx("app.game_runs_as_administrator_see"));
    tray_->showMessage("Game Sub", tx("app.exe_runs_as_administrator_so", {{"exe", f.exe}}), QSystemTrayIcon::Warning, 8000);
}

void App::autoHide() { if (ov_->isVisible() && !ov_->underMouse() && !pop_->isVisible()) { ov_->hide(); autoHidden_ = true; } }
void App::onError(const QString& msg) { ov_->setTag(msg, true); }

// ---------------- tra từ
QString App::curSrc() const { if (lookupScan_) return scan_.src; return history_.empty() ? ov_->src() : history_[pos_]->src; }
QString App::curVi() const { if (lookupScan_) return scan_.vi; return history_.empty() ? QString() : history_[pos_]->vi; }
void App::hoverFrom(bool scan, const QString& w, const QPoint& p) { if (!w.isEmpty()) lookupScan_ = scan; onHover(w, p); }
void App::clickFrom(bool scan, const QString& w, const QPoint& p) { lookupScan_ = scan; hoverT_.stop(); lookup(w, p, true); }

void App::onHover(const QString& w, const QPoint& p) {
    if (cfg_.str("popup_trigger") != "hover") return;          // mặc định: chỉ bấm vào từ mới hiện nghĩa
    if (pop_->pinned && pop_->isVisible()) return;
    if (w.isEmpty()) { hoverT_.stop(); pop_->requestHide(); return; }
    if (pop_->isVisible() && pop_->word == w) { pop_->hideT.stop(); return; }
    pendingWord_ = w; pendingPos_ = p;
    const int d = cfg_.i("hover_delay_ms"); hoverT_.start(cfg_.str("dict_mode") == "llm" ? std::max(d, 700) : d);
}

QString App::meta(const QString& word) {
    QStringList out;
    for (const Term& g : db_->glossary())
        if (g.term.toLower() == word.toLower()) {
            out << QString::fromUtf8("🏷 ") + (g.mode == "keep" || g.vi.isEmpty() ? tx("app.keep_as_is") : QString::fromUtf8("→ ") + g.vi.toHtmlEscaped()) +
                       (g.note.isEmpty() ? "" : QString::fromUtf8(" — ") + g.note.toHtmlEscaped());
            break;
        }
    if (db_->hasVocab(word)) out << QString::fromUtf8("📖 ") + tx("app.already_in_vocabulary");
    return out.isEmpty() ? QString() : QString("<div style='color:%1;font-size:11px'>%2</div>").arg(cfg_.str("accent"), out.join(QString::fromUtf8(" · ")));
}

void App::lookup(const QString& word, const QPoint& pos, bool pinned) {
    if (word.isEmpty()) return;
    const QString mode = cfg_.str("dict_mode"), mt = meta(word);
    if (mode == "offline" || mode == "auto") {
        if (auto r = dicts_.lookup(word)) { pop_->showFor(word, r->first, mt, r->second, pos, pinned, tx("app.offline_dictionary")); return; }
        if (mode == "offline") {
            pop_->showFor(word, "", mt, "<i>" + tx("app.not_in_offline_dictionary") + "</i>" +
                (dicts_.empty() ? "<br><i>" + tx("app.no_dictionary_file_loaded_settings") + "</i>" : QString()), pos, pinned, tx("app.offline_dictionary"));
            return;
        }
    }
    if (mode == "google" || mode == "auto" || mode == "online") {
        const QString tl = cfg_.str("target_lang"); const int to = cfg_.i("timeout_s");
        const bool online = mode == "online";
        const QString key = online ? "on:" + word.toLower() : QString("gg:%1:%2").arg(tl, word.toLower());
        const QString src = online ? tx("app.dictionaryapi_dev_english_english") : "Google Translate";
        const QString miss = "<i>" + tx("app.not_found_press_ai_in") + "</i>";
        if (auto cached = db_->cacheGet(key)) { pop_->showFor(word, "", mt, cached->isEmpty() ? miss : *cached, pos, pinned, src); return; }
        pop_->showFor(word, "", mt, "<i>" + tx(online ? WAIT_ONLINE : WAIT_GOOGLE) + "</i>", pos, pinned, src);
        fetch(key, [=](StrFn ok, StrFn bad) {
            auto done = [ok](std::optional<QPair<QString, QString>> r) { ok(r ? r->second : QString()); };
            if (online) onlineLookup(word, to, done, bad); else googleLookup(word, tl, to, done, bad);
        }, [=, this](const QString& html) { pop_->setBody(word, html.isEmpty() ? miss : html); },
           [=, this](const QString& e) { pop_->setBody(word, "<i>" + tx("app.lookup_error_e", {{"e", e.toHtmlEscaped()}}) + "</i>"); });
        return;
    }
    explain(word, curSrc(), &pos, pinned);
}

void App::explain(const QString& word, const QString& sentence, const QPoint* pos, bool pinned) {
    const QString key = "ai:" + word.toLower() + "|" + textnorm::norm(sentence);
    auto fmt = [](const QString& t) { return t.toHtmlEscaped().replace("\n", "<br>"); };
    const QString wait = "<i>" + tx(WAIT_AI) + "</i>";
    if (pos || !(pop_->isVisible() && pop_->word == word)) pop_->showFor(word, "", meta(word), wait, pos ? *pos : QCursor::pos(), pinned, tx("app.ai_in_context"));
    else { pop_->pinned = true; pop_->setSource(tx("app.ai_in_context")); pop_->setBody(word, wait); }
    if (auto cached = db_->cacheGet(key); cached && !cached->isEmpty()) { pop_->setBody(word, fmt(*cached)); return; }
    fetch(key, [=, this](StrFn ok, StrFn bad) { tr_->explain(word, sentence, ok, bad); },
          [=, this](const QString& t) { pop_->setBody(word, fmt(t)); },
          [=, this](const QString& e) { pop_->setBody(word, "<i>" + tx("app.error_e", {{"e", e.toHtmlEscaped()}}) + "</i>"); });
}

void App::fetch(const QString& key, std::function<void(StrFn, StrFn)> fn, StrFn show, StrFn error) {
    // gọi mạng 1 lần cho mỗi key: đang chờ thì không gửi trùng (popup tự cập nhật khi kết quả về)
    if (inflight_.contains(key)) return;
    inflight_.insert(key);
    fn([=, this](const QString& r) { inflight_.remove(key); db_->cacheSet(key, r); show(r); },
       [=, this](const QString& e) { inflight_.remove(key); error(e); });
}

void App::onLang(const QString& code) {
    cfg_.set("target_lang", code); cfg_.save();
    const QString m = cfg_.str("dict_mode");
    if (m == "offline" || m == "online" || m == "llm") cfg_.set("dict_mode", "google");     // chọn ngôn ngữ = muốn Google dịch
    if (!pop_->word.isEmpty()) lookup(pop_->word, pop_->anchor, true);
}

void App::onPhrase(const QString& act, const QString& phrase) {
    if (act == "lookup") lookup(phrase, QCursor::pos(), true);
    else if (act == "explain") explain(phrase, curSrc());
    else if (act == "vocab") {
        const QSet<QString> waits{"<i>" + tx(WAIT_ONLINE) + "</i>", "<i>" + tx(WAIT_GOOGLE) + "</i>", "<i>" + tx(WAIT_AI) + "</i>"};   // nghĩa chưa về thì không lưu chữ "Đang…"
        const QString body = pop_->word == phrase && pop_->isVisible() && !waits.contains(pop_->raw) ? pop_->raw : QString();
        db_->addVocab(phrase, body, curSrc(), curVi()); toast(tx("app.saved_w_vocabulary", {{"w", phrase}}));
    } else if (act == "keep") { db_->setTerm(phrase, "", "keep"); toast(tx("app.glossary_keep_w_as_is", {{"w", phrase}})); }
    else if (act == "translate") {
        QString cur;
        for (const Term& g : db_->glossary()) if (g.term.toLower() == phrase.toLower()) cur = g.vi;
        QInputDialog d; d.setWindowFlag(Qt::WindowStaysOnTopHint); d.setWindowTitle(tx("app.glossary_title"));
        d.setLabelText(tx("app.translate_w_as", {{"w", phrase}})); d.setTextValue(cur);
        if (d.exec() && !d.textValue().trimmed().isEmpty()) {
            db_->setTerm(phrase, d.textValue().trimmed(), "translate"); toast("Glossary: " + phrase + QString::fromUtf8(" → ") + d.textValue().trimmed());
        }
    }
    if ((act == "vocab" || act == "keep" || act == "translate") && pop_->isVisible() && pop_->word == phrase) { const QString m = meta(phrase); pop_->setBody(phrase, pop_->raw, &m); }
}

void App::toast(const QString& msg) {
    ov_->setStatus(msg);
    QTimer::singleShot(2500, this, [this, msg] { if (ov_->statusText() == msg) ov_->setStatus(""); });
}

// ---------------- hành động
void App::onAction(const QString& k) {
    if (k == "prev" && pos_ > 0) { --pos_; cleared_ = false; render(); }
    else if (k == "next" && pos_ < int(history_.size()) - 1) { ++pos_; cleared_ = false; render(); }
    else if (k == "pause") { worker_->paused = !worker_->paused; ov_->setPaused(worker_->paused); }
    else if (k == "rescan") { last_.clear(); worker_->force = true; }
    else if (k == "translate") {
        cfg_.set("translate", !cfg_.b("translate")); cfg_.save(); ov_->applyStyle();
        toast(cfg_.b("translate") ? tx("app.translation_on") : tx("app.translation_off_source_text_only"));
        if (!history_.empty()) resolve(history_[pos_]);
    } else if (k == "lock") {
        cfg_.set("locked", !cfg_.b("locked")); cfg_.save(); ov_->setLocked(cfg_.b("locked")); lockAction_->setChecked(cfg_.b("locked"));
        toast(cfg_.b("locked") ? tx("app.overlay_locked_mouse_passes_through", {{"hk", cfg_.hotkey("lock")}}) : tx("app.overlay_unlocked"));
    } else if (k == "clear") { ov_->showLine("", "", "", ""); pop_->closePop(); }
    else if (k == "retranslate" && !history_.empty()) resolve(history_[pos_], true);
    else if (k == "region" || k == "speaker" || k == "scan") selectRegion(k);
    else if (k == "show_region") showRegions();
    else if (k == "scan_retranslate" && !scan_.src.isEmpty()) scanTranslate(true);
    else if (k == "toggle") { autoHidden_ = false; ov_->setVisible(!ov_->isVisible()); pop_->hide(); }
    else if (k == "clickthrough") {
        const bool on = !cfg_.b("click_through"); ov_->setClickThrough(on); ctAction_->setChecked(on);
        toast(on ? tx("app.click_through_on_hk_turn", {{"hk", cfg_.hotkey("clickthrough")}}) : tx("app.click_through_off"));
    } else if (k == "hide") { autoHidden_ = false; ov_->hide(); pop_->hide(); toast(""); }
    else if (k == "subs") { SubsDialog d(*db_, index_, cfg_, [this] { rebuildIndex(); }); d.setWindowFlag(Qt::WindowStaysOnTopHint); d.exec(); render(); }
    else if (k == "glossary") { GlossaryDialog d(*db_, cfg_); d.setWindowFlag(Qt::WindowStaysOnTopHint); d.exec(); knownWords(); }
    else if (k == "vocab") { VocabDialog d(*db_); d.setWindowFlag(Qt::WindowStaysOnTopHint); d.exec(); }
    else if (k == "settings") openSettings();
    else if (k == "relaunch_admin") { if (winapp::relaunchAsAdmin()) quit(); }
    else if (k == "quit") quit();
}

void App::showRegions() {
    // viền sáng quanh vùng thoại + vùng tên nhân vật trong 3 giây; bấm lần nữa thì tắt
    if (!flash_.empty()) { flashOff(); return; }
    const Region r = cfg_.region("region"), s = cfg_.region("speaker_region");
    if (r.valid()) flash_.push_back(new RegionFlash(toLogical(r), tx("app.dialogue_area"), QColor(cfg_.str("accent"))));
    if (s.valid()) flash_.push_back(new RegionFlash(toLogical(s), tx("app.speaker_name_area"), QColor("#6ab7e8")));
    if (flash_.empty()) { toast(tx("app.no_dialogue_area_selected_press", {{"hk", cfg_.hotkey("region")}})); return; }
    for (auto* w : flash_) w->show();
    flashT_.start();
}

void App::flashOff() { flashT_.stop(); for (auto* w : flash_) { w->close(); w->deleteLater(); } flash_.clear(); }

void App::selectRegion(const QString& kind) {
    const bool ovVis = ov_->isVisible() || kind != "scan", scanVis = scanWin_->isVisible();
    ov_->hide(); pop_->hide(); scanWin_->hide(); worker_->paused = true;
    QTimer::singleShot(180, this, [=, this] {
        const char* title = kind == "region" ? N_("app.drag_select_dialogue_area_translate")
                          : kind == "scan" ? N_("app.drag_select_area_translate_once") : N_("app.drag_select_speaker_name_area");
        sel_ = new RegionSelector(tx(title));
        auto end = [=, this] {
            worker_->paused = false; ov_->setPaused(false);
            if (ovVis) ov_->show();
            if (scanVis) scanWin_->show();
        };
        connect(sel_, &RegionSelector::selected, this, [=, this](const Region& r) {
            if (kind == "scan") { end(); scanCapture(r); return; }
            cfg_.setRegion(kind == "region" ? "region" : "speaker_region", &r); cfg_.save(); pushCaptureSettings();
            last_.clear(); worker_->force = true; end();
        });
        connect(sel_, &RegionSelector::cancelled, this, [=, this] {
            if (kind == "speaker" && cfg_.region("speaker_region").valid() &&
                QMessageBox::question(nullptr, tx("app.speaker_name_area"), tx("app.remove_current_speaker_name_area")) == QMessageBox::Yes) {
                cfg_.setRegion("speaker_region", nullptr); cfg_.save(); pushCaptureSettings();
            }
            end();
        });
        sel_->start();
    });
}

// ---------------- chụp & dịch 1 vùng
void App::scanCapture(const Region& r) {
    const bool useGem = cfg_.str("scan_engine") == "gemini_image" && cfg_.b("translate");
    scanWin_->showResult(scan_.src, "", useGem ? tx("app.gemini_is_reading_image") : tx("app.running_ocr"));
    const QImage img = grabScreen(r);
    auto viaOcr = [=, this](const QString& gemErr) {
        const QString eng = cfg_.str("ocr_engine"), lang = cfg_.str("ocr_lang"); const double s = cfg_.d("ocr_scale") > 0 ? cfg_.d("ocr_scale") : 1;
        QThread* t = QThread::create([=, this] {                // OCR ở luồng phụ (Windows OCR cần luồng MTA)
            initWinrtThread(); QString err, text;
            if (auto e = createOcr(eng, lang, &err)) {
                QImage im = std::fabs(s - 1) > 0.01 ? img.scaled(int(img.width() * s), int(img.height() * s), Qt::IgnoreAspectRatio, Qt::SmoothTransformation) : img;
                try { text = textnorm::paragraphs(e->recognize(im)); } catch (...) { err = "OCR"; }   // giữ chia đoạn như trong ảnh
            }
            QMetaObject::invokeMethod(this, [=, this] {
                if (!err.isEmpty()) { scanWin_->showResult(scan_.src, "", tx("app.ocr_error_e", {{"e", err}})); return; }
                const QString n = gemErr.isEmpty() ? QString() : tx("app.gemini_image_reading_failed_e", {{"e", gemErr}});
                scan_ = {cfg_.b("fix_spacing") ? spacer_.fix(text) : text, "", n};
                if (scan_.src.trimmed().isEmpty()) { scanWin_->showResult("", "", tx("app.no_text_could_be_read") + note(n)); return; }
                scanTranslate();
            });
        });
        connect(t, &QThread::finished, t, &QObject::deleteLater); t->start();
    };
    if (!useGem) return viaOcr({});
    QByteArray png; QBuffer buf(&png); buf.open(QIODevice::WriteOnly); img.save(&buf, "PNG");
    tr_->readImage(png, [this](const QString& t) { scanWin_->showResult("", t, tx("app.gemini_is_reading_image")); },
        [this](const QString& src, const QString& vi) {
            scan_ = {src, vi, ""}; scanWin_->showResult(src, vi, tx("app.gemini_image_reading_model", {{"model", cfg_.str("gemini_model")}}));
        }, viaOcr);                                              // lỗi / hết quota -> quay về OCR
}

void App::scanTranslate(bool machine) {
    const QString src = scan_.src;
    if (!cfg_.b("translate") && !machine) { scanWin_->showResult(src, "", tx("app.not_translating_source_text_only")); return; }
    if (cfg_.b("use_subs") && !machine)
        if (auto m = index_.match(src, cfg_.d("fuzzy_threshold"))) { scan_.vi = m->vi; scanWin_->showResult(src, m->vi, tx("app.subtitle_pack_p_match", {{"p", QString::number(m->score, 'f', 0)}})); return; }
    scanWin_->showResult(src, "", tx("app.translating"));
    tr_->translate(src, "", {}, [=, this](const QString& t) { scanWin_->showResult(src, t, tx("app.translating")); },
        [=, this](const TrResult& r) { scan_.vi = r.vi; scanWin_->showResult(src, r.vi, tr_->label(r.provider) + note(scan_.note) + note(r.note)); },
        [=, this](const QString& e) { scanWin_->showResult(src, "", tx("app.translation_error_e", {{"e", e}})); }, cfg_.str("scan_engine"));
}

void App::openSettings() {
    QJsonObject old; for (const char* k : {"ocr_engine", "ocr_lang", "dict_files", "gender", "player_name", "name_tokens", "translate", "ui_lang"}) old.insert(k, cfg_.value(k));
    SettingsDialog d(cfg_, [this] { ov_->applyStyle(); pop_->applyStyle(); });     // đổi màu/khung -> overlay đổi ngay
    d.setWindowFlag(Qt::WindowStaysOnTopHint);
    connect(d.btnSnap, &QPushButton::clicked, this, [this] { worker_->requestSnapshot(dataDir() + "/region_snapshot.png"); });
    connect(d.btnShow, &QPushButton::clicked, this, [this] { flashOff(); showRegions(); });
    if (!d.exec()) return;
    d.apply(); noted_.clear(); pushCaptureSettings();
    if (d.installed || cfg_.value("ocr_engine") != old["ocr_engine"] || cfg_.value("ocr_lang") != old["ocr_lang"]) worker_->reloadEngine = true;
    if (cfg_.value("dict_files") != old["dict_files"]) {
        dicts_.load(cfg_.list("dict_files"));
        if (!dicts_.errors.isEmpty()) QMessageBox::warning(nullptr, tx("app.dictionary"), dicts_.errors.join('\n'));
    }
    for (const char* k : {"gender", "player_name", "name_tokens"}) if (cfg_.value(k) != old[k]) { rebuildIndex(); break; }
    ov_->applyStyle(); pop_->applyStyle(); scanWin_->applyStyle(); registerHotkeys(); render();
    if (cfg_.value("translate") != old["translate"] && !history_.empty()) resolve(history_[pos_]);
    if (cfg_.value("ui_lang") != old["ui_lang"] &&
        QMessageBox::question(nullptr, "Game Sub", QString::fromUtf8("Đổi ngôn ngữ cần mở lại app. Mở lại ngay?\nChanging the language requires restarting the app. Restart now?"))
            == QMessageBox::Yes) restart();
}

void App::restart() {
    hk_->registerAll({}); cfg_.save();                 // nhả hotkey trước để bản mới đăng ký được
    QProcess::startDetached(QCoreApplication::applicationFilePath(), QCoreApplication::arguments().mid(1));
    quit();
}

void App::quit() {
    cfg_.save(); worker_->stop(); if (tray_) tray_->hide(); q_.quit();
}
