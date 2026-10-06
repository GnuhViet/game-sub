"""Kiểm tra đa ngôn ngữ (python tools/i18n_check.py [--todo]):
- key dùng trong code (tr("key") / N_("key") / nhãn truyền vào hàm dựng form của Cài đặt; cả tx("key") của bản C++ cpp/src) phải có trong locales/vi.json
- mọi file locales/<mã>.json đủ key như vi.json, biến {…} khớp; key thừa / không còn dùng -> cảnh báo
- --todo: liệt kê chuỗi tiếng Việt còn viết thẳng trong code (bỏ docstring, log, dòng có ghi chú no-i18n)."""
import ast, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "gamesub"
LOC = PKG / "locales"
VI = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.I)
SKIP_FILES = {"config.py", "i18n.py"}           # prompt mặc định gửi AI / module i18n
SKIP_NAMES = {"DEFAULT_PROMPT", "EXPLAIN_PROMPT", "IMAGE_PROMPT", "LANGS"}
HELPERS = {"_tab", "_group", "_line", "_spin", "_dspin", "_check", "_combo", "_color", "_tip"}   # ui_dialogs: tự tr() nhãn bên trong
VARS = re.compile(r"(?<!{){(\w*)}(?!})")

def _docstrings(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str): out.add(id(b.value))
    return out

def _str(n): return isinstance(n, ast.Constant) and isinstance(n.value, str)

def scan():
    """-> (key dùng trong code {key: [vị trí]}, chuỗi tiếng Việt viết thẳng [(vị trí, text)])."""
    used, todo = {}, []
    for p in sorted(PKG.rglob("*.py")):
        src = p.read_text(encoding="utf-8"); lines = src.splitlines()
        tree = ast.parse(src); docs = _docstrings(tree); inside = set(); skip = set()
        def use(node):
            used.setdefault(node.value, []).append(f"{p.name}:{node.lineno}"); inside.add(id(node))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("tr", "N_") and n.args and _str(n.args[0]): use(n.args[0])
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in HELPERS:
                if n.func.attr in ("_tab", "_group"):
                    if len(n.args) > 1 and _str(n.args[1]): use(n.args[1])
                    continue
                for arg in n.args[2:]:
                    if _str(arg): use(arg)
                    elif isinstance(arg, ast.Dict):
                        for v in arg.values:
                            if _str(v): use(v)
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in SKIP_NAMES for t in n.targets):
                for m in ast.walk(n.value): skip.add(id(m))
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) in ("print", "log"):
                for m in ast.walk(n): skip.add(id(m))             # log ra console / file chẩn đoán
        if p.name in SKIP_FILES: continue
        for n in ast.walk(tree):
            if id(n) in inside or id(n) in docs or id(n) in skip: continue
            if hasattr(n, "lineno") and "no-i18n" in lines[n.lineno - 1]: continue    # dữ liệu / prompt AI, không phải giao diện
            if _str(n) and VI.search(n.value): todo.append((f"{p.relative_to(ROOT)}:{n.lineno}", n.value))
            elif isinstance(n, ast.JoinedStr) and any(_str(v) and VI.search(v.value) for v in n.values):
                todo.append((f"{p.relative_to(ROOT)}:{n.lineno}", "f-string"))
                for m in ast.walk(n): inside.add(id(m))
    return used, todo

CPP = ROOT / "cpp" / "src"
CPP_KEY = re.compile(r'"((?:app|tray|toolbar|overlay|popup|settings|glossary|vocab|review|subs|keycap|scan|region|ocr|engines|dict|translator|lang)\.[A-Za-z0-9_.\-]+)"')

FILE_EXT = re.compile(r"\.(h|cpp|csv|tsv|png|json|txt|db|exe|dll|qz|ttf|ico)$")

def scan_cpp():
    """Key dùng trong bản C++ (cpp/src/*.cpp): mọi chuỗi có dạng key i18n."""
    used = {}
    for p in sorted(CPP.glob("*.cpp")) if CPP.is_dir() else []:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#include"): continue
            for k in CPP_KEY.findall(line):
                if FILE_EXT.search(k): continue                              # tên file (glossary.csv, ocr.png…), không phải key
                if not k.startswith("settings.ocr.tip.") or k.count(".") > 3: used.setdefault(k, []).append(f"cpp/{p.name}:{n}")
            if 'QString("settings.ocr.tip.") + k' in line:                 # key ghép: settings.ocr.tip.<cfg>
                for k in ("ocr_engine", "ocr_lang", "ocr_scale", "interval_ms", "stable_ms", "diff_threshold", "dedupe_ratio", "clear_on_empty", "fix_spacing"):
                    used.setdefault("settings.ocr.tip." + k, []).append(f"cpp/{p.name}:{n}")
    return used

def load(code): return json.loads((LOC / f"{code}.json").read_text(encoding="utf-8"))

def check():
    """-> (lỗi, cảnh báo)."""
    used, _ = scan(); errs, warns = [], []
    for k, where in scan_cpp().items(): used.setdefault(k, []).extend(where)          # bản C++ dùng chung locales
    base = {k: v for k, v in load("vi").items() if k != "_name"}
    for k, where in used.items():
        if k not in base: errs.append(f"[vi] thiếu key ({where[0]}): {k!r}")
    for k in base:
        if k not in used: warns.append(f"[vi] key không còn dùng: {k!r}")
    for p in sorted(LOC.glob("*.json")):
        if p.stem == "vi": continue
        try: T = load(p.stem)
        except ValueError as e: errs.append(f"[{p.stem}] JSON lỗi: {e}"); continue
        if "_name" not in T: errs.append(f"[{p.stem}] thiếu \"_name\" (tên hiển thị của ngôn ngữ)")
        for k, v in base.items():
            if k not in T: errs.append(f"[{p.stem}] thiếu key: {k!r}")
            elif set(VARS.findall(v)) != set(VARS.findall(T[k])): errs.append(f"[{p.stem}] biến {{…}} không khớp vi.json: {k!r}")
        for k in T:
            if k != "_name" and k not in base: warns.append(f"[{p.stem}] key thừa (không có trong vi.json): {k!r}")
    return errs, warns

if __name__ == "__main__":
    if "--todo" in sys.argv:
        for where, s in scan()[1]: print(where, s[:100].replace("\n", "\\n"))
    else:
        errs, warns = check(); print("\n".join(warns + errs) or "OK"); sys.exit(1 if errs else 0)
