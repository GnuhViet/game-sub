#pragma once
// Overlay phụ đề + popup tra từ (giống ui_overlay.py).
#include <QFrame>
#include <QGraphicsEffect>
#include <QHash>
#include <QLayout>
#include <QPointer>
#include <QTimer>
#include <QWidget>
#include <vector>

class Config;
class QComboBox;
class QLabel;
class QSizeGrip;
class QSpacerItem;
class QToolButton;

struct ToolDef { const char* key; const char* icon; };
const QList<ToolDef>& toolbarDefs();                 // nút chọn hiện/ẩn + sắp xếp trong Cài đặt
const char* toolbarTip(const QString& key);          // key i18n tooltip
QString tokensHtml(const QString& text, const QString& linkColor);    // mỗi từ là 1 link w:<đầu>:<cuối>
QList<QPoint> outlineOffsets(int w);
QString captionFont();                               // "Segoe Fluent Icons" / "Segoe MDL2 Assets" / ""

class OutlineEffect : public QGraphicsEffect {       // viền đen quanh chữ kiểu phụ đề
public:
    OutlineEffect(int w, QObject* parent) : QGraphicsEffect(parent), w_(w), offs_(outlineOffsets(w)) {}
    QRectF boundingRectFor(const QRectF& r) const override { return r.adjusted(-w_, -w_, w_, w_); }
protected:
    void draw(QPainter* p) override;
private:
    int w_; QList<QPoint> offs_;
};

class FlowLayout : public QLayout {                  // xếp widget theo hàng, hết chỗ thì xuống dòng
public:
    explicit FlowLayout(QWidget* parent) : QLayout(parent) { setSpacing(2); setContentsMargins(0, 0, 0, 0); }
    ~FlowLayout() override { while (QLayoutItem* it = takeAt(0)) delete it; }
    void addItem(QLayoutItem* it) override { items_.append(it); }
    int count() const override { return int(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return items_.value(i); }
    QLayoutItem* takeAt(int i) override { return i >= 0 && i < items_.size() ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return {}; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return place(QRect(0, 0, w, 0), true); }
    void setGeometry(const QRect& r) override { QLayout::setGeometry(r); place(r, false); }
    QSize sizeHint() const override { return minimumSize(); }
    QSize minimumSize() const override;
    QList<QLayoutItem*>& items() { return items_; }
private:
    int place(const QRect& r, bool test) const;
    QList<QLayoutItem*> items_;
};

class Overlay : public QWidget {
    Q_OBJECT
public:
    explicit Overlay(Config& cfg);
    void applyStyle();
    void showLine(const QString& speaker, const QString& src, const QString& vi, const QString& tag, bool alert = false);
    void setTag(const QString& tag, bool alert) { tagText_ = tag; alert_ = alert; tagVis(); }
    void setStatus(const QString& s);
    QString statusText() const;
    void setPaused(bool p);
    void setLocked(bool on);
    void setClickThrough(bool on);
    bool passthroughWanted() const;
    QString src() const { return src_; }
    QString viText() const;
signals:
    void wordHover(const QString& word, const QPoint& pos);
    void wordClick(const QString& word, const QPoint& pos);
    void phraseAction(const QString& action, const QString& phrase);
    void action(const QString& key);
protected:
    void paintEvent(QPaintEvent*) override;
    void showEvent(QShowEvent*) override;
    void enterEvent(QEnterEvent*) override;
    void leaveEvent(QEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void resizeEvent(QResizeEvent*) override;
    bool eventFilter(QObject* o, QEvent* e) override;
private:
    void tagVis();
    void fit();
    void renderSrc();
    QString word(const QString& href) const;
    void icons();
    void applyInput();
    void pollAlt();
    void applyTextLayout();
    void applyDisplay();
    void setBar(bool on);
    void saveGeom();
    void menuSrc(const QPoint& pos);
    void menuVi(const QPoint& pos);

    Config& cfg_;
    QString src_, tagText_, capFont_;
    bool alert_ = false, auto_ = false, alt_ = false, paused_ = false;
    std::vector<int> unlockVks_;
    QTimer altT_, hideBar_;
    QWidget* bar_;
    FlowLayout* flow_;
    QHash<QString, QToolButton*> btns_;
    QLabel *speaker_, *srcLbl_, *vi_, *tag_, *status_;
    QSpacerItem *spTop_, *gap_, *spBot_;
    QSizeGrip* grip_;
    QPoint drag_; bool dragging_ = false;
    int baseH_ = 150;
};

class WordPopup : public QFrame {
    Q_OBJECT
public:
    explicit WordPopup(Config& cfg);
    void applyStyle();
    void showFor(const QString& word, const QString& head, const QString& meta, const QString& body, const QPoint& pos, bool pinned, const QString& source);
    void setBody(const QString& word, const QString& body, const QString* meta = nullptr);
    void setSource(const QString& s);
    void requestHide();
    void closePop();
    QString word, raw;
    bool pinned = false;
    QPoint anchor;
    QTimer hideT;
signals:
    void act(const QString& action, const QString& word);
    void langChanged(const QString& code);
protected:
    void enterEvent(QEnterEvent*) override;
    void leaveEvent(QEvent*) override;
    void showEvent(QShowEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
private:
    void set(const QString* meta, const QString& body);
    void autoHide();
    Config& cfg_;
    QString meta_, capFont_;
    QLabel *title_, *body_, *source_;
    QComboBox* lang_;
    QToolButton* close_;
};
