// tạm: kiểm tra biên dịch phần lõi
#include <QApplication>
#include "config.h"
#include "db.h"
#include "i18n.h"
#include "matcher.h"
#include "spacing.h"
#include "textnorm.h"

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    Config cfg; Spacer sp; SubIndex ix;
    qInfo("%s", qPrintable(sp.fix("youfinallywoke up, Rover,you")));
    return 0;
}
