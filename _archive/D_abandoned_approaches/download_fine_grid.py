# -*- coding: utf-8 -*-
"""下載金屬量較密的 isochrone 網格，供六參數聯合擬合使用。

現有網格的 [M/H] 只有 -0.2 到 0.2、步長 0.1，共 5 個格點 —— 當作連續參數擬合
太粗（isochrone_at 取最近格點，等於金屬量的解析度只有 0.1）。

年齡範圍收窄到 7.6–8.4：全域網格為了通用性涵蓋 7.0–9.5，但這次只擬合 M45，
不需要那麼寬，收窄可以把檔案控制在合理大小。
金屬量範圍放寬到 -0.5 – +0.3：涵蓋銀河系疏散星團的大致範圍，
之後套用到其他星團時不必重下。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import isochrones as iso

p = iso.download_grid(logage_lo=7.6, logage_hi=8.4, dlogage=0.05,
                      mh_lo=-0.5, mh_hi=0.3, dmh=0.05)
t = iso.load_grid(p)
import numpy as np
print(f"\n讀入 {len(t):,} 列")
print(f"logAge 格點 {len(np.unique(np.asarray(t['logAge'], float)))} 個")
print(f"[M/H] 格點 {len(np.unique(np.asarray(t['MH'], float)))} 個")
print(f"[M/H] 值：{np.unique(np.asarray(t['MH'], float))}")
