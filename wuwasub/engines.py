"""Tải OCR engine tùy chọn vào <thư mục exe>/engines (exe không phải đóng gói sẵn).
RapidOCR: giải nén wheel từ PyPI vào engines/py. Tesseract: chạy bộ cài UB-Mannheim im lặng vào engines/tesseract."""
import io, re, shutil, sys, zipfile
import requests
from .config import app_dir

ENG_DIR = app_dir() / "engines"
PY_DIR = ENG_DIR / "py"
TESS_DIR = ENG_DIR / "tesseract"

# Bộ phiên bản đã kiểm chứng với Python 3.12 + numpy/Pillow đóng gói trong exe.
RAPID_PKGS = {"rapidocr-onnxruntime": "1.4.4", "onnxruntime": "1.30.0", "opencv-python": "5.0.0.93", "pyclipper": "1.4.0",
              "shapely": "2.1.2", "PyYAML": "6.0.3", "six": "1.17.0", "tqdm": "4.70.1", "flatbuffers": "25.12.19",
              "packaging": "26.3", "protobuf": "7.36.2"}
TESS_API = "https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"

class Cancelled(Exception): pass

def setup():
    """Gọi lúc khởi động: cho phép import gói đã tải."""
    if PY_DIR.is_dir() and str(PY_DIR) not in sys.path: sys.path.insert(0, str(PY_DIR))
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS") and sys.platform == "win32":
        import os; os.add_dll_directory(sys._MEIPASS)    # msvcp140/vcruntime140_1 đóng gói trong exe cho onnxruntime/opencv

def has_rapidocr(): return (PY_DIR / "rapidocr_onnxruntime").is_dir()
def tesseract_exe():
    p = TESS_DIR / "tesseract.exe"; return str(p) if p.exists() else None

def _download(url, progress, label):
    """progress(text, percent) -> False để hủy."""
    r = requests.get(url, stream=True, timeout=30); r.raise_for_status()
    total = int(r.headers.get("content-length") or 0); buf = io.BytesIO(); done = 0
    for chunk in r.iter_content(1 << 16):
        buf.write(chunk); done += len(chunk)
        if progress(f"{label} — {done / 1e6:.1f}/{total / 1e6:.1f} MB", int(done * 100 / total) if total else 0) is False: raise Cancelled()
    return buf.getvalue()

def _wheel_url(name, ver):
    py = f"cp{sys.version_info.major}{sys.version_info.minor}"
    files = requests.get(f"https://pypi.org/pypi/{name}/{ver}/json", timeout=20).json()["urls"]
    def score(f):
        fn = f["filename"]
        if not fn.endswith(".whl"): return -1
        pyt, abi, plat = fn[:-4].split("-")[-3:]
        if plat not in ("win_amd64", "any"): return -1
        if py in pyt.split("."): return 3
        if abi == "abi3": return 2 if int(re.sub(r"\D", "", pyt.split(".")[0]) or 0) <= int(py[2:]) else -1
        return 1 if "py3" in pyt.split(".") and abi == "none" else -1
    best = max(files, key=score, default=None)
    if not best or score(best) < 0: raise RuntimeError(f"Không có bản {name} {ver} cho {py}/win_amd64")
    return best["url"]

def install_rapidocr(progress):
    tmp = ENG_DIR / "py.tmp"; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    for i, (name, ver) in enumerate(RAPID_PKGS.items(), 1):
        data = _download(_wheel_url(name, ver), progress, f"[{i}/{len(RAPID_PKGS)}] {name}")
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
    shutil.rmtree(PY_DIR, ignore_errors=True); tmp.rename(PY_DIR); setup()

def install_tesseract(progress):
    if sys.platform != "win32": raise RuntimeError("Chỉ hỗ trợ tự cài trên Windows")
    rel = requests.get(TESS_API, timeout=20).json()
    asset = next((a for a in rel.get("assets", []) if re.search(r"w64-setup.*\.exe$", a["name"])), None)
    if not asset: raise RuntimeError("Không tìm thấy bộ cài Tesseract trên GitHub")
    ENG_DIR.mkdir(parents=True, exist_ok=True); setup_exe = ENG_DIR / asset["name"]
    setup_exe.write_bytes(_download(asset["browser_download_url"], progress, "Tesseract"))
    progress("Đang cài Tesseract (đồng ý nếu Windows hỏi quyền)…", 100)
    try: _run_wait(str(setup_exe), f"/S /D={TESS_DIR}")
    finally: setup_exe.unlink(missing_ok=True)
    if not tesseract_exe(): raise RuntimeError("Cài Tesseract không thành công (bị hủy quyền admin?)")

def _run_wait(exe, args):
    """ShellExecuteEx để Windows tự hỏi UAC nếu bộ cài cần quyền admin, rồi chờ xong."""
    import ctypes; from ctypes import wintypes as wt
    class SEI(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("fMask", wt.ULONG), ("hwnd", wt.HWND), ("lpVerb", wt.LPCWSTR), ("lpFile", wt.LPCWSTR),
                    ("lpParameters", wt.LPCWSTR), ("lpDirectory", wt.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wt.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wt.LPCWSTR), ("hkeyClass", wt.HKEY), ("dwHotKey", wt.DWORD),
                    ("hIcon", wt.HANDLE), ("hProcess", wt.HANDLE)]
    sei = SEI(cbSize=ctypes.sizeof(SEI), fMask=0x40, lpVerb="open", lpFile=exe, lpParameters=args, nShow=0)   # NOCLOSEPROCESS
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)): raise RuntimeError("Không chạy được bộ cài (bị từ chối quyền?)")
    ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, 0xFFFFFFFF); ctypes.windll.kernel32.CloseHandle(sei.hProcess)
