"""口徑對照診斷：文獻間的 alpha 差異，有多少只是質量範圍/MF 定義不同？

**這支腳本回答的問題**：同一顆星團（M45／Pleiades），不同研究報出的
冪律指數 alpha 從 2.01 到 3.33，跨度 1.3。這是真實的方法論分歧，還是
只因為各家擬合的質量範圍與 MF 定義不一樣？

**做法**：拿 Hobart et al. (2026, arXiv:2607.17300) 為 Pleiades 發表的
三段冪律參數（斷點與各段斜率），理想抽樣出質量，再用**別人的質量範圍**
重新擬合成單一冪律，看會得到什麼數字。用的估計器就是本專案第 5 步在用
的 `pipeline.step5_imf.mle_powerlaw()`，不是另外寫一套。

**這支腳本不做什麼（重要）**：
- 不加觀測誤差、不加選擇函數、不模擬未解析雙星混合——純粹隔離
  「質量範圍」這一個變因，不是完整的端到端重現。
- 不證明任何一方是對的。它只能說明「這些數字有多少差距可以用口徑解釋」，
  剩下的差距才需要物理或方法論解釋。
- **Pang et al. (2024) 的實際擬合質量範圍本專案尚未查證**（只有 alpha
  數字是從他們 Table 1 解析出來的）。下方把 Pang 的數字跟 0.30-2.50 的
  換算值並排，是**假設**他們用類似範圍，這個假設還沒核對過原文，
  不能當已驗證的結論——這正是本專案對 Tang et al. (2019) 做過、
  但對 Pang+2024 還沒做的那種口徑核對。

不寫任何檔案，純診斷輸出。

用法：
    python scripts/diagnostics/check_massrange_crosscal.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.step5_imf import mle_powerlaw  # noqa: E402

try:  # Windows 主控台預設 cp950，輸出中文/數學符號會炸
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

RNG = np.random.default_rng(42)
N_SAMPLE = 400_000

# --- Hobart et al. (2026) 為 Pleiades 發表的三段冪律 ---------------------
# 斷點 mx1/mx2 與各段斜率取自該文 Table 2（PDMF，PARSEC 質量）與
# Table 5（stellar IMF，已修雙星＋動力學）。alpha 定義 dN/dm ∝ m^(-alpha)，
# 跟本專案 config.toml 一致。
# 註：我們的擬合上限 2.50 M☉ 遠低於他們涵蓋的 ~5.5 M☉，所以下面只用到
# mx2 以上那一段的斜率，抽樣上限一律取本專案的 2.50。
HOBART_PLEIADES = {
    "PDMF（未修雙星／動力學）": dict(mx1=0.24, mx2=0.91, a_med=1.62, a_high=3.04),
    "stellar IMF（已修雙星＋動力學）": dict(mx1=0.24, mx2=0.91, a_med=1.67, a_high=3.33),
}

# --- 要拿來重新擬合的質量範圍 -------------------------------------------
RANGES = [
    (0.30, 2.50, "0.30-2.50（本專案 alpha_naive／傳統法主表）"),
    (0.50, 2.50, "0.50-2.50（本專案 alpha_forward 的 Kroupa >0.5 段）"),
    (0.91, 2.50, "0.91-2.50（Hobart 自己的 alpha_high 起點，回收檢查）"),
]

# --- 對照用的實際數字 ---------------------------------------------------
# 每一筆都標明來源與可信度狀態，不要在這裡放沒出處的數字。
REFERENCE_VALUES = [
    ("Pang+2024 M45（單一冪律，**擬合質量範圍未查證**）", "2.01 +/- 0.09",
     "Pang et al. 2024 Table 1，本專案解析；質量範圍待核對原文"),
    ("本專案 alpha_naive（0.30-2.50 單一冪律）", "1.978 +/- 0.069",
     "x64 機器獨立重跑驗證，見 WORK_BOARD.md 2026-08-12 條目"),
    ("本專案 alpha_forward（>0.5 Kroupa 段，已修雙星）", "2.382 +/- 0.068",
     "headline p2_final2_v3 正式版（10/10 次重複，2026-08-20 定案，A1/A2 已解除）"),
    ("Hobart+2026 alpha_high（>0.91）", "PDMF 3.04 / stellar IMF 3.33",
     "arXiv:2607.17300 Table 2 / Table 5"),
]


def sample_broken(mx1: float, mx2: float, a_med: float, a_high: float,
                  lo: float, hi: float, n: int = N_SAMPLE) -> np.ndarray:
    """從分段冪律抽樣，只產生落在 [lo, hi] 內的質量。

    分段之間用連續性常數接起來：相鄰兩段在斷點處的 phi(m) 必須相等，
    所以 C_k = C_{k-1} * m_break^(alpha_k - alpha_{k-1})。
    每段的權重是該段在 [lo, hi] 交集區間內的積分。
    """
    segments = []
    for a, b, slope in [(mx1, mx2, a_med), (mx2, np.inf, a_high)]:
        a2, b2 = max(a, lo), min(b, hi)
        if b2 > a2:
            segments.append((a2, b2, slope))
    if not segments:
        raise ValueError(f"擬合範圍 [{lo}, {hi}] 跟分段冪律沒有交集")

    const = [1.0]
    for k in range(1, len(segments)):
        m_break = segments[k][0]
        const.append(const[k - 1] * m_break ** (segments[k][2] - segments[k - 1][2]))

    weights = []
    for (a, b, slope), c in zip(segments, const):
        if abs(slope - 1.0) < 1e-9:
            weights.append(c * np.log(b / a))
        else:
            weights.append(c * (b ** (1 - slope) - a ** (1 - slope)) / (1 - slope))
    weights = np.asarray(weights, float)
    weights /= weights.sum()

    counts = RNG.multinomial(n, weights)
    out = []
    for (a, b, slope), k in zip(segments, counts):
        if k == 0:
            continue
        u = RNG.random(k)
        if abs(slope - 1.0) < 1e-9:
            out.append(a * (b / a) ** u)
        else:
            lo_p, hi_p = a ** (1 - slope), b ** (1 - slope)
            out.append((lo_p + u * (hi_p - lo_p)) ** (1 / (1 - slope)))
    return np.concatenate(out)


def main() -> None:
    print(__doc__.split("用法：")[0].strip())
    print("=" * 78)
    print()
    print("把 Hobart+2026 的 Pleiades 分段冪律，用不同質量範圍重新擬合成單一冪律：")
    print()
    print(f"{'Hobart 的 MF':<34} {'擬合範圍':<46} {'單一冪律 alpha':>14}")
    print("-" * 96)

    recovered = {}
    for mf_name, params in HOBART_PLEIADES.items():
        for lo, hi, label in RANGES:
            masses = sample_broken(lo=lo, hi=hi, **params)
            fit = mle_powerlaw(masses, lo, hi)
            print(f"{mf_name:<34} {label:<46} {fit['alpha']:>14.3f}")
            recovered[(mf_name, lo)] = fit["alpha"]
        print()

    # 健全性檢查：0.91 以上只剩單一段，必須回收到原本發表的 alpha_high。
    for mf_name, params in HOBART_PLEIADES.items():
        got = recovered[(mf_name, 0.91)]
        want = params["a_high"]
        assert abs(got - want) < 0.02, (
            f"健全性檢查失敗：{mf_name} 在 0.91-2.50 應回收到 {want}，實得 {got:.3f}"
        )
    print("健全性檢查通過：0.91-2.50 的擬合值回收到 Hobart 原本發表的 alpha_high。")
    print()

    print("對照（實際文獻／本專案數字，含可信度狀態）")
    print("-" * 96)
    for label, value, provenance in REFERENCE_VALUES:
        print(f"  {label}")
        print(f"      alpha = {value}")
        print(f"      來源／狀態：{provenance}")
    print()
    print("初步判讀（不是定案）：把三方數字換算到同一個質量範圍之後，原本 1.3 的")
    print("跨度大幅收斂。這支援「文獻間 alpha 差異主要來自口徑而非物理」這個假說。")
    print()
    print("兩組比較要分開講，不要混成一個數字：")
    print("  [未修雙星 vs 未修雙星] alpha_naive 1.978 vs Hobart PDMF@0.30-2.50 = 2.058")
    print("      差 -0.080（約 1.2 sigma）。兩邊都沒修雙星，是目前最接近同口徑的一組。")
    print("  [已修雙星 vs 未修雙星] alpha_forward 2.382 vs Hobart PDMF@0.50-2.50 = 2.395")
    print("      差 -0.013。數字幾乎一樣，但**口徑不對等**：我們修了雙星、他們沒修。")
    print("      對上他們已修雙星＋動力學的 stellar IMF@0.50-2.50 = 2.549 則差 -0.167。")
    print()
    print("那個 ~0.15 是 Hobart 自己 PDMF -> stellar IMF 的落差（2.395 -> 2.549 = +0.154），")
    print("不是我們跟他們的差距；而且這段落差同時含雙星修正與動力學修正兩者")
    print("（他們在 >0.91 的鏈是 PDMF 3.04 -> 修雙星 3.11 -> stellar IMF 3.33，")
    print("雙星貢獻 +0.07、動力學貢獻 +0.22），不能只叫它動力學修正。")
    print()
    print("還沒理清、不能當已驗證結論的地方：")
    print("  1. Pang+2024 的擬合質量範圍尚未查證，上面的並排是假設不是核對結果。")
    print("  2. 我們的 alpha_forward 已修雙星，理應落在 Hobart 未修(2.395)與")
    print("     已修(2.549)之間，實際卻落在 2.395 稍下方——為什麼雙星修正沒有把")
    print("     我們的值推高，這個問題本身還沒有解釋。")


if __name__ == "__main__":
    main()
