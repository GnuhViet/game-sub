import re, unicodedata

WILD = "§"
TAG_RE = re.compile(r"</?[A-Za-z][^<>]{0,60}>")                       # <color=...>, </b>, <br>
GENDER_RE = re.compile(r"\{\s*(?:Male|M)\s*=\s*([^;{}]*?)\s*;\s*(?:Female|F)\s*=\s*([^{}]*?)\s*\}", re.I)
PH_RE = re.compile(r"\{[^{}]{0,40}\}|%[sdf]|\{\d+\}")
QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"', "…": "...", "—": "-", "–": "-", "｜": "|"})
NON_WORD = re.compile(rf"[^\w{WILD}]+", re.U)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")

def resolve(text: str, gender="male", name_tokens=(), player_name="", for_match=False) -> str:
    """Thay macro giới tính, tên người chơi, tag rich-text. for_match=True: placeholder -> WILD."""
    if not text: return ""
    t = TAG_RE.sub("", text).replace("\\n", " ")
    t = GENDER_RE.sub(lambda m: m.group(1) if gender == "male" else m.group(2), t)
    for tok in name_tokens:
        if tok: t = t.replace(tok, WILD if for_match else (player_name or tok))
    if for_match: t = PH_RE.sub(WILD, t)
    return t

def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).translate(QUOTES).lower()
    t = NON_WORD.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()

def ocr_for_match(text: str, player_name="") -> str:
    """Chuẩn hóa text OCR: tên người chơi -> WILD."""
    t = text
    if player_name and len(player_name) > 1:
        t = re.sub(rf"(?<!\w){re.escape(player_name)}(?!\w)", WILD, t, flags=re.I)
    return norm(t)

def join_lines(lines) -> str:
    out = ""
    for l in (x.strip() for x in lines):
        if not l: continue
        if out.endswith("-") and l[:1].islower(): out = out[:-1] + l
        else: out = f"{out} {l}" if out else l
    return re.sub(r"\s+", " ", out).strip()

SENT_RE = re.compile(r"(?<=[.!?…])\s+(?=[\"'A-Z“])")
def split_sentences(text: str):
    return [s for s in SENT_RE.split(text) if s.strip()]

def lemmas(word: str):
    """Ứng viên dạng gốc cho tra từ điển."""
    w = word.lower().strip("'-"); c = [word, w]
    if w.endswith("'s"): c.append(w[:-2])
    if w.endswith("ies") and len(w) > 4: c.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3: c.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3: c.append(w[:-1])
    if w.endswith("ied") and len(w) > 4: c.append(w[:-3] + "y")
    if w.endswith("ed") and len(w) > 3: c += [w[:-2], w[:-1]] + ([w[:-3]] if len(w) > 4 and w[-3] == w[-4] else [])
    if w.endswith("ing") and len(w) > 4: c += [w[:-3], w[:-3] + "e"] + ([w[:-4]] if w[-4] == w[-5] else [])
    if w.endswith("ly") and len(w) > 4: c.append(w[:-2])
    if w.endswith("er") and len(w) > 4: c.append(w[:-2])
    if w.endswith("est") and len(w) > 5: c.append(w[:-3])
    seen, out = set(), []
    for x in c:
        if x and x not in seen: seen.add(x); out.append(x)
    return out
