#include "dialogs.h"
#include "config.h"
#include "dictionary.h"
#include "engines.h"
#include "hotkeys.h"
#include "i18n.h"
#include "icons.h"
#include "importer.h"
#include "matcher.h"
#include "overlay.h"
#include "translator.h"
#include "winapp.h"
#include <QAbstractItemView>
#include <QCheckBox>
#include <QColorDialog>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QElapsedTimer>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QKeyEvent>
#include <QLabel>
#include <QLinearGradient>
#include <QListWidget>
#include <QMessageBox>
#include <QPainter>
#include <QPlainTextEdit>
#include <QProgressDialog>
#include <QPushButton>
#include <QRandomGenerator>
#include <QRegularExpression>
#include <QScrollArea>
#include <QSlider>
#include <QSpinBox>
#include <QTabWidget>
#include <QTableWidget>
#include <QVBoxLayout>
#include <memory>

// ======================================================= KeyCapture
KeyCapture::KeyCapture(const QString& seq) : QLineEdit(seq) {
    setReadOnly(true); setPlaceholderText(tx("keycap.off")); setToolTip(tx("keycap.click_field_then_press_key"));
}
void KeyCapture::focusInEvent(QFocusEvent* e) { QLineEdit::focusInEvent(e); setPlaceholderText(tx("keycap.press_key_mouse_button_backspace")); }
void KeyCapture::focusOutEvent(QFocusEvent* e) { QLineEdit::focusOutEvent(e); setPlaceholderText(tx("keycap.off")); }
void KeyCapture::setKey(const QString& key, Qt::KeyboardModifiers mods) {
    QStringList names;
    const QList<QPair<Qt::KeyboardModifier, QString>> M{{Qt::ControlModifier, "Ctrl"}, {Qt::AltModifier, "Alt"}, {Qt::ShiftModifier, "Shift"}, {Qt::MetaModifier, "Win"}};
    for (const auto& [m, n] : M) if ((mods & m) && n != key) names << n;
    const QString seq = (names << key).join('+');
    if (heldVks(seq)) setText(seq);
}
void KeyCapture::keyPressEvent(QKeyEvent* e) {
    static const QHash<int, QString> N{{Qt::Key_Control, "Ctrl"}, {Qt::Key_Alt, "Alt"}, {Qt::Key_Shift, "Shift"}, {Qt::Key_Meta, "Win"}};
    if (e->key() == Qt::Key_Backspace || e->key() == Qt::Key_Delete) clear();
    else if (e->key() == Qt::Key_Escape) clearFocus();
    else setKey(N.value(e->key(), QKeySequence(e->key()).toString()), e->modifiers());
}
void KeyCapture::mousePressEvent(QMouseEvent* e) {
    static const QHash<int, QString> M{{Qt::MiddleButton, "Mouse3"}, {Qt::BackButton, "Mouse4"}, {Qt::ForwardButton, "Mouse5"}};
    if (M.contains(e->button())) { setFocus(); setKey(M[e->button()], e->modifiers()); }
    else QLineEdit::mousePressEvent(e);
}

// ======================================================= ô xem trước (nền giả lập cảnh game + khung thoại mẫu)
namespace {
class Preview : public QWidget {
public:
    explicit Preview(Config& c) : c_(c) { setMinimumHeight(86); }
protected:
    void text(QPainter& p, const QRect& r, int flags, const QString& t, const QString& color) {
        if (const int w = c_.i("text_outline")) { p.setPen(QColor(0, 0, 0, 230)); for (const QPoint& d : outlineOffsets(w)) p.drawText(r.translated(d), flags, t); }
        p.setPen(QColor(color)); p.drawText(r, flags, t);
    }
    void paintEvent(QPaintEvent*) override {
        QPainter p(this); p.setRenderHint(QPainter::Antialiasing); const QRect r = rect();
        QLinearGradient g(0, 0, r.width(), 0);
        const QList<QPair<double, const char*>> stops{{0, "#f4f1e8"}, {0.3, "#7fb7e6"}, {0.55, "#3c7a3a"}, {0.8, "#d9a441"}, {1, "#141414"}};
        for (const auto& [pos, col] : stops) g.setColorAt(pos, QColor(col));
        p.fillRect(r, g);
        for (int x = 0; x < r.width(); x += 40) p.fillRect(x, 0, 14, r.height(), QColor(255, 255, 255, 60));
        const QRect box = r.adjusted(18, 14, -18, -14);
        if (c_.b("show_frame")) { QColor col(c_.str("bg")); col.setAlphaF(float(std::max(0.05, c_.d("opacity")))); p.setBrush(col); p.setPen(Qt::NoPen); p.drawRoundedRect(box, 10, 10); }
        QFont f; f.setPointSize(9); p.setFont(f);
        text(p, box.adjusted(12, 6, -12, 0), Qt::AlignTop | Qt::AlignLeft, "Rover, you finally woke up.", c_.str("src_fg"));
        f.setPointSize(12); p.setFont(f);
        text(p, box.adjusted(12, 0, -12, -8), Qt::AlignBottom | Qt::AlignLeft, QString::fromUtf8("Rover, cuối cùng anh cũng tỉnh rồi."), c_.str("fg"));
    }
private:
    Config& c_;
};

QList<QPair<QString, QString>> opts(std::initializer_list<std::pair<const char*, const char*>> l) {
    QList<QPair<QString, QString>> o; for (const auto& [k, v] : l) o.append(QPair<QString, QString>(k, v)); return o;
}
}  // namespace

// ======================================================= SettingsDialog: hàm dựng form
QFormLayout* SettingsDialog::tab(QTabWidget* tabs, const char* key) {
    auto* w = new QWidget; auto* f = new QFormLayout(w);
    auto* sa = new QScrollArea; sa->setWidgetResizable(true); sa->setFrameShape(QFrame::NoFrame); sa->setWidget(w);   // tab cuộn được (laptop 768p)
    tabs->addTab(sa, tx(key)); return f;
}
QFormLayout* SettingsDialog::group(QFormLayout* f, const char* key) { auto* g = new QGroupBox(tx(key)); auto* gf = new QFormLayout(g); f->addRow(g); return gf; }

QLineEdit* SettingsDialog::line(QFormLayout* f, const QString& k, const char* label, const char* ph, bool password) {
    auto* e = new QLineEdit(cfg_.value(k).toVariant().toString()); if (ph) e->setPlaceholderText(tx(ph));
    if (password) e->setEchoMode(QLineEdit::PasswordEchoOnEdit);
    f->addRow(tx(label), e); w_[k] = [e] { return QJsonValue(e->text().trimmed()); }; widgets_[k] = e; return e;
}
QWidget* SettingsDialog::spin(QFormLayout* f, const QString& k, const char* label, int lo, int hi) {
    auto* s = new QSpinBox; s->setRange(lo, hi); s->setValue(cfg_.i(k)); f->addRow(tx(label), s);
    w_[k] = [s] { return QJsonValue(s->value()); }; widgets_[k] = s; return s;
}
QWidget* SettingsDialog::dspin(QFormLayout* f, const QString& k, const char* label, double lo, double hi, double step) {
    auto* s = new QDoubleSpinBox; s->setRange(lo, hi); s->setSingleStep(step); s->setValue(cfg_.d(k)); f->addRow(tx(label), s);
    w_[k] = [s] { return QJsonValue(s->value()); }; widgets_[k] = s; return s;
}
QWidget* SettingsDialog::check(QFormLayout* f, const QString& k, const char* label) {
    auto* c = new QCheckBox(tx(label)); c->setChecked(cfg_.b(k)); f->addRow(c);
    w_[k] = [c] { return QJsonValue(c->isChecked()); }; widgets_[k] = c; return c;
}
QComboBox* SettingsDialog::combo(QFormLayout* f, const QString& k, const char* label, const QList<QPair<QString, QString>>& o) {
    auto* c = new QComboBox; for (const auto& [key, txt] : o) c->addItem(tx(txt), key);
    c->setCurrentIndex(std::max(0, c->findData(cfg_.str(k)))); f->addRow(tx(label), c);
    w_[k] = [c] { return QJsonValue(c->currentData().toString()); }; widgets_[k] = c; return c;
}
void SettingsDialog::color(QFormLayout* f, const QString& k, const char* label) {
    auto* b = new QPushButton; b->setMinimumWidth(120);
    auto show = [b](const QString& hex) {
        b->setText(hex);
        b->setStyleSheet(QString("background:%1; color:%2; border:1px solid #555; padding:4px").arg(hex, QColor(hex).lightness() > 140 ? "#111" : "#f2f2f2"));
    };
    show(cfg_.str(k));
    connect(b, &QPushButton::clicked, this, [=, this] {
        const QColor c = QColorDialog::getColor(QColor(b->text()), this, tx(label));
        if (c.isValid()) { show(c.name()); live(k, c.name()); }
    });
    f->addRow(tx(label), b); w_[k] = [b] { return QJsonValue(b->text()); }; widgets_[k] = b;
}
void SettingsDialog::tip(QFormLayout* f, QObject* field, const QString& key) {
    // icon ⓘ ngay sau nhãn của dòng (hoặc sau ô tick), rê chuột vào hiện giải thích
    auto* info = new QLabel; info->setPixmap(mdi("mdi6.information-outline", palette().placeholderText().color()).pixmap(15, 15));
    info->setToolTip("<p>" + tx(key).toHtmlEscaped() + "</p>"); info->setCursor(Qt::WhatsThisCursor);
    int row = -1; QFormLayout::ItemRole role{};
    if (auto* w = qobject_cast<QWidget*>(field)) f->getWidgetPosition(w, &row, &role);
    else f->getLayoutPosition(qobject_cast<QLayout*>(field), &row, &role);
    if (row < 0) return;
    QWidget* old = role == QFormLayout::FieldRole ? f->itemAt(row, QFormLayout::LabelRole)->widget() : qobject_cast<QWidget*>(field);
    if (!old) return;
    auto* box = new QWidget; auto* hb = new QHBoxLayout(box); hb->setContentsMargins(0, 0, 0, 0); hb->setSpacing(5);
    f->removeWidget(old); hb->addWidget(old); hb->addWidget(info); hb->addStretch(1);
    f->setWidget(row, role == QFormLayout::FieldRole ? QFormLayout::LabelRole : role, box);
}
void SettingsDialog::live(const QString& k, const QJsonValue& v) { cfg_.set(k, v); preview_->update(); if (onPreview_) onPreview_(); }

void SettingsDialog::reject() {
    for (auto it = snap_.begin(); it != snap_.end(); ++it) cfg_.set(it.key(), it.value());
    if (onPreview_) onPreview_();
    QDialog::reject();
}

// ======================================================= SettingsDialog
SettingsDialog::SettingsDialog(Config& cfg, std::function<void()> onPreview) : cfg_(cfg), onPreview_(std::move(onPreview)) {
    for (const char* k : {"opacity", "bg", "fg", "src_fg", "accent", "show_frame", "text_outline", "text_valign", "line_gap"}) snap_.insert(k, cfg_.value(k));
    setWindowTitle(tx("settings.title")); resize(760, 680);
    auto* tabs = new QTabWidget; auto* v = new QVBoxLayout(this); v->addWidget(tabs);
    // --- OCR
    QFormLayout* f = tab(tabs, "settings.tab.ocr");
    combo(f, "ocr_engine", "settings.ocr.ocr_engine", opts({{"windows", "settings.ocr.ocr_engine.windows"}, {"tesseract", "settings.ocr.ocr_engine.tesseract"}}));
    line(f, "ocr_lang", "settings.ocr.ocr_lang", "settings.ocr.ocr_lang.placeholder");
    dspin(f, "ocr_scale", "settings.ocr.ocr_scale", 0.5, 4, 0.25);
    spin(f, "interval_ms", "settings.ocr.interval_ms", 50, 2000);
    spin(f, "stable_ms", "settings.ocr.stable_ms", 0, 3000);
    dspin(f, "diff_threshold", "settings.ocr.diff_threshold", 0.2, 50, 0.5);
    spin(f, "dedupe_ratio", "settings.ocr.dedupe_ratio", 50, 100);
    appCombo_ = new QComboBox; appCombo_->setEditable(true); appCombo_->setMinimumWidth(260);
    auto* ref = new QPushButton(tx("settings.ocr.refresh")); connect(ref, &QPushButton::clicked, this, &SettingsDialog::loadApps); loadApps();
    auto* hbApp = new QHBoxLayout; hbApp->addWidget(appCombo_, 1); hbApp->addWidget(ref); f->addRow(tx("settings.ocr.only_translate_while_this_app"), hbApp);
    w_["target_app"] = [this] { return QJsonValue(appValue()); };
    check(f, "clear_on_empty", "settings.ocr.clear_on_empty");
    check(f, "fix_spacing", "settings.ocr.fix_spacing");
    f->addRow(new QLabel("<i>" + tx("settings.ocr.pick_dialogue_speaker_name_areas") + "</i>"));
    btnSnap = new QPushButton(tx("settings.ocr.save_current_region_image_for")); btnShow = new QPushButton(tx("settings.ocr.show_selected_areas"));
    btnShow->setToolTip("<p>" + tx("settings.ocr.outline_dialogue_and_speaker_name") + "</p>");
    btnSnap->setToolTip("<p>" + tx("settings.ocr.snap_tip") + "</p>");
    auto* hb2 = new QHBoxLayout; hb2->addWidget(btnShow); hb2->addWidget(btnSnap, 1); f->addRow(hb2);
    for (const char* k : {"ocr_engine", "ocr_lang", "ocr_scale", "interval_ms", "stable_ms", "diff_threshold", "dedupe_ratio", "clear_on_empty", "fix_spacing"})
        tip(f, widgets_[k], QString("settings.ocr.tip.") + k);
    tip(f, hbApp, "settings.ocr.tip.target_app");
    QFormLayout* g = group(f, "settings.ocr.group.downloadable_ocr_engines");     // OCR engine tải thêm (bản C++: Tesseract)
    tessStatus_ = new QLabel; tessInstall_ = new QPushButton; tessRemove_ = new QPushButton(tx("settings.ocr.remove"));
    connect(tessInstall_, &QPushButton::clicked, this, &SettingsDialog::install); connect(tessRemove_, &QPushButton::clicked, this, &SettingsDialog::remove);
    auto* hbT = new QHBoxLayout; hbT->addWidget(tessStatus_, 1); hbT->addWidget(tessInstall_); hbT->addWidget(tessRemove_); g->addRow("Tesseract", hbT);
    engStatus_ = new QLabel; engStatus_->setWordWrap(true); g->addRow(engStatus_);
    engRefresh();
    // --- Dịch
    QFormLayout* t = tab(tabs, "settings.tab.translate");
    f = group(t, "settings.translate.group.dialogue_translation_overlay");
    check(f, "translate", "settings.translate.translate");
    check(f, "use_subs", "settings.translate.use_subs"); spin(f, "fuzzy_threshold", "settings.translate.fuzzy_threshold", 50, 100);
    auto* de = combo(f, "dialog_engine", "settings.translate.dialog_engine", opts({{"google", N_("settings.translate.dialog_engine.google")},
        {"gemini_google", N_("settings.translate.dialog_engine.gemini_google")}, {"gemini", N_("settings.translate.dialog_engine.gemini")}}));
    f = group(t, "settings.translate.group.captured_area_translation");
    auto* se = combo(f, "scan_engine", "settings.translate.scan_engine", opts({{"ocr_google", N_("settings.translate.scan_engine.ocr_google")},
        {"ocr_gemini", N_("settings.translate.scan_engine.ocr_gemini")}, {"gemini_image", N_("settings.translate.scan_engine.gemini_image")}}));
    f = group(t, "settings.translate.group.gemini_ai_only");
    gemWarn_ = new QLabel; gemWarn_->setWordWrap(true); gemWarn_->setStyleSheet("color:#e8a33a"); f->addRow(gemWarn_);
    auto* key = line(f, "gemini_key", "settings.translate.gemini_key", nullptr, true);
    model_ = new QComboBox; model_->setEditable(true); model_->addItem(cfg_.str("gemini_model")); model_->setToolTip(tx("settings.translate.press_check_key_list_models"));
    f->addRow(tx("settings.translate.gemini_model"), model_); w_["gemini_model"] = [this] { return QJsonValue(model_->currentText().trimmed()); };
    auto* bt = new QPushButton(tx("settings.translate.check_key")); keyStatus_ = new QLabel; keyStatus_->setWordWrap(true);
    connect(bt, &QPushButton::clicked, this, &SettingsDialog::testKey);
    auto* hbK = new QHBoxLayout; hbK->addWidget(bt); hbK->addWidget(keyStatus_, 1); f->addRow(hbK);
    connect(de, &QComboBox::currentIndexChanged, this, &SettingsDialog::gemWarn); connect(se, &QComboBox::currentIndexChanged, this, &SettingsDialog::gemWarn);
    connect(key, &QLineEdit::textChanged, this, &SettingsDialog::gemWarn); gemWarn();
    spin(f, "context_lines", "settings.translate.context_lines", 0, 20); check(f, "keep_terms", "settings.translate.keep_terms");
    check(f, "stream", "settings.translate.stream");
    spin(f, "gemini_thinking_budget", "settings.translate.gemini_thinking_budget", -1, 8192);
    spin(f, "timeout_s", "settings.translate.timeout_s", 3, 120); spin(f, "cooldown_s", "settings.translate.cooldown_s", 0, 3600);
    line(f, "src_lang", "settings.translate.src_lang");
    // --- Prompt
    auto* pw = new QWidget; auto* pv = new QVBoxLayout(pw); tabs->addTab(pw, tx("settings.tab.prompt"));
    pv->addWidget(new QLabel(tx("settings.prompt.variables") + " {src_lang} {player} {gender} {keep_rule} {glossary}"));
    prompt_ = new QPlainTextEdit(cfg_.str("prompt")); pv->addWidget(prompt_);
    pv->addWidget(new QLabel(tx("settings.prompt.word_explanation_prompt_variables") + " {word} {sentence}"));
    explain_ = new QPlainTextEdit(cfg_.str("explain_prompt")); pv->addWidget(explain_);
    // --- Nhân vật
    f = tab(tabs, "settings.tab.character");
    line(f, "player_name", "settings.character.player_name");
    combo(f, "gender", "settings.character.gender", opts({{"male", N_("settings.character.gender.male")}, {"female", "settings.character.gender.female"}}));
    tokens_ = new QLineEdit(cfg_.list("name_tokens").join(", ")); f->addRow(tx("settings.character.name_placeholders_in_subtitle_files"), tokens_);
    f->addRow(new QLabel("<i>" + tx("settings.character.gender_macros_like_male_he", {{"_", ""}}) + "</i>"));
    // --- Từ điển
    f = tab(tabs, "settings.tab.dictionary");
    combo(f, "dict_mode", "settings.dictionary.dict_mode", opts({{"auto", "settings.dictionary.dict_mode.auto"}, {"google", "settings.dictionary.dict_mode.google"},
        {"offline", "settings.dictionary.dict_mode.offline"}, {"online", "settings.dictionary.dict_mode.online"}, {"llm", "settings.dictionary.dict_mode.llm"}}));
    combo(f, "target_lang", "settings.dictionary.target_lang", targetLangs());
    combo(f, "popup_trigger", "settings.dictionary.popup_trigger", opts({{"click", "settings.dictionary.popup_trigger.click"}, {"hover", "settings.dictionary.popup_trigger.hover"}}));
    spin(f, "hover_delay_ms", "settings.dictionary.hover_delay_ms", 0, 2000);
    dicts_ = new QListWidget; dicts_->addItems(cfg_.list("dict_files")); f->addRow(tx("settings.dictionary.dictionary_files"), dicts_);
    auto* hbD = new QHBoxLayout; auto* a = new QPushButton(tx("settings.dictionary.add")); auto* d = new QPushButton(tx("settings.dictionary.remove"));
    hbD->addWidget(a); hbD->addWidget(d); hbD->addStretch(1); f->addRow(hbD);
    connect(a, &QPushButton::clicked, this, [this] {
        const QStringList fs = QFileDialog::getOpenFileNames(this, tx("settings.dictionary.choose_dictionaries"), {}, tx("settings.dictionary.dictionary") + " (*.ifo *.tsv *.txt *.csv *.json)");
        dicts_->addItems(fs);
    });
    connect(d, &QPushButton::clicked, this, [this] { qDeleteAll(dicts_->selectedItems()); });
    f->addRow(new QLabel("<i>" + tx("settings.dictionary.supports_stardict_ifo_idx_dict", {{"_", ""}}) + "</i>"));
    // --- Giao diện
    t = tab(tabs, "settings.tab.appearance");
    auto* lc = new QComboBox; lc->addItem(QString::fromUtf8("Tự động (theo Windows) / Auto"), "");      // song ngữ: chọn nhầm vẫn tìm lại được
    for (const auto& [code, name] : i18n::langs()) lc->addItem(name, code);
    lc->setCurrentIndex(std::max(0, lc->findData(cfg_.str("ui_lang")))); t->addRow(QString::fromUtf8("Ngôn ngữ / Language"), lc);
    w_["ui_lang"] = [lc] { return QJsonValue(lc->currentData().toString()); };
    preview_ = new Preview(cfg_); t->addRow(preview_);      // khung / màu / viền chữ: đổi là overlay + ô xem trước cập nhật ngay; Cancel thì trả lại
    f = group(t, "settings.appearance.group.text");
    spin(f, "font_size", "settings.appearance.font_size", 8, 48); spin(f, "src_font_size", "settings.appearance.src_font_size", 8, 40);
    combo(f, "display", "settings.appearance.display", opts({{"both", "settings.appearance.display.both"}, {"vi", "settings.appearance.display.vi"},
        {"vi_hover", "settings.appearance.display.vi_hover"}, {"src_hover", "settings.appearance.display.src_hover"}}));
    auto* va = combo(f, "text_valign", "settings.appearance.text_valign", opts({{"top", "settings.appearance.text_valign.top"},
        {"center", "settings.appearance.text_valign.center"}, {"bottom", "settings.appearance.text_valign.bottom"}}));
    connect(va, &QComboBox::currentIndexChanged, this, [this, va] { live("text_valign", va->currentData().toString()); });
    tip(f, va, "settings.appearance.tip.when_frame_is_taller");
    auto* lg = static_cast<QSpinBox*>(spin(f, "line_gap", "settings.appearance.line_gap", 0, 40));
    connect(lg, &QSpinBox::valueChanged, this, [this](int x) { live("line_gap", x); });
    tip(f, lg, "settings.appearance.tip.extra_space_between_source");
    auto* to = static_cast<QSpinBox*>(spin(f, "text_outline", "settings.appearance.text_outline", 0, 4));
    connect(to, &QSpinBox::valueChanged, this, [this](int x) { live("text_outline", x); });
    check(f, "show_speaker", "settings.appearance.show_speaker");
    f = group(t, "settings.appearance.group.frame_colors");
    auto* sf = static_cast<QCheckBox*>(check(f, "show_frame", "settings.appearance.show_frame"));
    connect(sf, &QCheckBox::toggled, this, [this](bool on) { live("show_frame", on); });
    auto* sl = new QSlider(Qt::Horizontal); sl->setRange(0, 95); sl->setValue(int(std::lround((1 - cfg_.d("opacity")) * 100)));
    auto* pct = new QLabel(QString("%1%").arg(sl->value())); pct->setMinimumWidth(44);
    connect(sl, &QSlider::valueChanged, this, [this, pct](int x) { pct->setText(QString("%1%").arg(x)); live("opacity", std::round((1 - x / 100.0) * 100) / 100); });
    auto* hbO = new QHBoxLayout; hbO->addWidget(sl, 1); hbO->addWidget(pct); f->addRow(tx("settings.appearance.frame_transparency"), hbO);
    w_["opacity"] = [sl] { return QJsonValue(std::round((1 - sl->value() / 100.0) * 100) / 100); };
    auto* cols = new QHBoxLayout; QFormLayout* cf[2] = {new QFormLayout, new QFormLayout};
    cols->addLayout(cf[0]); cols->addSpacing(16); cols->addLayout(cf[1]); f->addRow(cols);
    const QList<QPair<const char*, const char*>> colors{{"bg", N_("settings.appearance.bg")}, {"fg", N_("settings.appearance.fg")},
                                                        {"src_fg", N_("settings.appearance.src_fg")}, {"accent", N_("settings.appearance.accent")}};
    for (int i = 0; i < colors.size(); ++i) color(cf[i % 2], colors[i].first, colors[i].second);
    tip(cf[1], widgets_["accent"], "settings.appearance.tip.speaker_name_lookup_popup");
    auto* gb = new QGroupBox(tx("settings.appearance.toolbar_buttons_tick_show_drag")); auto* gl = new QHBoxLayout(gb);
    auto* lst = new QListWidget; lst->setDragDropMode(QAbstractItemView::InternalMove); lst->setDefaultDropAction(Qt::MoveAction);
    const QColor col = lst->palette().text().color(); QHash<QString, QString> iconOf;
    for (const ToolDef& td : toolbarDefs()) iconOf.insert(td.key, td.icon);
    QStringList order = cfg_.list("toolbar");                // nút đang hiện theo thứ tự đã xếp, nút ẩn xuống cuối
    for (const ToolDef& td : toolbarDefs()) if (!order.contains(td.key)) order << td.key;
    for (const QString& k : order) {
        if (!iconOf.contains(k)) continue;
        auto* it = new QListWidgetItem(mdi(iconOf[k], col), tx(toolbarTip(k)).section(" (", 0, 0)); it->setData(Qt::UserRole, k);
        it->setFlags((it->flags() | Qt::ItemIsUserCheckable) & ~Qt::ItemIsDropEnabled);     // không thả đè lên item (mất item)
        it->setCheckState(cfg_.list("toolbar").contains(k) ? Qt::Checked : Qt::Unchecked); lst->addItem(it);
    }
    lst->setFixedHeight(lst->sizeHintForRow(0) * lst->count() + 2 * lst->frameWidth() + 2);
    auto* bv = new QVBoxLayout;
    const QList<std::tuple<const char*, int, const char*>> moves{{"mdi6.arrow-up", -1, N_("settings.appearance.up_further_left_on_toolbar")},
                                                                 {"mdi6.arrow-down", 1, N_("settings.appearance.down_further_right_on_toolbar")}};
    for (const auto& [ic, dir, tp] : moves) {
        auto* b = new QPushButton(mdi(ic, col), ""); b->setToolTip(tx(tp)); bv->addWidget(b);
        connect(b, &QPushButton::clicked, this, [lst, dir = dir] {
            const int r = lst->currentRow(), n = r + dir;
            if (r < 0 || n < 0 || n >= lst->count()) return;
            lst->insertItem(n, lst->takeItem(r)); lst->setCurrentRow(n);
        });
    }
    bv->addStretch(1); gl->addWidget(lst, 1); gl->addLayout(bv); t->addRow(gb);
    w_["toolbar"] = [lst] {
        QJsonArray a; for (int i = 0; i < lst->count(); ++i) if (lst->item(i)->checkState() == Qt::Checked) a << lst->item(i)->data(Qt::UserRole).toString();
        return QJsonValue(a);
    };
    f = group(t, "settings.appearance.group.behavior");
    dspin(f, "auto_hide_s", "settings.appearance.auto_hide_s", 0, 60, 0.5);
    auto* uk = new KeyCapture(cfg_.str("unlock_key")); f->addRow(tx("settings.appearance.hold_key_interact_while_locked"), uk);
    w_["unlock_key"] = [uk] { return QJsonValue(uk->text()); };
    tip(f, uk, "settings.appearance.tip.while_overlay_is_locked");
    tip(f, check(f, "hide_from_capture", "settings.appearance.hide_from_capture"), "settings.appearance.tip.overlay_stays_visible_on");
    // --- Hotkey
    f = tab(tabs, "settings.tab.hotkeys");
    const QList<QPair<const char*, const char*>> hks{{"toggle", N_("settings.hotkeys.toggle")}, {"region", N_("settings.hotkeys.region")},
        {"pause", N_("settings.hotkeys.pause")}, {"rescan", N_("settings.hotkeys.rescan")}, {"clickthrough", "Click-through"},
        {"clear", N_("settings.hotkeys.clear")}, {"translate", N_("settings.hotkeys.translate")}, {"scan", N_("settings.hotkeys.scan")}, {"lock", N_("settings.hotkeys.lock")}};
    for (const auto& [k, n] : hks) { auto* e = new QLineEdit(cfg_.hotkey(k)); f->addRow(tx(n), e); hk_.insert(k, e); }
    check(f, "run_as_admin", "settings.hotkeys.run_as_admin");
    auto* bb = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel);
    connect(bb, &QDialogButtonBox::accepted, this, &QDialog::accept); connect(bb, &QDialogButtonBox::rejected, this, &QDialog::reject);
    auto* ver = new QLabel(QString("Game Sub v%1 (C++)").arg(GAMESUB_VERSION)); ver->setStyleSheet("color:gray");
    auto* foot = new QHBoxLayout; foot->addWidget(ver); foot->addStretch(1); foot->addWidget(bb); v->addLayout(foot);
}

void SettingsDialog::engRefresh() {
    const bool ok = engines::hasTesseract();
    tessStatus_->setText(ok ? tx("settings.ocr.installed_mb_mb_on_disk", {{"mb", QString::number(engines::sizeMb(engines::tessDir()), 'f', 0)}}) : tx("settings.ocr.not_installed"));
    tessInstall_->setText(ok ? tx("settings.ocr.re_download") : tx("settings.ocr.download_size", {{"size", "~50 MB"}})); tessRemove_->setEnabled(ok);
    engStatus_->setText("<i>" + tx("settings.ocr.located_in_path", {{"path", engines::dir().toHtmlEscaped()}}) + "</i>");
}

void SettingsDialog::loadApps() {
    // app đang có cửa sổ mở (WuWa: client-win64-shipping.exe) + giá trị đang lưu
    const QString cur = appCombo_->count() ? appValue() : cfg_.str("target_app");
    appCombo_->clear(); appCombo_->addItem(tx("settings.ocr.any_window_no_filter"), "");
    QList<QPair<QString, QString>> apps = winapp::windows(); bool has = false;
    for (const auto& a : apps) has |= a.first == cur;
    if (!cur.isEmpty() && !has) apps.append({cur, tx("settings.ocr.not_open")});
    std::sort(apps.begin(), apps.end());
    for (const auto& [exe, title] : apps) appCombo_->addItem(exe + QString::fromUtf8(" — ") + title.left(40), exe);
    appCombo_->setCurrentIndex(std::max(0, appCombo_->findData(cur)));
}

QString SettingsDialog::appValue() const {
    const QString t = appCombo_->currentText().trimmed();
    if (appCombo_->currentIndex() >= 0 && t == appCombo_->itemText(appCombo_->currentIndex())) return appCombo_->currentData().toString();
    return t.section(QString::fromUtf8(" — "), 0, 0).trimmed().toLower();         // gõ tay tên exe
}

void SettingsDialog::gemWarn() {
    QStringList uses;
    if (w_["dialog_engine"]().toString().contains("gemini")) uses << tx("settings.translate.uses.dialog_engine");
    if (w_["scan_engine"]().toString().contains("gemini")) uses << tx("settings.translate.uses.scan_engine");
    const bool noKey = w_["gemini_key"]().toString().isEmpty();
    gemWarn_->setText(!uses.isEmpty() && noKey ? tx("settings.translate.gemini_is_selected_for_what", {{"what", uses.join(tx("settings.translate.and"))}}) : QString());
    gemWarn_->setVisible(!uses.isEmpty() && noKey);
}

void SettingsDialog::testKey() {
    // 1) lấy danh sách model (cũng là kiểm tra key)  2) model đang chọn không có -> tự chọn  3) gọi thử
    const QString key = w_["gemini_key"]().toString(), model = w_["gemini_model"]().toString();
    if (key.isEmpty()) { keyStatus_->setText(tx("settings.translate.no_key_entered")); return; }
    keyStatus_->setText(tx("settings.translate.testing"));
    struct Ctx { Config c; std::unique_ptr<Translator> t; QString picked; QElapsedTimer timer; };
    auto ctx = std::make_shared<Ctx>(Ctx{cfg_, nullptr, {}, {}});
    ctx->c.set("gemini_key", key); ctx->c.set("gemini_model", model); ctx->c.set("stream", false); ctx->c.set("timeout_s", 20);
    ctx->t = std::make_unique<Translator>(ctx->c, nullptr);
    QPointer<SettingsDialog> self(this);
    auto fail = [=](const QString& e) {
        if (!self) return;
        const QString note = ctx->picked.isEmpty() ? QString() : tx("settings.translate.model_replaced", {{"old", model.toHtmlEscaped()}, {"new", ctx->picked.toHtmlEscaped()}});
        keyStatus_->setText(QString::fromUtf8("<span style='color:#e86a6a'>%1✗ %2</span>").arg(note, e.section(": ", -1).toHtmlEscaped()));
    };
    ctx->t->listModels(key, [=](const QStringList& models) {
        if (!self) return;
        if (!models.isEmpty() && !models.contains(model)) { ctx->picked = Translator::pickModel(models); ctx->c.set("gemini_model", ctx->picked); }
        model_->clear(); model_->addItems(models); model_->setCurrentText(ctx->picked.isEmpty() ? model : ctx->picked);
        ctx->timer.start();
        ctx->t->gemini("", "Reply with exactly one word: OK", {}, [=](const QString&) {
            if (!self) return;
            const QString note = ctx->picked.isEmpty() ? QString() : tx("settings.translate.model_replaced", {{"old", model.toHtmlEscaped()}, {"new", ctx->picked.toHtmlEscaped()}});
            keyStatus_->setText(QString("<span style='color:#7bd88f'>%1%2</span>").arg(note, tx("settings.translate.key_works",
                {{"model", ctx->c.str("gemini_model").toHtmlEscaped()}, {"sec", QString::number(ctx->timer.elapsed() / 1000.0, 'f', 1)}})));
        }, fail);
    }, fail);
}

void SettingsDialog::install() {
    auto* dlg = new QProgressDialog(tx("settings.ocr.downloading"), tx("settings.ocr.cancel"), 0, 100, this);
    dlg->setWindowTitle(tx("settings.ocr.download_ocr_engine")); dlg->setMinimumWidth(420); dlg->setWindowModality(Qt::WindowModal);
    dlg->setAutoClose(false); dlg->setAutoReset(false); dlg->show();
    QPointer<SettingsDialog> self(this); QPointer<QProgressDialog> pd(dlg);
    auto cancel = engines::installTesseract([pd](const QString& t, int p) { if (pd) { pd->setLabelText(t); pd->setValue(p); } },
        [self, pd](const QString& err) {
            if (pd) pd->deleteLater();
            if (!self) return;
            self->engRefresh();
            if (err == "cancel") return;
            if (!err.isEmpty()) { QMessageBox::warning(self, tx("settings.ocr.download_ocr_engine"), tx("settings.ocr.error_e", {{"e", err}})); return; }
            self->installed = true;
            auto* c = static_cast<QComboBox*>(self->widgets_["ocr_engine"]); c->setCurrentIndex(std::max(0, c->findData("tesseract")));
            QMessageBox::information(self, tx("settings.ocr.download_ocr_engine"), tx("settings.ocr.installed_press_ok"));
        });
    connect(dlg, &QProgressDialog::canceled, this, [cancel] { cancel(); });
}

void SettingsDialog::remove() {
    if (QMessageBox::question(this, tx("settings.ocr.remove_ocr_engine"),
            tx("settings.ocr.remove_name_mb_mb", {{"name", "Tesseract"}, {"mb", QString::number(engines::sizeMb(engines::tessDir()), 'f', 0)}})) != QMessageBox::Yes) return;
    const bool now = engines::removeTesseract();
    auto* c = static_cast<QComboBox*>(widgets_["ocr_engine"]);
    if (c->currentData().toString() == "tesseract") c->setCurrentIndex(c->findData("windows"));     // đang chọn engine bị xóa -> về Windows OCR
    installed = true; engRefresh();
    if (!now) QMessageBox::information(this, tx("settings.ocr.remove_ocr_engine"), tx("settings.ocr.name_is_in_use_it", {{"name", "Tesseract"}}));
}

void SettingsDialog::apply() {
    for (auto it = w_.begin(); it != w_.end(); ++it) cfg_.set(it.key(), it.value()());
    cfg_.set("prompt", prompt_->toPlainText()); cfg_.set("explain_prompt", explain_->toPlainText());
    QJsonArray toks; for (const QString& x : tokens_->text().split(',')) if (!x.trimmed().isEmpty()) toks << x.trimmed();
    cfg_.set("name_tokens", toks);
    QJsonArray df; for (int i = 0; i < dicts_->count(); ++i) df << dicts_->item(i)->text();
    cfg_.set("dict_files", df);
    QJsonObject hk; for (auto it = hk_.begin(); it != hk_.end(); ++it) hk.insert(it.key(), it.value()->text().trimmed());
    cfg_.set("hotkeys", hk);
    cfg_.save();
}

// ======================================================= bảng dùng chung
static QTableWidget* table(const QStringList& headers) {
    auto* t = new QTableWidget(0, int(headers.size())); t->setHorizontalHeaderLabels(headers);
    t->horizontalHeader()->setSectionResizeMode(QHeaderView::Interactive); t->horizontalHeader()->setStretchLastSection(true);
    t->setSelectionBehavior(QAbstractItemView::SelectRows); t->verticalHeader()->setVisible(false); return t;
}
static QString cell(QTableWidget* t, int r, int c) { return t->item(r, c) ? t->item(r, c)->text() : QString(); }

// ======================================================= Glossary
GlossaryDialog::GlossaryDialog(DB& db, Config& cfg) : db_(db), cfg_(cfg) {
    setWindowTitle(tx("glossary.glossary_names_terms")); resize(720, 520);
    auto* v = new QVBoxLayout(this);
    keep_ = new QCheckBox(tx("glossary.dont_translate_names_terms_every")); keep_->setChecked(cfg_.b("keep_terms")); v->addWidget(keep_);
    auto* flt = new QLineEdit; flt->setPlaceholderText(tx("glossary.filter")); v->addWidget(flt);
    t_ = table({tx("glossary.term_source"), tx("glossary.translate_as"), tx("glossary.mode"), tx("glossary.note")}); v->addWidget(t_);
    connect(flt, &QLineEdit::textChanged, this, [this](const QString& s) {
        for (int r = 0; r < t_->rowCount(); ++r) {
            bool hit = s.isEmpty();
            for (int c : {0, 1, 3}) hit |= cell(t_, r, c).toLower().contains(s.toLower());
            t_->setRowHidden(r, !hit);
        }
    });
    auto* hb = new QHBoxLayout;
    auto btn = [&](const QString& txt, std::function<void()> fn) { auto* b = new QPushButton(txt); connect(b, &QPushButton::clicked, this, fn); hb->addWidget(b); };
    btn(tx("glossary.add"), [this] { const int r = row(); t_->scrollToBottom(); t_->editItem(t_->item(r, 0)); });
    btn(tx("glossary.remove"), [this] {
        QList<int> rows; for (const auto& i : t_->selectionModel()->selectedRows()) rows << i.row();
        std::sort(rows.rbegin(), rows.rend()); for (int r : rows) t_->removeRow(r);
    });
    btn(tx("glossary.import_csv"), [this] {
        const QString p = QFileDialog::getOpenFileName(this, tx("glossary.import_title"), {}, "CSV (*.csv)");
        if (p.isEmpty()) return;
        const int n = db_.importGlossaryCsv(p); load();
        QMessageBox::information(this, tx("glossary.imported_title"), tx("glossary.imported_n_entries_columns_term", {{"n", QString::number(n)}}));
    });
    btn(tx("glossary.export_csv"), [this] {
        const QString p = QFileDialog::getSaveFileName(this, tx("glossary.export_title"), "glossary.csv", "CSV (*.csv)");
        if (!p.isEmpty()) { save(false); db_.exportCsv("glossary", p); }
    });
    hb->addStretch(1); v->addLayout(hb);
    v->addWidget(new QLabel("<i>" + tx("glossary.only_applies_machine_translation_gemini") + "</i>"));
    auto* bb = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
    connect(bb, &QDialogButtonBox::accepted, this, [this] { save(); }); connect(bb, &QDialogButtonBox::rejected, this, &QDialog::reject); v->addWidget(bb);
    load();
}
int GlossaryDialog::row(const QString& term, const QString& vi, const QString& mode, const QString& note) {
    const int r = t_->rowCount(); t_->insertRow(r);
    t_->setItem(r, 0, new QTableWidgetItem(term)); t_->setItem(r, 1, new QTableWidgetItem(vi));
    auto* c = new QComboBox; c->addItem(tx("glossary.keep_as_is"), "keep"); c->addItem(tx("glossary.use_translate_as_column"), "translate");
    c->setCurrentIndex(mode == "keep" ? 0 : 1); t_->setCellWidget(r, 2, c); t_->setItem(r, 3, new QTableWidgetItem(note));
    return r;
}
void GlossaryDialog::load() {
    t_->setRowCount(0); QList<Term> g = db_.glossary();
    std::sort(g.begin(), g.end(), [](const Term& a, const Term& b) { return a.term.toLower() < b.term.toLower(); });
    for (const Term& x : g) row(x.term, x.vi, x.mode, x.note);
    t_->resizeColumnsToContents();
}
void GlossaryDialog::save(bool close) {
    for (const Term& g : QList<Term>(db_.glossary())) db_.delTerm(g.term);
    for (int r = 0; r < t_->rowCount(); ++r) {
        const QString term = cell(t_, r, 0).trimmed();
        if (!term.isEmpty()) db_.setTerm(term, cell(t_, r, 1), static_cast<QComboBox*>(t_->cellWidget(r, 2))->currentData().toString(), cell(t_, r, 3));
    }
    cfg_.set("keep_terms", keep_->isChecked()); cfg_.save();
    if (close) accept();
}

// ======================================================= Sổ từ
static QString plain(QString h) {          // html nghĩa -> chữ thường (giữ xuống dòng)
    h.remove(QRegularExpression("<(?!br)[^>]+>")); h.replace(QRegularExpression("<br\\s*/?>"), "\n");
    return h.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&#x27;", "'").replace("&#39;", "'").replace("&amp;", "&");
}

VocabDialog::VocabDialog(DB& db) : db_(db) {
    setWindowTitle(tx("vocab.vocabulary")); resize(820, 520);
    auto* v = new QVBoxLayout(this);
    flt_ = new QLineEdit; flt_->setPlaceholderText(tx("vocab.filter")); connect(flt_, &QLineEdit::textChanged, this, [this] { load(); }); v->addWidget(flt_);
    t_ = table({tx("vocab.word"), tx("vocab.meaning"), tx("vocab.source_line"), tx("vocab.translated_line"), tx("vocab.saved_on"), tx("vocab.reviews")});
    t_->setEditTriggers(QAbstractItemView::NoEditTriggers); t_->setWordWrap(true); v->addWidget(t_);
    auto* hb = new QHBoxLayout;
    auto btn = [&](const QString& txt, std::function<void()> fn) { auto* b = new QPushButton(txt); connect(b, &QPushButton::clicked, this, fn); hb->addWidget(b); };
    btn(tx("vocab.review"), [this] { const auto rows = db_.vocab(); if (!rows.isEmpty()) { ReviewDialog(db_, rows, this).exec(); load(); } });
    btn(tx("vocab.remove"), [this] {
        QList<int> rows; for (const auto& i : t_->selectionModel()->selectedRows()) rows << i.row();
        for (int r : rows) db_.delVocab(cell(t_, r, 0));
        load();
    });
    btn(tx("vocab.export_anki"), [this] {
        const QString p = QFileDialog::getSaveFileName(this, tx("vocab.export_vocabulary"), "vocab.csv", "CSV (*.csv)");
        if (!p.isEmpty()) db_.exportCsv("vocab", p);
    });
    hb->addStretch(1); count_ = new QLabel; hb->addWidget(count_); v->addLayout(hb); load();
}
void VocabDialog::load() {
    const QString s = flt_->text().toLower(); QList<VocabRow> rows;
    for (const VocabRow& r : db_.vocab())
        if (s.isEmpty() || r.word.toLower().contains(s) || r.meaning.toLower().contains(s) || r.sentence.toLower().contains(s) || r.sentenceVi.toLower().contains(s)) rows << r;
    t_->setRowCount(int(rows.size()));
    for (int i = 0; i < rows.size(); ++i) {
        const VocabRow& r = rows[i];
        const QStringList cells{r.word, plain(r.meaning), r.sentence, r.sentenceVi, r.added, QString::number(r.reviews)};
        for (int j = 0; j < cells.size(); ++j) t_->setItem(i, j, new QTableWidgetItem(cells[j]));
    }
    t_->setColumnWidth(0, 140); t_->setColumnWidth(1, 220); t_->setColumnWidth(2, 220); t_->setColumnWidth(3, 160);
    count_->setText(tx("vocab.n_words", {{"n", QString::number(rows.size())}}));
}

// ======================================================= Ôn tập (flashcard: ưu tiên từ ít ôn)
ReviewDialog::ReviewDialog(DB& db, QList<VocabRow> rows, QWidget* parent) : QDialog(parent), db_(db), rows_(std::move(rows)) {
    setWindowTitle(tx("review.review")); resize(520, 360);
    QHash<QString, quint32> rnd; for (const auto& r : rows_) rnd.insert(r.word, QRandomGenerator::global()->generate());
    std::sort(rows_.begin(), rows_.end(), [&](const VocabRow& a, const VocabRow& b) { return a.reviews != b.reviews ? a.reviews < b.reviews : rnd[a.word] < rnd[b.word]; });
    auto* v = new QVBoxLayout(this);
    word_ = new QLabel; word_->setAlignment(Qt::AlignCenter); word_->setStyleSheet("font-size:28px;font-weight:600");
    ctx_ = new QLabel; ctx_->setWordWrap(true); ctx_->setAlignment(Qt::AlignCenter); ctx_->setStyleSheet("color:gray");
    ans_ = new QLabel; ans_->setWordWrap(true); ans_->setTextFormat(Qt::RichText);
    for (QLabel* w : {word_, ctx_, ans_}) v->addWidget(w);
    v->addStretch(1); auto* hb = new QHBoxLayout;
    auto* sb = new QPushButton(tx("review.show_meaning_space")); auto* nb = new QPushButton(tx("review.next"));
    connect(sb, &QPushButton::clicked, this, [this] { showAnswer(); }); connect(nb, &QPushButton::clicked, this, [this] { next(); });
    hb->addWidget(sb); hb->addWidget(nb); v->addLayout(hb); render();
}
void ReviewDialog::render() {
    const VocabRow& r = rows_[i_]; word_->setText(r.word); ans_->setText({});
    QString s = r.sentence; ctx_->setText(s.isEmpty() ? QString() : s.replace(r.word, "<b>" + r.word + "</b>"));
}
void ReviewDialog::showAnswer() {
    const VocabRow& r = rows_[i_];
    ans_->setText(r.meaning + "<br><br><span style='color:gray'>" + r.sentenceVi.toHtmlEscaped() + "</span>"); db_.reviewed(r.word);
}
void ReviewDialog::next() { i_ = int((i_ + 1) % rows_.size()); render(); }
void ReviewDialog::keyPressEvent(QKeyEvent* e) {
    if (e->key() == Qt::Key_Space) showAnswer();
    else if (e->key() == Qt::Key_Right || e->key() == Qt::Key_Return || e->key() == Qt::Key_Enter) next();
    else QDialog::keyPressEvent(e);
}

// ======================================================= Bộ sub
SubsDialog::SubsDialog(DB& db, SubIndex& index, Config& cfg, std::function<void()> onChanged)
    : db_(db), index_(index), cfg_(cfg), onChanged_(std::move(onChanged)) {
    setWindowTitle(tx("subs.subtitle_pack")); resize(860, 600); auto* v = new QVBoxLayout(this);
    v->addWidget(new QLabel(tx("subs.imported_files_later_imports_win")));
    files_ = new QListWidget; files_->setMaximumHeight(120); v->addWidget(files_);
    auto* hb = new QHBoxLayout; auto* b1 = new QPushButton(tx("subs.choose_subtitle_file")); auto* b2 = new QPushButton(tx("subs.remove_imported_file"));
    hb->addWidget(b1); hb->addWidget(b2); hb->addStretch(1); v->addLayout(hb);
    connect(b1, &QPushButton::clicked, this, [this] { open(); }); connect(b2, &QPushButton::clicked, this, [this] { del(); });
    prevLbl_ = new QLabel; v->addWidget(prevLbl_);
    auto* cb = new QHBoxLayout; srcC_ = new QComboBox; viC_ = new QComboBox;
    cb->addWidget(new QLabel(tx("subs.source_column_en"))); cb->addWidget(srcC_, 1); cb->addWidget(new QLabel(tx("subs.translation_column"))); cb->addWidget(viC_, 1);
    impB_ = new QPushButton(tx("subs.import")); impB_->setEnabled(false); connect(impB_, &QPushButton::clicked, this, [this] { import(); });
    cb->addWidget(impB_); v->addLayout(cb);
    t_ = table({}); t_->setEditTriggers(QAbstractItemView::NoEditTriggers); v->addWidget(t_, 1);
    test_ = new QLineEdit; test_->setPlaceholderText(tx("subs.test_matching_paste_english_line"));
    connect(test_, &QLineEdit::returnPressed, this, [this] { test(); }); v->addWidget(test_);
    testOut_ = new QLabel; testOut_->setWordWrap(true); testOut_->setTextInteractionFlags(Qt::TextSelectableByMouse); v->addWidget(testOut_);
    files();
}
void SubsDialog::files() {
    files_->clear();
    for (const auto& [f, n] : db_.subFiles()) {
        auto* it = new QListWidgetItem(tx("subs.file_n_lines", {{"file", f}, {"n", QLocale(QLocale::English).toString(n)}}));
        it->setData(Qt::UserRole, f); files_->addItem(it);
    }
    setWindowTitle(tx("subs.subtitle_pack_n_lines_indexed", {{"n", QLocale(QLocale::English).toString(index_.size())}}));
}
void SubsDialog::open() {
    const QString p = QFileDialog::getOpenFileName(this, tx("subs.choose_subtitle_pack"), {}, "Sub (*.csv *.tsv *.txt *.xlsx *.json);;" + tx("subs.all_files") + " (*)");
    if (p.isEmpty()) return;
    try { const auto t = importer::readTable(p); hdr_ = t.hdr; rows_ = t.rows; }
    catch (const std::exception& e) { QMessageBox::warning(this, tx("subs.couldnt_read_file"), QString::fromUtf8(e.what())); return; }
    if (hdr_.size() < 2) { QMessageBox::warning(this, tx("subs.error"), tx("subs.file_needs_at_least_2")); return; }
    path_ = p; const auto [s, vi] = importer::guessCols(hdr_, rows_);
    for (QComboBox* c : {srcC_, viC_}) { c->clear(); c->addItems(hdr_); }
    srcC_->setCurrentIndex(s); viC_->setCurrentIndex(vi);
    t_->setColumnCount(int(hdr_.size())); t_->setHorizontalHeaderLabels(hdr_);
    const auto show = rows_.mid(0, 200); t_->setRowCount(int(show.size()));
    for (int i = 0; i < show.size(); ++i) for (int j = 0; j < show[i].size(); ++j) t_->setItem(i, j, new QTableWidgetItem(show[i][j].left(300)));
    prevLbl_->setText(tx("subs.file_rows_rows_cols_columns", {{"file", QFileInfo(p).fileName().toHtmlEscaped()},
        {"rows", QLocale(QLocale::English).toString(rows_.size())}, {"cols", QString::number(hdr_.size())}}));
    impB_->setEnabled(true);
}
void SubsDialog::import() {
    const int s = srcC_->currentIndex(), v = viC_->currentIndex();
    if (s == v) { QMessageBox::warning(this, tx("subs.error"), tx("subs.source_and_translation_columns_must")); return; }
    const auto pairs = importer::extractPairs(rows_, s, v);
    db_.addSubs(QFileInfo(path_).fileName(), pairs); onChanged_(); files(); impB_->setEnabled(false);
    QMessageBox::information(this, tx("subs.imported"), tx("subs.imported_n_line_pairs_from",
        {{"n", QLocale(QLocale::English).toString(pairs.size())}, {"file", QFileInfo(path_).fileName()}}));
}
void SubsDialog::del() {
    for (QListWidgetItem* it : files_->selectedItems()) db_.delSubFile(it->data(Qt::UserRole).toString());
    onChanged_(); files();
}
void SubsDialog::test() {
    const auto m = index_.match(test_->text(), cfg_.i("fuzzy_threshold"));
    testOut_->setText(m ? QString::fromUtf8("<b>%1%</b> — %2<br>→ %3").arg(m->score, 0, 'f', 1).arg(m->src.toHtmlEscaped(), m->vi.toHtmlEscaped())
                        : "<i>" + tx("subs.no_line_matches_above_threshold") + "</i>");
}
