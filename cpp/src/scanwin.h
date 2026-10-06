#pragma once
// Cửa sổ "Chụp & dịch 1 vùng": câu gốc (bấm từ để tra) + bản dịch (giống ui_scan.py).
#include <QWidget>

class Config;
class QLabel;
class QTextBrowser;

class ScanWindow : public QWidget {
    Q_OBJECT
public:
    explicit ScanWindow(Config& cfg);
    void applyStyle();
    void showResult(const QString& src, const QString& vi, const QString& tag);
    QString src() const { return src_; }
signals:
    void wordHover(const QString& word, const QPoint& pos);
    void wordClick(const QString& word, const QPoint& pos);
    void action(const QString& key);          // scan / scan_retranslate
protected:
    void showEvent(QShowEvent* e) override;
    bool eventFilter(QObject* o, QEvent* e) override;
private:
    QString word(const QUrl& u) const;
    void renderSrc();
    Config& cfg_;
    QString src_;
    QTextBrowser *srcView_, *viView_;
    QLabel* tag_;
};
