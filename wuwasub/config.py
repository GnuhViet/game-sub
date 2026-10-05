import json, sys, copy
from pathlib import Path

def app_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

DATA_DIR = app_dir() / "data"
CFG_PATH = DATA_DIR / "settings.json"

DEFAULT_PROMPT = """Bạn là người dịch thoại game Wuthering Waves từ {src_lang} sang tiếng Việt.
- Văn phong tự nhiên, đúng xưng hô theo quan hệ nhân vật và ngữ cảnh các câu trước.
- Nhân vật chính: {player} ({gender}), xưng "tôi".
- {keep_rule}
- Chỉ trả về bản dịch của câu cần dịch, không giải thích, không ngoặc kép.
{glossary}"""

EXPLAIN_PROMPT = """Giải nghĩa ngắn gọn bằng tiếng Việt cho "{word}" trong câu: "{sentence}".
Định dạng:
/IPA/ (loại từ) nghĩa trong câu này
• Nghĩa phổ biến khác (nếu có, tối đa 2)
• Ví dụ ngắn kèm dịch"""

DEFAULTS = {
    "region": None, "speaker_region": None,          # {"x","y","w","h"} physical px
    "ocr_engine": "windows", "ocr_lang": "en-US", "ocr_scale": 1.0,
    "interval_ms": 250, "stable_ms": 350, "diff_threshold": 3.0, "dedupe_ratio": 92,
    "src_lang": "tiếng Anh",
    # dịch
    "use_subs": True, "fuzzy_threshold": 86,
    "chain": ["gemini", "google"],                    # thứ tự fallback: gemini/openai/google
    "gemini_key": "", "gemini_model": "gemini-2.5-flash-lite", "gemini_thinking_budget": 0,
    "openai_base": "https://api.deepseek.com/v1", "openai_key": "", "openai_model": "deepseek-chat",
    "stream": True, "context_lines": 4, "prompt": DEFAULT_PROMPT, "explain_prompt": EXPLAIN_PROMPT,
    "keep_terms": True,                               # không dịch tên riêng/thuật ngữ
    "timeout_s": 15, "cooldown_s": 30,
    # nhân vật
    "player_name": "Rover", "gender": "male", "name_tokens": ["{PlayerName}", "{Nickname}", "{PLAYER_NAME}"],
    # từ điển
    "dict_mode": "auto",                              # offline / online / llm / auto
    "dict_files": [], "hover_delay_ms": 250,
    # overlay
    "font_size": 17, "src_font_size": 13, "opacity": 0.82, "show_source": True, "show_speaker": True,
    "auto_hide_s": 0,                                 # tự ẩn khi hết thoại sau N giây (0 = tắt)
    "click_through": False,                           # chuột xuyên qua overlay (bật/tắt bằng hotkey)
    "overlay_geom": None, "bg": "#101418", "fg": "#f2f2f2", "src_fg": "#9fb3c8", "accent": "#e8c26a",
    "hotkeys": {"toggle": "Alt+T", "region": "Alt+R", "pause": "Alt+P", "rescan": "Alt+S", "clickthrough": "Alt+C"},
}

class Config(dict):
    def __init__(self, path=None):
        super().__init__(copy.deepcopy(DEFAULTS)); self.path = Path(path or CFG_PATH)
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
                for k, v in data.items():
                    if k == "hotkeys" and isinstance(v, dict): self[k].update(v)
                    elif k in DEFAULTS: self[k] = v
            except Exception as e: print("settings.json lỗi, dùng mặc định:", e)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self, ensure_ascii=False, indent=2), "utf-8")
