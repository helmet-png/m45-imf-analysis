# -*- coding: utf-8 -*-
"""網路存取的共用設定。

PARSEC 的 isochrone 服務（stev.oapd.inaf.it）沒有送出中繼憑證，OpenSSL 補不上
憑證鏈，所以 Python 會驗證失敗而瀏覽器不會。這裡把 certifi 的根憑證與
setup_ca.ps1 抓下來的中繼憑證合併成一個 bundle，讓驗證能通過 ——
不是關掉驗證。
"""
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CERT_DIR = ROOT / "certs"
CHAIN_PEM = CERT_DIR / "parsec_chain.pem"
BUNDLE_PEM = CERT_DIR / "parsec_bundle.pem"

UA = "m45-pipeline/1.0 (academic research; contact via repository)"

_ctx_cache = {}


def _build_bundle() -> Path:
    """把 certifi 的根憑證與本地抓到的鏈合併成一個 bundle。"""
    import certifi

    roots = Path(certifi.where()).read_text(encoding="utf-8")
    if not CHAIN_PEM.exists():
        raise FileNotFoundError(
            f"找不到 {CHAIN_PEM}。\n"
            f"請先執行一次：powershell -ExecutionPolicy Bypass -File setup_ca.ps1"
        )
    extra = CHAIN_PEM.read_text(encoding="utf-8")
    CERT_DIR.mkdir(exist_ok=True)
    BUNDLE_PEM.write_text(roots + "\n" + extra, encoding="utf-8")
    return BUNDLE_PEM


def ssl_context(extra_chain: bool = False) -> ssl.SSLContext:
    """回傳 SSL context。extra_chain=True 時加上本地補的中繼憑證。"""
    key = bool(extra_chain)
    if key in _ctx_cache:
        return _ctx_cache[key]
    if extra_chain:
        bundle = BUNDLE_PEM if BUNDLE_PEM.exists() else _build_bundle()
        ctx = ssl.create_default_context(cafile=str(bundle))
    else:
        ctx = ssl.create_default_context()
    _ctx_cache[key] = ctx
    return ctx


def get(url: str, timeout: int = 120, extra_chain: bool = False) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(
            req, timeout=timeout, context=ssl_context(extra_chain)) as r:
        return r.read()


def post(url: str, data: bytes, timeout: int = 300,
         extra_chain: bool = False) -> tuple[bytes, str]:
    """POST 並回傳 (內容, 最終網址)。"""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(
            req, timeout=timeout, context=ssl_context(extra_chain)) as r:
        return r.read(), r.geturl()
