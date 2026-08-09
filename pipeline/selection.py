# -*- coding: utf-8 -*-
"""測光品質篩選的選擇函數：讓前向模型套用與觀測相同的那幾把刀。

**為什麼不是一條完整度曲線**

一開始的作法是量「每個 G 星等有多少比例的成員通過品質篩選」，得到一維曲線。
實測否決了它：G 17–18 的紅半邊存活率 0.410、藍半邊 0.799，差 0.388，
比整條星等趨勢（0.152）還大 2.6 倍。改用 BP 星等或 RP 星等當自變數也沒塌掉
（殘留 0.378 / 0.350）。

追下去發現成因很集中：G>=17 的紅星有 56.1% 被砍、藍星只有 18.7%，
而這個差幾乎全部（+0.374 中的 +0.374）來自 `min_flux_snr_bp = 20` 那一刀。
再往下一層問「BP 訊噪比是不是 BP 星等的函數」，答案是否定的 ——
同一個 BP 星等下，紅星的訊噪比只有藍星的 0.70–0.81 倍，
而且這個比值在四個星等區間都一致：

    BP 區間      SNR 中位   紅半邊   藍半邊   比值
    16–17        175.6     146.9    199.7   0.74
    17–18         88.5      79.2    112.6   0.70
    18–19         47.7      44.0     54.6   0.81
    19–20         22.8      18.9     27.0   0.70

所以正確的作法不是量一張經驗完整度地圖（格子一多每格星數就不夠、
量到的是雜訊），而是**把訊噪比本身建模成 (該波段星等, 顏色) 的函數，
再原封不動套用 config 裡那幾把刀**。這樣：

  * 沒有新的自由參數 —— 係數由資料迴歸決定，不進擬合
  * 顏色相依自然浮現，不必手動塞進去
  * 同一組關係順便修好另一個缺陷：原本的測光誤差模型用 G 去查 BP/RP 的誤差，
    對紅星會嚴重低估 BP 誤差（因為紅星在同一個 G 之下 BP 暗得多）

BP/RP 流量超額那一刀（85 顆）另外處理：它的成因是 M45 泡在反射星雲裡、
孔徑測光被鄰近光源汙染，不是星本身的性質，而且實測它對顏色幾乎中性
（G>=17 的紅藍差只有 +0.014）。因此用星等相依的隨機移除近似。
"""
from __future__ import annotations

import numpy as np

BANDS = ("g", "bp", "rp")


def fit_snr_model(mag, colour, snr, min_snr=3.0, bin_width=0.5, min_per_bin=15):
    """把 log10(SNR) 建模成「星等的非參數函數 + 顏色的線性項」。

    **不能用 log10 SNR = a + b*mag + c*colour 這種全域線性式。** 實測過：
    全域斜率被大量的亮星主導，得到 −0.137/星等，但暗端實際是 −0.30/星等
    （亮端有系統誤差地板讓 SNR 飽和，關係本來就不是直線）。
    結果是暗端 SNR 被高估 60%（BP 19–20 預測 36.6、實測中位 22.8），
    該被砍掉的星大量存活，選擇函數完全失效。

    改法：星等方向用 0.5 星等的分箱（非參數，讓資料自己決定形狀），
    顏色方向仍用線性項（實測比值在四個星等區間都穩定在 0.70–0.81，
    所以單一係數是夠的），兩者同時最小平方求解以免互相吸收。
    散布也逐星等量 —— 暗端的散布本來就比亮端大，用單一值會把切抹糊。
    """
    ok = (np.isfinite(mag) & np.isfinite(colour) & np.isfinite(snr)
          & (snr > min_snr))
    m, c, y = mag[ok], colour[ok], np.log10(snr[ok])

    edges = np.arange(np.floor(m.min() / bin_width) * bin_width,
                      m.max() + bin_width, bin_width)
    idx = np.clip(np.digitize(m, edges) - 1, 0, len(edges) - 2)
    counts = np.bincount(idx, minlength=len(edges) - 1)
    keep_bin = counts >= min_per_bin
    use = keep_bin[idx]
    m, c, y, idx = m[use], c[use], y[use], idx[use]
    # 重新編號，讓設計矩陣沒有空欄（空欄會讓最小平方奇異）
    remap = np.full(len(edges) - 1, -1)
    remap[keep_bin] = np.arange(keep_bin.sum())
    col = remap[idx]

    nbin = keep_bin.sum()
    A = np.zeros((len(y), nbin + 1))
    A[np.arange(len(y)), col] = 1.0        # 每個星等分箱一個截距
    A[:, -1] = c                            # 共用的顏色係數
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef

    centres = 0.5 * (edges[:-1] + edges[1:])[keep_bin]
    level = coef[:nbin]
    colour_coef = float(coef[-1])
    # 逐分箱的殘差散布
    scat = np.array([np.std(resid[col == j]) if (col == j).sum() > 3
                     else np.nan for j in range(nbin)])
    good = np.isfinite(scat)
    scat = np.interp(centres, centres[good], scat[good])
    return {"mag": centres, "level": level, "colour_coef": colour_coef,
            "scatter": scat, "n": int(len(y))}


class SelectionModel:
    """把三個波段的訊噪比關係包起來，提供「這顆合成星會不會被留下」。"""

    def __init__(self, fits, thresholds, excess_curve=None):
        self.fits = fits                # {band: fit_snr_model 的輸出}
        self.thr = thresholds           # {band: 訊噪比下限}
        self.excess_curve = excess_curve  # (G 格點, 存活比例) 或 None

    def log_snr(self, band, mag, colour):
        f = self.fits[band]
        base = np.interp(mag, f["mag"], f["level"],
                         left=f["level"][0], right=f["level"][-1])
        return base + f["colour_coef"] * colour

    def scatter(self, band, mag):
        f = self.fits[band]
        return np.interp(mag, f["mag"], f["scatter"],
                         left=f["scatter"][0], right=f["scatter"][-1])

    def keep(self, g, bp, rp, z_snr, u_sel):
        """回傳留下來的布林遮罩。

        z_snr 與 u_sel 是預先抽好的亂數（共用亂數原則）：
        訊噪比在關係式周圍有散布，所以切不是硬階梯而是機率性的；
        用固定的亂數才能讓概似仍是參數的確定性函數。
        """
        colour = bp - rp
        keep = np.ones(len(g), bool)
        for band, mag in zip(BANDS, (g, bp, rp)):
            ls = (self.log_snr(band, mag, colour)
                  + self.scatter(band, mag) * z_snr)
            keep &= ls >= np.log10(self.thr[band])
        if self.excess_curve is not None:
            gg, ff = self.excess_curve
            keep &= u_sel < np.interp(g, gg, ff, left=ff[0], right=ff[-1])
        return keep

    def describe(self):
        out = []
        for b in BANDS:
            f = self.fits[b]
            lo, hi = f["mag"][0], f["mag"][-1]
            slope_faint = ((f["level"][-1] - f["level"][-4])
                           / (f["mag"][-1] - f["mag"][-4]))
            out.append(
                f"  {b.upper()}: {f['n']:,} 顆、{len(f['mag'])} 個星等分箱 "
                f"{lo:.1f}–{hi:.1f}   顏色係數 {f['colour_coef']:+.3f}"
                f"   暗端斜率 {slope_faint:+.3f}/星等"
                f"   散布 {f['scatter'].min():.2f}–{f['scatter'].max():.2f} dex"
                f"   門檻 {self.thr[b]:g}")
        return "\n".join(out)


def load(path):
    """讀回 build_selection.py 存下的選擇函數。"""
    z = np.load(path)
    fits = {}
    for b in BANDS:
        fits[b] = {"mag": z[f"{b}_mag"], "level": z[f"{b}_level"],
                   "colour_coef": float(z[f"{b}_colour_coef"]),
                   "scatter": z[f"{b}_scatter"], "n": 0}
    thr = {b: float(z[f"thr_{b}"]) for b in BANDS}
    return SelectionModel(fits, thr, (z["excess_g"], z["excess_f"]))


def build(mags, colours, snrs, thresholds, excess_curve=None, verbose=True):
    """由觀測資料建立 SelectionModel。

    mags / snrs 是 {band: array}，colours 是共用的 BP-RP。
    """
    fits = {}
    for b in BANDS:
        fits[b] = fit_snr_model(mags[b], colours, snrs[b])
        if verbose:
            print(f"  {b.upper()}: {fits[b]['n']:,} 顆迴歸，"
                  f"{len(fits[b]['mag'])} 個星等分箱")
    return SelectionModel(fits, thresholds, excess_curve)
