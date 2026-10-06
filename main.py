import sys
from gamesub import engines
if __name__ == "__main__":
    engines.setup()                          # OCR engine tải về (engines/py)
    if "--diag" in sys.argv:                 # GameSub.exe --diag -> data/diag.txt
        import diag; diag.main()
    else:
        from gamesub import i18n; from gamesub.config import Config
        i18n.set_lang(Config()["ui_lang"])   # trước khi import giao diện (chuỗi ở mức module cũng được dịch)
        from gamesub.app import main; main()
