#include "scanwin.h"
#include "config.h"
#include "i18n.h"
#include "overlay.h"
#include "winapp.h"
#include <QApplication>
#include <QClipboard>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QPushButton>
#include <QSplitter>
#include <QTextBrowser>
#include <QTimer>
#include <QVBoxLayout>

ScanWindow::ScanWindow(Config& cfg) : QWidget(nullptr, Qt::Tool | Qt::WindowStaysOnTopHint), cfg_(cfg) {
    setAttribute(Qt::WA_AlwaysShowToolTips);
    setWindowTitle(tx("scan.area_translation_hover_word_look")); resize(620, 560);
    auto* v = new QVBoxLayout(this); v->setContentsMargins(8, 8, 8, 8);
    srcView_ = new QTextBrowser; srcView_->setOpenLinks(false);
    connect(srcView_, &QTextBrowser::highlighted, this, [this](const QUrl& u) { emit wordHover(word(u), QCursor::pos()); });
    connect(srcView_, &QTextBrowser::anchorClicked, this, [this](const QUrl& u) { emit wordClick(word(u), QCursor::pos()); });
    srcView_->viewport()->installEventFilter(this);            // bôi đen xong -> tra đoạn bôi đen
    viView_ = new QTextBrowser;
    auto* sp = new QSplitter(Qt::Vertical); sp->addWidget(srcView_); sp->addWidget(viView_); v->addWidget(sp, 1);
    auto* hb = new QHBoxLayout; tag_ = new QLabel; hb->addWidget(tag_, 1);
    const QList<QPair<QString, QString>> btns{{"scan", tx("scan.scan")}, {"scan_retranslate", tx("scan.scan_retranslate")}, {"copy", tx("scan.copy")}, {"close", tx("scan.close")}};
    for (const auto& [k, t] : btns) {
        auto* b = new QPushButton(t); hb->addWidget(b);
        connect(b, &QPushButton::clicked, this, [this, k] {
            if (k == "copy") QApplication::clipboard()->setText(src_ + "\n\n" + viView_->toPlainText());
            else if (k == "close") hide();
            else emit action(k);
        });
    }
    v->addLayout(hb); applyStyle();
}

bool ScanWindow::eventFilter(QObject* o, QEvent* e) {
    if (o == srcView_->viewport() && e->type() == QEvent::MouseButtonRelease && static_cast<QMouseEvent*>(e)->button() == Qt::LeftButton)
        QTimer::singleShot(0, this, [this] {
            const QString sel = srcView_->textCursor().selectedText().simplified();      // simplified() bỏ cả U+2029 xuống đoạn
            if (sel.size() >= 2) emit wordClick(sel, QCursor::pos());
        });
    return QWidget::eventFilter(o, e);
}

void ScanWindow::showEvent(QShowEvent* e) { QWidget::showEvent(e); winapp::excludeFromCapture(this, cfg_.b("hide_from_capture")); }

void ScanWindow::applyStyle() {
    setStyleSheet(QString("QWidget { background:%1; color:%2; }"
                          "QTextBrowser { border:1px solid rgba(255,255,255,0.12); border-radius:6px; padding:6px; }"
                          "QPushButton { background:rgba(255,255,255,0.08); border:none; padding:4px 10px; border-radius:4px; }"
                          "QPushButton:hover { background:%3; color:#111; } QLabel { color:%4; font-size:11px; }")
                      .arg(cfg_.str("bg"), cfg_.str("fg"), cfg_.str("accent"), cfg_.str("src_fg")));
    srcView_->setStyleSheet(QString("font-size:%1pt;").arg(cfg_.i("src_font_size") + 2));
    viView_->setStyleSheet(QString("font-size:%1pt;").arg(cfg_.i("font_size")));
    renderSrc();
}

QString ScanWindow::word(const QUrl& u) const {
    const QStringList p = u.toString().split(':');
    if (p.size() != 3) return {};
    return src_.mid(p[1].toInt(), p[2].toInt() - p[1].toInt());
}

void ScanWindow::renderSrc() {
    QString body = tokensHtml(src_, cfg_.str("src_fg")); body.replace("\n", "<br><br>");     // giữ chia đoạn
    srcView_->setHtml(QString("<div style='color:%1'>%2</div>").arg(cfg_.str("src_fg"), body));
}

void ScanWindow::showResult(const QString& src, const QString& vi, const QString& tag) {
    if (src != src_) { src_ = src; renderSrc(); }
    QString v = vi; viView_->setPlainText(v.replace("\n", "\n\n")); tag_->setText(tag);
    if (!isVisible()) show();
    raise();
}
