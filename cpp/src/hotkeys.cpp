#include "hotkeys.h"
#include <QCoreApplication>
#include <QHash>
#include <windows.h>

namespace {
const QHash<QString, int> MODS{{"alt", MOD_ALT}, {"ctrl", MOD_CONTROL}, {"control", MOD_CONTROL}, {"shift", MOD_SHIFT}, {"win", MOD_WIN}};
QHash<QString, int> vkTable() {
    QHash<QString, int> v{{"space", 0x20}, {"enter", 0x0D}, {"tab", 0x09}, {"esc", 0x1B}, {"left", 0x25}, {"up", 0x26}, {"right", 0x27},
                          {"down", 0x28}, {"pgup", 0x21}, {"pgdn", 0x22}, {"`", 0xC0}, {"home", 0x24}, {"end", 0x23}};
    for (int i = 1; i <= 12; ++i) v.insert(QString("f%1").arg(i), 0x6F + i);
    return v;
}
const QHash<QString, int> VK = vkTable();
const QHash<QString, int> HOLD{{"alt", 0x12}, {"ctrl", 0x11}, {"control", 0x11}, {"shift", 0x10}, {"win", 0x5B}, {"meta", 0x5B},
                               {"capslock", 0x14}, {"backspace", 0x08}, {"return", 0x0D}, {"pgdown", 0x22}, {"ins", 0x2D}, {"del", 0x2E},
                               {"mouse3", 0x04}, {"mouse4", 0x05}, {"mouse5", 0x06}};

QStringList parts(const QString& seq) { QString s = seq.toLower(); s.remove(' '); return s.split('+', Qt::SkipEmptyParts); }
int single(const QString& p) { return p.size() == 1 && p[0].isLetterOrNumber() && p[0].unicode() < 128 ? p.toUpper()[0].unicode() : 0; }

std::pair<int, int> parse(const QString& seq) {
    int mods = 0, vk = 0;
    for (const QString& p : parts(seq)) {
        if (MODS.contains(p)) mods |= MODS[p];
        else if (VK.contains(p)) vk = VK[p];
        else if (int c = single(p)) vk = c;
    }
    return {mods, vk};
}
}  // namespace

std::optional<std::vector<int>> heldVks(const QString& seq) {
    std::vector<int> out;
    for (const QString& p : parts(seq)) {
        int vk = HOLD.value(p, VK.value(p, single(p)));
        if (!vk) return std::nullopt;
        out.push_back(vk);
    }
    return out;
}

Hotkeys::Hotkeys() { QCoreApplication::instance()->installNativeEventFilter(this); }
Hotkeys::~Hotkeys() { for (int id : ids_.keys()) UnregisterHotKey(nullptr, id); }

QStringList Hotkeys::registerAll(const QList<QPair<QString, QString>>& mapping) {
    for (int id : ids_.keys()) UnregisterHotKey(nullptr, id);
    ids_.clear(); QStringList errs; int n = 0;
    for (const auto& [action, seq] : mapping) {
        ++n;
        if (seq.isEmpty()) continue;
        const auto [mods, vk] = parse(seq);
        if (!vk || !RegisterHotKey(nullptr, n, mods | MOD_NOREPEAT, vk)) errs << action + "=" + seq;
        else ids_.insert(n, action);
    }
    return errs;
}

bool Hotkeys::nativeEventFilter(const QByteArray& type, void* message, qintptr* result) {
    if (type != "windows_generic_MSG") return false;
    const MSG* m = static_cast<MSG*>(message);
    if (m->message != WM_HOTKEY || !ids_.contains(int(m->wParam))) return false;
    emit triggered(ids_.value(int(m->wParam)));
    if (result) *result = 0;
    return true;
}
