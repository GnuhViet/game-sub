# WuWa Sub — OCR dịch thoại game

Overlay dịch thoại cho Wuthering Waves (và game bất kỳ) chỉ bằng **OCR màn hình**: không hook, không đọc bộ nhớ, không sửa file game.

## Cài & chạy (Windows 10/11, Python 3.10+)
```
run.bat            # lần đầu tự tạo .venv và cài thư viện
build.bat          # (tùy chọn) đóng gói thành dist\WuWaSub\WuWaSub.exe
```
Game để **Borderless/Windowed**, ngôn ngữ text **English**, tắt Auto-play thoại.

## Dùng
| Nút / Hotkey | Chức năng |
|---|---|
| ⬚ / `Alt+R` | Chọn vùng thoại (màn hình dưới con trỏ) |
| 👤 | Chọn vùng tên nhân vật (Esc để bỏ) |
| ⏸ / `Alt+P` | Tạm dừng |
| ⟳ / `Alt+S` | Quét lại |
| `Alt+T` | Ẩn/hiện overlay (hoặc click icon khay) |
| ◀ ▶ | Xem lại các câu trước |

Toolbar hiện khi rê chuột vào overlay; kéo phần nền để di chuyển, góc phải dưới để resize.

**Tra từ:** hover từ trong câu gốc → popup nghĩa. Click từ để ghim popup; chuột phải popup để đóng.
Bôi đen cụm từ → chuột phải: tra cụm, lưu sổ từ, thêm glossary, giải nghĩa AI.

## Luồng dịch
```
OCR → khớp bộ sub (exact → fuzzy → tách câu) ─ khớp ─→ bản Việt hóa
                                                └ không ─→ Gemini → OpenAI-compatible → Google (theo thứ tự cài đặt)
```
- Chữ chạy từng ký tự: tool chờ ảnh đứng yên `stable_ms` rồi mới OCR.
- Gặp 429 (hết quota) thì nhà cung cấp đó nghỉ `cooldown_s` giây, tự chuyển sang cái tiếp theo.

## Bộ sub (📂)
Nhận CSV / TSV / TXT / XLSX / JSON. Chọn file → xem trước → chọn cột EN và cột VI → Nhập. Ô "Thử khớp" để test.
- Placeholder tên người chơi (`{PlayerName}`, `{Nickname}`… chỉnh trong Cài đặt → Nhân vật) được thay bằng tên Rover của bạn.
- Macro `{Male=..;Female=..}` chọn theo giới tính Rover; tag `<color=..>` tự bỏ.
- File nhập sau ưu tiên khi trùng câu.

## Glossary (🏷) & tùy chọn không dịch tên riêng
- Mỗi mục: **Giữ nguyên** hoặc **Dịch theo cột "Dịch là"**.
- Tick **"Không dịch tên riêng / thuật ngữ"** → mọi mục đều giữ nguyên và AI được yêu cầu giữ tên riêng.
- Chỉ áp dụng cho dịch máy; câu lấy từ bộ sub giữ nguyên bản của người dịch.
- Google Translate cũng được bảo vệ thuật ngữ (thay token trước khi gửi, khôi phục sau).

## Sổ từ (📖)
Lưu từ + nghĩa + câu gốc + câu dịch. Có chế độ ôn tập flashcard, export CSV (nhập được vào Anki).

## Từ điển (Cài đặt → Từ điển)
| Chế độ | Nguồn |
|---|---|
| Offline → Online → nút AI | mặc định |
| Chỉ offline | file từ điển bạn nạp |
| Online | dictionaryapi.dev (Anh-Anh, free) |
| AI theo ngữ cảnh | Gemini/OpenAI, có cache, tốn quota |

File offline hỗ trợ: **StarDict** (`.ifo` + `.idx` + `.dict`/`.dict.dz` — dạng phổ biến của từ điển Anh-Việt), TSV/CSV `từ⇥nghĩa`, JSON `{từ: nghĩa}`.

## API
- **Gemini**: lấy key free tại aistudio.google.com → model `gemini-2.5-flash-lite` (nhanh, quota rộng). Thinking budget `0` để giảm delay; model không hỗ trợ sẽ tự bỏ.
- **OpenAI-compatible**: DeepSeek (`https://api.deepseek.com/v1`, `deepseek-chat`), OpenRouter, hoặc LLM local qua Ollama (`http://localhost:11434/v1`).

## OCR
- **Windows OCR** (mặc định): nhẹ, cần gói ngôn ngữ English trong Windows.
- **RapidOCR**: `pip install rapidocr_onnxruntime`, tốt hơn với font lạ/nền rối.
- Chữ nhỏ → tăng "Phóng to ảnh trước OCR" lên 1.5–2. Nút "Lưu ảnh vùng hiện tại" để kiểm tra vùng chụp có đúng không.

## Dữ liệu
Tất cả nằm trong `data/`: `settings.json`, `wuwasub.db` (sub, glossary, sổ từ, cache tra từ).

## Test
```
python tests/test_core.py
python tests/test_capture_translate.py
python tests/test_ui_smoke.py
```
