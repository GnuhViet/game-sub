import sqlite3, threading, re, csv
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS subs(id INTEGER PRIMARY KEY, file TEXT, src TEXT NOT NULL, vi TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_subs_file ON subs(file);
CREATE TABLE IF NOT EXISTS glossary(term TEXT PRIMARY KEY COLLATE NOCASE, vi TEXT DEFAULT '', mode TEXT DEFAULT 'keep', note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS vocab(word TEXT PRIMARY KEY COLLATE NOCASE, meaning TEXT DEFAULT '', sentence TEXT DEFAULT '',
  sentence_vi TEXT DEFAULT '', added TEXT, reviews INTEGER DEFAULT 0, last_review TEXT);
CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, v TEXT);
"""

class DB:
    def __init__(self, path):
        self.lock = threading.RLock(); self.path = path
        self.c = sqlite3.connect(str(path), check_same_thread=False)
        self.c.execute("PRAGMA journal_mode=WAL"); self.c.execute("PRAGMA synchronous=NORMAL")   # ít fsync khi lưu cache tra từ
        self.c.executescript(SCHEMA); self.c.commit()
        self._gl_cache = None

    def q(self, sql, args=()):
        with self.lock: return self.c.execute(sql, args).fetchall()

    def x(self, sql, args=(), many=False):
        with self.lock:
            (self.c.executemany if many else self.c.execute)(sql, args); self.c.commit()

    # ---- subs
    def add_subs(self, file, pairs):
        self.x("DELETE FROM subs WHERE file=?", (file,))
        self.x("INSERT INTO subs(file,src,vi) VALUES(?,?,?)", [(file, s, v) for s, v in pairs], many=True)

    def sub_files(self): return self.q("SELECT file, COUNT(*) FROM subs GROUP BY file ORDER BY MIN(id)")
    def del_sub_file(self, file): self.x("DELETE FROM subs WHERE file=?", (file,))
    def all_subs(self): return self.q("SELECT src, vi FROM subs ORDER BY id")

    def reader(self):
        """Kết nối chỉ đọc riêng (WAL cho đọc song song): xem / tìm bộ sub không giữ self.lock của luồng khớp câu."""
        from pathlib import Path
        return sqlite3.connect(Path(self.path).resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)

    # ---- glossary
    def glossary(self):
        if self._gl_cache is None:
            self._gl_cache = [dict(term=t, vi=v, mode=m, note=n) for t, v, m, n in
                              self.q("SELECT term,vi,mode,note FROM glossary ORDER BY length(term) DESC")]
        return self._gl_cache

    def set_term(self, term, vi="", mode="keep", note=""):
        self.x("INSERT OR REPLACE INTO glossary(term,vi,mode,note) VALUES(?,?,?,?)", (term.strip(), vi.strip(), mode, note))
        self._gl_cache = None

    def del_term(self, term): self.x("DELETE FROM glossary WHERE term=?", (term,)); self._gl_cache = None

    def terms_in(self, text):
        """Các mục glossary xuất hiện trong text (khớp nguyên từ, không phân biệt hoa thường)."""
        out = []
        for g in self.glossary():
            if re.search(rf"(?<!\w){re.escape(g['term'])}(?!\w)", text, re.I): out.append(g)
        return out

    # ---- vocab
    def add_vocab(self, word, meaning="", sentence="", sentence_vi=""):
        self.x("""INSERT INTO vocab(word,meaning,sentence,sentence_vi,added) VALUES(?,?,?,?,?)
                  ON CONFLICT(word) DO UPDATE SET meaning=COALESCE(NULLIF(excluded.meaning,''),meaning),
                  sentence=COALESCE(NULLIF(excluded.sentence,''),sentence), sentence_vi=COALESCE(NULLIF(excluded.sentence_vi,''),sentence_vi)""",
               (word.strip(), meaning, sentence, sentence_vi, datetime.now().strftime("%Y-%m-%d %H:%M")))

    def vocab(self): return self.q("SELECT word,meaning,sentence,sentence_vi,added,reviews FROM vocab ORDER BY added DESC")
    def has_vocab(self, word): return bool(self.q("SELECT 1 FROM vocab WHERE word=?", (word,)))
    def del_vocab(self, word): self.x("DELETE FROM vocab WHERE word=?", (word,))
    def reviewed(self, word):
        self.x("UPDATE vocab SET reviews=reviews+1, last_review=? WHERE word=?", (datetime.now().strftime("%Y-%m-%d %H:%M"), word))

    # ---- cache (giải nghĩa LLM/online)
    def cache_get(self, k):
        r = self.q("SELECT v FROM cache WHERE k=?", (k,)); return r[0][0] if r else None
    def cache_set(self, k, v): self.x("INSERT OR REPLACE INTO cache(k,v) VALUES(?,?)", (k, v))

    # ---- CSV
    def export_csv(self, table, path):
        cols = {"glossary": "term,vi,mode,note", "vocab": "word,meaning,sentence,sentence_vi,added,reviews"}[table]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(cols.split(",")); w.writerows(self.q(f"SELECT {cols} FROM {table}"))

    def import_glossary_csv(self, path):
        n = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t = (r.get("term") or "").strip()
                if t: self.set_term(t, r.get("vi", ""), r.get("mode") or ("translate" if r.get("vi") else "keep"), r.get("note", "")); n += 1
        return n
