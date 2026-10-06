#pragma once
// Hotkey toàn cục qua RegisterHotKey (không cần quyền admin, không hook bàn phím) + phím đang giữ (GetAsyncKeyState).
#include <QAbstractNativeEventFilter>
#include <QHash>
#include <QObject>
#include <QStringList>
#include <optional>
#include <vector>

std::optional<std::vector<int>> heldVks(const QString& seq);    // "Ctrl+Mouse4" -> [VK…]; nullopt nếu có phần không hiểu

class Hotkeys : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT
public:
    Hotkeys();
    ~Hotkeys() override;
    QStringList registerAll(const QList<QPair<QString, QString>>& mapping);    // [(action, "Ctrl+Alt+T")] -> lỗi "action=seq"
    bool nativeEventFilter(const QByteArray& type, void* message, qintptr* result) override;
signals:
    void triggered(const QString& action);
private:
    QHash<int, QString> ids_;
};
