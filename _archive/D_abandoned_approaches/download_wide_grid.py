# -*- coding: utf-8 -*-
"""下載金屬量範圍更寬的 isochrone 網格，用來做先驗敏感度測試。

為什麼需要：六參數擬合的金屬量後驗 95 百分位是 0.224，而先驗上界 0.25 ——
走者貼在牆上。這代表報出的金屬量不是資料算出來的，是我設的牆決定的。
而那道牆之所以在 0.25，只因為前一份網格下載到 +0.3 為止 ——
一個純技術的方便選擇變成了科學結論的決定因素。

把範圍放寬到 +0.6 重跑：若後驗仍貼在新的牆上，代表資料對金屬量毫無約束力；
若後驗停在範圍內，代表原本的牆確實在扭曲結果，新結果才可信。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import isochrones as iso

# PARSEC 單次最多 400 條 isochrone。金屬量才是這次要測的對象，
# 所以年齡步長放寬到 0.1（17 x 25 = 425 仍超標，故年齡範圍也收窄）。
p = iso.download_grid(logage_lo=7.7, logage_hi=8.3, dlogage=0.05,
                      mh_lo=-0.6, mh_hi=0.6, dmh=0.05)
t = iso.load_grid(p)
mh = np.unique(np.asarray(t["MH"], float))
print(f"\n讀入 {len(t):,} 列")
print(f"[M/H] 格點 {len(mh)} 個：{mh.min():.2f} 到 {mh.max():.2f}")
print(f"logAge 格點 {len(np.unique(np.asarray(t['logAge'], float)))} 個")
