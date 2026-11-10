"""Tự cập nhật bản exe từ GitHub Releases: tìm bản mới -> tải GameSub.zip (kiểm SHA256) -> giải nén vào %TEMP%
-> script .bat đợi app tắt, chép đè rồi mở lại. Chỉ thay GameSub.exe/file cạnh exe + _internal\\ — data\\ và engines\\ không đụng tới.
Không dùng robocopy /MIR cho cả thư mục app: /XD theo đường dẫn đầy đủ vẫn xóa data\\ (đã thử), /XD theo tên thì bỏ sót thư mục "data" trong _internal."""
import hashlib, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
from . import net, __version__
from .config import app_dir
from .engines import Cancelled
from .i18n import tr

REPO = "GnuhViet/game-sub"
PAGE = f"https://github.com/{REPO}/releases"
API = f"https://api.github.com/repos/{REPO}/releases"
ASSET, BETA_ASSET = "GameSub.zip", "GameSub-beta.zip"
EXE = "GameSub.exe"
TMP = Path(tempfile.gettempdir()) / "GameSub-update"

def ver(tag):
    """Khóa so sánh: 'v0.2.10' -> ((0, 2, 10), 1, ()); 'v0.3.0-beta.1' -> ((0, 3, 0), 0, (1,)) — beta đứng trước bản chính thức cùng số."""
    main, _, pre = (tag or "").strip().lstrip("vV").partition("-")
    return tuple(int(x) for x in re.findall(r"\d+", main)), 0 if pre else 1, tuple(int(x) for x in re.findall(r"\d+", pre))

def is_beta(tag):
    """Bản thử nghiệm: tag có hậu tố sau dấu '-' (v0.3.0-beta.1). Tự cập nhật không bao giờ đưa lên bản này.
    Bản beta đặt file tải là GameSub-beta.zip (không phải GameSub.zip) để các bản cũ — chỉ tìm GameSub.zip — cũng bỏ qua."""
    return "-" in (tag or "").strip()

def can_install():
    """Chỉ bản exe trên Windows tự cập nhật được (chạy từ source thì git pull)."""
    return getattr(sys, "frozen", False) and sys.platform == "win32"

def releases(beta=False):
    """Các bản cài được, mới nhất trước: [{"tag", "name", "notes", "url", "size", "digest", "page", "date", "beta"}].
    Lấy danh sách releases (không dùng /latest: các bản chính thức cũng đang gắn cờ pre-release); bỏ draft; beta=False bỏ bản beta.
    Bản chính thức dùng file GameSub.zip, bản beta GameSub-beta.zip (hoặc GameSub.zip)."""
    r = net.session().get(API, params={"per_page": 50}, headers={"Accept": "application/vnd.github+json"}, timeout=15)
    if r.status_code != 200: raise RuntimeError(f"GitHub {r.status_code}: {r.json().get('message', '') if r.content else ''}")
    out = []
    for rel in r.json():
        b = is_beta(rel["tag_name"]); names = (BETA_ASSET, ASSET) if b else (ASSET,)
        a = next((a for n in names for a in rel.get("assets", []) if a["name"] == n), None)
        if rel.get("draft") or not a or (b and not beta): continue
        out.append({"tag": rel["tag_name"], "name": rel.get("name") or rel["tag_name"], "notes": (rel.get("body") or "").strip(),
                    "url": a["browser_download_url"], "size": a.get("size", 0), "digest": a.get("digest") or "", "page": rel.get("html_url") or PAGE,
                    "date": (rel.get("published_at") or rel.get("created_at") or "")[:10], "beta": b})
    return sorted(out, key=lambda x: ver(x["tag"]), reverse=True)

def is_current(tag): return ver(tag) == ver(__version__)

def check(beta=False):
    """-> bản mới nhất (dict như releases()) nếu mới hơn bản đang chạy, không thì None. beta=True: tính cả bản beta."""
    rels = releases(beta)
    return rels[0] if rels and ver(rels[0]["tag"]) > ver(__version__) else None

def download(info, progress):
    """Tải + kiểm SHA256 + giải nén vào TMP. progress(text, percent) -> False để hủy. -> thư mục chứa GameSub.exe bản mới."""
    shutil.rmtree(TMP, ignore_errors=True); TMP.mkdir(parents=True)
    z, h, done = TMP / ASSET, hashlib.sha256(), 0
    r = net.session().get(info["url"], stream=True, timeout=30); r.raise_for_status()
    total = int(r.headers.get("content-length") or info["size"] or 0)
    with open(z, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk); h.update(chunk); done += len(chunk)
            if progress(tr("updater.downloading_tag_mb", tag=info["tag"], done=f"{done / 1e6:.1f}", total=f"{total / 1e6:.1f}"),
                        int(done * 100 / total) if total else 0) is False: raise Cancelled()
    algo, _, want = info["digest"].partition(":")
    if algo == "sha256" and want.lower() != h.hexdigest(): raise RuntimeError(tr("updater.checksum_mismatch"))
    progress(tr("updater.extracting"), 100)
    with zipfile.ZipFile(z) as zf: zf.extractall(TMP / "new")
    z.unlink()
    new = next((p.parent for p in (TMP / "new").rglob(EXE)), None)     # zip có thư mục GameSub\ ở gốc
    if not new or not (new / "_internal").is_dir(): raise RuntimeError(tr("updater.bad_package"))
    return new

SCRIPT = r"""@echo off
rem Game Sub updater: wait for app exit -> copy new build over it (data\ engines\ untouched) -> relaunch. Paths come in GS_* env vars.
powershell -NoProfile -Command "Wait-Process -Id %GS_PID% -ErrorAction SilentlyContinue"
robocopy "%GS_NEW%\_internal" "%GS_APP%\_internal" /MIR /IS /IT /R:10 /W:1 /NP /LOG:"%GS_TMP%\update.log"
if errorlevel 8 goto fail
robocopy "%GS_NEW%" "%GS_APP%" /LEV:1 /IS /IT /R:10 /W:1 /NP /LOG+:"%GS_TMP%\update.log"
if errorlevel 8 goto fail
start "" "%GS_APP%\GameSub.exe" --wait
(goto) 2>nul & rmdir /s /q "%GS_TMP%"
:fail
start "" notepad "%GS_TMP%\update.log"
start "" "%GS_APP%\GameSub.exe" --wait
"""

def apply(new):
    """Chạy script cập nhật tách rời (cửa sổ ẩn); app phải tự thoát ngay sau đó để script chép đè."""
    app = app_dir()
    try: (app / ".update_test").touch(); (app / ".update_test").unlink()
    except OSError: raise RuntimeError(tr("updater.folder_not_writable", path=str(app)))
    bat = TMP / "update.bat"; bat.write_text(SCRIPT, "utf-8")
    env = dict(os.environ, GS_PID=str(os.getpid()), GS_APP=str(app), GS_NEW=str(new), GS_TMP=str(TMP))
    subprocess.Popen(["cmd", "/c", str(bat)], env=env, cwd=tempfile.gettempdir(), close_fds=True,
                     creationflags=0x08000000 | 0x00000200)            # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
