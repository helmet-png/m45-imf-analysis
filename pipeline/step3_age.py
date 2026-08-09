# -*- coding: utf-8 -*-
"""第 3 步：用前向模型（生成合成星團）擬合年齡與消光。

不是「拿一條 isochrone 去擬合主序中心線、把雙星當離群值剔除」，而是：
給定參數 -> 生成一整群合成星（含雙星、含實測等級的測光誤差）-> 比較
合成 CMD 與觀測 CMD 的整片點雲分布 -> 調參數重生成。

好處是雙星成為模型參數而非雜訊，年齡與雙星比例可同時求解、不需迭代；
且同一個生成模型第 4、5 步都能用。
"""
from __future__ import annotations

import numpy as np

from .table_compat import Table

# isochrone 表裡的 Gaia 星等欄位。fSB = 球對稱非自轉的基準值；
# _i00.._i90 是自轉模型在不同傾角下的值，我們用 omega_i=0 所以取 fSB。
COL_G, COL_BP, COL_RP = "G_fSBmag", "G_BP_fSBmag", "G_RP_fSBmag"


IMF_BREAKS = {
    # 名稱: (分界質量, 各段的 dN/dm 冪次)
    "salpeter": ([0.01, 200.0], [-2.35]),
    "kroupa": ([0.01, 0.08, 0.5, 200.0], [-0.3, -1.3, -2.3]),
    # 低質量端用 Kroupa 的分段冪律近似 Chabrier 的對數常態
    "chabrier": ([0.01, 0.08, 1.0, 200.0], [-0.3, -1.3, -2.3]),
}


def _clip_segments(breaks, slopes, m_min, m_max):
    """把分段冪律裁切到 [m_min, m_max]，回傳 (分界, 冪次)。"""
    b, s = [], []
    for i, a in enumerate(slopes):
        lo, hi = max(breaks[i], m_min), min(breaks[i + 1], m_max)
        if hi <= lo:
            continue
        if not b:
            b.append(lo)
        b.append(hi)
        s.append(a)
    return b, s


def sample_imf(u: np.ndarray, kind: str, m_min: float,
               m_max: float) -> np.ndarray:
    """由預先抽好的均勻亂數 u 反解出初始質量。

    **每顆星只消耗一個亂數，且與 IMF 參數無關** —— 這是「共用亂數」能成立的
    前提。若改用 rng.choice 先挑分段、再抽段內位置，改變 IMF 參數會改變各段
    被挑中的數量，隨機串流就會岔開，概似曲面上會混進蒙地卡羅雜訊，
    看起來像是參數造成的差異其實只是換了一組亂數。
    """
    u = np.asarray(u, float)
    breaks, slopes = IMF_BREAKS.get(kind, IMF_BREAKS["kroupa"])
    b, s = _clip_segments(breaks, slopes, m_min, m_max)
    if len(s) == 0:
        return np.full(len(u), m_min)

    # 各段係數由連續性決定：C_{i+1} * b^a_{i+1} = C_i * b^a_i
    coef = [1.0]
    for i in range(len(s) - 1):
        coef.append(coef[-1] * b[i + 1] ** (s[i] - s[i + 1]))

    def seg_integral(c, a, lo, hi):
        if abs(a + 1) < 1e-9:
            return c * (np.log(hi) - np.log(lo))
        return c * (hi ** (a + 1) - lo ** (a + 1)) / (a + 1)

    w = np.array([seg_integral(coef[i], s[i], b[i], b[i + 1])
                  for i in range(len(s))], float)
    w /= w.sum()
    cum = np.concatenate([[0.0], np.cumsum(w)])
    cum[-1] = 1.0

    out = np.empty(len(u))
    for i, a in enumerate(s):
        m = (u >= cum[i]) & (u < cum[i + 1])
        if not m.any():
            continue
        # 把 u 換算成該段內的相對位置
        v = (u[m] - cum[i]) / max(cum[i + 1] - cum[i], 1e-15)
        lo, hi = b[i], b[i + 1]
        if abs(a + 1) < 1e-9:
            out[m] = lo * (hi / lo) ** v
        else:
            out[m] = (lo ** (a + 1)
                      + v * (hi ** (a + 1) - lo ** (a + 1))) ** (1.0 / (a + 1))
    return out


def draw_randoms(n: int, rng: np.random.Generator) -> dict:
    """一次抽好所有亂數，之後不論參數怎麼變都重複使用同一批。

    這樣概似曲面的起伏才純粹反映參數差異，而不是換了一組隨機數。

    z_av 與 u_sel 是後來追加的（差異消光、測光完整度），**刻意排在最後抽**：
    前面六組的抽取次序完全沒變，所以舊結果仍然逐位元可重現。
    """
    return {
        "u_mass": rng.random(n),
        "u_bin": rng.random(n),
        "u_q": rng.random(n),
        "z_g": rng.normal(0, 1, n),
        "z_bp": rng.normal(0, 1, n),
        "z_rp": rng.normal(0, 1, n),
        "z_av": rng.normal(0, 1, n),    # 差異消光：每顆星的 A_V 偏移
        "z_snr": rng.normal(0, 1, n),   # 訊噪比在關係式周圍的散布
        "u_sel": rng.random(n),         # BP/RP 流量超額那一刀的存活判定
    }


def _interp_err(gmag: np.ndarray, errmodel: dict, key: str) -> np.ndarray:
    return np.interp(gmag, errmodel["g"], errmodel[key],
                     left=errmodel[key][0], right=errmodel[key][-1])


def synth_populations(iso: Table, n: int, dist_mod: float, av: float,
                      binary_fraction: float, q_gamma: float, q_min: float,
                      imf_kind: str, errmodel: dict, ext, draws: dict,
                      g_faint: float | None = None,
                      g_bright: float | None = None) -> dict:
    """生成一群合成星，回傳含單星／雙星標記的完整結果。

    雙星處理：抽一個伴星質量 m2 = q·m1，兩顆星的**流量相加**後再轉回星等。
    這正是「未解析雙星」的物理 —— 望遠鏡看到的是一個光點，亮度是兩顆之和。

    `draws` 由 draw_randoms() 預先產生。所有參數組合共用同一批亂數，
    這樣概似曲面的起伏才只反映參數差異，不混入蒙地卡羅雜訊。
    """
    mi = np.asarray(iso["Mini"], float)
    order = np.argsort(mi)
    mi = mi[order]
    gi = np.asarray(iso[COL_G], float)[order]
    bpi = np.asarray(iso[COL_BP], float)[order]
    rpi = np.asarray(iso[COL_RP], float)[order]

    m1 = sample_imf(draws["u_mass"][:n], imf_kind, mi.min(), mi.max())

    def mags(m):
        return (np.interp(m, mi, gi), np.interp(m, mi, bpi), np.interp(m, mi, rpi))

    g1, bp1, rp1 = mags(m1)

    # 門檻式判定：改變 binary_fraction 只移動門檻，不改變消耗的亂數
    is_bin = draws["u_bin"][:n] < binary_fraction
    q_all = np.zeros(n)
    if is_bin.any():
        # f(q) ∝ q^gamma，逆變換取樣
        u = draws["u_q"][:n][is_bin]
        if abs(q_gamma + 1) < 1e-9:
            q = q_min * (1.0 / q_min) ** u
        else:
            q = (q_min**(q_gamma + 1)
                 + u * (1.0 - q_min**(q_gamma + 1))) ** (1.0 / (q_gamma + 1))
        q_all[is_bin] = q
        m2 = np.clip(m1[is_bin] * q, mi.min(), None)
        g2, bp2, rp2 = mags(m2)
        for arr, second in ((g1, g2), (bp1, bp2), (rp1, rp2)):
            arr[is_bin] = -2.5 * np.log10(
                10 ** (-0.4 * arr[is_bin]) + 10 ** (-0.4 * second))

    # 距離模數與消光
    g_obs = g1 + dist_mod + ext.g * av
    bp_obs = bp1 + dist_mod + ext.bp * av
    rp_obs = rp1 + dist_mod + ext.rp * av

    # 加上與觀測同等量級的測光誤差。誤差用「加雜訊前」的 G 去查表，
    # 否則查表用的星等本身已被雜訊汙染，三個波段會用到不一致的誤差。
    g_obs = g_obs + draws["z_g"][:n] * _interp_err(g_obs, errmodel, "e_g")
    bp_obs = bp_obs + draws["z_bp"][:n] * _interp_err(g_obs, errmodel, "e_bp")
    rp_obs = rp_obs + draws["z_rp"][:n] * _interp_err(g_obs, errmodel, "e_rp")

    # 套用與觀測相同的選擇函數。合成星團若不受同一組星等限制，
    # 暗端會多出觀測裡根本不可能存在的星，把擬合往錯的方向拉。
    keep = np.ones(n, bool)
    if g_faint is not None:
        keep &= g_obs <= g_faint
    if g_bright is not None:
        keep &= g_obs >= g_bright

    return {"color": (bp_obs - rp_obs)[keep], "mag": g_obs[keep],
            "is_binary": is_bin[keep], "q": q_all[keep], "m1": m1[keep]}


def synth_cluster(*args, **kwargs) -> tuple:
    """只要 (顏色, 星等) 時的薄包裝。"""
    p = synth_populations(*args, **kwargs)
    return p["color"], p["mag"]


def hess(color, mag, cbins, mbins, crange, mrange,
         smooth: float = 0.0) -> np.ndarray:
    """把 CMD 轉成二維直方圖（Hess 圖），並正規化成機率密度。

    smooth > 0 時對直方圖做高斯平滑（單位為格）。**只該對模型用，不要對觀測用**：
    模型的 Hess 圖是有限筆合成星的取樣估計，未平滑時會有很多「剛好沒抽到星」的
    空格；觀測若落在那些空格上，Poisson 概似會給出巨大的懲罰（log 接近零的密度），
    造成參數只要微動、邊界格子翻轉，概似就跳幾十。平滑後模型密度連續，
    概似曲面才反映真正的參數差異。
    """
    h, _, _ = np.histogram2d(color, mag, bins=[cbins, mbins],
                             range=[crange, mrange])
    if smooth > 0:
        from scipy.ndimage import gaussian_filter
        h = gaussian_filter(h, smooth, mode="constant")
    s = h.sum()
    return h / s if s > 0 else h


def poisson_loglike(obs_h: np.ndarray, mod_h: np.ndarray, n_obs: int,
                    outlier_frac: float = 0.01) -> float:
    """Poisson 概似，模型混入一個均勻的離群成分。

    模型 = (1 - eps) * 合成分布 + eps * 均勻分布

    為什麼需要那個均勻成分：模型密度為零、觀測卻有星的格子，用純粹的
    clip(1e-6) 當下限會讓每顆星罰 log(1e-6) = -13.8。參數稍微一動、
    合成分布的邊緣位移，格子就在「有密度」與「零密度」之間翻轉，
    幾顆星便造成數百 lnL 的跳動 —— 概似曲面因此佈滿尖刺，
    最佳化器會卡在假峰，MCMC 的自相關時間也會隨鏈長惡化。

    均勻成分的物理意義是「有 eps 比例的星可能出現在任何位置」，
    涵蓋模型沒描述到的成分（殘留場星、變星、測光異常者）。
    它是**加法**而非摺積，所以不會像高斯平滑那樣把雙星序抹掉 ——
    平滑的尺度會跟 0.753 星等的雙星偏移競爭，均勻背景不會。
    """
    n_bins = mod_h.size
    mix = (1.0 - outlier_frac) * mod_h + outlier_frac / n_bins
    expect = mix * n_obs
    counts = obs_h * n_obs
    return float(np.sum(counts * np.log(expect) - expect))


class _Ext:
    def __init__(self, g, bp, rp):
        self.g, self.bp, self.rp = g, bp, rp


def fit(cfg, obs_color, obs_mag, iso_grid, errmodel, dist_mod: float,
        verbose: bool = True) -> dict:
    """在 (logAge, A_V) 網格上搜尋最佳解。"""
    from . import isochrones as iso_mod

    c3 = cfg.step3_age
    c2 = cfg.step2_cmd
    ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)
    # 共用亂數：每個網格點從同一顆種子重新開始，讓概似差異只反映參數差異，
    # 不混入蒙地卡羅雜訊（否則概似曲面會抖，最佳解可能只是雜訊高點）。
    seed = cfg.step1_membership.random_seed

    crange = tuple(c3.hess_color_range)
    mrange = tuple(c3.hess_mag_range)
    obs_h = hess(obs_color, obs_mag, c3.hess_color_bins, c3.hess_mag_bins,
                 crange, mrange)
    n_obs = len(obs_color)

    ages = np.arange(c3.fit_logage_min, c3.fit_logage_max + 1e-9,
                     c3.fit_logage_step)
    avs = np.arange(c3.fit_av_min, c3.fit_av_max + 1e-9, c3.fit_av_step)
    mh = c3.metallicity_mh
    draws = draw_randoms(c3.n_synthetic, np.random.default_rng(seed))

    ll = np.full((len(ages), len(avs)), -np.inf)
    for i, la in enumerate(ages):
        one = iso_mod.isochrone_at(iso_grid, la, mh)
        if len(one) < 10:
            continue
        for j, av in enumerate(avs):
            col, mag = synth_cluster(
                one, c3.n_synthetic, dist_mod, av,
                c3.binary_fraction, c3.binary_q_gamma, c3.binary_q_min,
                c3.imf, errmodel, ext, draws,
                g_faint=cfg.step1_membership.g_mag_max,
                g_bright=c2.g_bright_limit)
            mod_h = hess(col, mag, c3.hess_color_bins, c3.hess_mag_bins,
                         crange, mrange, smooth=c3.model_hess_smooth)
            ll[i, j] = poisson_loglike(obs_h, mod_h, n_obs)
        if verbose:
            best_j = int(np.argmax(ll[i]))
            print(f"  logAge={la:.2f}  最佳 A_V={avs[best_j]:.2f}  "
                  f"lnL={ll[i, best_j]:.1f}")

    k = np.unravel_index(np.argmax(ll), ll.shape)
    return {
        "logage": float(ages[k[0]]), "av": float(avs[k[1]]),
        "age_myr": float(10 ** ages[k[0]] / 1e6),
        "loglike": float(ll[k]), "ages": ages, "avs": avs, "loglike_grid": ll,
    }
