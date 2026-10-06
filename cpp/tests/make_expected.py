"""Sinh đáp án từ bản Python cho test đối chiếu C++ (tests/core_test.cpp).
Chạy: .venv\\Scripts\\python cpp\\tests\\make_expected.py  -> cpp/tests/expected.json"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from gamesub import textnorm as T
from gamesub.spacing import Spacer
from gamesub.matcher import SubIndex

TEXTS = ["Rover, you finally woke up. Let's head to Jinzhou.", "  Đây là “quote” — và… ‘thử’ ｜ ok  ", "Hello<color=#ff0>World</color>\\nNext",
         "{Male=he;Female=she} went to {PlayerName}'s house", "%s has %d items {0}", "ROVER!!! You're    late", "Ｆｕｌｌｗｉｄｔｈ ＡＢＣ"]
WORDS = ["woke", "running", "studies", "tried", "happiest", "quickly", "Rover's", "stopped", "makes", "glasses", "'quoted'", "-dash-"]
SPACE = ["youfinallywoke", "Rover,you are here.Thanks", "Theyarecomingtowardsus", "Jinzhouisbeautifultoday", "Rovernaut", "abcdefghxyz",
         "Iwanttogohomenow!", "thisisatest of thesystem", "Bigredballoon"]
LINES = [["Dear Rover,", "Thank you for your help in the last", "battle. We could not have won", "without you.", "Sincerely,", "Jiyan"],
         ["The quick brown fox jumps over the", "lazy dog and runs away into the", "forest."], ["hyphen-", "ated word", "next line"]]
SUBS = [("Rover, you finally woke up.", "Rover, cuối cùng anh cũng tỉnh rồi."), ("{PlayerName}, are you okay?", "{PlayerName}, cậu ổn chứ?"),
        ("{Male=He;Female=She} is waiting.", "{Male=Anh ấy;Female=Cô ấy} đang đợi."), ("Let's head to Jinzhou.", "Đi Jinzhou thôi."),
        ("<color=red>Danger</color> ahead!", "Nguy hiểm phía trước!")]
QUERIES = ["Rover, you finaIly woke up.", "Rover, are you okay?", "He is waiting", "Rover, you finally woke up. Let's head to Jinzhou.",
           "Danger ahead", "Totally unrelated sentence here", "Let's head to Jinzhou"]

sp = Spacer(); sp.set_known(["Jinzhou", "Rover"])
ix = SubIndex(); ix.build(SUBS, "male", ["{PlayerName}"], "Rover")
out = {
    "norm": {t: T.norm(t) for t in TEXTS},
    "resolve": {t: [T.resolve(t, "male", ["{PlayerName}"], "Rover"), T.resolve(t, "female", ["{PlayerName}"], "Rover", True)] for t in TEXTS},
    "ocr_for_match": {t: T.ocr_for_match(t, "Rover") for t in TEXTS},
    "lemmas": {w: T.lemmas(w) for w in WORDS},
    "spacing": {s: sp.fix(s) for s in SPACE},
    "join_lines": [[l, T.join_lines(l)] for l in LINES],
    "paragraphs": [[l, T.paragraphs(l)] for l in LINES],
    "sentences": {t: T.split_sentences(t) for t in TEXTS},
    "subs": SUBS, "match": {q: (lambda m: [m.vi, round(m.score, 3), m.src] if m else None)(ix.match(q, 86)) for q in QUERIES},
}
p = pathlib.Path(__file__).with_name("expected.json"); p.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
print("ok", p)
