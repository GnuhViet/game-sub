#include "region.h"
#include "i18n.h"
#include "winapp.h"
#include <QApplication>
#include <QKeyEvent>
#include <QPainter>
#include <QScreen>
#include <cmath>

Region toPhysical(QScreen* s, const QRect& r) {
    // Qt6/Windows: gốc màn hình giữ nguyên pixel vật lý, phần bên trong scale theo DPR
    const QRect g = s->geometry(); const double d = s->devicePixelRatio();
    return {int(std::lround(g.x() + r.x() * d)), int(std::lround(g.y() + r.y() * d)), int(std::lround(r.width() * d)), int(std::lround(r.height() * d))};
}

QRect toLogical(const Region& r) {
    for (QScreen* s : QApplication::screens()) {
        const QRect g = s->geometry(); const double d = s->devicePixelRatio();
        if (g.x() <= r.x && r.x < g.x() + g.width() * d && g.y() <= r.y && r.y < g.y() + g.height() * d)
            return QRect(int(std::lround(g.x() + (r.x - g.x()) / d)), int(std::lround(g.y() + (r.y - g.y()) / d)), int(std::lround(r.w / d)), int(std::lround(r.h / d)));
    }
    return QRect(r.x, r.y, r.w, r.h);
}

RegionSelector::RegionSelector(const QString& title) : QWidget(nullptr, Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool) {
    setAttribute(Qt::WA_DeleteOnClose);
    scr_ = QApplication::screenAt(QCursor::pos()); if (!scr_) scr_ = QApplication::primaryScreen();
    bg_ = scr_->grabWindow(0); title_ = title.isEmpty() ? tx("region.drag_select_area_esc_cancel") : title;
    setGeometry(scr_->geometry()); setCursor(Qt::CrossCursor);
}

void RegionSelector::start() {
    show(); activateWindow(); raise(); setFocus();
    winapp::forceForeground(reinterpret_cast<void*>(winId()));      // gọi bằng hotkey khi game đang focus
}

void RegionSelector::paintEvent(QPaintEvent*) {
    QPainter p(this); p.drawPixmap(rect(), bg_); p.fillRect(rect(), QColor(0, 0, 0, 120));
    if (dragging_) {
        const QRect r = QRect(p0_, p1_).normalized();
        const QRect src(int(r.x() * bg_.width() / double(width())), int(r.y() * bg_.height() / double(height())),
                        int(r.width() * bg_.width() / double(width())), int(r.height() * bg_.height() / double(height())));
        p.drawPixmap(r, bg_, src); p.setPen(QPen(QColor("#e8c26a"), 2)); p.drawRect(r);
        const double d = scr_->devicePixelRatio();
        p.drawText(r.bottomLeft() + QPoint(2, 16), QString("%1×%2").arg(std::lround(r.width() * d)).arg(std::lround(r.height() * d)));
    }
    QFont f; f.setPointSize(14); p.setFont(f); p.setPen(Qt::white);
    p.drawText(rect().adjusted(0, 30, 0, 0), Qt::AlignHCenter | Qt::AlignTop, title_);
}

void RegionSelector::mousePressEvent(QMouseEvent* e) { p0_ = p1_ = e->position().toPoint(); dragging_ = true; update(); }
void RegionSelector::mouseMoveEvent(QMouseEvent* e) { if (dragging_) { p1_ = e->position().toPoint(); update(); } }
void RegionSelector::mouseReleaseEvent(QMouseEvent* e) {
    if (!dragging_) return;
    const QRect r = QRect(p0_, e->position().toPoint()).normalized(); close();
    if (r.width() < 8 || r.height() < 8) { emit cancelled(); return; }
    emit selected(toPhysical(scr_, r));
}
void RegionSelector::keyPressEvent(QKeyEvent* e) { if (e->key() == Qt::Key_Escape) { close(); emit cancelled(); } }

static const int PAD = 3, LABEL_H = 22;

RegionFlash::RegionFlash(const QRect& r, const QString& label, const QColor& color)
    : QWidget(nullptr, Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool | Qt::WindowTransparentForInput), label_(label), color_(color) {
    setAttribute(Qt::WA_TranslucentBackground); setAttribute(Qt::WA_ShowWithoutActivating);
    setGeometry(r.adjusted(-PAD, -PAD - LABEL_H, PAD, PAD));
}
void RegionFlash::showEvent(QShowEvent* e) { QWidget::showEvent(e); winapp::excludeFromCapture(this); }
void RegionFlash::paintEvent(QPaintEvent*) {
    QPainter p(this); const QRect box = rect().adjusted(1, LABEL_H + 1, -1, -1);
    p.setPen(QPen(color_, 2)); p.setBrush(QColor(color_.red(), color_.green(), color_.blue(), 35)); p.drawRect(box);
    QFont f; f.setPointSize(9); f.setBold(true); p.setFont(f);
    const QRect tab(box.x() - 1, 0, p.fontMetrics().horizontalAdvance(label_) + 14, LABEL_H);
    p.fillRect(tab, color_); p.setPen(QColor("#111")); p.drawText(tab, Qt::AlignCenter, label_);
}
