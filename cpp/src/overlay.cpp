#include "overlay.h"
#include "config.h"
#include "dictionary.h"
#include "hotkeys.h"
#include "i18n.h"
#include "icons.h"
#include "textnorm.h"
#include "winapp.h"
#include <QAbstractItemView>
#include <QApplication>
#include <QClipboard>
#include <QComboBox>
#include <QFontDatabase>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QMenu>
#include <QMouseEvent>
#include <QPainter>
#include <QPushButton>
#include <QScreen>
#include <QSizeGrip>
#include <QSpacerItem>
#include <QToolButton>
#include <QVBoxLayout>

static const Qt::WindowFlags FLAGS = Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool;
static const QHash<QString, QString> ICON_ON{{"pause", "mdi6.play"}, {"translate", "mdi6.translate-off"}, {"lock", "mdi6.lock-open-variant"}};
static const QList<ToolDef> RIGHT_BTNS{{"settings", "mdi6.cog"}, {"hide", "mdi6.window-minimize"}, {"quit", "mdi6.close"}};
static const QHash<QString, QString> CAPTION{{"hide", QString(QChar(0xE921))}, {"quit", QString(QChar(0xE8BB))}};   // ChromeMinimize / ChromeClose

const QList<ToolDef>& toolbarDefs() {
    static const QList<ToolDef> T{{"prev", "mdi6.skip-previous"}, {"next", "mdi6.skip-next"}, {"pause", "mdi6.pause"}, {"translate", "mdi6.translate"},
                                  {"rescan", "mdi6.refresh"}, {"clear", "mdi6.eraser"}, {"scan", "mdi6.camera"}, {"region", "mdi6.selection-drag"},
                                  {"speaker", "mdi6.account"}, {"show_region", "mdi6.selection-search"}, {"subs", "mdi6.folder-open"},
                                  {"glossary", "mdi6.tag"}, {"vocab", "mdi6.book-open-variant"}, {"lock", "mdi6.lock"}};
    return T;
}

const char* toolbarTip(const QString& k) {
    static const QHash<QString, const char*> TIPS{
        {"prev", N_("toolbar.prev")}, {"next", N_("toolbar.next")}, {"pause", N_("toolbar.pause")}, {"translate", N_("toolbar.translate")},
        {"rescan", N_("toolbar.rescan")}, {"clear", N_("toolbar.clear")}, {"scan", N_("toolbar.scan")}, {"region", N_("toolbar.region")},
        {"speaker", N_("toolbar.speaker")}, {"show_region", N_("toolbar.show_region")}, {"subs", N_("toolbar.subs")}, {"glossary", N_("toolbar.glossary")},
        {"vocab", N_("toolbar.vocab")}, {"lock", N_("toolbar.lock")}, {"settings", N_("toolbar.settings")}, {"hide", N_("toolbar.hide")}, {"quit", N_("toolbar.quit")}};
    return TIPS.value(k, "");
}

QString captionFont() {
    const QStringList fams = QFontDatabase::families();
    for (const char* f : {"Segoe Fluent Icons", "Segoe MDL2 Assets"}) if (fams.contains(f)) return f;
    return {};
}

QList<QPoint> outlineOffsets(int w) {
    QList<QPoint> o;
    for (int dx = -w; dx <= w; ++dx) for (int dy = -w; dy <= w; ++dy) if ((dx || dy) && dx * dx + dy * dy <= w * w + 1) o << QPoint(dx, dy);
    return o;
}

void OutlineEffect::draw(QPainter* p) {
    QPoint off; const QPixmap pm = sourcePixmap(Qt::LogicalCoordinates, &off, QGraphicsEffect::PadToEffectiveBoundingRect);
    if (pm.isNull()) return;
    QPixmap sh = pm; { QPainter q(&sh); q.setCompositionMode(QPainter::CompositionMode_SourceIn); q.fillRect(sh.rect(), QColor(0, 0, 0, 230)); }
    for (const QPoint& d : offs_) p->drawPixmap(off + d, sh);
    p->drawPixmap(off, pm);
}

QSize FlowLayout::minimumSize() const {
    QSize s; for (QLayoutItem* it : items_) s = s.expandedTo(it->minimumSize());
    return s;
}
int FlowLayout::place(const QRect& r, bool test) const {
    int x = r.x(), y = r.y(), lineH = 0; const int sp = spacing();
    for (QLayoutItem* it : items_) {
        if (it->isEmpty()) continue;
        const QSize h = it->sizeHint();
        if (x > r.x() && x + h.width() > r.right() + 1) { x = r.x(); y += lineH + sp; lineH = 0; }    // xuống dòng
        if (!test) it->setGeometry(QRect(QPoint(x, y), h));
        x += h.width() + sp; lineH = std::max(lineH, h.height());
    }
    return y + lineH - r.y();
}

static QString esc(const QString& s) {           // không mã hóa ' " (Qt không hiểu &#x27;)
    QString o = s; return o.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;");
}

QString tokensHtml(const QString& text, const QString& color) {
    QString out; qsizetype i = 0;
    for (auto it = textnorm::wordRe().globalMatch(text); it.hasNext();) {
        auto m = it.next();
        out += esc(text.mid(i, m.capturedStart() - i));
        out += QString("<a href=\"w:%1:%2\" style=\"color:%3;text-decoration:none\">%4</a>").arg(m.capturedStart()).arg(m.capturedEnd()).arg(color, esc(m.captured()));
        i = m.capturedEnd();
    }
    return out + esc(text.mid(i));
}

// ======================================================= Overlay
Overlay::Overlay(Config& cfg) : QWidget(nullptr, FLAGS), cfg_(cfg) {
    altT_.setInterval(60); connect(&altT_, &QTimer::timeout, this, &Overlay::pollAlt);   // đang khóa: giữ phím mở khóa -> overlay nhận chuột
    hideBar_.setSingleShot(true); hideBar_.setInterval(1200); connect(&hideBar_, &QTimer::timeout, this, [this] { setBar(false); });
    setAttribute(Qt::WA_TranslucentBackground); setMouseTracking(true);
    setAttribute(Qt::WA_AlwaysShowToolTips);                   // cửa sổ Tool không focus: Windows mặc định không hiện tooltip
    setWindowTitle("Game Sub"); setMinimumSize(320, 90);
    auto* v = new QVBoxLayout(this); v->setContentsMargins(14, 6, 14, 8); v->setSpacing(3);
    // toolbar: nút tùy chọn xếp tự xuống dòng bên trái; Cài đặt / Ẩn / Thoát luôn ghim bên phải
    bar_ = new QWidget; auto* hb = new QHBoxLayout(bar_); hb->setContentsMargins(0, 0, 0, 0); hb->setSpacing(6);
    auto* left = new QWidget; flow_ = new FlowLayout(left); auto* right = new QHBoxLayout; right->setSpacing(2);
    capFont_ = captionFont();
    auto mk = [&](const ToolDef& d, bool pinned) {
        auto* b = new QToolButton; b->setAutoRaise(true); b->setFixedSize(28, 26); b->setIconSize(QSize(18, 18));
        const QString k = d.key; connect(b, &QToolButton::clicked, this, [this, k] { emit action(k); });
        if (pinned) right->addWidget(b); else flow_->addWidget(b);
        btns_.insert(k, b);
    };
    for (const ToolDef& d : toolbarDefs()) mk(d, false);
    for (const ToolDef& d : RIGHT_BTNS) mk(d, true);
    if (!capFont_.isEmpty())
        for (auto it = CAPTION.begin(); it != CAPTION.end(); ++it) {
            auto* b = btns_[it.key()]; b->setText(it.value()); b->setObjectName("cap_" + it.key());
            QFont f(capFont_); f.setPixelSize(10); b->setFont(f);
        }
    hb->addWidget(left, 1); hb->addLayout(right); hb->setAlignment(right, Qt::AlignTop);
    QSizePolicy sp = bar_->sizePolicy(); sp.setRetainSizeWhenHidden(true); bar_->setSizePolicy(sp);   // ẩn vẫn giữ chỗ: chữ không xê dịch
    v->addWidget(bar_);
    speaker_ = new QLabel; srcLbl_ = new QLabel; vi_ = new QLabel; tag_ = new QLabel; tag_->setToolTip(tx("overlay.translation_source_subtitle_pack_gemini"));
    for (QLabel* l : {speaker_, srcLbl_, vi_}) l->setWordWrap(true);
    srcLbl_->setTextFormat(Qt::RichText);
    srcLbl_->setTextInteractionFlags(Qt::TextSelectableByMouse | Qt::LinksAccessibleByMouse);
    connect(srcLbl_, &QLabel::linkHovered, this, [this](const QString& h) { emit wordHover(h.isEmpty() ? QString() : word(h), QCursor::pos()); });
    connect(srcLbl_, &QLabel::linkActivated, this, [this](const QString& h) { emit wordClick(word(h), QCursor::pos()); });
    srcLbl_->installEventFilter(this);                         // bôi đen xong (thả chuột) -> tra đoạn bôi đen
    srcLbl_->setContextMenuPolicy(Qt::CustomContextMenu); connect(srcLbl_, &QLabel::customContextMenuRequested, this, &Overlay::menuSrc);
    vi_->setTextInteractionFlags(Qt::TextSelectableByMouse); vi_->setTextFormat(Qt::PlainText);
    vi_->setContextMenuPolicy(Qt::CustomContextMenu); connect(vi_, &QLabel::customContextMenuRequested, this, &Overlay::menuVi);
    // khoảng trống thừa của khung dồn vào spTop/spBot (theo "Vị trí chữ"), không chen giữa câu gốc và bản dịch
    spTop_ = new QSpacerItem(0, 0, QSizePolicy::Minimum, QSizePolicy::Fixed); gap_ = new QSpacerItem(0, 0, QSizePolicy::Minimum, QSizePolicy::Fixed);
    spBot_ = new QSpacerItem(0, 0, QSizePolicy::Minimum, QSizePolicy::Fixed);
    v->addItem(spTop_); v->addWidget(speaker_); v->addWidget(srcLbl_); v->addItem(gap_); v->addWidget(vi_); v->addItem(spBot_);
    grip_ = new QSizeGrip(this);
    status_ = new QLabel;                                      // trạng thái (OCR đang dùng, tạm dừng…) góc trái dưới, hiện khi rê chuột
    auto* foot = new QHBoxLayout; foot->setSpacing(10); foot->addWidget(status_); foot->addWidget(tag_); foot->addStretch(1);
    foot->addWidget(grip_, 0, Qt::AlignBottom | Qt::AlignRight); v->addLayout(foot);
    const QJsonArray g = cfg_.value("overlay_geom").toArray();
    QRect geo;
    if (g.size() == 4) geo = QRect(g[0].toInt(), g[1].toInt(), g[2].toInt(), g[3].toInt());
    else { const QRect sc = QApplication::primaryScreen()->availableGeometry(); geo = QRect(sc.x() + sc.width() / 2 - 380, sc.y() + int(sc.height() * 0.70), 760, 150); }
    baseH_ = geo.height(); auto_ = true; setGeometry(geo); auto_ = false;    // baseH = cỡ người dùng đặt; khung tự giãn khi chữ dài
    bar_->setVisible(false); status_->setVisible(false); applyStyle();
}

void Overlay::applyStyle() {
    const QString fg = cfg_.str("fg"), sfg = cfg_.str("src_fg"), acc = cfg_.str("accent");
    setStyleSheet(QString("QLabel { color:%1; } QToolButton { color:%2; border:none; padding:0; }"
                          "QToolButton:hover { color:%3; background:rgba(255,255,255,0.08); border-radius:4px; }"
                          "QToolButton#cap_hide:hover { color:%2; } QToolButton#cap_quit:hover { color:white; background:#c42b1c; }").arg(fg, sfg, acc));
    QFont f; f.setPointSize(cfg_.i("font_size")); vi_->setFont(f);
    QFont fs; fs.setPointSize(cfg_.i("src_font_size")); srcLbl_->setFont(fs); speaker_->setFont(fs);
    speaker_->setStyleSheet(QString("color:%1; font-weight:600").arg(acc));
    tag_->setStyleSheet(QString("color:%1; font-size:10px").arg(sfg)); status_->setStyleSheet(QString("color:%1; font-size:10px").arg(sfg));
    const int w = cfg_.i("text_outline");
    for (QLabel* l : {speaker_, srcLbl_, vi_, tag_, status_}) l->setGraphicsEffect(w > 0 ? new OutlineEffect(w, l) : nullptr);
    applyTextLayout(); applyDisplay(); update(); renderSrc();
    icons();
    const QStringList tb = cfg_.list("toolbar");
    for (const ToolDef& d : toolbarDefs()) btns_[d.key]->setVisible(tb.contains(d.key));
    std::stable_sort(flow_->items().begin(), flow_->items().end(), [&](QLayoutItem* a, QLayoutItem* b) {    // xếp theo thứ tự đã chọn
        auto pos = [&](QLayoutItem* it) { const QString k = btns_.key(qobject_cast<QToolButton*>(it->widget())); const int i = int(tb.indexOf(k)); return i < 0 ? 99 : i; };
        return pos(a) < pos(b);
    });
    flow_->invalidate();
    for (auto it = btns_.begin(); it != btns_.end(); ++it) {
        const QString k = it.key(); QString tip = tx(toolbarTip(k));
        QString hk = cfg_.hotkey(k); if (hk.isEmpty() && k == "hide") hk = cfg_.hotkey("toggle");
        if (k == "translate") tip = cfg_.b("translate") ? tx("overlay.translating_click_turn_off_source") : tx("overlay.translation_is_off_click_turn");
        it.value()->setToolTip(tip + (hk.isEmpty() ? "" : "  [" + hk + "]"));
    }
    setLocked(cfg_.b("locked")); fit(); winapp::excludeFromCapture(this, cfg_.b("hide_from_capture"));
}

void Overlay::paintEvent(QPaintEvent*) {
    QPainter p(this); p.setRenderHint(QPainter::Antialiasing);
    double a = cfg_.b("show_frame") ? std::clamp(cfg_.d("opacity"), 0.05, 1.0)
                                    : (bar_->isVisible() ? 0.35 : 1.0 / 255);   // không khung: gần trong suốt (alpha 0 thì chuột xuyên qua), rê chuột hiện mờ
    QColor c(cfg_.str("bg")); c.setAlphaF(float(a));
    p.setBrush(c); p.setPen(Qt::NoPen); p.drawRoundedRect(rect(), 10, 10);
}

void Overlay::showLine(const QString& speaker, const QString& src, const QString& vi, const QString& tag, bool alert) {
    speaker_->setText(speaker); speaker_->setVisible(!speaker.isEmpty() && cfg_.b("show_speaker"));
    if (src != src_) { src_ = src; renderSrc(); }
    vi_->setText(vi); tagText_ = tag; alert_ = alert; tagVis(); fit();
}

void Overlay::tagVis() { tag_->setText(bar_->isVisible() || alert_ ? tagText_ : QString()); }   // nguồn dịch chỉ hiện khi rê chuột; lỗi luôn hiện
void Overlay::setStatus(const QString& s) { status_->setText(s); }
QString Overlay::statusText() const { return status_->text(); }
QString Overlay::viText() const { return vi_->text(); }

void Overlay::fit() {
    // khung tự giãn lên trên (giữ mép dưới) khi chữ dài, co về cỡ người dùng đặt khi chữ ngắn
    const int need = layout()->totalHeightForWidth(width());
    const int h = std::max(baseH_, need);
    if (h == height()) return;
    const QRect g = geometry(); int top = g.bottom() + 1 - h;
    QScreen* scr = QApplication::screenAt(g.center()); if (!scr) scr = QApplication::primaryScreen();
    top = std::max(top, scr->availableGeometry().top());
    auto_ = true; setGeometry(g.x(), top, g.width(), h); auto_ = false;
}

void Overlay::renderSrc() {         // bọc cả dòng để dấu câu (ngoài link) cùng màu với chữ
    srcLbl_->setText(QString("<span style='color:%1'>%2</span>").arg(cfg_.str("src_fg"), tokensHtml(src_, cfg_.str("src_fg"))));
}

QString Overlay::word(const QString& href) const {
    const QStringList p = href.split(':');
    if (p.size() != 3) return {};
    const int a = p[1].toInt(), b = p[2].toInt();
    return src_.mid(a, b - a);
}

bool Overlay::eventFilter(QObject* o, QEvent* e) {
    if (o == srcLbl_ && e->type() == QEvent::MouseButtonRelease && static_cast<QMouseEvent*>(e)->button() == Qt::LeftButton)
        QTimer::singleShot(0, this, [this] {
            const QString sel = srcLbl_->selectedText().simplified();
            if (sel.size() >= 2) emit phraseAction("lookup", sel);
        });
    return QWidget::eventFilter(o, e);
}

void Overlay::menuSrc(const QPoint& pos) {
    const QString sel = srcLbl_->selectedText().trimmed(); QMenu m(this);
    if (!sel.isEmpty()) {
        const QList<QPair<QString, QString>> acts{{"lookup", tx("overlay.lookup", {{"w", sel.left(30)}})}, {"vocab", tx("overlay.vocab")},
                                                  {"keep", tx("overlay.keep")}, {"translate", tx("overlay.translate")}, {"explain", tx("overlay.explain")}};
        for (const auto& [k, t] : acts) m.addAction(t, this, [this, k, sel] { emit phraseAction(k, sel); });
        m.addSeparator();
    }
    m.addAction(tx("overlay.copy_source_line"), this, [this] { QApplication::clipboard()->setText(src_); });
    m.exec(srcLbl_->mapToGlobal(pos));
}

void Overlay::menuVi(const QPoint& pos) {
    QMenu m(this);
    m.addAction(tx("overlay.copy_translation"), this, [this] { QApplication::clipboard()->setText(vi_->text()); });
    m.addAction(tx("overlay.re_translate_by_machine"), this, [this] { emit action("retranslate"); });
    m.exec(vi_->mapToGlobal(pos));
}

void Overlay::setClickThrough(bool on) { cfg_.set("click_through", on); applyInput(); }
bool Overlay::passthroughWanted() const { return (cfg_.b("locked") && !alt_) || cfg_.b("click_through"); }

void Overlay::applyInput() {
    // chuột xuyên qua khi khóa (trừ lúc giữ phím mở khóa) hoặc bật click-through
    const bool want = passthroughWanted();
    if (want) { bar_->setVisible(false); status_->setVisible(false); }
    winapp::setPassthrough(this, want);
}

void Overlay::icons() {
    // icon tô theo màu câu gốc, rê chuột -> màu nhấn; nút bật/tắt đổi icon theo trạng thái
    const QColor c(cfg_.str("src_fg")), a(cfg_.str("accent"));
    const QHash<QString, bool> on{{"pause", paused_}, {"translate", !cfg_.b("translate")}, {"lock", cfg_.b("locked")}};
    auto set = [&](const ToolDef& d) {
        if (CAPTION.contains(d.key) && !capFont_.isEmpty()) return;
        btns_[d.key]->setIcon(mdi(on.value(d.key) ? ICON_ON.value(d.key) : d.icon, c, a));
    };
    for (const ToolDef& d : toolbarDefs()) set(d);
    for (const ToolDef& d : RIGHT_BTNS) set(d);
}

void Overlay::setPaused(bool p) { paused_ = p; icons(); status_->setText(p ? tx("overlay.paused") : QString()); }

void Overlay::showEvent(QShowEvent* e) { QWidget::showEvent(e); winapp::excludeFromCapture(this, cfg_.b("hide_from_capture")); applyInput(); }

void Overlay::setLocked(bool on) {
    grip_->setVisible(!on);
    if (on) setBar(false);
    icons(); applyInput();
    unlockVks_ = heldVks(cfg_.str("unlock_key")).value_or(std::vector<int>{});
    if (on && !unlockVks_.empty()) altT_.start();
    else { altT_.stop(); alt_ = false; }
}

void Overlay::pollAlt() {
    bool down = !unlockVks_.empty();
    for (int vk : unlockVks_) down &= winapp::keyDown(vk);
    if (down == alt_) return;
    alt_ = down; applyInput();
    if (!down) setBar(false);
}

void Overlay::applyTextLayout() {
    // vị trí khối chữ trong khung (trên / giữa / dưới) + khoảng cách thêm giữa câu gốc và bản dịch
    const QString al = cfg_.str("text_valign");
    auto grow = [](bool on) { return on ? QSizePolicy::Expanding : QSizePolicy::Fixed; };
    spTop_->changeSize(0, 0, QSizePolicy::Minimum, grow(al == "center" || al == "bottom"));
    spBot_->changeSize(0, 0, QSizePolicy::Minimum, grow(al == "center" || al == "top"));
    const bool both = srcLbl_->isVisibleTo(this) && vi_->isVisibleTo(this);    // chỉ 1 dòng thì khỏi chừa khoảng
    gap_->changeSize(0, both ? cfg_.i("line_gap") : 0, QSizePolicy::Minimum, QSizePolicy::Fixed);
    layout()->invalidate();
}

void Overlay::applyDisplay() {
    // 2 ngôn ngữ / chỉ bản dịch / chỉ 1 thứ, rê chuột vào hiện thêm thứ còn lại
    const QString d = cfg_.str("display"); const bool h = bar_->isVisible(), tr = cfg_.b("translate");
    const bool src = !tr || d == "both" || d == "src_hover" || (d == "vi_hover" && h);
    const bool vi = tr && (d == "both" || d == "vi" || d == "vi_hover" || (d == "src_hover" && h));
    if (srcLbl_->isVisibleTo(this) != src || vi_->isVisibleTo(this) != vi) { srcLbl_->setVisible(src); vi_->setVisible(vi); applyTextLayout(); fit(); }
}

void Overlay::setBar(bool on) { bar_->setVisible(on); status_->setVisible(on); tagVis(); applyDisplay(); update(); }

void Overlay::enterEvent(QEnterEvent*) {
    if (cfg_.b("locked") && !alt_) return;      // khóa: rê chuột không hiện gì (giữ phím mở khóa thì được)
    hideBar_.stop(); setBar(true);
}
void Overlay::leaveEvent(QEvent*) { hideBar_.start(); }
void Overlay::mousePressEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton && (!cfg_.b("locked") || alt_)) { drag_ = e->globalPosition().toPoint() - frameGeometry().topLeft(); dragging_ = true; }
}
void Overlay::mouseMoveEvent(QMouseEvent* e) { if (dragging_ && (e->buttons() & Qt::LeftButton)) move(e->globalPosition().toPoint() - drag_); }
void Overlay::mouseReleaseEvent(QMouseEvent*) { dragging_ = false; saveGeom(); }
void Overlay::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    if (!auto_) { baseH_ = height(); saveGeom(); fit(); }     // người dùng tự đổi cỡ
}
void Overlay::saveGeom() {
    const QRect g = geometry();
    cfg_.set("overlay_geom", QJsonArray{g.x(), g.bottom() + 1 - baseH_, g.width(), baseH_});
}

// ======================================================= WordPopup
WordPopup::WordPopup(Config& cfg) : QFrame(nullptr, FLAGS), cfg_(cfg) {
    setAttribute(Qt::WA_ShowWithoutActivating); setAttribute(Qt::WA_AlwaysShowToolTips); setObjectName("pop");
    auto* v = new QVBoxLayout(this); v->setContentsMargins(10, 8, 10, 8);
    title_ = new QLabel; title_->setTextFormat(Qt::RichText);
    lang_ = new QComboBox; lang_->setToolTip(tx("popup.target_language"));
    for (const auto& [code, name] : targetLangs()) lang_->addItem(tx(name), code);
    lang_->setCurrentIndex(std::max(0, lang_->findData(cfg_.str("target_lang"))));
    connect(lang_, &QComboBox::activated, this, [this](int) { emit langChanged(lang_->currentData().toString()); });
    close_ = new QToolButton; close_->setToolTip(tx("popup.close")); close_->setAutoRaise(true); close_->setFixedSize(26, 22);
    capFont_ = captionFont();
    if (!capFont_.isEmpty()) { close_->setText(CAPTION["quit"]); QFont f(capFont_); f.setPixelSize(10); close_->setFont(f); }
    connect(close_, &QToolButton::clicked, this, &WordPopup::closePop);
    auto* th = new QHBoxLayout; th->addWidget(title_, 1); th->addWidget(lang_); th->addWidget(close_);
    body_ = new QLabel; body_->setWordWrap(true); body_->setTextFormat(Qt::RichText); body_->setMaximumWidth(420); body_->setMinimumWidth(260);
    body_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    v->addLayout(th); v->addWidget(body_);
    auto* hb = new QHBoxLayout; hb->setSpacing(4);
    const QList<QPair<QString, QString>> btns{{"vocab", tx("popup.vocab")}, {"keep", tx("popup.keep")}, {"translate", tx("popup.translate")}, {"explain", tx("popup.explain")}};
    for (const auto& [k, t] : btns) { auto* b = new QPushButton(t); connect(b, &QPushButton::clicked, this, [this, k] { emit act(k, word); }); hb->addWidget(b); }
    v->addLayout(hb);
    source_ = new QLabel; source_->setAlignment(Qt::AlignRight); v->addWidget(source_);     // nguồn tra: Google / offline / AI
    hideT.setSingleShot(true); hideT.setInterval(450); connect(&hideT, &QTimer::timeout, this, &WordPopup::autoHide);
    applyStyle();
}

void WordPopup::applyStyle() {
    const QString bg = cfg_.str("bg"), fg = cfg_.str("fg"), sfg = cfg_.str("src_fg"), acc = cfg_.str("accent");
    setStyleSheet(QString("QFrame#pop { background:%1; border:1px solid %2; border-radius:8px; }"
                          "QLabel { color:%3; } QPushButton { color:%3; background:rgba(255,255,255,0.08); border:none;"
                          "padding:3px 8px; border-radius:4px; font-size:11px; } QPushButton:hover { background:%2; color:#111; }"
                          "QComboBox { color:%3; background:rgba(255,255,255,0.08); border:none; padding:2px 6px; font-size:11px; }").arg(bg, acc, fg));
    title_->setStyleSheet(QString("color:%1; font-weight:600; font-size:14px").arg(acc));
    source_->setStyleSheet(QString("color:%1; font-size:10px").arg(sfg));
    close_->setStyleSheet(QString("QToolButton { color:%1; border:none; padding:0; border-radius:4px; } QToolButton:hover { color:white; background:#c42b1c; }").arg(sfg));
    if (capFont_.isEmpty()) close_->setIcon(mdi("mdi6.close", QColor(sfg), Qt::white));
}

void WordPopup::set(const QString* meta, const QString& body) {
    if (meta) meta_ = *meta;
    raw = body; body_->setText(meta_ + "<div>" + body + "</div>"); adjustSize();
}

void WordPopup::showFor(const QString& w, const QString& head, const QString& meta, const QString& body, const QPoint& pos, bool pin, const QString& source) {
    word = w; pinned = pin; anchor = pos; source_->setText(source);
    lang_->setCurrentIndex(std::max(0, lang_->findData(cfg_.str("target_lang"))));
    const QString t = esc(w.size() <= 48 ? w : w.left(46) + QString::fromUtf8("…"));
    title_->setText(t + (!head.isEmpty() && head.toLower() != w.toLower() ? QString::fromUtf8(" <span style='opacity:.6;font-weight:400'>→ %1</span>").arg(esc(head)) : QString()));
    set(&meta, body);
    QScreen* scr = QApplication::screenAt(pos); if (!scr) scr = QApplication::primaryScreen();
    const QRect a = scr->availableGeometry();
    const int x = std::min(std::max(a.x(), pos.x() - width() / 2), a.right() - width());
    int y = pos.y() - height() - 14;
    if (y < a.y()) y = pos.y() + 20;
    move(x, y); show(); raise(); hideT.stop();
}

void WordPopup::setBody(const QString& w, const QString& body, const QString* meta) { if (w == word && isVisible()) set(meta, body); }
void WordPopup::setSource(const QString& s) { source_->setText(s); }
void WordPopup::requestHide() { if (!pinned) hideT.start(); }
void WordPopup::autoHide() { if (!underMouse() && !pinned && !lang_->view()->isVisible()) hide(); }
void WordPopup::enterEvent(QEnterEvent*) { hideT.stop(); }
void WordPopup::leaveEvent(QEvent*) { if (!pinned) hideT.start(); }
void WordPopup::closePop() { pinned = false; hide(); }
void WordPopup::showEvent(QShowEvent* e) { QFrame::showEvent(e); winapp::excludeFromCapture(this, cfg_.b("hide_from_capture")); }
void WordPopup::mousePressEvent(QMouseEvent* e) { if (e->button() == Qt::RightButton) closePop(); }
