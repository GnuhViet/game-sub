import sys
if __name__ == "__main__":
    if "--diag" in sys.argv:                 # WuWaSub.exe --diag -> data/diag.txt
        import diag; diag.main()
    else:
        from wuwasub.app import main; main()
