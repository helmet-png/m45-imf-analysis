# -*- coding: utf-8 -*-
"""B4（已解決，見 `RESOLVED.md`）：Hess 圖概似真的是「當獨立 Poisson」嗎？

**當初的疑慮**：Hess 圖各格的觀測次數聯合分布嚴格來說是多項分布（總星數
固定，格間負相關），`poisson_loglike()`（`pipeline/step3_age.py`）卻把
每格當獨立 Poisson 算，直覺上像是多算了一個「總數也是自由參數」的自由度。

**查證後發現這個直覺是錯的，錯在哪裡**：`hess()`
（`pipeline/step3_age.py`）在回傳直方圖前一定會 `h / h.sum()`，也就是說
`mod_h`（合成星團的 Hess 圖）**恆等於機率分布，總和永遠精確等於 1**，
不管 theta 是什麼。混入離群成分的 `mix = (1-eps)*mod_h + eps/n_bins`
因此也恆等於 1（凸組合）。

推導（`k_i`=觀測次數、`p_i`=`mix_i`、`N`=`n_obs`，兩者皆與 theta 無關或
恆等於 1，`sum(p_i)=1` 是關鍵）：

    LL_poisson  = sum_i[ k_i*log(p_i*N) - p_i*N ]
                = sum_i[ k_i*log(p_i) ] + N*log(N) - N        （用 sum(p_i)=1、sum(k_i)=N）
                = LL_multinomial + 常數（不含 theta）

也就是「獨立 Poisson 加總」在**這個實作**下跟真正的多項分布概似只差一個
跟 theta 無關的常數——梯度、argmax、後驗形狀完全相同，不是近似，是代數
恆等式。這個結論**依賴於 `hess()` 把 mod_h 強制正規化到總和為 1** 這個
實作細節；如果哪天 `hess()` 改成回傳未正規化的原始計數，這個等價性就會
失效，需要重新檢查（見下面 `main()` 的數值驗證，之後改動 `hess()` 可以
重跑這支腳本確認等價性還在）。

跑法：`python check_poisson_vs_multinomial.py`，不需要真實資料，純數學/
數值驗證，幾秒內跑完。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline.step3_age import hess  # noqa: E402 —— 故意真的 import，見下方 main()


def poisson_loglike(obs_h, mod_h, n_obs, outlier_frac=0.01):
    """概似公式本身逐字抄自 pipeline/step3_age.py，故意不 import——這是要
    驗證的對象，保持獨立才不會改動主程式碼時悄悄跟著變、讓驗證失去意義。
    但 `mod_h`／`obs_h` 的來源（`hess()` 的正規化行為）**有真的 import**，
    見 main()，不能連這個關鍵前提都用手刻的假設取代（2026-08-13
    CodeRabbit review 指出手刻 `mod_raw/mod_raw.sum()` 沒有真的驗證
    `hess()` 的契約，`hess()` 改動也不會讓這支腳本失敗）。"""
    n_bins = mod_h.size
    mix = (1.0 - outlier_frac) * mod_h + outlier_frac / n_bins
    expect = mix * n_obs
    counts = obs_h * n_obs
    return float(np.sum(counts * np.log(expect) - expect))


def multinomial_loglike(obs_h, mod_h, n_obs, outlier_frac=0.01):
    n_bins = mod_h.size
    mix = (1.0 - outlier_frac) * mod_h + outlier_frac / n_bins
    counts = obs_h * n_obs
    return float(np.sum(counts * np.log(mix)))


def main():
    rng = np.random.default_rng(0)
    # cbins/mbins/crange/mrange 跟 config.toml 的 hess_color_bins／
    # hess_mag_bins／hess_color_range／hess_mag_range 一致。
    cbins, mbins = 40, 50
    crange, mrange = (-0.5, 4.0), (2.0, 18.0)
    n_bins = cbins * mbins
    n_obs = 1078

    # 觀測 Hess 圖也用真正的 hess()（不是隨機數，用固定分布模擬觀測樣本），
    # 這樣 obs_h 的正規化也走跟合成星團同一條路徑，不是另外假設。
    obs_color = rng.normal(1.0, 0.5, n_obs).clip(*crange)
    obs_mag = rng.uniform(*mrange, n_obs)
    obs_h = hess(obs_color, obs_mag, cbins, mbins, crange, mrange)
    if abs(obs_h.sum() - 1.0) >= 1e-9:
        print(f"hess() 沒有把觀測 Hess 圖正規化到總和=1（實際={obs_h.sum()}），"
              f"契約已改變，下面的推導不再成立。", file=sys.stderr)
        raise SystemExit(1)

    theoretical_const = n_obs * np.log(n_obs) - n_obs
    diffs = []
    for i in range(20):
        # 模擬「換一個 theta」：每次用不同的合成星數量與分布形狀生成 CMD，
        # 再用**真正的** hess()（不是手刻的 mod_raw/mod_raw.sum()）轉成
        # Hess 圖——這樣才是在驗證 hess() 實際的正規化契約，不是驗證我們
        # 自己對這個契約的假設。
        n_syn = rng.integers(5000, 50000)
        mod_color = rng.normal(rng.uniform(0.5, 1.5), rng.uniform(0.3, 0.8),
                               n_syn).clip(*crange)
        mod_mag = rng.uniform(*mrange, n_syn)
        mod_h = hess(mod_color, mod_mag, cbins, mbins, crange, mrange)
        if abs(mod_h.sum() - 1.0) >= 1e-9:
            print(f"第 {i} 次試驗：hess() 沒有把模型 Hess 圖正規化到總和=1"
                  f"（實際={mod_h.sum()}），契約已改變，下面的推導不再成立。",
                  file=sys.stderr)
            raise SystemExit(1)
        llp = poisson_loglike(obs_h, mod_h, n_obs)
        llm = multinomial_loglike(obs_h, mod_h, n_obs)
        diffs.append(llp - llm)

    diffs = np.array(diffs)
    spread = diffs.max() - diffs.min()
    print("20 個隨機 theta 下 LL_poisson - LL_multinomial 的差：")
    print(f"  平均 = {diffs.mean():.6f}")
    print(f"  理論常數 n_obs*log(n_obs) - n_obs = {theoretical_const:.6f}")
    print(f"  20 次之間的變化幅度 = {spread:.2e}（應該只是浮點誤差，不是"
          f"theta 依賴性）")

    ok = abs(diffs.mean() - theoretical_const) < 1e-6 and spread < 1e-8
    if ok:
        print("\n驗證通過：poisson_loglike() 在 hess() 正規化的前提下，跟"
              "多項分布概似只差一個 theta 無關的常數，argmax/後驗形狀完全"
              "相同。B4 的疑慮不成立，見 RESOLVED.md。")
    else:
        print("\n驗證失敗！差值不是常數，代表某個假設（多半是 hess() 的"
              "正規化行為）已經改變，B4 需要重新評估，不要沿用 RESOLVED.md "
              "的結論。", file=__import__("sys").stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
