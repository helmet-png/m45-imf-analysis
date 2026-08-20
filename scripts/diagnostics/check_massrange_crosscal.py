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
# 修正鏈的中繼值：只修雙星、還沒做動力學回推的 alpha_high。取自該文
# Table 4「Binary corrected cluster IMF properties」的 h,bin 欄（Pleiades
# 那一列）。這個中繼值不在 HOBART_PLEIADES 裡（那組是分段冪律的完整
# 參數，Table 4 只給高質量段單一數字，沒有斷點/中質量段可以重建完整
# 分段冪律），只用來拆解 PDMF→stellar IMF 這段落差裡雙星修正跟動力學
# 修正各自的貢獻。
HOBART_PLEIADES_ALPHA_HIGH_BINARY_CORRECTED = 3.11

# --- 要拿來重新擬合的質量範圍 -------------------------------------------
RANGES = [
    (0.30, 2.50, "0.30-2.50（本專案 alpha_naive／傳統法主表）"),
    (0.50, 2.50, "0.50-2.50（本專案 alpha_forward 的 Kroupa >0.5 段）"),
    (0.91, 2.50, "0.91-2.50（Hobart 自己的 alpha_high 起點，回收檢查）"),
]

# --- 對照用的實際數字 ---------------------------------------------------
# 每一筆都標明來源與可信度狀態，不要在這裡放沒出處的數字。alpha/err 是
# 數值（不是字串），下面的比較與判讀文字全部從這裡算出來，不要另外
#手動抄一份數字進 print 字串——避免上面的常數改了、下面判讀文字忘記
#跟著動，兩邊silently 不一致（2026-08-20 CodeRabbit review 提醒）。
PANG_M45 = {"label": "Pang+2024 M45（單一冪律，**擬合質量範圍未查證**）",
            "alpha": 2.01, "err": 0.09,
            "provenance": "Pang et al. 2024 Table 1，本專案解析；質量範圍待核對原文"}
OUR_NAIVE = {"label": "本專案 alpha_naive（0.30-2.50 單一冪律）",
             "alpha": 1.978, "err": 0.069,
             "provenance": "x64 機器獨立重跑驗證，見 WORK_BOARD.md 2026-08-12 條目"}
OUR_FORWARD = {"label": "本專案 alpha_forward（>0.5 Kroupa 段，已修雙星）",
               "alpha": 2.382, "err": 0.068,
               "provenance": "headline p2_final2_v3 正式版（10/10 次重複，2026-08-20 定案，A1/A2 已解除）"}
REFERENCE_VALUES = [PANG_M45, OUR_NAIVE, OUR_FORWARD]


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
    for ref in REFERENCE_VALUES:
        print(f"  {ref['label']}")
        print(f"      alpha = {ref['alpha']:.3f} +/- {ref['err']:.3f}")
        print(f"      來源／狀態：{ref['provenance']}")
    print()

    # 下面所有差值都從 recovered（上面表格算出來的）與具名常數計算，
    # 不要手動抄一份數字進判讀文字——常數改了，這裡會自動跟著動。
    pdmf_030 = recovered[("PDMF（未修雙星／動力學）", 0.30)]
    pdmf_050 = recovered[("PDMF（未修雙星／動力學）", 0.50)]
    imf_050 = recovered[("stellar IMF（已修雙星＋動力學）", 0.50)]
    pdmf_high = HOBART_PLEIADES["PDMF（未修雙星／動力學）"]["a_high"]
    imf_high = HOBART_PLEIADES["stellar IMF（已修雙星＋動力學）"]["a_high"]

    diff_naive = OUR_NAIVE["alpha"] - pdmf_030
    diff_forward_vs_pdmf = OUR_FORWARD["alpha"] - pdmf_050
    diff_forward_vs_imf = OUR_FORWARD["alpha"] - imf_050
    # 不報告差異顯著度（sigma）：Hobart 的 PDMF 參數、我們重擬合的抽樣
    # 誤差、蒙地卡羅抽樣本身的誤差都沒有量化與傳播，只除以我們自己的
    # 統計誤差不能代表兩組測量的差異顯著度（2026-08-20 CodeRabbit 提醒）。
    hobart_pdmf_to_imf_gap = imf_050 - pdmf_050
    binary_corrected_high = HOBART_PLEIADES_ALPHA_HIGH_BINARY_CORRECTED
    hobart_binary_step = binary_corrected_high - pdmf_high
    hobart_dynamic_step = imf_high - binary_corrected_high

    # 一致性檢查：確保 Table 4 的雙星修正中繼值真的落在 PDMF 與
    # stellar IMF 兩個高質量段端點之間，不是筆誤或抄錯欄位——直接比較
    # 三個高質量段值本身，不要拿階段差跟整體擬合落差比較（後者只保證
    # 量級相符，沒辦法保證真的落在區間內，2026-08-20 CodeRabbit 提醒）。
    assert pdmf_high < binary_corrected_high < imf_high, (
        f"一致性檢查失敗：雙星修正中繼值 {binary_corrected_high} 不在 "
        f"PDMF({pdmf_high}) 與 stellar IMF({imf_high}) 之間，需要重新核對 Hobart 原文 Table 4"
    )

    print("初步判讀（不是定案）：把三方數字換算到同一個質量範圍之後，原本 1.3 的")
    print("跨度大幅收斂。這支持「質量範圍這項口徑因素可能解釋部分 alpha 差異」這個")
    print("假說——**這支腳本只隔離了質量範圍一個變因，沒有測 Pang+2024 的實際質量")
    print("範圍、選擇函數、觀測誤差、未解析雙星或動力學修正，不足以支持「主要來自")
    print("口徑而非物理」這種更廣的判讀，也不排除還有其他變因造成剩下的差距**。")
    print()
    print("兩組比較要分開講，不要混成一個數字：")
    print(f"  [未修雙星 vs 未修雙星] alpha_naive {OUR_NAIVE['alpha']:.3f} vs "
          f"Hobart PDMF@0.30-2.50 = {pdmf_030:.3f}")
    print(f"      差 {diff_naive:+.3f}。Hobart 參數不確定度尚未傳播，"
          f"不報告差異顯著度。兩邊都沒修雙星，是目前最接近同口徑的一組。")
    print(f"  [已修雙星 vs 未修雙星] alpha_forward {OUR_FORWARD['alpha']:.3f} vs "
          f"Hobart PDMF@0.50-2.50 = {pdmf_050:.3f}")
    print(f"      差 {diff_forward_vs_pdmf:+.3f}。數字幾乎一樣，但**口徑不對等**："
          f"我們修了雙星、他們沒修。")
    print(f"      對上他們已修雙星＋動力學的 stellar IMF@0.50-2.50 = {imf_050:.3f} "
          f"則差 {diff_forward_vs_imf:+.3f}。")
    print()
    print(f"那個 ~0.15 是 Hobart 自己 PDMF -> stellar IMF 的落差"
          f"（{pdmf_050:.3f} -> {imf_050:.3f} = {hobart_pdmf_to_imf_gap:+.3f}），")
    print("不是我們跟他們的差距；而且這段落差同時含雙星修正與動力學修正兩者")
    print(f"（他們在 >0.91 的鏈是 PDMF {pdmf_high:.2f} -> 修雙星 {binary_corrected_high:.2f} -> "
          f"stellar IMF {imf_high:.2f}，")
    print(f"雙星貢獻 {hobart_binary_step:+.2f}、動力學貢獻 {hobart_dynamic_step:+.2f}），"
          f"不能只叫它動力學修正。")
    print()
    print("還沒理清、不能當已驗證結論的地方：")
    print("  1. Pang+2024 的擬合質量範圍尚未查證，上面的並排是假設不是核對結果。")
    print(f"  2. 我們的 alpha_forward 已修雙星，理應落在 Hobart 未修({pdmf_050:.3f})與")
    print(f"     已修({imf_050:.3f})之間，實際卻落在 {pdmf_050:.3f} 稍下方"
          f"——為什麼雙星修正沒有把")
    print("     我們的值推高，這個問題本身還沒有解釋。")


if __name__ == "__main__":
    main()
