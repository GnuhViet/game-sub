// Test đối chiếu phần lõi C++ với bản Python: core_test <expected.json>  (sinh bằng tests/make_expected.py)
#include <QCoreApplication>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <cmath>
#include <cstdio>
#include "matcher.h"
#include "spacing.h"
#include "textnorm.h"

using namespace textnorm;
static int fails = 0, total = 0;

static QStringList strs(const QJsonValue& v) { QStringList o; for (const auto& x : v.toArray()) o << x.toString(); return o; }
static void check(const char* what, const QString& in, const QString& got, const QString& want) {
    ++total;
    if (got != want) { ++fails; std::printf("FAIL %s\n  in:   %s\n  got:  %s\n  want: %s\n", what, qUtf8Printable(in), qUtf8Printable(got), qUtf8Printable(want)); }
}

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QFile f(argc > 1 ? argv[1] : "expected.json");
    if (!f.open(QIODevice::ReadOnly)) { std::puts("không mở được expected.json"); return 2; }
    const QJsonObject e = QJsonDocument::fromJson(f.readAll()).object();
    const QStringList tokens{"{PlayerName}"};

    for (const QJsonObject o_norm = e["norm"].toObject(); auto kv : o_norm.asKeyValueRange()) if (const std::pair<QString, QJsonValue> it{kv.first.toString(), kv.second}; true) check("norm", it.first, norm(it.first), it.second.toString());
    for (const QJsonObject o_resolve = e["resolve"].toObject(); auto kv : o_resolve.asKeyValueRange()) if (const std::pair<QString, QJsonValue> it{kv.first.toString(), kv.second}; true) {
        const QJsonArray w = it.second.toArray();
        check("resolve", it.first, resolve(it.first, "male", tokens, "Rover"), w[0].toString());
        check("resolve(match)", it.first, resolve(it.first, "female", tokens, "Rover", true), w[1].toString());
    }
    for (const QJsonObject o_ocr_for_match = e["ocr_for_match"].toObject(); auto kv : o_ocr_for_match.asKeyValueRange()) if (const std::pair<QString, QJsonValue> it{kv.first.toString(), kv.second}; true)
        check("ocr_for_match", it.first, ocrForMatch(it.first, "Rover"), it.second.toString());
    for (const QJsonObject o_lemmas = e["lemmas"].toObject(); auto kv : o_lemmas.asKeyValueRange()) if (const std::pair<QString, QJsonValue> it{kv.first.toString(), kv.second}; true)
        check("lemmas", it.first, lemmas(it.first).join(" | "), strs(it.second).join(" | "));
    for (const QJsonObject o_sentences = e["sentences"].toObject(); auto kv : o_sentences.asKeyValueRange()) if (const std::pair<QString, QJsonValue> it{kv.first.toString(), kv.second}; true)
        check("split_sentences", it.first, splitSentences(it.first).join(" | "), strs(it.second).join(" | "));
    for (const auto& v : e["join_lines"].toArray()) { const auto a = v.toArray(); check("join_lines", strs(a[0]).join("/"), joinLines(strs(a[0])), a[1].toString()); }
    for (const auto& v : e["paragraphs"].toArray()) { const auto a = v.toArray(); check("paragraphs", strs(a[0]).join("/"), paragraphs(strs(a[0])), a[1].toString()); }

    Spacer sp; sp.setKnown({"Jinzhou", "Rover"});
    for (const QJsonObject o_spacing = e["spacing"].toObject(); auto kv : o_spacing.asKeyValueRange()) if (const std::pair<QString, QJsonValue> it{kv.first.toString(), kv.second}; true) check("spacing", it.first, sp.fix(it.first), it.second.toString());

    QList<QPair<QString, QString>> subs;
    for (const auto& v : e["subs"].toArray()) subs.append({v.toArray()[0].toString(), v.toArray()[1].toString()});
    SubIndex ix; ix.build(subs, "male", tokens, "Rover");
    for (const QJsonObject o_match = e["match"].toObject(); auto kv : o_match.asKeyValueRange()) if (const std::pair<QString, QJsonValue> it{kv.first.toString(), kv.second}; true) {
        const auto m = ix.match(it.first, 86);
        QString got = m ? QString("%1 | %2 | %3").arg(m->vi).arg(std::round(m->score * 1000) / 1000).arg(m->src) : "None";
        QString want = "None";
        if (it.second.isArray()) { const auto a = it.second.toArray(); want = QString("%1 | %2 | %3").arg(a[0].toString()).arg(a[1].toDouble()).arg(a[2].toString()); }
        check("match", it.first, got, want);
    }
    std::printf("%d/%d khớp bản Python\n", total - fails, total);
    return fails ? 1 : 0;
}
