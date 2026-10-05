"""Từ điển offline (StarDict / TSV / CSV / JSON) + online (dictionaryapi.dev, Anh-Anh)."""
import csv, gzip, html, json, struct, re
from pathlib import Path
import requests
from . import net
from .textnorm import lemmas

class StarDict:
    def __init__(self, ifo: Path):
        info = dict(l.split("=", 1) for l in ifo.read_text("utf-8", errors="ignore").splitlines() if "=" in l)
        self.name = info.get("bookname", ifo.stem); self.sts = info.get("sametypesequence", "")
        bits = 64 if info.get("idxoffsetbits") == "64" else 32
        base = ifo.with_suffix("")
        idx = next((p for p in (Path(f"{base}.idx"), Path(f"{base}.idx.gz")) if p.exists()), None)
        if not idx: raise FileNotFoundError(f"Thiếu file .idx cho {ifo.name}")
        raw = gzip.decompress(idx.read_bytes()) if idx.suffix == ".gz" else idx.read_bytes()
        dz, dc = Path(f"{base}.dict.dz"), Path(f"{base}.dict")
        self.data = gzip.decompress(dz.read_bytes()) if dz.exists() else dc.read_bytes()
        fmt, step = (">QI", 12) if bits == 64 else (">II", 8)
        self.index, i = {}, 0
        while i < len(raw):
            j = raw.index(b"\0", i); w = raw[i:j].decode("utf-8", "ignore").lower()
            off, size = struct.unpack_from(fmt, raw, j + 1); i = j + 1 + step
            self.index.setdefault(w, (off, size))

    def get(self, w):
        e = self.index.get(w.lower())
        if not e: return None
        b = self.data[e[0]:e[0] + e[1]]
        if len(self.sts) == 1: return _fmt(self.sts, b.decode("utf-8", "ignore"))
        out, i, types = [], 0, list(self.sts)            # nhiều field: (type char) + data\0
        while i < len(b):
            if self.sts:
                if not types: break
                t = types.pop(0)
            else: t = chr(b[i]); i += 1
            if self.sts and not types: seg, i = b[i:], len(b)   # field cuối không có \0
            else:
                j = b.find(b"\0", i); j = len(b) if j < 0 else j; seg, i = b[i:j], j + 1
            out.append(_fmt(t, seg.decode("utf-8", "ignore")))
        return "<br>".join(x for x in out if x)

def _fmt(t, s):
    if t in "hg": return s
    if t == "x": return re.sub(r"<[^>]+>", "", s).replace("\n", "<br>")
    return html.escape(s).replace("\n", "<br>")

class TableDict:
    def __init__(self, p: Path):
        self.name, self.index = p.stem, {}
        if p.suffix.lower() == ".json":
            d = json.loads(p.read_text("utf-8-sig"))
            items = d.items() if isinstance(d, dict) else ((r.get("word"), r.get("meaning")) for r in d)
        else:
            text = p.read_text("utf-8-sig", errors="ignore")
            delim = "\t" if "\t" in text[:5000] else ","
            items = ((r[0], r[1]) for r in csv.reader(text.splitlines(), delimiter=delim) if len(r) >= 2)
        for w, m in items:
            if w and m: self.index.setdefault(str(w).strip().lower(), str(m))
    def get(self, w):
        m = self.index.get(w.lower()); return html.escape(m).replace("\\n", "<br>").replace("\n", "<br>") if m else None

class Dictionaries:
    def __init__(self): self.dicts, self.errors = [], []

    def load(self, files):
        self.dicts, self.errors = [], []
        for f in files:
            p = Path(f)
            try: self.dicts.append(StarDict(p) if p.suffix.lower() == ".ifo" else TableDict(p))
            except Exception as e: self.errors.append(f"{p.name}: {e}")
        return self

    def lookup(self, word):
        """-> (headword, html) hoặc None."""
        for cand in lemmas(word):
            parts = [(d.name, m) for d in self.dicts if (m := d.get(cand))]
            if parts:
                body = "".join(f"<div style='margin-top:4px'><i style='opacity:.6'>{html.escape(n)}</i><br>{m}</div>" for n, m in parts) if len(parts) > 1 else parts[0][1]
                return cand, body
        return None

LANGS = {"vi": "Tiếng Việt", "en": "English", "ja": "日本語", "zh-CN": "中文 (简)", "zh-TW": "中文 (繁)", "ko": "한국어",
         "fr": "Français", "de": "Deutsch", "es": "Español", "ru": "Русский", "th": "ไทย", "id": "Indonesia"}

def google_lookup(word, tl="vi", timeout=6):
    """Google Translate (gtx, free): nghĩa chính + phiên âm + nghĩa theo từ loại. -> (nghĩa chính, html) | None"""
    r = net.session().get("https://translate.googleapis.com/translate_a/single", timeout=timeout,
                     params=[("client", "gtx"), ("sl", "auto"), ("tl", tl), ("dt", "t"), ("dt", "bd"), ("dt", "rm"), ("q", word)])
    r.raise_for_status(); d = r.json()
    main = "".join(s[0] for s in (d[0] or []) if s and s[0]).strip()
    ph = next((s[3] for s in (d[0] or []) if s and len(s) > 3 and s[3]), "")
    out = [f"<b style='font-size:15px'>{html.escape(main)}</b>" + (f" &nbsp;<span style='opacity:.65'>/{html.escape(ph)}/</span>" if ph else "")]
    for pos in (d[1] or [])[:4] if len(d) > 1 else []:
        out.append(f"<i>{html.escape(pos[0])}</i>: " + ", ".join(html.escape(w) for w in pos[1][:6]))
    return (main, "<br>".join(out)) if main else None

def online_lookup(word, timeout=6):
    for cand in lemmas(word)[1:3] or [word]:
        r = net.session().get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{requests.utils.quote(cand)}", timeout=timeout)
        if r.status_code != 200: continue
        e = r.json()[0]; ph = e.get("phonetic") or next((p.get("text") for p in e.get("phonetics", []) if p.get("text")), "")
        out = [f"<b>{html.escape(e.get('word', cand))}</b> {html.escape(ph or '')}"]
        for m in e.get("meanings", [])[:3]:
            out.append(f"<i>{html.escape(m.get('partOfSpeech', ''))}</i>")
            for d in m.get("definitions", [])[:2]:
                out.append("• " + html.escape(d.get("definition", "")) + (f"<br>&nbsp;&nbsp;<span style='opacity:.65'>e.g. {html.escape(d['example'])}</span>" if d.get("example") else ""))
        return cand, "<br>".join(out)
    return None
