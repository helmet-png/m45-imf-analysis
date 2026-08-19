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
import os
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CERT_DIR = ROOT / "certs"

UA = "m45-pipeline/1.0 (academic research; contact via repository)"

_ctx_cache = {}


def atomic_write(path: Path, data, encoding: str | None = None) -> Path:
    """先寫到同目錄的暫存檔，成功才 os.replace() 換過去。

    2026-08-19 CodeRabbit PR #65 指出：這個模組與 pipeline/bhac.py 直接
    write_bytes()／write_text() 到目標路徑，寫到一半被中斷（斷網、斷電、
    被砍行程）會留下截斷的檔案，而兩處的呼叫端都是「檔案存在就直接沿用」
    ——截斷的憑證 bundle 會讓之後每一次連線都驗證失敗，截斷的 52 MB
    BHAC15 原始檔則會被當成下載完成、解析出一份缺了尾段的網格，而且
    看不出來。跟 fit_real.py／inject_lowmass.py 的 atomic_savez() 是同一
    個理由、同一套寫法：os.replace() 在 POSIX 與 Windows 都保證原子性，
    不會有「新檔寫一半、舊檔已被砍」的中間狀態。暫存檔放同目錄，
    跨磁區的 replace 不保證原子。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        if encoding is None:
            tmp_path.write_bytes(data)
        else:
            tmp_path.write_text(data, encoding=encoding)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return path


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
    atomic_write(bundle_pem, roots + "\n" + extra, encoding="utf-8")
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
