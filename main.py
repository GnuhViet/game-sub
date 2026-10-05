import sys
from wuwasub import engines
if __name__ == "__main__":
    engines.setup()                          # OCR engine tải về (engines/py)
    if "--diag" in sys.argv:                 # WuWaSub.exe --diag -> data/diag.txt
        import diag; diag.main()
    else:
        from wuwasub.app import main; main()
