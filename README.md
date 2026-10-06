# Game Sub — OCR dịch thoại game

Overlay dịch thoại cho game bất kỳ chỉ bằng **OCR màn hình**: không hook, không đọc bộ nhớ, không sửa file game —
an toàn với game online có anti-cheat. Mã nguồn mở, giấy phép [MIT](LICENSE).

**Ngôn ngữ giao diện / UI language:** Tiếng Việt, English — Cài đặt → Giao diện → *Ngôn ngữ / Language* (mặc định theo ngôn ngữ Windows; đổi xong app hỏi mở lại).

## Tải về (Windows 10/11, không cần Python)
Tải `GameSub.zip` ở trang [Releases](https://github.com/GnuhViet/game-sub/releases) → **giải nén hết** → chạy `GameSub\GameSub.exe`
(đừng chạy thẳng trong zip). Để thư mục ở chỗ ghi được (vd. `D:\GameSub`), không để trong Program Files.
Bản exe chỉ có Windows OCR (cần gói ngôn ngữ English trong Windows, thường có sẵn); OCR khác tải trong app.

Dữ liệu nằm trong `data\` (và `engines\` nếu tải OCR) cạnh exe — copy cả thư mục là mang sang máy khác được.

## Cập nhật
App tự kiểm tra bản mới khi mở (tắt ở Cài đặt → Giao diện) và báo ở khay; hoặc bấm **Kiểm tra cập nhật** ở góc dưới Cài đặt / menu khay.
Bấm **Cập nhật**: app tải bản mới (kiểm tra SHA256), tự tắt, thay file rồi mở lại. `data\` và `engines\` giữ nguyên — không phải tải zip, copy dữ liệu bằng tay nữa.
File ngôn ngữ tự thêm vào `_internal\gamesub\locales\` sẽ bị thay khi cập nhật — giữ bản sao, hoặc gửi pull request để có sẵn trong bản sau.

## Chạy từ mã nguồn (Python 3.10+)
```
run.bat            # lần đầu tự tạo .venv và cài thư viện
build.bat          # (tùy chọn) đóng gói thành dist\GameSub\GameSub.exe + dist\GameSub.zip
diag.bat           # tự kiểm tra DPI/đa màn hình, chụp game, OCR, hotkey -> data\diag.txt
```
Ra bản mới: tăng `__version__` trong `gamesub/__init__.py` → `build.bat` → tạo release tag `vX.Y.Z` đính kèm `dist\GameSub.zip`
(tên file phải đúng `GameSub.zip`, app tìm file này để tự cập nhật).

Gặp lỗi (vùng lệch, ảnh đen, OCR không chạy, hotkey không ăn): chạy `diag.bat` (bản exe: `GameSub.exe --diag`) và gửi `data\diag.txt` + `data\diag_region.png`.
Game để **Borderless/Windowed**, ngôn ngữ text **English**, tắt Auto-play thoại.

## Dùng
| Nút / Hotkey | Chức năng |
|---|---|
| Chọn vùng / `Ctrl+Alt+R` | Chọn vùng thoại (màn hình dưới con trỏ) |
| Chọn vùng tên | Chọn vùng tên nhân vật (Esc để bỏ) |
| Xem vùng | Hiện viền quanh vùng thoại + vùng tên nhân vật đang chọn trong 3 giây (cũng có ở Cài đặt → OCR) |
| Tạm dừng / `Ctrl+Alt+P` | Tạm dừng |
| Quét lại / `Ctrl+Alt+S` | Quét lại |
| `Ctrl+Alt+T` | Ẩn/hiện overlay (hoặc click icon khay) |
| `Ctrl+Alt+C` | Click-through: chuột xuyên qua overlay để bấm game (cũng có ở menu khay) |
| Dịch / `Ctrl+Alt+D` | Bật/tắt dịch (tắt = chỉ hiện câu gốc để tra từ, không tốn quota) |
| Xóa / `Ctrl+Alt+X` | Xóa chữ trên overlay |
| Khóa / `Ctrl+Alt+L` | Khóa overlay: rê chuột không hiện toolbar, không kéo/đổi cỡ (tra từ vẫn được). Giữ **Alt** để bấm trên overlay — đổi phím trong Cài đặt → Giao diện (phím, tổ hợp hoặc nút chuột giữa/bên) |
| Chụp / `Ctrl+Alt+Q` | Chụp & dịch 1 vùng bất kỳ (thư, bảng…) → cửa sổ riêng, bấm từ để tra |
| Câu trước / sau | Xem lại các câu trước |

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

## Glossary & tùy chọn không dịch tên riêng
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

## Đa ngôn ngữ
Mỗi ngôn ngữ là 1 file `gamesub/locales/<mã>.json`: `{"_name": "English", "settings.title": "Settings", …}` (bản exe: `_internal\gamesub\locales\`).
- **Thêm ngôn ngữ:** copy `en.json` thành `<mã>.json` (vd `ja.json`), đổi `"_name"` và dịch phần giá trị — app tự nhận, không cần sửa code.
  Key nào chưa dịch thì app hiện chữ tiếng Việt. Giữ nguyên các biến `{n}`, `{w}`… trong chữ.
- **Sửa chữ:** sửa thẳng trong file JSON. `vi.json` là ngôn ngữ gốc, có đủ mọi key.
- **Cho người sửa code:** giao diện gọi `tr("key")` / `tr("key", n=5)`; bảng hằng (tooltip, menu) đánh dấu `N_("key")` rồi `tr()` lúc dùng.
  Thêm chữ mới: thêm key vào `vi.json` + các file khác. `python tools/i18n_check.py` báo key thiếu / thừa / sai biến giữa các file,
  `--todo` liệt kê chuỗi tiếng Việt còn viết thẳng trong code (dòng là dữ liệu / prompt AI thì ghi chú `# no-i18n`).

## Dữ liệu
Tất cả nằm trong `data/`: `settings.json`, `gamesub.db` (sub, glossary, sổ từ, cache tra từ).

## Test
```
python tests/test_core.py
python tests/test_capture_translate.py
python tests/test_ui_smoke.py
python tests/test_i18n.py         # mọi chuỗi giao diện đã có bản dịch
```

## Giấy phép
[MIT](LICENSE) © 2026 Nguyễn Việt Hưng. Bản exe đóng gói kèm thư viện bên thứ ba theo giấy phép riêng của chúng
(PySide6/Qt: LGPLv3, Material Design Icons: Apache 2.0 — xem `gamesub/assets/mdi6-NOTICE.txt`, …).
