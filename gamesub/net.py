"""Một requests.Session dùng chung với SSLContext nạp CA đúng 1 lần.
Mặc định mỗi kết nối TLS mới urllib3 nạp lại chứng chỉ (Windows: ~120k lần đọc đĩa/kết nối) -> mỗi lần tra từ lại đọc đĩa."""
import ssl, threading
import requests
from requests.adapters import HTTPAdapter

class _CtxAdapter(HTTPAdapter):
    def __init__(self, ctx, **kw): self.ctx = ctx; super().__init__(**kw)
    def init_poolmanager(self, *a, **kw): kw["ssl_context"] = self.ctx; return super().init_poolmanager(*a, **kw)
    def cert_verify(self, conn, url, verify, cert):
        super().cert_verify(conn, url, verify, cert)
        conn.ca_certs = conn.ca_cert_dir = None              # CA đã có trong ctx -> urllib3 khỏi nạp lại mỗi kết nối

_s, _lock = None, threading.Lock()

def session():
    global _s
    with _lock:
        if _s is None:
            import certifi                                     # verify + check_hostname như mặc định của requests
            ctx = ssl.create_default_context(cafile=certifi.where())
            _s = requests.Session(); _s.mount("https://", _CtxAdapter(ctx, pool_maxsize=8))
        return _s
