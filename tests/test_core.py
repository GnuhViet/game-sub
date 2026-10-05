import json, struct, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from wuwasub.textnorm import resolve, norm, join_lines, lemmas, split_sentences
from wuwasub.matcher import SubIndex
from wuwasub import importer
from wuwasub.db import DB
from wuwasub.dictionary import Dictionaries
from wuwasub.translator import Translator
from wuwasub.config import Config

T = Path(tempfile.mkdtemp())
PAIRS = [
    ("Rover, you finally woke up.", "Rover, cuối cùng anh cũng tỉnh rồi."),
    ("{PlayerName}, do you remember anything?", "{PlayerName}, anh còn nhớ gì không?"),
    ("{Male=He;Female=She} is the Rover we were looking for.", "{Male=Anh ấy;Female=Cô ấy} chính là Rover chúng ta đang tìm."),
    ("The <color=#ffcc00>Tacet Discord</color> is coming!", "<color=#ffcc00>Tacet Discord</color> đang tới!"),
    ("Let's go to Jinzhou.", "Đi tới Jinzhou thôi."),
    ("Be careful.", "Cẩn thận đấy."),
] + [(f"Filler line number {i} about Resonators and Echoes.", f"Câu đệm số {i}.") for i in range(3000)]

def test_norm_resolve():
    assert norm("“Hello”, Rover…") == "hello rover"
    assert resolve("{Male=He;Female=She} came", "female") == "She came"
    assert "§" in resolve("{PlayerName} hi", name_tokens=["{PlayerName}"], for_match=True)
    assert resolve("<color=red>X</color>") == "X"
    assert join_lines(["Hello wor-", "ld and", "more"]) == "Hello world and more"
    assert "walk" in lemmas("walking") and "study" in lemmas("studies") and "stop" in lemmas("stopped")
    assert split_sentences("Hi. Who are you? I'm Rover.") == ["Hi.", "Who are you?", "I'm Rover."]

def test_matcher():
    ix = SubIndex(); ix.build(PAIRS, "male", ["{PlayerName}"], "Hưng")
    m = ix.match("Rover, you finally woke up."); assert m and m.score == 100 and "tỉnh" in m.vi
    m = ix.match("Rover, y0u finaIly woke up"); assert m and m.score > 86, m          # lỗi OCR
    m = ix.match("Hưng, do you remember anything?"); assert m and m.vi.startswith("Hưng,"), m   # tên người chơi
    m = ix.match("He is the Rover we were looking for."); assert m and m.vi.startswith("Anh ấy"), m
    ix.build(PAIRS, "female", ["{PlayerName}"], "Hưng")
    assert ix.match("She is the Rover we were looking for.").vi.startswith("Cô ấy")
    m = ix.match("The Tacet Discord is coming!"); assert m and m.vi == "Tacet Discord đang tới!", m
    m = ix.match("Let's go to Jinzhou. Be careful."); assert m and m.vi == "Đi tới Jinzhou thôi. Cẩn thận đấy.", m   # gộp 2 câu
    assert ix.match("Completely unrelated sentence here.") is None

def test_importer():
    (T / "a.csv").write_text("id,english,vietnamese\n1,Hello there,Xin chào\n2,Be careful.,Cẩn thận đấy.\n", "utf-8")
    h, r = importer.read_table(T / "a.csv"); s, v = importer.guess_cols(h, r)
    assert (h[s], h[v]) == ("english", "vietnamese") and importer.extract_pairs(r, s, v)[0] == ("Hello there", "Xin chào")
    (T / "b.tsv").write_text("Hello there\tXin chào bạn\nGood night\tChúc ngủ ngon\n", "utf-8")
    h, r = importer.read_table(T / "b.tsv"); s, v = importer.guess_cols(h, r); assert len(r) == 2 and r[0][v] == "Xin chào bạn"
    (T / "c.json").write_text(json.dumps({"k1": {"en": "Hello", "vi": "Chào"}, "k2": {"en": "Bye", "vi": "Tạm biệt"}}, ensure_ascii=False), "utf-8")
    h, r = importer.read_table(T / "c.json"); s, v = importer.guess_cols(h, r); assert importer.extract_pairs(r, s, v) == [("Hello", "Chào"), ("Bye", "Tạm biệt")]
    import openpyxl; wb = openpyxl.Workbook(); ws = wb.active; ws.append(["Source", "Dịch"]); ws.append(["Run!", "Chạy đi!"]); wb.save(T / "d.xlsx")
    h, r = importer.read_table(T / "d.xlsx"); s, v = importer.guess_cols(h, r); assert importer.extract_pairs(r, s, v) == [("Run!", "Chạy đi!")]
    (T / "e.csv").write_bytes("en;vi\nYes;Vâng\n".encode("utf-16"))
    h, r = importer.read_table(T / "e.csv"); assert r == [["Yes", "Vâng"]]

def test_db_glossary_vocab():
    db = DB(T / "t.db"); db.add_subs("f.csv", PAIRS[:5]); assert db.sub_files() == [("f.csv", 5)]
    db.set_term("Tacet Discord", "", "keep"); db.set_term("Resonator", "Cộng Minh Giả", "translate")
    assert [g["term"] for g in db.terms_in("A resonator fights the Tacet Discord")] == ["Tacet Discord", "Resonator"]
    db.add_vocab("echo", "tiếng vang", "Use your Echo.", "Dùng Echo đi."); db.add_vocab("echo", "", "", "")
    assert db.vocab()[0][1] == "tiếng vang" and db.has_vocab("ECHO")
    db.export_csv("glossary", T / "g.csv"); db.del_term("Resonator"); assert db.import_glossary_csv(T / "g.csv") == 2
    return db

def test_translator_prompt_and_protect():
    db = test_db_glossary_vocab(); cfg = Config(T / "s.json"); tr = Translator(cfg, db)
    cfg["keep_terms"] = False
    sp = tr.system_prompt("The Resonator meets the Tacet Discord")
    assert '"Resonator" → "Cộng Minh Giả"' in sp and '"Tacet Discord": giữ nguyên' in sp
    cfg["keep_terms"] = True; assert '"Resonator": giữ nguyên' in tr.system_prompt("The Resonator")
    up = tr.user_prompt("Run!", "Chixia", [("Yangyang", "Hi.", "Chào.")]); assert "Yangyang: Hi." in up and up.endswith("Chixia: Run!")
    t, mp = tr._protect("The Tacet Discord attacks a resonator."); assert "⟦0⟧" in t and "⟦1⟧" in t
    assert tr._restore("⟦ 0 ⟧ tấn công ⟦1⟧.", mp) == "Tacet Discord tấn công Resonator."
    cfg["keep_terms"] = False; t, mp = tr._protect("a resonator"); assert tr._restore(t.replace("a ", "một "), mp) == "một Cộng Minh Giả"

def test_dictionaries():
    (T / "d.tsv").write_text("run\tchạy\necho\ttiếng vang\n", "utf-8")
    # StarDict tối thiểu
    words = [("apple", b"qu\xe1\xba\xa3 t\xc3\xa1o"), ("go", b"\xc4\x91i")]; data, idx = b"", b""
    for w, m in words: idx += w.encode() + b"\0" + struct.pack(">II", len(data), len(m)); data += m
    (T / "sd.idx").write_bytes(idx); (T / "sd.dict").write_bytes(data)
    (T / "sd.ifo").write_text(f"StarDict's dict ifo file\nversion=2.4.2\nbookname=Test AV\nwordcount=2\nidxfilesize={len(idx)}\nsametypesequence=m\n", "utf-8")
    d = Dictionaries().load([T / "d.tsv", T / "sd.ifo", T / "missing.ifo"])
    assert d.lookup("running")[0] == "run" and d.lookup("Apples") == ("apple", "quả táo") and d.lookup("going")[1] == "đi"
    assert len(d.errors) == 1 and d.lookup("zzz") is None

def test_spacing():
    from wuwasub.spacing import Spacer
    s = Spacer(); s.set_known(["Huanglong"])
    assert s.fix("Rover,youfinallywoke up.") == "Rover, you finally woke up."
    assert s.fix("Letsheadto Jinzhou with Yangyang.") == "Lets head to Jinzhou with Yangyang."    # tên riêng giữ nguyên
    assert s.fix("Huanglong, Tacetdiscord, Resonators, understanding") == "Huanglong, Tacetdiscord, Resonators, understanding"

def test_hotkey_migration():
    import json, tempfile
    from wuwasub.config import Config
    p = Path(tempfile.mkdtemp()) / "s.json"
    p.write_text(json.dumps({"hotkeys": {"toggle": "Alt+T", "pause": "F8", "scan": "Alt+Q"}}), "utf-8")
    hk = Config(p)["hotkeys"]
    assert hk["toggle"] == "Ctrl+Alt+T" and hk["scan"] == "Ctrl+Alt+Q" and hk["pause"] == "F8", hk    # mặc định cũ -> mới, tự đặt giữ nguyên

def test_engine_remove():
    import tempfile, shutil
    from wuwasub import engines as E
    root = Path(tempfile.mkdtemp()); E.ENG_DIR, E.PY_DIR, E.TESS_DIR, E.PENDING = root, root / "py", root / "tesseract", root / "pending_remove.txt"
    (E.PY_DIR / "rapidocr_onnxruntime").mkdir(parents=True); (E.PY_DIR / "rapidocr_onnxruntime" / "m.onnx").write_bytes(b"x" * 2_000_000)
    assert E.has_rapidocr() and 1.9 < E.size_mb("rapidocr") < 2.1
    assert E.remove("rapidocr") is True and not E.has_rapidocr()
    (E.TESS_DIR).mkdir(); (E.TESS_DIR / "tesseract.exe").write_bytes(b"x")
    real = shutil.rmtree; E.shutil.rmtree = lambda *a, **k: None          # giả lập file đang bị khóa
    try: assert E.remove("tesseract") is False and E.pending() == {"tesseract"}
    finally: E.shutil.rmtree = real
    E.setup(); assert not E.TESS_DIR.exists() and not E.PENDING.exists()   # khởi động lại -> xóa hẳn

def test_paragraphs():
    from wuwasub.textnorm import paragraphs
    L = ["Dear Rover,", "I hope this letter finds you well. The Black Shores have", "been quiet since the incident, but I fear the",
         "calm will not last.", "Yours,", "Jinhsi"]
    assert paragraphs(L).split("\n") == ["Dear Rover,", "I hope this letter finds you well. The Black Shores have been quiet since the incident, but I fear the calm will not last.", "Yours,", "Jinhsi"]

def test_pick_model():
    from wuwasub.translator import Translator as T
    assert T.pick_model(["gemini-3.1-pro", "gemini-3.1-flash-lite-preview", "gemini-3-flash-lite", "gemini-3-flash"]) == "gemini-3-flash-lite"
    assert T.pick_model(["gemini-2.5-pro", "gemini-2.5-flash"]) == "gemini-2.5-flash" and T.pick_model([]) == ""

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("PASS", n)
