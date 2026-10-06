#pragma once
// Cài đặt, Glossary, Sổ từ, Ôn tập, Bộ sub (giống ui_dialogs.py).
#include <QDialog>
#include <QHash>
#include <QJsonObject>
#include <QLineEdit>
#include <functional>
#include "db.h"

class Config;
class SubIndex;
class QComboBox;
class QFormLayout;
class QLabel;
class QLayout;
class QListWidget;
class QPlainTextEdit;
class QPushButton;
class QTabWidget;
class QTableWidget;

class KeyCapture : public QLineEdit {        // bấm vào ô rồi nhấn phím / tổ hợp / nút chuột giữa-bên để gán; Backspace = tắt
public:
    explicit KeyCapture(const QString& seq);
protected:
    void focusInEvent(QFocusEvent* e) override;
    void focusOutEvent(QFocusEvent* e) override;
    void keyPressEvent(QKeyEvent* e) override;
    void mousePressEvent(QMouseEvent* e) override;
private:
    void setKey(const QString& key, Qt::KeyboardModifiers mods);
};

class SettingsDialog : public QDialog {
    Q_OBJECT
public:
    SettingsDialog(Config& cfg, std::function<void()> onPreview);
    void apply();
    bool installed = false;
    QPushButton *btnSnap, *btnShow;
    void reject() override;
private:
    using Getter = std::function<QJsonValue()>;
    QFormLayout* tab(QTabWidget* tabs, const char* key);
    QFormLayout* group(QFormLayout* f, const char* key);
    QLineEdit* line(QFormLayout* f, const QString& k, const char* label, const char* ph = nullptr, bool password = false);
    QWidget* spin(QFormLayout* f, const QString& k, const char* label, int lo, int hi);
    QWidget* dspin(QFormLayout* f, const QString& k, const char* label, double lo, double hi, double step);
    QWidget* check(QFormLayout* f, const QString& k, const char* label);
    QComboBox* combo(QFormLayout* f, const QString& k, const char* label, const QList<QPair<QString, QString>>& opts);
    void color(QFormLayout* f, const QString& k, const char* label);
    void tip(QFormLayout* f, QObject* field, const QString& text);
    void live(const QString& k, const QJsonValue& v);
    void engRefresh();
    void loadApps();
    QString appValue() const;
    void gemWarn();
    void testKey();
    void install();
    void remove();

    Config& cfg_;
    std::function<void()> onPreview_;
    QHash<QString, Getter> w_;
    QHash<QString, QWidget*> widgets_;
    QJsonObject snap_;
    QHash<QString, QLineEdit*> hk_;
    QComboBox *appCombo_, *model_;
    QLabel *gemWarn_, *keyStatus_, *engStatus_, *tessStatus_;
    QPushButton *tessInstall_, *tessRemove_;
    QPlainTextEdit *prompt_, *explain_;
    QLineEdit* tokens_;
    QListWidget* dicts_;
    QWidget* preview_;
};

class GlossaryDialog : public QDialog {
public:
    GlossaryDialog(DB& db, Config& cfg);
private:
    int row(const QString& term = {}, const QString& vi = {}, const QString& mode = "keep", const QString& note = {});
    void load();
    void save(bool close = true);
    DB& db_; Config& cfg_;
    QTableWidget* t_;
    class QCheckBox* keep_;
};

class VocabDialog : public QDialog {
public:
    explicit VocabDialog(DB& db);
private:
    void load();
    DB& db_;
    QTableWidget* t_;
    QLineEdit* flt_;
    QLabel* count_;
};

class ReviewDialog : public QDialog {
public:
    ReviewDialog(DB& db, QList<VocabRow> rows, QWidget* parent);
protected:
    void keyPressEvent(QKeyEvent* e) override;
private:
    void render();
    void showAnswer();
    void next();
    DB& db_;
    QList<VocabRow> rows_;
    int i_ = 0;
    QLabel *word_, *ctx_, *ans_;
};

class SubsDialog : public QDialog {
public:
    SubsDialog(DB& db, SubIndex& index, Config& cfg, std::function<void()> onChanged);
private:
    void files();
    void open();
    void import();
    void del();
    void test();
    DB& db_; SubIndex& index_; Config& cfg_;
    std::function<void()> onChanged_;
    QListWidget* files_;
    QLabel *prevLbl_, *testOut_;
    QComboBox *srcC_, *viC_;
    QPushButton* impB_;
    QTableWidget* t_;
    QLineEdit* test_;
    QString path_;
    QStringList hdr_;
    QList<QStringList> rows_;
};
