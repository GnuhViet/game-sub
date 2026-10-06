"""Tách từ bị OCR dính liền ("youfinallywoke" -> "you finally woke") bằng tần suất từ tiếng Anh (wordninja).
Bảo thủ: không đụng từ có thật, tên trong glossary / bộ sub, và không tách nếu ra mảnh lạ."""
import re

TOKEN_RE = re.compile(r"[A-Za-z]{6,}")
PUNCT_RE = re.compile(r"([,!?;:]|(?<=[a-z])\.)(?=[A-Za-z])")     # "Rover,you" -> "Rover, you"
MAX_COST = 12.5           # cost wordninja ~ log(rank): <=12.5 ≈ từ thông dụng

class Spacer:
    def __init__(self):
        self.lm = None; self.known = set()

    def set_known(self, words): self.known = {w.lower() for w in words if w}

    def _model(self):
        if self.lm is None:
            import wordninja; self.lm = wordninja.DEFAULT_LANGUAGE_MODEL
        return self.lm

    def fix(self, text):
        try: lm = self._model()
        except ImportError: return text
        text = PUNCT_RE.sub(r"\1 ", text)
        return TOKEN_RE.sub(lambda m: self._split(m.group(), lm), text)

    def _split(self, tok, lm):
        lo = tok.lower(); cost = lm._wordcost
        if lo in cost or lo in self.known: return tok
        parts = lm.split(lo)
        if len(parts) < 2 or any(len(p) == 1 and p not in ("a", "i") for p in parts) or any(cost.get(p, 99) > MAX_COST for p in parts):
            return tok
        if tok[0].isupper() and len(parts) < 3 and len(tok) < 10: return tok            # nhiều khả năng là tên riêng
        out, i = [], 0
        for p in parts: out.append(tok[i:i + len(p)]); i += len(p)                       # giữ nguyên hoa/thường gốc
        return " ".join(out)
