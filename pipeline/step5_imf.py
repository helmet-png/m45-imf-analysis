# -*- coding: utf-8 -*-
"""第 5 步：質量函數與 IMF 斜率（傳統法的核心工具箱）。

======================================================================
【這支程式在做什麼】
======================================================================
回答一個問題：「這群成員星的質量分布，冪律斜率 α 是多少？」
用兩種作法算，重點在**兩者的差距**：

方法 A（樸素／傳統法）：把每顆觀測星當單星，用 isochrone 的質量-光度
    關係指派質量，再對質量做冪律擬合。這是傳統作法，也是文獻裡最常見的。
方法 B（前向模型）：把 IMF 斜率當成合成星團的自由參數，讓合成 CMD 去
    符合觀測。雙星在模型裡本來就存在，不需要事先挑掉。
    ⚠ 本檔的方法 B（fit_imf_forward）是早期的循序版本。目前頭條數字改由
    pipeline/joint_fit.py＋fit_real.py 產生，這裡的結果已不再被引用
    （見 results/RESULTS_LOG.md）。

兩者的差距就是「忽略未解析雙星對 IMF 斜率造成的偏差」的直接測量。
arXiv:2603.15779 指出這個偏差不隨樣本數縮小（統計誤差 ~1/sqrt(N) 遞減，
偏差是常數），樣本夠大時會「精確地錯」。

冪律擬合一律用未分箱資料的最大概似估計，不用分箱後的最小平方 ——
分箱方式會左右斜率，而且計數是 Poisson 不是 Gaussian。

這個檔案**沒有 main()，不能直接執行**。它是一個「工具箱模組」，由別的
程式 import 之後呼叫裡面的函式：
  - scripts/diagnostics/traditional_accounting.py：傳統法頭條數字
    （用 assign_masses、mle_powerlaw、exclude_confirmed_non_members）
  - scripts/drivers/run_pipeline.py --steps 5：舊版循序流程（四個主要函式都用）
  - fit_real.py：只用 exclude_confirmed_non_members 排除非成員
  - scripts/nbody_petar/nbody_summary_stats.py：對 N-body 的假觀測用同一個
    assign_masses 量 α，確保真資料與模擬資料用同一把尺

======================================================================
【(a) 引用的外部函式庫】
======================================================================
第三方套件：
  numpy（簡寫 np）  數值陣列運算。本檔用到：
      np.asarray    把輸入轉成數值陣列
      np.argsort    回傳「排序後各元素原本的位置」，用同一組位置去重排
                    好幾個陣列，它們才會保持一一對應
      np.interp     一維線性內插：已知一張 (x, y) 對照表，給新的 x 查出 y
      np.isfinite   判斷是不是正常數字（排除 NaN 與無限大）
      np.isin       判斷每個元素是否在某個集合裡
      np.where      依條件逐元素二選一
      np.arange     產生等間隔數列（方法 B 掃 α 用）
  astropy.table.Table
                    天文常用的表格型別。等時線就是用它存：每一列是一個
                    模型質量點，欄位有初始質量 Mini、G／BP／RP 絕對星等等。
  scipy.optimize.minimize_scalar
                    一維最佳化：在指定範圍內找出讓函數值最小的 x。本檔用來
                    找讓「負的對數概似」最小的 α（等於讓概似最大的 α）。
本專案其他模組（pipeline/step3_age.py）：
  COL_G, COL_BP, COL_RP  等時線表格裡 G、BP、RP 絕對星等的欄位名稱
  _Ext                   把三個消光係數 (g, bp, rp) 包在一起的小盒子
  IMF_BREAKS             各種 IMF 的分段定義。Kroupa：分界 0.01／0.08／0.5／200 M☉，
                         各段 dN/dm 冪次 −0.3／−1.3／−2.3
  draw_randoms           一次抽好合成星團需要的所有亂數，之後重複使用
  synth_populations      用給定參數生成一整群合成星（含雙星、測光誤差）
  hess                   把色光圖切成格子、數每格有幾顆星（Hess 圖）
  poisson_loglike        比較觀測與模型的 Hess 圖，回傳對數概似

======================================================================
【(b) 用到的參數與意義】
======================================================================
函式參數（由呼叫者傳入）：
  iso         一條等時線：固定年齡與金屬量下，各質量恆星的絕對星等
  dist_mod    距離模數 m−M，把絕對星等換成視星等要加的量
              （M45 距離約 135.5 pc，m−M ≈ 5.66）
  av          V 波段消光 A_V（星等）：星際塵埃讓星變暗的程度
  ext         消光係數：A_G = ext.g × A_V，A_BP、A_RP 同理
              （config.toml 的 [step2_cmd]：g=0.83、bp=1.08、rp=0.63）
  obs_mag     觀測星的 G 視星等陣列
  obs_color   觀測星的 BP−RP 顏色陣列；有給才做顏色一致性檢查
  color_tol   顏色檢查門檻，預設 0.4 星等
  masses      每顆星的質量陣列（M☉）
  m_lo, m_hi  冪律擬合的質量範圍（config 預設 0.30–2.50 M☉；
              traditional_accounting.py 的主表用 0.50–2.50）
  radii_deg   每顆星離星團中心的角距（度）
  edges       分環的邊界（度），config 預設 [0, 1, 2, 3, 5.1]
config.toml 裡被讀到的設定（只有 fit_imf_forward 用到）：
  [step5_imf]  fit_alpha_min／max／step = 1.5／3.2／0.05：方法 B 掃 α 的範圍與間隔
  [step3_age]  n_synthetic = 100000：合成星數
               binary_q_gamma = 0.0、binary_q_min = 0.1：雙星質量比 q 的分布
               hess_color_bins／hess_mag_bins = 40／50：Hess 圖格數
               hess_color_range／hess_mag_range：Hess 圖涵蓋的顏色與星等範圍
               model_hess_smooth = 0.0：模型 Hess 圖的平滑量
  [step2_cmd]  g_bright_limit = 4.0：比這更亮的星不用（測光飽和）
  [step1_membership]  g_mag_max = 18.0：比這更暗的星不用
                      random_seed = 42：亂數種子，固定以求可重現

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 162–199 行｜main_sequence_mass_luminosity()：從等時線建出「星等 → 質量」對照表
  核心 2｜第 232–266 行｜assign_masses()：每顆星用 G 星等查表得到質量，並做顏色檢查
  核心 3｜第 269–328 行｜mle_powerlaw()：對質量做截斷冪律的最大概似擬合，得到 α 與誤差
  核心 4｜第 359–404 行｜fit_imf_forward() 的迴圈：方法 B 逐一試 α（舊版，已不被引用）
其餘函式是輔助：exclude_confirmed_non_members（排除已確認的非成員）、
main_sequence_color（給顏色檢查用）、mass_function_by_radius（分環重複呼叫
mle_powerlaw）。

======================================================================
【(d) 整體流程】
======================================================================
方法 A（傳統法）：
  等時線 iso
    → main_sequence_mass_luminosity：絕對星等加上距離模數與消光換成視星等，
      只留「質量越大越亮」的主序段，得到 (G 星等, 質量) 對照表
    → assign_masses：每顆觀測星用 G 星等在對照表上內插出質量；
      顏色跟主序差超過 0.4 星等的星，質量設為 NaN（判定不是主序星）
    → mle_powerlaw：只留 m_lo–m_hi 內的星，找讓概似最大的 α，
      再用概似曲線在最高點的彎曲程度估誤差
    → 得到傳統法的 α_PDMF
方法 B（舊版前向模型）：
  觀測 CMD → 觀測 Hess 圖
    → 對每個候選 α：改 Kroupa 高質量段冪次 → 生成合成星團 → 合成 Hess 圖
      → 跟觀測 Hess 圖逐格比較，算對數概似
    → 概似最大的 α
質量分層：
  依離中心的距離把星分環 → 每一環各跑一次 mle_powerlaw → 得到 α(r)
"""
from __future__ import annotations

import numpy as np
from astropy.table import Table
from scipy.optimize import minimize_scalar

from .step3_age import (COL_G, COL_BP, COL_RP, _Ext, draw_randoms, hess,
                        poisson_loglike, synth_populations)

# 已確認的非成員天體，顏色跟真成員無異（assign_masses() 的顏色一致性檢查
# 抓不到），只有 RV+logg 兩個獨立訊號才抓得到，見 LIMITATIONS.md A6、
# check_giant_subgiant_contamination.py 的驗證過程。這是一個小型、有清楚
# 出處的名單，不是隨手刪資料——每一筆都附上發現時的判定依據。換一批
# `data/cmd_members.csv` 後要重跑 check_giant_subgiant_contamination.py
# 確認名單有沒有變化，不會自動更新（需要 data/astrophys.csv，這份檔案
# 依賴外部 TAP 查詢工具，不是每台機器都能重新產生）。
CONFIRMED_NON_MEMBER_IDS = {
    # logg_gspphot=4.00, Teff=3317K, RV=-93.65+/-5.08 km/s（偏離
    # bulk_rv=5.343 km/s 達 19.5 sigma），2026-08-13 查證
    64895139073954944,
    # D9 那顆亮星：RV=53.062+/-0.136 km/s（偏離 bulk_rv=5.343 km/s 達
    # 350 sigma，rv_nb_transits=13，不是單次量測雜訊），且不在 HR23
    # (Hunt & Reffert 2023) 的 M45 成員表裡（任何機率都沒有，見 C20
    # 重建出的原始「20 顆判定分歧」集合，check_c20_disagree_set.py）。
    # 三個獨立證據（RV、HR23 排除、顏色偏離主序）都指向同一個結論，
    # 2026-08-13 查證
    68409590552589184,
}


def exclude_confirmed_non_members(source_id) -> np.ndarray:
    """回傳跟 source_id 對齊的布林遮罩，True 表示應該排除（已確認非成員）。"""
    # ↓ 把 Gaia source_id 轉成 64 位元整數陣列（ID 很長，一般整數裝不下）
    sid = np.asarray(source_id, np.int64)
    # ↓ np.isin(A, B)：A 的每個元素若出現在 B 裡就是 True。
    #   B 是上面那份非成員名單，所以回傳的 True 就是「該排除的星」
    return np.isin(sid, np.array(list(CONFIRMED_NON_MEMBER_IDS), np.int64))


# ═══════════════ 核心 1：建立「星等 → 質量」對照表 ═══════════════
def main_sequence_mass_luminosity(iso: Table, dist_mod: float, av: float,
                                  ext) -> tuple[np.ndarray, np.ndarray]:
    """從 isochrone 取出單調的主序段，回傳 (視星等 G, 初始質量)。

    必須單調才能反過來由星等查質量。轉折點以上的演化階段 G 與質量不再單調
    （巨星比主序星亮但質量未必大），所以只取單調遞減的那一段。
    """
    # ↓ 取出等時線每個模型點的初始質量 Mini（單位 M☉），轉成浮點數陣列
    m = np.asarray(iso["Mini"], float)
    # ↓ 取出 G 絕對星等，換算成「從地球看 M45 時的」視星等：
    #   視星等 = 絕對星等 + 距離模數 + G 波段消光（ext.g × A_V）
    g = np.asarray(iso[COL_G], float) + dist_mod + ext.g * av
    # ↓ argsort 回傳「依質量由小到大排好時，各元素原本的位置」
    order = np.argsort(m)
    # ↓ 用同一組位置同時重排 m 與 g，兩個陣列才保持一一對應
    m, g = m[order], g[order]
    # 由低質量往高質量走，保留 G 持續變亮（數值變小）的部分
    # ↓ keep：每個點要不要保留，先全部設為 True
    keep = np.ones(len(m), bool)
    # ↓ gmin：「到目前為止最亮的星等」，從無限大開始（任何星都比它亮）
    gmin = np.inf
    for i in range(len(m)):
        # ↓ 這個點比之前所有點都亮（星等數字更小）→ 仍在主序上，保留，
        #   並更新最亮紀錄
        if g[i] < gmin:
            gmin = g[i]
        # ↓ 沒有更亮 → 已經過了主序轉折點（進入巨星等演化階段，
        #   同一個星等可能對應兩個質量），丟掉
        else:
            keep[i] = False
    # ↓ 只留下單調段：現在每個星等只對應一個質量，才能反查
    m, g = m[keep], g[keep]
    # 讓 G 遞增以便 np.interp 使用
    # ↓ np.interp 要求表格的 x（這裡是星等）由小到大排列，所以改依星等排序
    idx = np.argsort(g)
    # ↓ 回傳 (星等, 質量) 對照表，給 assign_masses 查表用
    return g[idx], m[idx]


def main_sequence_color(iso: Table, dist_mod: float, av: float,
                        ext) -> tuple[np.ndarray, np.ndarray]:
    """從 isochrone 取出單調主序段，回傳 (視星等 G, BP-RP 顏色)。

    跟 `main_sequence_mass_luminosity()` 用同一個「保留 G 持續變亮」的
    單調篩選，確保兩者定義的是同一段主序，查出來的質量與顏色可以對同一顆
    觀測星互相對照。
    """
    m = np.asarray(iso["Mini"], float)
    g = np.asarray(iso[COL_G], float) + dist_mod + ext.g * av
    # ↓ 顏色 = BP 星等 − RP 星等，再加上消光造成的「紅化」：
    #   (A_BP − A_RP) = (ext.bp − ext.rp) × A_V，塵埃讓星看起來更紅
    c = (np.asarray(iso[COL_BP], float) - np.asarray(iso[COL_RP], float)
         + (ext.bp - ext.rp) * av)
    # ↓ 以下的排序與單調篩選跟 main_sequence_mass_luminosity 完全相同，
    #   只是最後回傳的是顏色而不是質量
    order = np.argsort(m)
    g, c = g[order], c[order]
    keep = np.ones(len(m), bool)
    gmin = np.inf
    for i in range(len(g)):
        if g[i] < gmin:
            gmin = g[i]
        else:
            keep[i] = False
    g, c = g[keep], c[keep]
    idx = np.argsort(g)
    return g[idx], c[idx]


# ═══════════════ 核心 2：每顆星查質量（傳統法的關鍵假設：全當單星） ═══════════════
def assign_masses(obs_mag, iso: Table, dist_mod: float, av: float,
                  ext, obs_color=None, color_tol: float = 0.4) -> np.ndarray:
    """方法 A：把每顆星當單星，由 G 星等查出質量。

    `obs_color`（BP-RP）給定時，額外做顏色一致性檢查：算出該 G 星等對應
    的主序顏色，觀測顏色偏離超過 `color_tol` 星等就回傳 NaN，跟現有處理
    範圍外星等的機制一致。門檻抓 0.4：已知混入 `cmd_members.csv` 的白矮星
    （source_id=66697547870378368）bp_rp=-0.403，同一 G 星等的主序顏色
    偏離達 1 星等以上，遠超過未解析主序雙星的典型顏色偏移（通常 <0.2
    星等），0.4 足以擋下非主序天體、不會誤殺正常雙星（見 `LIMITATIONS.md`
    A6）。不給 `obs_color` 時完全不做這項檢查，行為與修正前一致。
    """
    # ↓ 先建出 (G 星等, 質量) 對照表（核心 1）
    g_ms, m_ms = main_sequence_mass_luminosity(iso, dist_mod, av, ext)
    # ↓ 對每顆觀測星做一維線性內插：np.interp(要查的 x, 表格 x, 表格 y, ...)
    #     obs_mag    每顆觀測星的 G 星等（要查的值）
    #     g_ms, m_ms 對照表的星等與質量
    #     left/right=np.nan  比表格最亮的還亮、或最暗的還暗的星不外推，直接給 NaN
    #   ⚠ 這一步就是「全當單星」：未解析雙星因為兩顆星的光加在一起而偏亮，
    #     會被查成一顆質量偏大的單星——這正是傳統法偏差的來源
    masses = np.interp(obs_mag, g_ms, m_ms, left=np.nan, right=np.nan)
    # ↓ 有給顏色才做顏色一致性檢查
    if obs_color is not None:
        # ↓ 同一段主序的 (G 星等, 顏色) 對照表
        g_c, c_ms = main_sequence_color(iso, dist_mod, av, ext)
        # ↓ 查出「如果這顆星真的在主序上，它應該是什麼顏色」
        pred_color = np.interp(obs_mag, g_c, c_ms, left=np.nan, right=np.nan)
        # ↓ 實際顏色與預測顏色差超過 color_tol → 標記為 bad（不是主序星，
        #   例如白矮星）
        bad = np.abs(np.asarray(obs_color, float) - pred_color) > color_tol
        # ↓ np.where(條件, 成立時的值, 不成立時的值)：bad 的星質量改成 NaN，
        #   之後 mle_powerlaw 會自動略過 NaN
        masses = np.where(bad, np.nan, masses)
    return masses


# ═══════════════ 核心 3：截斷冪律的最大概似擬合 ═══════════════
def mle_powerlaw(masses: np.ndarray, m_lo: float, m_hi: float) -> dict:
    """對 dN/dm ∝ m^(-alpha) 做最大概似估計（未分箱、含上下截斷）。

    截斷冪律的正規化常數：C = (1-alpha) / (m_hi^(1-alpha) - m_lo^(1-alpha))
    對數概似：lnL = n·ln(C) - alpha·sum(ln m)

    直覺：每顆星的質量 m 在這個冪律下出現的機率密度是 C·m^(-α)。
    所有星的機率相乘就是概似 L；取對數後乘法變加法，得到上面的 lnL。
    哪個 α 讓 lnL 最大，就是「最能解釋這批質量」的斜率。
    """
    # ↓ 轉成浮點數陣列
    m = np.asarray(masses, float)
    # ↓ 只保留正常數字（排除 assign_masses 給的 NaN）且落在 m_lo–m_hi 之間的星
    m = m[np.isfinite(m) & (m >= m_lo) & (m <= m_hi)]
    # ↓ n：真正參與擬合的星數
    n = len(m)
    # ↓ 少於 10 顆就不擬合，直接回傳 NaN（樣本太少，斜率沒有意義）
    if n < 10:
        return {"alpha": np.nan, "alpha_err": np.nan, "n": n}
    # ↓ 先算好 Σ ln m（每顆星質量取自然對數後全部相加）。
    #   不管試哪個 α 都要用到它，所以只算一次
    slog = np.sum(np.log(m))

    def neg_ll(alpha):
        # 負的對數概似 −lnL：數值越小代表這個 α 越能解釋資料。
        # 最佳化器只會「找最小值」，所以把 lnL 加負號交給它。
        # ↓ α = 1 時公式裡的 (1−α) 會變成 0、分母也變 0，往旁邊偏一點點避開
        if abs(alpha - 1.0) < 1e-8:
            alpha = 1.0 + 1e-8
        # ↓ 歸一化常數的分母：m_hi^(1−α) − m_lo^(1−α)
        denom = m_hi ** (1 - alpha) - m_lo ** (1 - alpha)
        # ↓ 分母為 0、或算出的常數 C ≤ 0（機率密度不可能是負的）時回傳超大值，
        #   等於告訴最佳化器「不要選這個 α」
        if denom == 0 or (1 - alpha) / denom <= 0:
            return 1e18
        # ↓ C：讓機率密度在 m_lo 到 m_hi 之間積分剛好等於 1 的常數
        c = (1 - alpha) / denom
        # ↓ lnL = n·ln C − α·Σ ln m，回傳 −lnL
        return -(n * np.log(c) - alpha * slog)

    # ↓ 在 α = 0.1 到 5.0 之間找讓 neg_ll 最小的 α
    #     neg_ll          要最小化的函數
    #     bounds=(0.1, 5.0)  搜尋範圍
    #     method="bounded"  限制在範圍內搜尋（有界版的 Brent 法）
    r = minimize_scalar(neg_ll, bounds=(0.1, 5.0), method="bounded")
    # ↓ r.x 就是找到的最佳 α
    alpha = float(r.x)
    # 用概似曲率估標準誤（二階數值微分）
    # ↓ h：數值微分的步長
    h = 1e-3
    # ↓ 二階中央差分：在 α−h、α、α+h 各算一次 −lnL，估計曲線在最低點有多「彎」。
    #   越彎（d2 越大），α 稍微偏離就讓資料變得很不可能，代表 α 被約束得越緊
    d2 = (neg_ll(alpha + h) - 2 * neg_ll(alpha) + neg_ll(alpha - h)) / h ** 2
    # ↓ 標準誤 = 1/√d2（大樣本下的常態近似）；d2 ≤ 0 表示不是最低點，給 NaN
    #   ⚠ 這個誤差只反映「星數有限」的抽樣雜訊，不含雙星、等時線等系統效應。
    #     traditional_accounting.py 用注入回收實測，它低估約 4 倍
    err = float(1.0 / np.sqrt(d2)) if d2 > 0 else np.nan
    return {"alpha": alpha, "alpha_err": err, "n": n,
            "m_lo": m_lo, "m_hi": m_hi}


def fit_imf_forward(cfg, obs_color, obs_mag, iso: Table, errmodel,
                    dist_mod: float, av: float, fbin: float,
                    verbose: bool = True) -> dict:
    """方法 B：把 IMF 斜率當自由參數，用前向模型擬合。

    只改高質量端那一段的冪次（Kroupa 分段冪律的 m > 0.5 M☉ 段），
    因為觀測的星等下限決定了低質量端根本沒有涵蓋到足以約束的資料。

    ⚠ 舊版：年齡、消光、雙星比例都是從前幾步固定下來的值，只有 α 在變。
    目前頭條數字改用 pipeline/joint_fit.py 讓所有參數一起變。
    """
    from .step3_age import IMF_BREAKS
    # ↓ 從 config 取出三組設定：c3＝第 3 步、c2＝第 2 步、c5＝第 5 步
    c3, c2 = cfg.step3_age, cfg.step2_cmd
    c5 = cfg.step5_imf
    # ↓ 三個波段的消光係數包成 ext
    ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)
    # 共用亂數，理由同 step3/step4：讓概似差異只反映 alpha 的差異
    seed = cfg.step1_membership.random_seed

    # ↓ Hess 圖涵蓋的顏色範圍與星等範圍
    crange, mrange = tuple(c3.hess_color_range), tuple(c3.hess_mag_range)
    # ↓ 把觀測 CMD 切成 40×50 格、數每格星數 → 觀測 Hess 圖
    obs_h = hess(obs_color, obs_mag, c3.hess_color_bins, c3.hess_mag_bins,
                 crange, mrange)
    # ↓ 觀測星數：算概似時用來把模型機率換成每格的預期星數
    n_obs = len(obs_color)

    # ═══════════════ 核心 4：逐一試 α（方法 B，舊版） ═══════════════
    # ↓ 要試的 α：1.50, 1.55, …, 3.20（+1e-9 是為了讓終點 3.20 也被包含）
    alphas = np.arange(c5.fit_alpha_min, c5.fit_alpha_max + 1e-9,
                       c5.fit_alpha_step)
    # ↓ 準備一個陣列存每個 α 的對數概似，先全部填 −∞
    ll = np.full(len(alphas), -np.inf)
    # ↓ 一次抽好 n_synthetic 顆合成星要用的亂數，所有 α 共用同一批
    draws = draw_randoms(c3.n_synthetic, np.random.default_rng(seed))
    # ↓ 備份原本的 Kroupa 定義，迴圈結束後要還原
    orig = IMF_BREAKS["kroupa"]
    try:
        for i, a in enumerate(alphas):
            # 暫時把高質量段的冪次換成 -a
            # ↓ orig[0] 是分界質量（不變）；冪次只換第三段（m > 0.5 M☉）。
            #   IMF_BREAKS 存的是 dN/dm 的冪次，斜率 α 對應冪次 −α，所以加負號
            IMF_BREAKS["kroupa"] = (orig[0], [orig[1][0], orig[1][1], -a])
            # ↓ 用這個 α 生成一整群合成星：
            #     iso, dist_mod, av   等時線、距離、消光（固定值）
            #     fbin                雙星比例（固定值）
            #     binary_q_gamma, binary_q_min  雙星質量比的分布
            #     "kroupa"            用剛剛改過的 Kroupa IMF 抽質量
            #     errmodel            加上跟觀測同等級的測光誤差
            #     draws               共用的亂數
            #     g_faint, g_bright   只留跟觀測同樣星等範圍內的星
            pop = synth_populations(
                iso, c3.n_synthetic, dist_mod, av, fbin,
                c3.binary_q_gamma, c3.binary_q_min, "kroupa",
                errmodel, ext, draws,
                g_faint=cfg.step1_membership.g_mag_max,
                g_bright=c2.g_bright_limit)
            # ↓ 合成星的 Hess 圖（跟觀測用同樣的格子）
            mod_h = hess(pop["color"], pop["mag"], c3.hess_color_bins,
                         c3.hess_mag_bins, crange, mrange,
                         smooth=c3.model_hess_smooth)
            # ↓ 觀測與合成的 Hess 圖逐格比較，算 Poisson 對數概似
            ll[i] = poisson_loglike(obs_h, mod_h, n_obs)
            if verbose:
                print(f"  alpha={a:.2f}  lnL={ll[i]:.1f}", flush=True)
    finally:
        # ↓ 不管迴圈有沒有出錯都把 Kroupa 定義還原，避免影響之後呼叫的程式
        IMF_BREAKS["kroupa"] = orig

    # ↓ 概似最大的那個 α 就是方法 B 的答案（解析度就是掃描間隔 0.05）
    k = int(np.argmax(ll))
    return {"alpha": float(alphas[k]), "loglike": float(ll[k]),
            "alphas": alphas, "loglike_grid": ll}


def mass_function_by_radius(masses, radii_deg, edges, m_lo, m_hi) -> Table:
    """量質量函數隨半徑的變化 —— 質量分層的直接測量。

    M45 已動力學演化，低質量星會優先被甩到外圍。若在有限半徑內量 IMF，
    量到的 alpha 會偏平（偏向重星）。把它當成要測量的物理量而不是要消除的誤差。
    """
    rows = []
    r = np.asarray(radii_deg, float)
    m = np.asarray(masses, float)
    # ↓ zip(edges[:-1], edges[1:]) 把邊界兩兩配對成環：(0,1)、(1,2)、(2,3)、(3,5.1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        # ↓ 選出落在這一環內、且有質量的星
        sel = (r >= lo) & (r < hi) & np.isfinite(m)
        # ↓ 對這一環的星做一次核心 3 的冪律擬合
        fit = mle_powerlaw(m[sel], m_lo, m_hi)
        # ↓ 記下這一環的結果：內外半徑、星數、α、誤差、質量中位數
        rows.append({
            "r_lo": lo, "r_hi": hi, "n": fit["n"],
            "alpha": fit["alpha"], "alpha_err": fit["alpha_err"],
            "median_mass": float(np.nanmedian(m[sel])) if sel.sum() else np.nan,
        })
    return Table(rows)
