#pragma once
// Cài đặt data/settings.json — cùng định dạng, cùng key, cùng mặc định với bản Python (đọc chung được).
#include <QJsonObject>
#include <QRect>
#include <QString>
#include <QStringList>
#include <QVariant>

QString appDir();                 // thư mục chứa exe
QString dataDir();                // <exe>/data (biến môi trường GAMESUB_DATA để thử)

struct Region { int x = 0, y = 0, w = 0, h = 0; bool valid() const { return w > 0 && h > 0; } };

class Config {
public:
    explicit Config(const QString& path = {});
    void save();

    QJsonValue value(const QString& k) const { return o_.value(k); }
    QString str(const QString& k) const { return o_.value(k).toString(); }
    int i(const QString& k) const { return o_.value(k).toInt(); }
    double d(const QString& k) const { return o_.value(k).toDouble(); }
    bool b(const QString& k) const { return o_.value(k).toBool(); }
    QStringList list(const QString& k) const;
    QJsonObject obj(const QString& k) const { return o_.value(k).toObject(); }
    QString hotkey(const QString& action) const { return obj("hotkeys").value(action).toString(); }
    Region region(const QString& k) const;
    void set(const QString& k, const QJsonValue& v) { o_.insert(k, v); }
    void setRegion(const QString& k, const Region* r);
    QJsonObject& raw() { return o_; }

    static QJsonObject defaults();
    static const QStringList& toolbarDefault();

private:
    QString path_;
    QJsonObject o_;
};
