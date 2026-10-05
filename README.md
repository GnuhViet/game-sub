# WuWa Sub — OCR dịch thoại game

Overlay dịch thoại cho Wuthering Waves (và game bất kỳ) chỉ bằng **OCR màn hình**: không hook, không đọc bộ nhớ, không sửa file game.

## Cài & chạy (Windows 10/11, Python 3.10+)
```
run.bat            # lần đầu tự tạo .venv và cài thư viện
build.bat          # (tùy chọn) đóng gói thành dist\WuWaSub\WuWaSub.exe
diag.bat           # tự kiểm tra DPI/đa màn hình, chụp game, OCR, hotkey -> data\diag.txt
```
**Chạy trên máy khác không cần Python:** chạy `build.bat` → gửi `dist\WuWaSub.zip`. Bên kia **giải nén hết** rồi chạy
`WuWaSub\WuWaSub.exe` (đừng chạy thẳng trong zip). Dạng thư mục mở nhanh, không giải nén gì ra `%TEMP%`.
Dữ liệu nằm trong `data\` (và `engines\` nếu tải OCR) cạnh exe — copy cả thư mục là mang sang máy khác được. Kiểm tra lỗi: `WuWaSub.exe --diag` → `data\diag.txt`.
Bản exe chỉ có Windows OCR (cần gói ngôn ngữ English trong Windows, thường có sẵn).

Gặp lỗi (vùng lệch, ảnh đen, OCR không chạy, hotkey không ăn): chạy `diag.bat` và gửi `data\diag.txt` + `data\diag_region.png`.
Game để **Borderless/Windowed**, ngôn ngữ text **English**, tắt Auto-play thoại.

## Dùng
| Nút / Hotkey | Chức năng |
|---|---|
| ⬚ / `Ctrl+Alt+R` | Chọn vùng thoại (màn hình dưới con trỏ) |
| 👤 | Chọn vùng tên nhân vật (Esc để bỏ) |
| ⏸ / `Ctrl+Alt+P` | Tạm dừng |
| ⟳ / `Ctrl+Alt+S` | Quét lại |
| `Ctrl+Alt+T` | Ẩn/hiện overlay (hoặc click icon khay) |
| `Ctrl+Alt+C` | Click-through: chuột xuyên qua overlay để bấm game (cũng có ở menu khay) |
| 🌐 / `Ctrl+Alt+D` | Bật/tắt dịch (tắt = chỉ hiện câu gốc để tra từ, không tốn quota) |
| ⌫ / `Ctrl+Alt+X` | Xóa chữ trên overlay |
| 🔒 / `Ctrl+Alt+L` | Khóa overlay: rê chuột không hiện toolbar, không kéo/đổi cỡ (tra từ vẫn được) |
| 📷 / `Ctrl+Alt+Q` | Chụp & dịch 1 vùng bất kỳ (thư, bảng…) → cửa sổ riêng, bấm từ để tra |
| ◀ ▶ | Xem lại các câu trước |

**Tự ẩn khi hết thoại:** Cài đặt → Giao diện → "Tự ẩn… sau (s)" > 0; có thoại mới tự hiện lại.

Toolbar hiện khi rê chuột vào overlay; kéo phần nền để di chuyển, góc phải dưới để resize.

**Tra từ:** bấm vào từ trong câu gốc (hoặc bôi đen cụm/câu) → popup nghĩa; ✕ hoặc chuột phải để đóng. Muốn rê chuột là hiện: Cài đặt → Từ điển → Hiện nghĩa khi.
Bôi đen cụm từ → chuột phải: tra cụm, lưu sổ từ, thêm glossary, giải nghĩa AI.

## Luồng dịch
```
OCR → khớp bộ sub (exact → fuzzy → tách câu) ─ khớp ─→ bản Việt hóa
                                                └ không ─→ engine đã chọn: Google / Gemini / Gemini→Google
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
| Offline → Google dịch tự động | mặc định; chọn ngôn ngữ ngay trên popup (vi/ja/zh/ko/…) |
| Google dịch tự động | Google Translate, có từ loại + phiên âm |
| Chỉ offline | file từ điển bạn nạp |
| Online | dictionaryapi.dev (Anh-Anh, free) |
| AI theo ngữ cảnh | Gemini, có cache, tốn quota |

File offline hỗ trợ: **StarDict** (`.ifo` + `.idx` + `.dict`/`.dict.dz` — dạng phổ biến của từ điển Anh-Việt), TSV/CSV `từ⇥nghĩa`, JSON `{từ: nghĩa}`.

## API
- **Gemini**: lấy key free tại aistudio.google.com → model `gemini-2.5-flash-lite` (nhanh, quota rộng). Thinking budget `0` để giảm delay; model không hỗ trợ sẽ tự bỏ.
- Cài đặt → Dịch chọn riêng: **Dịch thoại** (Google / Gemini / Gemini lỗi thì Google) và **Dịch vùng chụp 📷**
  (OCR + Google / OCR + Gemini / Gemini đọc thẳng ảnh). Gemini chỉ dùng khi được chọn.

## OCR
- **Windows OCR** (mặc định): nhẹ, cần gói ngôn ngữ English trong Windows.
- **RapidOCR** / **Tesseract**: Cài đặt → OCR → nút «Tải…», cài vào thư mục `engines\` cạnh exe. RapidOCR tốt hơn với font lạ/nền rối nhưng chậm hơn (~2s/lần).
- Chữ nhỏ → tăng "Phóng to ảnh trước OCR" lên 1.5–2. Nút "Lưu ảnh vùng hiện tại" để kiểm tra vùng chụp có đúng không.

## Dữ liệu
Tất cả nằm trong `data/`: `settings.json`, `wuwasub.db` (sub, glossary, sổ từ, cache tra từ).

## Test
```
python tests/test_core.py
python tests/test_capture_translate.py
python tests/test_ui_smoke.py
```
