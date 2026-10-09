"""Tra câu OCR trong bộ sub: exact -> fuzzy (lọc theo độ dài) -> tách câu."""
import bisect
from dataclasses import dataclass
from rapidfuzz import fuzz, process
from .textnorm import resolve, norm, ocr_for_match, split_sentences

@dataclass
class Match:
    vi: str; score: float; src: str

class SubIndex:
    def __init__(self): self.exact, self.by_len, self.lens, self.items = {}, [], [], []

    def build(self, pairs, gender="male", name_tokens=(), player_name=""):
        self.cfg = (gender, tuple(name_tokens), player_name)
        exact, items = {}, []
        for src, vi in pairs:
            k = norm(resolve(src, gender, name_tokens, for_match=True))
            if not k: continue
            v = resolve(vi, gender, name_tokens, player_name)
            exact[k] = (v, src)                                   # bản import sau ghi đè
            items.append((len(k), k, v, src))
        items.sort(key=lambda x: x[0])
        self.exact, self.items = exact, items
        self.lens = [x[0] for x in items]; self.keys = [x[1] for x in items]
        return len(exact)

    def __len__(self): return len(self.exact)

    def _one(self, q, th):
        if not q: return None
        if q in self.exact: v, s = self.exact[q]; return Match(v, 100.0, s)
        lo = bisect.bisect_left(self.lens, int(len(q) * 0.7)); hi = bisect.bisect_right(self.lens, int(len(q) * 1.3) + 2)
        if lo >= hi: return None
        r = process.extractOne(q, self.keys[lo:hi], scorer=fuzz.ratio, score_cutoff=th)
        if not r: return None
        _, score, i = r; _, _, v, s = self.items[lo + i]
        return Match(v, score, s)

    def _best(self, text, th):
        """Thử cả bản thay tên người chơi -> § và bản giữ nguyên (tên trùng chữ thường, vd 'Rover')."""
        qs = dict.fromkeys([ocr_for_match(text, self.cfg[2]), norm(text)])
        return max((m for q in qs if (m := self._one(q, th))), key=lambda m: m.score, default=None)

    def match(self, text, threshold=86):
        if not self.items: return None
        m = self._best(text, threshold)
        if m: return m
        sents = split_sentences(text)                              # màn hình gộp nhiều câu sub
        if len(sents) > 1:
            parts = [self._best(s, threshold) for s in sents]
            if all(parts):
                return Match(" ".join(p.vi for p in parts), min(p.score for p in parts), " ".join(p.src for p in parts))
        return None

    def match_parts(self, text, threshold=86):
        """Vùng chụp (thư, bảng…): khớp từng đoạn, không được thì từng câu.
        -> [[(câu gốc, Match | None), …] mỗi đoạn]; câu không khớp liền nhau gộp 1 phần để dịch máy theo cụm."""
        out = []
        for para in (p.strip() for p in text.split("\n")):
            if not para: continue
            m = self.match(para, threshold) if self.items else None
            if m: out.append([(para, m)]); continue
            row = []
            for s in split_sentences(para):
                m = self._best(s, threshold) if self.items else None
                if not m and row and row[-1][1] is None: row[-1] = (row[-1][0] + " " + s, None)
                else: row.append((s, m))
            out.append(row)
        return out
