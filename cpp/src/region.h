#pragma once
// Chọn vùng màn hình (đóng băng màn hình dưới con trỏ, kéo chuột) + viền "Xem vùng đang chọn" + quy đổi pixel vật lý <-> Qt.
#include <QColor>
#include <QPixmap>
#include <QRect>
#include <QWidget>
#include "config.h"

class QScreen;

Region toPhysical(QScreen* screen, const QRect& local);
QRect toLogical(const Region& r);

class RegionSelector : public QWidget {
    Q_OBJECT
public:
    explicit RegionSelector(const QString& title = {});
    void start();
signals:
    void selected(const Region& r);
    void cancelled();
protected:
    void paintEvent(QPaintEvent*) override;
    void mousePressEvent(QMouseEvent* e) override;
    void mouseMoveEvent(QMouseEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;
    void keyPressEvent(QKeyEvent* e) override;
private:
    QScreen* scr_;
    QPixmap bg_;
    QString title_;
    QPoint p0_, p1_; bool dragging_ = false;
};

class RegionFlash : public QWidget {          // viền sáng + nhãn quanh vùng; chuột xuyên qua; vô hình với ảnh chụp
public:
    RegionFlash(const QRect& r, const QString& label, const QColor& color);
protected:
    void showEvent(QShowEvent* e) override;
    void paintEvent(QPaintEvent*) override;
private:
    QString label_; QColor color_;
};
