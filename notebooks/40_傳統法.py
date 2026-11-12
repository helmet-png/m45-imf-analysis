# -*- coding: utf-8 -*-
# %% [markdown]
# # 階段 40：傳統法，從成員星表到 α
#
# 這份筆記把傳統法最短的一條路走一遍：**讀成員星表 → 用等時線把亮度換成
# 質量 → 對質量做冪律擬合 → 得到 α**。只做「全當單星」這一種變體，
# 最後跟正式結果檔比對，數字應該一模一樣。
#
# 計算全部呼叫 `pipeline/` 裡的正式函式，這裡沒有另外寫一份。
# 完整版（五種雙星處理變體＋假資料測偏差）是
# `scripts/diagnostics/traditional_accounting.py`。
#
# 執行方式：在 repo 根目錄 `python notebooks/40_傳統法.py`；
# 或用 VS Code 開啟，`# %%` 會被當成一格一格的 notebook 儲存格。
# 需要等時線快取（`isochrones/` 底下的 PARSEC 檔，第一次跑主流程時下載）。

# %%
import sys
from pathlib import Path

import numpy as np

# 這個檔案在 notebooks/ 底下，repo 根目錄是上一層
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline import config as cfgmod, isochrones as isomod          # noqa: E402
from pipeline.step3_age import _Ext                                   # noqa: E402
from pipeline.step5_imf import (assign_masses, mle_powerlaw,          # noqa: E402
                                exclude_confirmed_non_members)
from pipeline.table_compat import Table                               # noqa: E402
from measure_overconfidence import GRID                               # noqa: E402

cfg = cfgmod.load()

# %% [markdown]
# ## 1. 讀成員星表
#
# `data/cmd_members.csv` 是階段 30 的產物：成員機率 ≥ 0.7、且通過測光品質
# 篩選的星。另外排除幾顆事後確認不是成員的星（`LIMITATIONS.md` A6）。

# %%
stars = Table.read(REPO / "data" / "cmd_members.csv", format="csv")
color = np.asarray(stars["bp_rp"], float)            # 顏色 BP−RP
mag = np.asarray(stars["phot_g_mean_mag"], float)    # G 視星等
keep = np.isfinite(color) & np.isfinite(mag)
keep &= ~exclude_confirmed_non_members(np.asarray(stars["source_id"], np.int64))
color, mag = color[keep], mag[keep]
print(f"星表 {len(stars)} 顆，使用 {len(mag)} 顆")

# %% [markdown]
# ## 2. 距離模數
#
# 視星等 − 絕對星等 = 5·log10(距離/pc) − 5。距離用所有成員視差的中位數
# （先扣掉 Gaia 視差零點 −0.017 mas）。

# %%
plx = np.asarray(stars["parallax"], float)
plx_corrected = np.median(plx) - cfg.step3_age.parallax_zero_point
distance_pc = 1000.0 / plx_corrected
dist_mod = 5.0 * np.log10(distance_pc) - 5.0
print(f"距離 {distance_pc:.1f} pc，距離模數 {dist_mod:.3f}")

# %% [markdown]
# ## 3. 取一條等時線
#
# 等時線是「同年齡的星，各質量該有多亮」的理論表。傳統法自己定不出年齡與
# 消光，這裡借用前向模型的結果：log(年齡) = 8.033、A_V = 0.383、金屬量 0。
# `isochrone_at()` 取網格上最接近的那一條（網格間距 0.05，所以實際拿到 8.05）。

# %%
LOGAGE, AV = 8.033, 0.383
grid = isomod.load_grid(isomod.CACHE / GRID)
iso = isomod.isochrone_at(grid, LOGAGE, 0.0)
c2 = cfg.step2_cmd
ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)   # 消光係數
print(f"等時線共 {len(iso)} 個質量點")

# %% [markdown]
# ## 4. 亮度換質量
#
# `assign_masses()`：把等時線的絕對星等加上距離模數與消光，得到「G 視星等 →
# 質量」的對照表，每顆星查表內插。顏色跟主序差太多（超過 0.4 星等）的星
# 不是主序星，質量記為 NaN。**這一步把每個光點都當成一顆單星**，
# 未解析雙星的問題就出在這裡。

# %%
masses = assign_masses(mag, iso, dist_mod, AV, ext, obs_color=color)
M_LO, M_HI = 0.50, cfg.step5_imf.mass_max
in_range = (masses >= M_LO) & (masses <= M_HI)
print(f"查得到質量的星 {int(np.isfinite(masses).sum())} 顆；"
      f"其中 {M_LO}–{M_HI} M☉ 有 {int(in_range.sum())} 顆")

# %% [markdown]
# ## 5. 冪律擬合
#
# 假設 dN/dm ∝ m^(−α)。`mle_powerlaw()` 找出讓「看到這批質量」的機率最大的
# α（最大概似估計），誤差由概似曲線在最高點的彎曲程度算出。

# %%
fit = mle_powerlaw(masses, M_LO, M_HI)
print(f"α = {fit['alpha']:.4f} ± {fit['alpha_err']:.4f}（{fit['n']} 顆）")

# %% [markdown]
# ## 6. 跟正式結果比對
#
# `results/traditional_accounting_v2.npz` 是 `traditional_accounting.py`
# 在 2026-08-10 存下的結果。**它比現在的程式舊**：2026-08-14 之後程式多了
# 「排除已確認非成員」這一步（第 1 節），結果檔沒有重新產生。所以分兩步比：
# 先關掉排除，確認能重現結果檔的數字；再看排除造成多少差異。

# %%
ref = np.load(REPO / "results" / "traditional_accounting_v2.npz", allow_pickle=True)
key = "real::config C 最終值(8.033,0.383)::0.50-2.50對齊::全當單星::alpha"
alpha_ref = float(ref[key])

all_mag = np.asarray(stars["phot_g_mean_mag"], float)
old = mle_powerlaw(assign_masses(all_mag, iso, dist_mod, AV, ext), M_LO, M_HI)
print(f"結果檔      α = {alpha_ref:.4f}")
print(f"不排除重算  α = {old['alpha']:.4f}（{old['n']} 顆），差 {old['alpha'] - alpha_ref:+.1e}")
print(f"現行程式    α = {fit['alpha']:.4f}（{fit['n']} 顆），"
      f"比結果檔多 {fit['alpha'] - alpha_ref:+.4f}")
assert abs(old["alpha"] - alpha_ref) < 1e-6, "重現不了結果檔的數字，先查原因再往下"

# %% [markdown]
# 少一顆星，α 就動了 0.013；統計誤差是 0.118，所以結論不變，
# 但引用傳統法的數字時要注意結果檔與現行程式差在這裡。
