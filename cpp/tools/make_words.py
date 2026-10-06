r"""Danh sách từ của wordninja (sắp theo tần suất) -> resources/words.qz (định dạng qCompress của Qt: 4 byte độ dài + zlib).
Chạy bằng Python của dự án: .venv\Scripts\python cpp\tools\make_words.py"""
import gzip, struct, zlib, pathlib, wordninja
src = pathlib.Path(wordninja.__file__).parent / "wordninja" / "wordninja_words.txt.gz"
data = gzip.decompress(src.read_bytes())
out = pathlib.Path(__file__).resolve().parent.parent / "resources" / "words.qz"
out.write_bytes(struct.pack(">I", len(data)) + zlib.compress(data, 9))
print(out, len(data.split()), "words,", out.stat().st_size, "bytes")
