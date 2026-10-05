"""Dịch máy: Gemini / OpenAI-compatible (DeepSeek, OpenRouter, Ollama...) / Google free. Chuỗi fallback + cooldown khi 429."""
import json, re, time
import requests

class ProviderError(Exception): pass

class Translator:
    def __init__(self, cfg, db):
        self.cfg, self.db, self.cool = cfg, db, {}
        self.s = requests.Session()

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
    def translate(self, text, speaker="", context=(), on_partial=None):
        errs = []
        for name in self.cfg["chain"]:
            if time.time() < self.cool.get(name, 0): errs.append(f"{name}: đang cooldown"); continue
            try:
                if name == "google": return self.google(text), name
                if name == "gemini": return self.gemini(self.system_prompt(text), self.user_prompt(text, speaker, context), on_partial), name
                if name == "openai": return self.openai(self.system_prompt(text), self.user_prompt(text, speaker, context), on_partial), name
            except ProviderError as e: errs.append(f"{name}: {e}")
            except requests.RequestException as e: errs.append(f"{name}: {type(e).__name__}")
        raise ProviderError("; ".join(errs) or "Chưa cấu hình nhà cung cấp dịch")

    def explain(self, word, sentence):
        p = self.cfg["explain_prompt"].replace("{word}", word).replace("{sentence}", sentence)
        for name in self.cfg["chain"]:
            if name == "google" or time.time() < self.cool.get(name, 0): continue
            try:
                if name == "gemini": return self.gemini("", p, None)
                if name == "openai": return self.openai("", p, None)
            except (ProviderError, requests.RequestException): continue
        g = self.google(word); return f"{g} (Google)"

    # ---------- providers
    def _check(self, name, r):
        if r.status_code == 429:
            self.cool[name] = time.time() + self.cfg["cooldown_s"]; raise ProviderError("hết quota (429)")
        if r.status_code >= 400:
            try: msg = r.json().get("error", {}); msg = msg.get("message", msg) if isinstance(msg, dict) else msg
            except Exception: msg = r.text[:200]
            raise ProviderError(f"HTTP {r.status_code} {str(msg)[:160]}")

    def google(self, text):
        protected, mapping = self._protect(text)
        r = self.s.get("https://translate.googleapis.com/translate_a/single",
                       params={"client": "gtx", "sl": "auto", "tl": "vi", "dt": "t", "q": protected}, timeout=self.cfg["timeout_s"])
        self._check("google", r)
        out = "".join(seg[0] for seg in r.json()[0] if seg and seg[0])
        return self._restore(out, mapping)

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

    def gemini(self, system, user, on_partial):
        c = self.cfg
        if not c["gemini_key"]: raise ProviderError("chưa có API key")
        body = {"contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}}
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

    def openai(self, system, user, on_partial):
        c = self.cfg
        if not c["openai_base"]: raise ProviderError("chưa cấu hình base URL")
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        stream = bool(c["stream"] and on_partial)
        r = self.s.post(c["openai_base"].rstrip("/") + "/chat/completions",
                        headers={"Authorization": f"Bearer {c['openai_key']}"} if c["openai_key"] else {},
                        json={"model": c["openai_model"], "messages": msgs, "temperature": 0.3, "stream": stream},
                        timeout=c["timeout_s"], stream=stream)
        self._check("openai", r)
        if not stream: return r.json()["choices"][0]["message"]["content"].strip()
        acc = ""
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"): continue
            d = line[5:].strip()
            if d == "[DONE]": break
            try: acc += json.loads(d)["choices"][0]["delta"].get("content") or ""
            except (ValueError, KeyError, IndexError): continue
            on_partial(acc)
        return acc.strip()

def _gem_text(d):
    try: return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
    except (KeyError, IndexError):
        if d.get("promptFeedback", {}).get("blockReason"): raise ProviderError("bị chặn bởi safety filter")
        return ""
