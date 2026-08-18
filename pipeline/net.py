# -*- coding: utf-8 -*-
"""網路存取的共用設定。

有些學術服務（PARSEC 的 stev.oapd.inaf.it、BHAC15 的 perso.ens-lyon.fr）
沒有送出完整的中繼憑證，OpenSSL 補不上憑證鏈，所以 Python 會驗證失敗而
瀏覽器（會自己做 AIA chasing）不會。這裡把 certifi 的根憑證與各服務各自
抓下來的中繼憑證合併成一個 bundle，讓驗證能通過 —— 不是關掉驗證。

每個服務各自一組 `<chain_name>_chain.pem`／`<chain_name>_bundle.pem`
（見 `setup/setup_ca.ps1` 抓 PARSEC 的那份，其他服務照同樣手法抓），
用 `chain_name` 參數選要用哪一組，預設 `"parsec"` 保留舊行為不變。
"""
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CERT_DIR = ROOT / "certs"

UA = "m45-pipeline/1.0 (academic research; contact via repository)"

_ctx_cache = {}


def _build_bundle(chain_name: str) -> Path:
    """把 certifi 的根憑證與本地抓到的鏈合併成一個 bundle。"""
    import certifi

    chain_pem = CERT_DIR / f"{chain_name}_chain.pem"
    bundle_pem = CERT_DIR / f"{chain_name}_bundle.pem"
    roots = Path(certifi.where()).read_text(encoding="utf-8")
    if not chain_pem.exists():
        raise FileNotFoundError(
            f"找不到 {chain_pem}。\n"
            f"請先抓一次這個服務的憑證鏈（比照 setup/setup_ca.ps1 抓 PARSEC "
            f"的手法，把 target host 換成這個服務的網域）。"
        )
    extra = chain_pem.read_text(encoding="utf-8")
    CERT_DIR.mkdir(exist_ok=True)
    bundle_pem.write_text(roots + "\n" + extra, encoding="utf-8")
    return bundle_pem


def ssl_context(extra_chain: bool = False, chain_name: str = "parsec") -> ssl.SSLContext:
    """回傳 SSL context。extra_chain=True 時加上本地補的中繼憑證
    （用哪一組由 chain_name 選，預設 "parsec" 跟原本行為一致）。"""
    key = (bool(extra_chain), chain_name)
    if key in _ctx_cache:
        return _ctx_cache[key]
    if extra_chain:
        bundle_pem = CERT_DIR / f"{chain_name}_bundle.pem"
        bundle = bundle_pem if bundle_pem.exists() else _build_bundle(chain_name)
        ctx = ssl.create_default_context(cafile=str(bundle))
    else:
        ctx = ssl.create_default_context()
    _ctx_cache[key] = ctx
    return ctx


def get(url: str, timeout: int = 120, extra_chain: bool = False,
        chain_name: str = "parsec") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(
            req, timeout=timeout,
            context=ssl_context(extra_chain, chain_name)) as r:
        return r.read()


def post(url: str, data: bytes, timeout: int = 300,
         extra_chain: bool = False, chain_name: str = "parsec") -> tuple[bytes, str]:
    """POST 並回傳 (內容, 最終網址)。"""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(
            req, timeout=timeout,
            context=ssl_context(extra_chain, chain_name)) as r:
        return r.read(), r.geturl()
