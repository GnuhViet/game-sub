# HANDOFF — Game Sub (tiếp tục trong Claude Code)

> Dán file này + giải nén `gamesub.zip` vào repo, rồi nói: "Đọc HANDOFF.md và README.md, tiếp tục dự án."

## 1. Mục tiêu
Tool overlay dịch thoại game sang tiếng Việt, chạy trên **Windows**, chỉ dùng **OCR màn hình**
(không hook/inject/sửa file game → tránh anti-cheat). Người dùng: Hưng, dev Java, thích code gọn, trả lời ngắn bằng tiếng Việt, làm theo kiểu lặp dần.

## 2. Bối cảnh & quyết định đã chốt
- Đã cân nhắc Translumo / LunaTranslator. Translumo hay sai chủ ngữ vì dịch từng câu không ngữ cảnh → tự build tool riêng.
- Game online thường có anti-cheat → **chỉ OCR**. Game để text **English**, chế độ Borderless/Windowed, tắt Auto-play thoại.
- Dịch: **ưu tiên bộ sub Việt hóa có sẵn** (file riêng của user, định dạng chưa biết → importer generic có chọn cột).
  Không khớp → engine chọn riêng cho thoại (`dialog_engine`) và vùng chụp (`scan_engine`): Google / Gemini (fallback Google). Đã bỏ OpenAI/DeepSeek.
- Gemini free tier (từ 04/2026 chỉ còn Flash/Flash-Lite, khoảng 5–15 RPM): mặc định `gemini-2.5-flash-lite`, thinking budget 0, streaming.
- Stack: **Python + PySide6**.
- "Ghi nhớ từ" = **cả hai**: sổ từ để học **và** glossary cố định cách dịch, kèm option **không dịch tên riêng/thuật ngữ**.
- Nguồn nghĩa khi hover = **tùy setting**: offline / online / AI / auto.

## 3. Tính năng đã làm
| Yêu cầu | Đã làm |
|---|---|
| Khoanh vùng | `ui_region.py`: đóng băng màn hình dưới con trỏ, kéo chọn; quy đổi logical→physical theo DPR. Thêm vùng tên nhân vật (tùy chọn). |
| Ghi nhớ từ | `db.py` vocab (sổ từ + flashcard + export CSV/Anki) và glossary (keep/translate). Global toggle `keep_terms`. Google được bảo vệ thuật ngữ bằng token `⟦n⟧`. |
| Hover tra từ | `ui_overlay.py`: câu gốc render thành link mỗi từ (`linkHovered`) → `WordPopup` (ghim bằng click). Bôi đen cụm → menu chuột phải. `dictionary.py`: StarDict/TSV/JSON offline, dictionaryapi.dev online, AI giải nghĩa theo câu (cache SQLite). |
| Mapping bộ sub | `importer.py` (CSV/TSV/TXT/XLSX/JSON, đoán cột EN/VI), `matcher.py` (exact → rapidfuzz lọc theo độ dài → tách câu). Xử lý `{PlayerName}`, `{Male=..;Female=..}`, `<color>`. |

Ngoài ra: `capture.py` chờ ảnh đứng yên `stable_ms` (hiệu ứng chữ chạy) rồi mới OCR, bỏ câu trùng (dedupe); lịch sử ◀ ▶; tray icon; hotkey Win32 `RegisterHotKey` (Ctrl+Alt+T/R/P/S); cooldown khi gặp 429.

## 4. Cấu trúc
```
main.py                  entry
gamesub/config.py        settings mặc định + prompt dịch / giải nghĩa (data/settings.json)
gamesub/app.py           controller: pipeline OCR→sub→LLM, tra từ, action, Task (QThreadPool)
gamesub/capture.py       QThread: mss chụp → phát hiện thay đổi → chờ ổn định → OCR
gamesub/ocr.py           WindowsOcr (winrt/winsdk), RapidOcr, TesseractOcr
gamesub/matcher.py       SubIndex
gamesub/textnorm.py      resolve placeholder, norm, lemmas, join_lines
gamesub/translator.py    Gemini (SSE, đọc ảnh) / Google gtx; CHAINS theo engine; prompt + glossary
gamesub/dictionary.py    StarDict, TableDict, online_lookup
gamesub/db.py            SQLite: subs, glossary, vocab, cache
gamesub/hotkeys.py       RegisterHotKey + QAbstractNativeEventFilter
gamesub/ui_overlay.py    Overlay + WordPopup
gamesub/ui_region.py     RegionSelector + to_physical
gamesub/ui_dialogs.py    Settings, Glossary, Vocab, Review, Subs
gamesub/i18n.py          tr("key") / N_() / set_lang; chữ ở gamesub/locales/<mã>.json (vi = gốc, en), tự nhận file mới
gamesub/assets/          icon.ico / icon.png (vẽ lại: python tools/make_icon.py); mdi6.ttf + mdi6.json = font icon toolbar
gamesub/icons.py         icon đơn sắc từ mdi6.ttf (thay qtawesome: đỡ ~40 MB RAM); thêm icon: tools/make_icon_font.py
tools/i18n_check.py      key thiếu / thừa / sai biến giữa các file locales (--todo: chuỗi tiếng Việt còn viết thẳng)
tests/                   test_core, test_capture_translate, test_ui_smoke (offscreen), test_i18n
```

Phiên 2: `diag.py`/`diag.bat` (tự kiểm tra các mục chưa test ở §5), tự ẩn khi hết thoại (`auto_hide_s`),
click-through (`click_through`, Ctrl+Alt+C, menu khay), tương thích mss 10 (`capture.open_sct`). RapidOCR đã kiểm chứng trên Linux.

Phiên 3 (Windows 11, Python 3.12, 1 màn 1920x1080 @100%): diag OK. Sửa `WindowsOcr`: pywinrt không có overload 5 tham số
của `create_copy_from_buffer` → dùng 4 tham số. Windows OCR: 81ms, khớp 100%, chạy được trong QThread. Đăng ký hotkey OK.

Phiên 4: build exe 1 file (`build.bat`, `--diag`). Nút tải OCR engine (`engines.py`): RapidOCR = giải nén wheel PyPI (bản ghim) vào `engines/py`
(exe cần `--collect-submodules numpy`), Tesseract = bộ cài UB-Mannheim `/S /D=engines/tesseract` (CHƯA test, cần UAC).
Popup tra từ: Google dịch tự động (`google_lookup`, dt=bd) + chọn ngôn ngữ đích (`target_lang`). EasyOCR: bỏ qua (PyTorch >1GB, chậm trên CPU).

Build: dạng thư mục (onedir) vào `build\out`, robocopy sang `dist\GameSub` chừa `data\`/`engines\` (PyInstaller xóa sạch thư mục đích),
zip ra `dist\GameSub.zip`. Bỏ onefile vì giải nén ~160MB ra %TEMP% mỗi lần chạy, để rác khi bị tắt cưỡng bức.

## 5. Trạng thái test
**Pass trên Linux:** core (matcher, importer, db, glossary/prompt, StarDict), capture (logic chờ ổn định), parser streaming Gemini + 429 fallback + engine, UI smoke offscreen.

**CHƯA test (cần Windows thật):**
1. `WindowsOcr`: API pywinrt (`DataWriter.write_bytes`, `SoftwareBitmap.create_copy_from_buffer`, `recognize_async`).
2. Hotkey toàn cục (`hotkeys.py`).
3. Vùng chụp khi Windows scale ≠ 100% / đa màn hình (`to_physical` giả định gốc màn hình logical = physical). Kiểm tra bằng Cài đặt → OCR → "Lưu ảnh vùng hiện tại" → `data/region_snapshot.png`.
4. Overlay có hiện đè lên game Borderless không; mss có chụp được game không (màn hình đen?).
5. `build.bat` (PyInstaller + winrt).

## 6. Việc tiếp theo
1. User chạy `diag.bat` + `run.bat` trên Windows, gửi `data/diag.txt` → sửa lỗi theo báo cáo.
2. User gửi 1–2 dòng mẫu của **file sub riêng** → chỉnh `importer.guess_cols` và placeholder (`name_tokens`, regex giới tính) cho đúng định dạng.
3. Tinh chỉnh `stable_ms`, `diff_threshold`, `fuzzy_threshold` với thoại game thật.
4. Ý tưởng chưa làm: nhiều vùng OCR, gợi ý tự thêm tên riêng vào glossary, lọc OCR rác khi không có hộp thoại (ảnh cảnh nền).

## 7. Lệnh hữu ích
```
python tests/test_core.py && python tests/test_capture_translate.py && python tests/test_ui_smoke.py && python tests/test_i18n.py
python -m pyflakes gamesub tests tools main.py diag.py
QT_QPA_PLATFORM=offscreen python diag.py        # trên Linux chỉ kiểm được RapidOCR
```
