#include "icons.h"
#include <QFile>
#include <QFontDatabase>
#include <QHash>
#include <QIconEngine>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPainter>
#include <QPixmap>

namespace {
const QHash<QString, int>& codes() {
    static const QHash<QString, int> c = [] {
        QHash<QString, int> m; QFile f(":/mdi6.json");
        if (f.open(QIODevice::ReadOnly)) {
            const QJsonObject o = QJsonDocument::fromJson(f.readAll()).object();
            for (auto it = o.begin(); it != o.end(); ++it) m.insert(it.key(), it->toInt());
        }
        return m;
    }();
    return c;
}

QString family() {
    static const QString fam = [] {           // nạp font lần đầu cần icon (sau khi đã có QApplication)
        const QStringList f = QFontDatabase::applicationFontFamilies(QFontDatabase::addApplicationFont(":/mdi6.ttf"));
        return f.value(0);
    }();
    return fam;
}

class Engine : public QIconEngine {
public:
    Engine(QString ch, QColor c, QColor a) : ch_(std::move(ch)), c_(c), a_(a.isValid() ? a : c) {}
    void paint(QPainter* p, const QRect& rect, QIcon::Mode mode, QIcon::State) override {
        QColor col = mode == QIcon::Active || mode == QIcon::Selected ? a_ : c_;
        if (mode == QIcon::Disabled) col.setAlphaF(col.alphaF() * 0.4f);
        QFont f(family()); f.setPixelSize(std::max(1, std::min(rect.width(), rect.height())));
        p->save(); p->setRenderHint(QPainter::TextAntialiasing); p->setFont(f); p->setPen(col);
        p->drawText(rect, Qt::AlignCenter, ch_); p->restore();
    }
    QPixmap pixmap(const QSize& size, QIcon::Mode mode, QIcon::State state) override { return scaledPixmap(size, mode, state, 1.0); }
    QPixmap scaledPixmap(const QSize& size, QIcon::Mode mode, QIcon::State state, qreal scale) override {   // HiDPI: không mờ
        QPixmap pm(size * scale); pm.setDevicePixelRatio(scale); pm.fill(Qt::transparent);
        QPainter p(&pm); paint(&p, QRect(QPoint(0, 0), size), mode, state);
        return pm;
    }
    QIconEngine* clone() const override { return new Engine(ch_, c_, a_); }
private:
    QString ch_; QColor c_, a_;
};
}  // namespace

QIcon mdi(const QString& name, const QColor& color, const QColor& active) {
    const char32_t code = char32_t(codes().value(name.section('.', -1), 0));
    return QIcon(new Engine(code ? QString::fromUcs4(&code, 1) : QString(), color, active));
}
