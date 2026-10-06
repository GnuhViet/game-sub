"""Kiểm tra đa ngôn ngữ (python tools/i18n_check.py [--todo]):
- chuỗi trong tr("…") / N_("…") chưa có bản dịch ở locales/<mã>.py -> lỗi
- bản dịch thừa (không còn chuỗi gốc) -> cảnh báo
- --todo: liệt kê chuỗi tiếng Việt chưa bọc tr()/N_() (bỏ docstring, chuỗi trong SKIP, dòng có ghi chú no-i18n)."""
import ast, importlib, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "gamesub"
VI = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.I)
SKIP_FILES = {"config.py"}                      # prompt mặc định gửi AI, không phải giao diện
SKIP_NAMES = {"DEFAULT_PROMPT", "EXPLAIN_PROMPT", "IMAGE_PROMPT", "LANGS"}
HELPERS = {"_tab", "_group", "_line", "_spin", "_dspin", "_check", "_combo", "_color", "_tip"}   # ui_dialogs: tự tr() nhãn bên trong

def _docstrings(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str): out.add(id(b.value))
    return out

def scan():
    """-> (chuỗi đã đánh dấu {text: [vị trí]}, chuỗi tiếng Việt chưa bọc [(vị trí, text)])."""
    marked, todo = {}, []
    for p in sorted(PKG.rglob("*.py")):
        if "locales" in p.parts: continue
        src = p.read_text(encoding="utf-8"); lines = src.splitlines()
        tree = ast.parse(src); docs = _docstrings(tree); inside = set(); skip = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("tr", "N_") and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str): marked.setdefault(a.value, []).append(f"{p.name}:{a.lineno}")
                for m in ast.walk(a): inside.add(id(m))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in HELPERS:
                for arg in n.args[2:]:                                  # (f, key/field, nhãn, …) — bỏ 2 tham số đầu
                    for m in ast.walk(arg):
                        if isinstance(m, ast.Constant) and isinstance(m.value, str) and VI.search(m.value) or (n.func.attr in ("_tab", "_group") and isinstance(m, ast.Constant) and isinstance(m.value, str)):
                            marked.setdefault(m.value, []).append(f"{p.name}:{m.lineno}"); inside.add(id(m))
                if n.func.attr in ("_tab", "_group") and len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                    marked.setdefault(n.args[1].value, []).append(f"{p.name}:{n.args[1].lineno}"); inside.add(id(n.args[1]))
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in SKIP_NAMES for t in n.targets):
                for m in ast.walk(n.value): skip.add(id(m))
            if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute)) and getattr(n.func, "id", getattr(n.func, "attr", "")) in ("print", "log"):
                for m in ast.walk(n): skip.add(id(m))             # log ra console / file chẩn đoán
        if p.name in SKIP_FILES: continue
        for n in ast.walk(tree):
            if id(n) in inside or id(n) in docs or id(n) in skip: continue
            if hasattr(n, "lineno") and "no-i18n" in lines[n.lineno - 1]: continue    # dữ liệu / prompt AI, không phải giao diện
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and VI.search(n.value): todo.append((f"{p.relative_to(ROOT)}:{n.lineno}", n.value))
            elif isinstance(n, ast.JoinedStr) and any(isinstance(v, ast.Constant) and VI.search(str(v.value)) for v in n.values):
                todo.append((f"{p.relative_to(ROOT)}:{n.lineno}", "f-string"))
                for m in ast.walk(n): inside.add(id(m))
    return marked, todo

def check():
    """-> list lỗi (chuỗi thiếu bản dịch) cho mọi ngôn ngữ khác vi."""
    sys.path.insert(0, str(ROOT))
    from gamesub.i18n import LANGS
    marked, _ = scan(); errs = []
    for code in LANGS:
        if code == "vi": continue
        T = importlib.import_module("gamesub.locales").TABLES[code]
        for s, where in marked.items():
            if s not in T: errs.append(f"[{code}] thiếu bản dịch ({where[0]}): {s!r}")
            elif set(re.findall(r"{(\w*)}", s)) != set(re.findall(r"{(\w*)}", T[s])): errs.append(f"[{code}] biến {{…}} không khớp ({where[0]}): {s!r}")
        for s in T:
            if s not in marked: print(f"[{code}] bản dịch thừa: {s!r}")
    return errs

if __name__ == "__main__":
    if "--todo" in sys.argv:
        for where, s in scan()[1]: print(where, s[:100].replace("\n", "\\n"))
    else:
        errs = check(); print("\n".join(errs) or "OK"); sys.exit(1 if errs else 0)
