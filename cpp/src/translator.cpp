#include "translator.h"
#include "config.h"
#include "db.h"
#include "i18n.h"
#include "net.h"
#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <algorithm>
#include <memory>

namespace {
const QString SEP = "=====";
const int GOOGLE_COOLDOWN = 10;           // endpoint free chặn tạm theo IP khi gửi dồn dập -> nghỉ ngắn
qint64 nowMs() { return QDateTime::currentMSecsSinceEpoch(); }

QStringList chainOf(const QString& eng) {   // engine -> nhà cung cấp thử lần lượt (gemini_image đọc ảnh lỗi -> OCR + Google)
    static const QHash<QString, QStringList> C{{"google", {"google"}}, {"gemini", {"gemini"}}, {"gemini_google", {"gemini", "google"}},
                                               {"ocr_google", {"google"}}, {"ocr_gemini", {"gemini", "google"}}, {"gemini_image", {"google"}}};
    return C.value(eng, {"google"});
}

QString gemText(const QJsonObject& d, QString* blocked) {
    const QJsonArray c = d.value("candidates").toArray();
    if (c.isEmpty()) {
        if (!d.value("promptFeedback").toObject().value("blockReason").toString().isEmpty() && blocked) *blocked = tx("translator.blocked_by_safety_filter");
        return {};
    }
    QString out;
    for (const auto& p : c[0].toObject().value("content").toObject().value("parts").toArray())
        if (!p.toObject().value("thought").toBool()) out += p.toObject().value("text").toString();
    return out;
}

QRegularExpression wordRe(const QString& term) {
    return QRegularExpression("(?<!\\w)" + QRegularExpression::escape(term) + "(?!\\w)",
                              QRegularExpression::CaseInsensitiveOption | QRegularExpression::UseUnicodePropertiesOption);
}
}  // namespace

void googleFree(const QString& text, const QString& tl, int timeoutS, QHash<QString, qint64>* cool, StrFn done, StrFn err) {
    net::get(net::url("https://translate.googleapis.com/translate_a/single", {{"client", "gtx"}, {"sl", "auto"}, {"tl", tl}, {"dt", "t"}, {"q", text}}),
             timeoutS, [=](const net::Response& r) {
        if (r.status == 200) {
            QString out;
            for (const auto& seg : QJsonDocument::fromJson(r.body).array().at(0).toArray())
                if (seg.isArray() && seg.toArray().at(0).isString()) out += seg.toArray().at(0).toString();
            return done(out);
        }
        auto blocked = [=](int status) {
            if (status == 429) { if (cool) cool->insert("google", nowMs() + GOOGLE_COOLDOWN * 1000); return err(tx("translator.google_is_temporarily_blocking_too")); }
            err(status ? QString("Google HTTP %1").arg(status) : r.error);
        };
        if (r.status != 429) return blocked(r.status);
        net::get(net::url("https://clients5.google.com/translate_a/t", {{"client", "dict-chrome-ex"}, {"sl", "auto"}, {"tl", tl}, {"q", text}}),
                 timeoutS, [=](const net::Response& r2) {
            if (r2.status != 200) return blocked(r2.status ? r2.status : 429);
            QJsonValue d = QJsonDocument::fromJson(r2.body).isArray() ? QJsonValue(QJsonDocument::fromJson(r2.body).array()) : QJsonValue();
            if (d.isArray() && !d.toArray().isEmpty()) d = d.toArray().at(0);
            done(d.isArray() ? d.toArray().at(0).toString() : d.toString());
        });
    });
}

// ---------- prompt
QString Translator::glossaryBlock(const QString& text) {
    QStringList lines; const bool keepAll = cfg_.b("keep_terms");
    for (const Term& g : db_ ? db_->termsIn(text) : QList<Term>()) {
        if (keepAll || g.mode == "keep" || g.vi.isEmpty()) lines << QString::fromUtf8("- \"%1\": giữ nguyên").arg(g.term);
        else lines << QString::fromUtf8("- \"%1\" → \"%2\"").arg(g.term, g.vi);
    }
    return lines.isEmpty() ? QString() : QString::fromUtf8("Bảng thuật ngữ bắt buộc:\n") + lines.join('\n');
}

QString Translator::systemPrompt(const QString& text) {
    const QString keep = cfg_.b("keep_terms")
        ? QString::fromUtf8("Giữ nguyên tiếng Anh mọi tên riêng (nhân vật, địa danh, tổ chức) và thuật ngữ game.")
        : QString::fromUtf8("Tên riêng giữ nguyên; thuật ngữ được phép dịch nghĩa nếu tự nhiên hơn.");
    QString p = cfg_.str("prompt");
    p.replace("{src_lang}", cfg_.str("src_lang"));
    p.replace("{player}", cfg_.str("player_name").isEmpty() ? "Rover" : cfg_.str("player_name"));
    p.replace("{gender}", cfg_.str("gender") == "male" ? "nam" : QString::fromUtf8("nữ"));
    p.replace("{keep_rule}", keep);
    p.replace("{glossary}", glossaryBlock(text));
    return p.trimmed();
}

QString Translator::userPrompt(const QString& text, const QString& speaker, const QList<CtxLine>& ctx) const {
    QStringList c;
    for (const CtxLine& l : ctx) if (!l.vi.isEmpty()) c << (l.speaker.isEmpty() ? "" : l.speaker + ": ") + l.src + QString::fromUtf8("\n→ ") + l.vi;
    QString out = c.isEmpty() ? QString() : QString::fromUtf8("Các câu trước (để tham khảo ngữ cảnh):\n") + c.join('\n') + "\n\n";
    return out + QString::fromUtf8("Câu cần dịch:\n") + (speaker.isEmpty() ? "" : speaker + ": ") + text;
}

QString Translator::label(const QString& name) const {
    if (name == "gemini") return QString::fromUtf8("Gemini · ") + cfg_.str("gemini_model");
    if (name == "google") return "Google Translate";
    return name;
}

bool Translator::cooling(const QString& name) const { return nowMs() < cool_.value(name, 0); }

// ---------- dịch
void Translator::translate(const QString& text, const QString& speaker, const QList<CtxLine>& ctx, StrFn partial,
                           std::function<void(const TrResult&)> done, StrFn err, const QString& engine) {
    const QString eng = engine.isEmpty() ? cfg_.str("dialog_engine") : engine;
    const QString key = QString("tr:%1:%2:%3").arg(eng, cfg_.str("target_lang"), text);
    if (db_) if (auto hit = db_->cacheGet(key); hit && !hit->isEmpty()) {          // câu đã dịch -> khỏi gọi lại (đỡ bị Google chặn)
        const qsizetype t = hit->indexOf('\t');
        return done({hit->mid(t + 1), hit->left(t), {}});
    }
    chain(chainOf(eng), 0, {}, text, speaker, ctx, partial, [this, key, done](const TrResult& r) {
        if (db_ && !r.vi.isEmpty()) db_->cacheSet(key, r.provider + "\t" + r.vi);
        done(r);
    }, err);
}

void Translator::chain(const QStringList& names, int i, QStringList errs, const QString& text, const QString& speaker, const QList<CtxLine>& ctx,
                       StrFn partial, std::function<void(const TrResult&)> done, StrFn err) {
    while (i < names.size() && cooling(names[i])) { errs << names[i] + ": " + tx("translator.paused_after_rate_limit_429"); ++i; }
    if (i >= names.size()) return err(errs.isEmpty() ? tx("translator.no_translation_provider_configured") : errs.join("; "));
    const QString name = names[i];
    const QString note = errs.join("; ").replace("gemini:", tx("translator.gemini_error"));
    auto next = [=, this](const QString& e) { QStringList es = errs; es << name + ": " + e; chain(names, i + 1, es, text, speaker, ctx, partial, done, err); };
    if (name == "google") google(text, [=](const QString& vi) { done({vi, name, note}); }, next);
    else gemini(systemPrompt(text), userPrompt(text, speaker, ctx), partial, [=](const QString& vi) { done({vi, name, note}); }, next);
}

void Translator::explain(const QString& word, const QString& sentence, StrFn done, StrFn err) {
    QString p = cfg_.str("explain_prompt"); p.replace("{word}", word).replace("{sentence}", sentence);
    auto viaGoogle = [=, this] { google(word, [=](const QString& g) { done(g + " " + tx("translator.google_gemini_key_is_needed")); }, err); };
    if (!cfg_.str("gemini_key").isEmpty() && !cooling("gemini")) gemini("", p, {}, done, [=](const QString&) { viaGoogle(); });
    else viaGoogle();
}

void Translator::google(const QString& text, StrFn done, StrFn err) {
    // thuật ngữ glossary -> token ⟦n⟧ để Google không dịch, rồi khôi phục
    QString t = text; auto mapping = std::make_shared<QStringList>();
    for (const Term& g : db_ ? db_->termsIn(text) : QList<Term>()) {
        const bool keep = cfg_.b("keep_terms") || g.mode == "keep" || g.vi.isEmpty();
        const QString tok = QString::fromUtf8("⟦%1⟧").arg(mapping->size()); *mapping << (keep ? g.term : g.vi);
        t.replace(wordRe(g.term), tok);
    }
    googleFree(t, cfg_.str("target_lang"), cfg_.i("timeout_s"), &cool_, [=](const QString& out) {
        static const QRegularExpression tokRe(QString::fromUtf8(R"(⟦\s*(\d+)\s*⟧)"));
        QString res; qsizetype last = 0;
        for (auto it = tokRe.globalMatch(out); it.hasNext();) {
            auto m = it.next(); const int n = m.captured(1).toInt();
            res += out.mid(last, m.capturedStart() - last) + (n < mapping->size() ? mapping->at(n) : m.captured());
            last = m.capturedEnd();
        }
        done(res + out.mid(last));
    }, err);
}

QString Translator::checkError(const QString& name, int status, const QByteArray& body) {
    if (status == 429) { cool_.insert(name, nowMs() + qint64(cfg_.i("cooldown_s")) * 1000); return tx("translator.out_quota_429"); }
    if (status >= 400) {
        const QJsonValue e = QJsonDocument::fromJson(body).object().value("error");
        QString msg = e.isObject() ? e.toObject().value("message").toString() : (e.isString() ? e.toString() : QString::fromUtf8(body.left(200)));
        if (msg.contains("API key not valid") || msg.contains("API_KEY_INVALID")) return tx("translator.invalid_api_key");
        if (status == 404) return tx("translator.model_m_doesnt_exist_isnt", {{"m", cfg_.str("gemini_model")}});
        if (status == 403) return tx("translator.key_not_permitted_blocked_or");
        return QString("HTTP %1 %2").arg(status).arg(msg.left(160));
    }
    return {};
}

void Translator::gemini(const QString& system, const QString& user, StrFn partial, StrFn done, StrFn err, const QByteArray& png, int maxTokens) {
    if (cfg_.str("gemini_key").isEmpty()) return err(tx("translator.no_api_key"));
    QJsonArray parts{QJsonObject{{"text", user}}};
    if (!png.isEmpty()) parts.prepend(QJsonObject{{"inline_data", QJsonObject{{"mime_type", "image/png"}, {"data", QString::fromLatin1(png.toBase64())}}}});
    QJsonObject gen{{"temperature", 0.3}, {"maxOutputTokens", maxTokens}};
    const int budget = cfg_.i("gemini_thinking_budget");
    if (budget >= 0) gen.insert("thinkingConfig", QJsonObject{{"thinkingBudget", budget}});
    QJsonObject body{{"contents", QJsonArray{QJsonObject{{"role", "user"}, {"parts", parts}}}}, {"generationConfig", gen}};
    if (!system.isEmpty()) body.insert("systemInstruction", QJsonObject{{"parts", QJsonArray{QJsonObject{{"text", system}}}}});
    const bool stream = cfg_.b("stream") && partial;
    const QUrl u("https://generativelanguage.googleapis.com/v1beta/models/" + cfg_.str("gemini_model") +
                 (stream ? ":streamGenerateContent?alt=sse" : ":generateContent"));
    const QList<QPair<QByteArray, QByteArray>> hdr{{"x-goog-api-key", cfg_.str("gemini_key").toUtf8()}};

    geminiSend(u, hdr, body, stream, partial, done, err, false);
}

void Translator::geminiSend(const QUrl& u, const QList<QPair<QByteArray, QByteArray>>& hdr, const QJsonObject& body, bool stream,
                            StrFn partial, StrFn done, StrFn err, bool retried) {
    struct St { QByteArray raw, line; QString acc, blocked; };
    auto st = std::make_shared<St>();
    net::Chunk chunk;
    if (stream) chunk = [=](const QByteArray& data, int status) {          // SSE: mỗi dòng "data: {...}" là 1 đoạn chữ mới
        st->raw += data;
        if (status != 200) return;
        st->line += data; qsizetype nl;
        while ((nl = st->line.indexOf('\n')) >= 0) {
            const QByteArray l = st->line.left(nl).trimmed(); st->line.remove(0, nl + 1);
            if (!l.startsWith("data:")) continue;
            const QJsonDocument d = QJsonDocument::fromJson(l.mid(5));
            if (!d.isObject()) continue;
            st->acc += gemText(d.object(), &st->blocked); partial(st->acc);
        }
    };
    net::post(u, QJsonDocument(body).toJson(QJsonDocument::Compact), cfg_.i("timeout_s"), [=, this](const net::Response& r) {
        const QByteArray full = stream ? st->raw : r.body;
        if (r.status == 400 && !retried && full.toLower().contains("thinking")) {          // model không hỗ trợ tắt thinking
            QJsonObject b2 = body; QJsonObject g = b2["generationConfig"].toObject(); g.remove("thinkingConfig"); b2["generationConfig"] = g;
            return geminiSend(u, hdr, b2, stream, partial, done, err, true);
        }
        if (r.status == 0) return err(r.error);
        if (const QString e = checkError("gemini", r.status, full); !e.isEmpty()) return err(e);
        if (stream) { if (st->acc.isEmpty() && !st->blocked.isEmpty()) return err(st->blocked); return done(st->acc.trimmed()); }
        QString blocked; const QString t = gemText(QJsonDocument::fromJson(full).object(), &blocked);
        if (t.isEmpty() && !blocked.isEmpty()) return err(blocked);
        done(t.trimmed());
    }, hdr, chunk);
}

void Translator::readImage(const QByteArray& png, StrFn partial, std::function<void(const QString&, const QString&)> done, StrFn err) {
    const QString user = QString::fromUtf8(
        "Ảnh là một phần màn hình game (thư, bảng thông tin…). Chép lại NGUYÊN VĂN toàn bộ chữ trong ảnh theo đúng thứ tự đọc, "
        "giữ cách chia đoạn như trong ảnh (mỗi đoạn một dòng; dòng bị ngắt giữa câu thì nối lại), "
        "rồi một dòng chỉ có %1, rồi bản dịch sang tiếng Việt theo các quy tắc trên, chia đoạn y như bản gốc. Không thêm gì khác.").arg(SEP);
    auto split = [](const QString& t) -> QPair<QString, QString> {
        const qsizetype i = t.indexOf(SEP);
        return i < 0 ? QPair<QString, QString>{{}, t.trimmed()} : QPair<QString, QString>{t.left(i).trimmed(), t.mid(i + SEP.size()).trimmed()};
    };
    StrFn part = partial ? StrFn([=](const QString& t) { partial(t.contains(SEP) ? split(t).second : QString()); }) : StrFn();
    gemini(systemPrompt(""), user, part, [=](const QString& t) {
        const auto [src, vi] = split(t);
        if (src.isEmpty()) return err(tx("translator.gemini_returned_no_readable_text"));
        done(src, vi);
    }, err, png, 4096);
}

void Translator::listModels(const QString& key, std::function<void(const QStringList&)> done, StrFn err) {
    net::get(net::url("https://generativelanguage.googleapis.com/v1beta/models", {{"pageSize", "1000"}}), cfg_.i("timeout_s"),
             [=, this](const net::Response& r) {
        if (r.status == 0) return err(r.error);
        if (const QString e = checkError("gemini", r.status, r.body); !e.isEmpty()) return err(e);
        static const QRegularExpression skip("embedding|tts|image|audio|live|robotics|computer"), digits(R"(\d+)");
        QStringList names;
        for (const auto& m : QJsonDocument::fromJson(r.body).object().value("models").toArray()) {
            const QJsonObject o = m.toObject(); const QString full = o.value("name").toString();
            const QString n = full.section('/', 1); bool gen = false;
            for (const auto& x : o.value("supportedGenerationMethods").toArray()) gen |= x.toString() == "generateContent";
            if (gen && full.section('/', -1).startsWith("gemini") && !skip.match(full).hasMatch() && !names.contains(n)) names << n;
        }
        auto ver = [&](const QString& n) {
            QList<int> v; const QString part = n.contains('-') ? n.section('-', 1, 1) : "0";
            for (auto it = digits.globalMatch(part); it.hasNext();) v << it.next().captured().toInt();
            return v;
        };
        auto stable = [](const QString& n) { return !n.contains("preview") && !n.contains("exp"); };
        std::stable_sort(names.begin(), names.end(), [&](const QString& a, const QString& b) {    // mới nhất trước, bản ổn định trước bản preview
            const auto va = ver(a), vb = ver(b);
            if (va != vb) return vb < va;
            return stable(a) && !stable(b);
        });
        done(names);
    }, {{"x-goog-api-key", key.toUtf8()}});
}

QString Translator::pickModel(const QStringList& names) {
    // ưu tiên Flash-Lite (nhanh, quota free rộng) bản ổn định mới nhất, rồi Flash
    static const QRegularExpression unstable(R"(preview|exp|\d{3,}$)");
    QStringList stable; for (const QString& n : names) if (!unstable.match(n).hasMatch()) stable << n;
    if (stable.isEmpty()) stable = names;
    for (const char* kw : {"flash-lite", "flash"}) for (const QString& n : stable) if (n.contains(QLatin1String(kw))) return n;
    return names.value(0);
}
