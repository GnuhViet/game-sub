#include "config.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSaveFile>

QString appDir() { return QCoreApplication::applicationDirPath(); }
QString dataDir() {
    const QString env = qEnvironmentVariable("GAMESUB_DATA");
    return env.isEmpty() ? appDir() + "/data" : env;
}

static const char* DEFAULT_PROMPT =
    "Bạn là người dịch thoại game Wuthering Waves từ {src_lang} sang tiếng Việt.\n"
    "- Văn phong tự nhiên, đúng xưng hô theo quan hệ nhân vật và ngữ cảnh các câu trước.\n"
    "- Nhân vật chính: {player} ({gender}), xưng \"tôi\".\n"
    "- {keep_rule}\n"
    "- Chỉ trả về bản dịch của câu cần dịch, không giải thích, không ngoặc kép.\n"
    "{glossary}";

static const char* EXPLAIN_PROMPT =
    "Giải nghĩa ngắn gọn bằng tiếng Việt cho \"{word}\" trong câu: \"{sentence}\".\n"
    "Định dạng:\n"
    "/IPA/ (loại từ) nghĩa trong câu này\n"
    "• Nghĩa phổ biến khác (nếu có, tối đa 2)\n"
    "• Ví dụ ngắn kèm dịch";

const QStringList& Config::toolbarDefault() {
    static const QStringList tb = {"prev", "next", "pause", "translate", "rescan", "clear", "scan", "region", "speaker",
                                   "show_region", "subs", "glossary", "vocab", "lock"};
    return tb;
}

QJsonObject Config::defaults() {
    QJsonObject hk{{"toggle", "Ctrl+Alt+T"}, {"region", "Ctrl+Alt+R"}, {"pause", "Ctrl+Alt+P"}, {"rescan", "Ctrl+Alt+S"},
                   {"clickthrough", "Ctrl+Alt+C"}, {"clear", "Ctrl+Alt+X"}, {"translate", "Ctrl+Alt+D"}, {"scan", "Ctrl+Alt+Q"},
                   {"lock", "Ctrl+Alt+L"}};
    return QJsonObject{
        {"region", QJsonValue::Null}, {"speaker_region", QJsonValue::Null},
        {"ocr_engine", "windows"}, {"ocr_lang", "en-US"}, {"ocr_scale", 1.0},
        {"interval_ms", 250}, {"stable_ms", 350}, {"diff_threshold", 3.0}, {"dedupe_ratio", 92},
        {"src_lang", QString::fromUtf8("tiếng Anh")}, {"fix_spacing", true}, {"clear_on_empty", true}, {"target_app", ""},
        {"translate", true}, {"dialog_engine", "google"}, {"scan_engine", "ocr_google"},
        {"use_subs", true}, {"fuzzy_threshold", 86},
        {"gemini_key", ""}, {"gemini_model", "gemini-2.5-flash-lite"}, {"gemini_thinking_budget", 0},
        {"stream", true}, {"context_lines", 4}, {"prompt", QString::fromUtf8(DEFAULT_PROMPT)},
        {"explain_prompt", QString::fromUtf8(EXPLAIN_PROMPT)}, {"keep_terms", true}, {"timeout_s", 15}, {"cooldown_s", 30},
        {"player_name", "Rover"}, {"gender", "male"}, {"name_tokens", QJsonArray{"{PlayerName}", "{Nickname}", "{PLAYER_NAME}"}},
        {"dict_mode", "auto"}, {"target_lang", "vi"}, {"dict_files", QJsonArray{}}, {"hover_delay_ms", 250}, {"popup_trigger", "click"},
        {"font_size", 17}, {"src_font_size", 13}, {"opacity", 0.82}, {"show_frame", true}, {"locked", false},
        {"hide_from_capture", true}, {"show_speaker", true}, {"text_valign", "center"}, {"line_gap", 0}, {"display", "both"},
        {"ui_lang", ""}, {"unlock_key", "Alt"}, {"run_as_admin", false},
        {"toolbar", QJsonArray::fromStringList(toolbarDefault())}, {"toolbar_known", QJsonArray{}},
        {"text_outline", 0}, {"auto_hide_s", 0}, {"click_through", false}, {"overlay_geom", QJsonValue::Null},
        {"bg", "#101418"}, {"fg", "#f2f2f2"}, {"src_fg", "#9fb3c8"}, {"accent", "#e8c26a"}, {"hotkeys", hk},
    };
}

Config::Config(const QString& path) : path_(path.isEmpty() ? dataDir() + "/settings.json" : path), o_(defaults()) {
    QFile f(path_);
    if (!f.open(QIODevice::ReadOnly)) return;
    QJsonParseError err;
    const QJsonObject data = QJsonDocument::fromJson(f.readAll(), &err).object();
    if (err.error != QJsonParseError::NoError) { qWarning("settings.json lỗi, dùng mặc định: %s", qPrintable(err.errorString())); return; }
    static const QJsonObject oldHk{{"toggle", "Alt+T"}, {"region", "Alt+R"}, {"pause", "Alt+P"}, {"rescan", "Alt+S"}, {"clickthrough", "Alt+C"},
                                   {"clear", "Alt+X"}, {"translate", "Alt+D"}, {"scan", "Alt+Q"}, {"lock", "Alt+L"}};
    const QJsonObject def = defaults();
    for (auto it = data.begin(); it != data.end(); ++it) {
        if (it.key() == "hotkeys" && it.value().isObject()) {          // hotkey còn để mặc định cũ (Alt+phím) -> lên mặc định mới
            QJsonObject hk = o_.value("hotkeys").toObject(); const QJsonObject v = it.value().toObject();
            for (auto h = v.begin(); h != v.end(); ++h)
                if (h.value().toString() != oldHk.value(h.key()).toString()) hk.insert(h.key(), h.value());
            o_.insert("hotkeys", hk);
        } else if (def.contains(it.key())) o_.insert(it.key(), it.value());
    }
    if (!data.contains("display") && data.value("show_source") == QJsonValue(false)) o_.insert("display", "vi");      // cài đặt cũ
    if (!data.contains("unlock_key") && data.value("alt_unlock") == QJsonValue(false)) o_.insert("unlock_key", "");
    if (data.contains("toolbar")) {               // nút toolbar mới ra sau lần lưu trước: chèn ngay sau nút đứng trước nó (theo mặc định)
        static const QStringList oldTb = {"prev", "next", "pause", "translate", "rescan", "clear", "scan", "region", "speaker", "subs", "glossary", "vocab", "lock"};
        QStringList known; for (const auto& v : data.value("toolbar_known").toArray()) known << v.toString();
        if (known.isEmpty()) known = oldTb;
        QStringList tb = list("toolbar"); const QStringList& order = toolbarDefault();
        for (int k = 0; k < order.size(); ++k) {
            if (known.contains(order[k]) || tb.contains(order[k])) continue;
            int at = 0;
            for (int j = 0; j < k; ++j) if (tb.contains(order[j])) at = std::max(at, int(tb.indexOf(order[j])) + 1);
            tb.insert(at, order[k]);
        }
        o_.insert("toolbar", QJsonArray::fromStringList(tb));
    }
}

void Config::save() {
    o_.insert("toolbar_known", QJsonArray::fromStringList(toolbarDefault()));
    QDir().mkpath(QFileInfo(path_).absolutePath());
    QSaveFile f(path_);
    if (!f.open(QIODevice::WriteOnly)) return;
    f.write(QJsonDocument(o_).toJson(QJsonDocument::Indented)); f.commit();
}

QStringList Config::list(const QString& k) const {
    QStringList out;
    for (const auto& v : o_.value(k).toArray()) out << v.toString();
    return out;
}

Region Config::region(const QString& k) const {
    const QJsonObject r = o_.value(k).toObject(); Region g;
    if (r.isEmpty()) return g;
    g.x = r.value("x").toInt(); g.y = r.value("y").toInt(); g.w = r.value("w").toInt(); g.h = r.value("h").toInt();
    return g;
}

void Config::setRegion(const QString& k, const Region* r) {
    if (!r) { o_.insert(k, QJsonValue::Null); return; }
    o_.insert(k, QJsonObject{{"x", r->x}, {"y", r->y}, {"w", r->w}, {"h", r->h}});
}
