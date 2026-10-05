"""Dịch máy: Gemini (AI) / Google free. Mỗi mục đích (thoại, vùng chụp) chọn engine riêng; fallback + cooldown khi 429."""
import base64, json, re, time
import requests
from . import net

SEP = "====="
# engine -> các nhà cung cấp thử lần lượt (thoại: dialog_engine; vùng chụp: scan_engine)
CHAINS = {"google": ["google"], "gemini": ["gemini"], "gemini_google": ["gemini", "google"],
          "ocr_google": ["google"], "ocr_gemini": ["gemini", "google"], "gemini_image": ["google"]}   # gemini_image đọc ảnh lỗi -> OCR + Google

class ProviderError(Exception): pass

GOOGLE_COOLDOWN = 10        # endpoint free chặn tạm theo IP khi gửi dồn dập -> nghỉ ngắn

def google_free(s, text, tl, timeout, cool):
    """Google Translate free: endpoint gtx, bị chặn (429) thì thử endpoint dict-chrome-ex (hạn mức riêng)."""
    r = s.get("https://translate.googleapis.com/translate_a/single",
              params={"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text}, timeout=timeout)
    if r.status_code == 200: return "".join(seg[0] for seg in r.json()[0] if seg and seg[0])
    if r.status_code == 429:
        r = s.get("https://clients5.google.com/translate_a/t", params={"client": "dict-chrome-ex", "sl": "auto", "tl": tl, "q": text}, timeout=timeout)
        if r.status_code == 200:
            d = r.json(); d = d[0] if isinstance(d, list) and d else d
            return d[0] if isinstance(d, list) else str(d)
    if r.status_code == 429:
        cool["google"] = time.time() + GOOGLE_COOLDOWN; raise ProviderError("Google tạm chặn do gửi quá nhiều (429), thử lại sau 10s")
    raise ProviderError(f"Google HTTP {r.status_code}")

class Translator:
    def __init__(self, cfg, db):
        self.cfg, self.db, self.cool = cfg, db, {}
        self.s = net.session()

    # ---------- prompt
    def _glossary_block(self, text):
        terms = self.db.terms_in(text); keep_all = self.cfg["keep_terms"]
        lines = []
        for g in terms:
            if keep_all or g["mode"] == "keep" or not g["vi"]: lines.append(f'- "{g["term"]}": giữ nguyên')
            else: lines.append(f'- "{g["term"]}" → "{g["vi"]}"')
        return ("Bảng thuật ngữ bắt buộc:\n" + "\n".join(lines)) if lines else ""

    def system_prompt(self, text):
        c = self.cfg
        keep = ("Giữ nguyên tiếng Anh mọi tên riêng (nhân vật, địa danh, tổ chức) và thuật ngữ game."
                if c["keep_terms"] else "Tên riêng giữ nguyên; thuật ngữ được phép dịch nghĩa nếu tự nhiên hơn.")
        p = c["prompt"]
        for k, v in {"{src_lang}": c["src_lang"], "{player}": c["player_name"] or "Rover",
                     "{gender}": "nam" if c["gender"] == "male" else "nữ", "{keep_rule}": keep,
                     "{glossary}": self._glossary_block(text)}.items():
            p = p.replace(k, v)
        return p.strip()

    def user_prompt(self, text, speaker, context):
        ctx = "\n".join(f"{(s + ': ') if s else ''}{src}\n→ {vi}" for s, src, vi in context if vi)
        out = (f"Các câu trước (để tham khảo ngữ cảnh):\n{ctx}\n\n" if ctx else "")
        return out + "Câu cần dịch:\n" + (f"{speaker}: " if speaker else "") + text

    # ---------- public
    def translate(self, text, speaker="", context=(), on_partial=None, engine=None):
        """-> (bản dịch, nhà cung cấp, ghi chú lỗi của nhà cung cấp bị bỏ qua — vd. Gemini lỗi nên dùng Google)"""
        eng = engine or self.cfg["dialog_engine"]; key = f"tr:{eng}:{self.cfg['target_lang']}:{text}"
        hit = self.db.cache_get(key) if self.db else None                  # câu đã dịch -> khỏi gọi lại (đỡ bị Google chặn)
        if hit:
            name, _, vi = hit.partition("\t"); return vi, name, ""
        res = self._translate(text, speaker, context, on_partial, eng)
        if self.db and res[0]: self.db.cache_set(key, f"{res[1]}\t{res[0]}")
        return res

    def _translate(self, text, speaker, context, on_partial, eng):
        errs = []
        for name in CHAINS.get(eng, ["google"]):
            if time.time() < self.cool.get(name, 0): errs.append(f"{name}: đang nghỉ do bị giới hạn (429)"); continue
            note = ("; ".join(errs)).replace("gemini:", "Gemini lỗi:")
            try:
                if name == "google": return self.google(text), name, note
                if name == "gemini": return self.gemini(self.system_prompt(text), self.user_prompt(text, speaker, context), on_partial), name, note
            except ProviderError as e: errs.append(f"{name}: {e}")
            except requests.RequestException as e: errs.append(f"{name}: {type(e).__name__}")
        raise ProviderError("; ".join(errs) or "Chưa cấu hình nhà cung cấp dịch")

    def label(self, name):
        """Tên hiển thị nguồn bản dịch ở góc overlay."""
        c = self.cfg
        return {"gemini": f"Gemini · {c['gemini_model']}", "google": "Google Translate"}.get(name, name)

    def explain(self, word, sentence):
        p = self.cfg["explain_prompt"].replace("{word}", word).replace("{sentence}", sentence)
        if self.cfg["gemini_key"] and time.time() >= self.cool.get("gemini", 0):
            try: return self.gemini("", p, None)
            except (ProviderError, requests.RequestException): pass
        g = self.google(word); return f"{g} (Google — cần Gemini key để giải nghĩa AI)"

    # ---------- providers
    def _check(self, name, r):
        if r.status_code == 429:
            self.cool[name] = time.time() + self.cfg["cooldown_s"]; raise ProviderError("hết quota (429)")
        if r.status_code >= 400:
            try: msg = r.json().get("error", {}); msg = msg.get("message", msg) if isinstance(msg, dict) else msg
            except Exception: msg = r.text[:200]
            msg = str(msg)
            if "API key not valid" in msg or "API_KEY_INVALID" in msg: raise ProviderError("API key sai")
            if r.status_code == 404: raise ProviderError(f"model '{self.cfg.get('gemini_model')}' không tồn tại / không dùng được")
            if r.status_code == 403: raise ProviderError("key không có quyền (bị chặn hoặc chưa bật Gemini API)")
            raise ProviderError(f"HTTP {r.status_code} {msg[:160]}")

    def google(self, text):
        protected, mapping = self._protect(text)
        return self._restore(google_free(self.s, protected, self.cfg["target_lang"], self.cfg["timeout_s"], self.cool), mapping)

    def _protect(self, text):
        """Google: thay thuật ngữ bằng token rồi khôi phục."""
        mapping = []
        for g in self.db.terms_in(text):
            keep = self.cfg["keep_terms"] or g["mode"] == "keep" or not g["vi"]
            tok = f"⟦{len(mapping)}⟧"; mapping.append(g["term"] if keep else g["vi"])
            text = re.sub(rf"(?<!\w){re.escape(g['term'])}(?!\w)", tok, text, flags=re.I)
        return text, mapping

    @staticmethod
    def _restore(text, mapping):
        return re.sub(r"⟦\s*(\d+)\s*⟧", lambda m: mapping[int(m.group(1))] if int(m.group(1)) < len(mapping) else m.group(0), text)

    def list_models(self, key):
        """Model Gemini key dùng được (hỗ trợ generateContent), mới nhất trước."""
        r = self.s.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 1000},
                       headers={"x-goog-api-key": key}, timeout=self.cfg["timeout_s"])
        self._check("gemini", r)
        names = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", []) and m["name"].split("/")[-1].startswith("gemini")
                 and not re.search(r"embedding|tts|image|audio|live|robotics|computer", m["name"])]
        ver = lambda n: [int(x) for x in re.findall(r"\d+", n.split("-")[1] if "-" in n else "0")]
        return sorted(set(names), key=lambda n: (ver(n), "preview" not in n and "exp" not in n), reverse=True)

    @staticmethod
    def pick_model(names):
        """Ưu tiên Flash-Lite (nhanh, quota free rộng) bản ổn định mới nhất, rồi Flash."""
        stable = [n for n in names if not re.search(r"preview|exp|\d{3,}$", n)] or names
        for kw in ("flash-lite", "flash"):
            m = [n for n in stable if kw in n]
            if m: return m[0]
        return names[0] if names else ""

    def read_image(self, png, on_partial=None):
        """Gemini đọc ảnh vùng chụp: chép nguyên văn + dịch. -> (câu gốc, bản dịch)"""
        user = ("Ảnh là một phần màn hình game (thư, bảng thông tin…). Chép lại NGUYÊN VĂN toàn bộ chữ trong ảnh theo đúng thứ tự đọc, "
                "giữ cách chia đoạn như trong ảnh (mỗi đoạn một dòng; dòng bị ngắt giữa câu thì nối lại), "
                f"rồi một dòng chỉ có {SEP}, rồi bản dịch sang tiếng Việt theo các quy tắc trên, chia đoạn y như bản gốc. Không thêm gì khác.")
        split = lambda t: [x.strip() for x in t.split(SEP, 1)] if SEP in t else ["", t.strip()]
        part = (lambda t: on_partial(split(t)[1] if SEP in t else "")) if on_partial else None
        src, vi = split(self.gemini(self.system_prompt(""), user, part, image=png, max_tokens=4096))
        if not src: raise ProviderError("Gemini không trả về chữ đọc được")
        return src, vi

    def gemini(self, system, user, on_partial, image=None, max_tokens=1024):
        c = self.cfg
        if not c["gemini_key"]: raise ProviderError("chưa có API key")
        parts = [{"text": user}]
        if image: parts.insert(0, {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image).decode()}})
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens}}
        if system: body["systemInstruction"] = {"parts": [{"text": system}]}
        if c["gemini_thinking_budget"] is not None and c["gemini_thinking_budget"] >= 0:
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": int(c["gemini_thinking_budget"])}
        base = f"https://generativelanguage.googleapis.com/v1beta/models/{c['gemini_model']}"
        hdr = {"x-goog-api-key": c["gemini_key"], "Content-Type": "application/json"}
        stream = bool(c["stream"] and on_partial)
        for attempt in (0, 1):
            r = self.s.post(f"{base}:{'streamGenerateContent?alt=sse' if stream else 'generateContent'}",
                            headers=hdr, json=body, timeout=c["timeout_s"], stream=stream)
            if r.status_code == 400 and attempt == 0 and "thinking" in r.text.lower():
                body["generationConfig"].pop("thinkingConfig", None); continue   # model không hỗ trợ tắt thinking
            break
        self._check("gemini", r)
        if not stream:
            return _gem_text(r.json()).strip()
        acc = ""
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try: acc += _gem_text(json.loads(line[5:]))
                except ValueError: continue
                on_partial(acc)
        return acc.strip()

def _gem_text(d):
    try: return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
    except (KeyError, IndexError):
        if d.get("promptFeedback", {}).get("blockReason"): raise ProviderError("bị chặn bởi safety filter")
        return ""
