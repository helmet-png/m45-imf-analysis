# -*- coding: utf-8 -*-
"""astropy.table.Table 的極簡替代品，只用 numpy 實作。

**為什麼需要**：astropy 的相依套件 `pyerfa` 沒有 ARM64 wheel，而這台機器是
Snapdragon X（ARM64）。實測原生 ARM64 比 x64 模擬快 13.9 倍
（`gaussian_kde` 單項快 38 倍），但只要 import astropy 就得退回模擬的 x64。

我們對 Table 的用法只有「讀 CSV／空白分隔文字、依欄名取陣列、遮罩篩選、
加欄、寫回檔案」這幾種，用 numpy 重做並不難，換掉就能跑原生。

**沒有實作的**：單位、遮罩欄、metadata、多維欄位、astropy 特有的 I/O 格式。
若日後需要那些，就該退回用 astropy 而不是把這裡撐大。
"""
from __future__ import annotations

import csv as _csv
from pathlib import Path

import numpy as np


def _to_array(values):
    """把一欄字串轉成適當型別的 numpy 陣列。整數優先，其次浮點，最後字串。"""
    arr = np.asarray(values)
    if arr.dtype.kind in "ifb":
        return arr
    s = arr.astype(str)
    blank = (s == "") | (s == "--") | (np.char.lower(s) == "nan")
    try:
        # source_id 這種 19 位數必須保持整數，轉成 float 會失去精度
        if not blank.any():
            return s.astype(np.int64)
    except (ValueError, OverflowError):
        pass
    try:
        out = np.empty(len(s), float)
        out[blank] = np.nan
        if (~blank).any():
            out[~blank] = s[~blank].astype(float)
        return out
    except ValueError:
        return s


class Table:
    """欄名 -> numpy 陣列 的薄包裝。"""

    def __init__(self, data=None):
        self._cols: dict[str, np.ndarray] = {}
        if data is None:
            return
        if isinstance(data, dict):
            for k, v in data.items():
                self._cols[str(k)] = np.asarray(v)
        elif isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
            keys = list(data[0])
            for k in keys:
                self._cols[str(k)] = _to_array([row[k] for row in data])
        else:
            raise TypeError(f"不支援的輸入型別：{type(data)}")

    # ---------- 讀寫 ----------
    @classmethod
    def read(cls, path, format=None, comment="#", names=None, **kw):
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if format == "csv":
            rows = list(_csv.reader([ln for ln in text if ln.strip()]))
            header, body = rows[0], rows[1:]
        else:
            # ascii：空白分隔。註解行以 comment 開頭；欄名可由 names 指定，
            # 否則取第一行非註解行。
            data_lines = [ln for ln in text
                          if ln.strip() and not ln.lstrip().startswith(comment)]
            if names is not None:
                header, body = list(names), [ln.split() for ln in data_lines]
            else:
                header = data_lines[0].split()
                body = [ln.split() for ln in data_lines[1:]]
        t = cls()
        ncol = len(header)
        cols = [[] for _ in range(ncol)]
        for row in body:
            if len(row) < ncol:
                row = list(row) + [""] * (ncol - len(row))
            for i in range(ncol):
                cols[i].append(row[i])
        for name, vals in zip(header, cols):
            t._cols[name] = _to_array(vals)
        return t

    def write(self, path, format="csv", overwrite=False):
        path = Path(path)
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        names = list(self._cols)
        n = len(self)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            if format == "csv":
                w = _csv.writer(fh)
                w.writerow(names)
                for i in range(n):
                    w.writerow([self._cols[c][i] for c in names])
            else:
                fh.write(" ".join(names) + "\n")
                for i in range(n):
                    fh.write(" ".join(str(self._cols[c][i]) for c in names) + "\n")

    # ---------- 基本存取 ----------
    @property
    def colnames(self):
        return list(self._cols)

    def __len__(self):
        return len(next(iter(self._cols.values()))) if self._cols else 0

    def __contains__(self, name):
        return name in self._cols

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._cols[key]
        if isinstance(key, list) and key and isinstance(key[0], str):
            t = Table()
            for c in key:
                t._cols[c] = self._cols[c]
            return t
        # 遮罩或索引陣列 -> 篩選後的新表
        idx = np.asarray(key)
        t = Table()
        for c, v in self._cols.items():
            t._cols[c] = v[idx]
        return t

    def __setitem__(self, name, values):
        self._cols[str(name)] = np.asarray(values)

    def __iter__(self):
        """逐列迭代，每列是欄名 -> 值 的 dict。"""
        for i in range(len(self)):
            yield {c: v[i] for c, v in self._cols.items()}

    def rename_column(self, old, new):
        self._cols = {(new if k == old else k): v for k, v in self._cols.items()}

    def pprint(self, max_width=None, max_lines=None):
        names = list(self._cols)
        widths = [max(len(str(n)), 10) for n in names]
        print("  ".join(str(n).rjust(w) for n, w in zip(names, widths)))
        for i in range(len(self)):
            print("  ".join(str(self._cols[c][i])[:w].rjust(w)
                            for c, w in zip(names, widths)))
