# -*- coding: utf-8 -*-
"""讀 config.toml。

用 TOML 而不是 YAML：tomllib 是 Python 3.11+ 標準庫，不必多裝套件，
而且 TOML 支援註解（JSON 不支援），使用者可以直接在設定檔裡看到說明。
"""
from __future__ import annotations

from pathlib import Path

# tomllib 是 Python 3.11 才進標準庫的；3.10 以下要用 PyPI 上的 tomli
# （同一批作者、同一套 API——tomllib 本來就是從 tomli 收編進標準庫的，
# 所以 `import tomli as tomllib` 之後下游程式碼一行都不用改）。
#
# **2026-08-29 實際踩到才補上**：新接進來的運算節點是 Ubuntu 22.04，
# 內建 Python 3.10.12，`import tomllib` 直接 ModuleNotFoundError，
# 整條 pipeline 在載入設定檔這一步就死掉。原本的寫法等於隱性要求每台
# worker 都是 3.11+，但這個限制既沒寫進文件、也沒有任何檢查會提早
# 報錯——只有真的派工下去、跑到一半才會發現。
#
# 不改成「要求 worker 升級 Python」的理由：升級系統 Python 需要 root
# 權限，而 worker 常常是別人提供的機器（這次就是學長的），不該為了
# 我們的專案去動人家的系統環境；裝一個純 Python 的相容套件到使用者
# 家目錄就能解決，代價小得多。
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config.toml"


class Config:
    """薄薄一層包裝，讓 cfg.step1.radius_deg 這種寫法能用。"""

    def __init__(self, data: dict, path: Path | None = None):
        self._data = data
        self.path = path

    def __getattr__(self, name):
        # 底線開頭的一律不接手。否則 pickle（多行程平行時會用到）在還原物件時
        # 會先查 _data / __getstate__ 等屬性，此時 __init__ 尚未執行，
        # self._data 又觸發 __getattr__，造成無限遞迴。
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            v = self._data[name]
        except KeyError:
            raise AttributeError(
                f"設定檔裡沒有 '{name}'（可用的有：{', '.join(self._data)}）"
            ) from None
        return Config(v) if isinstance(v, dict) else v

    def get(self, name, default=None):
        v = self._data.get(name, default)
        return Config(v) if isinstance(v, dict) else v

    def __contains__(self, name):
        return name in self._data

    def __repr__(self):
        return f"Config({', '.join(self._data)})"

    def as_dict(self) -> dict:
        return self._data


def load(path: str | Path | None = None) -> Config:
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        raise FileNotFoundError(f"找不到設定檔 {p}")
    with open(p, "rb") as fh:
        return Config(tomllib.load(fh), p)
