# -*- coding: utf-8 -*-
"""查三維塵埃圖，取得 M45 方向、M45 距離處的消光獨立估計。

**為什麼這件事重要**：年齡、金屬量、消光三者在 CMD 上幾乎完全簡併
（實測相關係數 ±0.95，96.7% 的變異集中在單一方向），資料只能定出
「三者落在某條線上」，無法定出個別的值。

三維塵埃圖提供的是**與 CMD 無關的第二個約束**：它直接說「往這個方向、
到這個距離，累積了多少消光」。有了它就能把那條線截斷成一段。

用 Argonaut 的 web API（Green et al. 2019 的 Bayestar19），不必下載
數 GB 的資料檔。M45 在 dec +24 度，落在該圖的涵蓋範圍內（dec > -30）。
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pipeline import net  # noqa: E402

ARGONAUT = "https://argonaut.skymaps.info/api/v2/bayestar"
RA, DEC = 56.60083, 24.11389
DIST_PC = 135.5          # 由 Gaia 視差定出

# Bayestar 回傳的是 E(g-r) 樣式的「模組」值，需乘以係數換成各波段消光。
# Green et al. 2019 建議 A_V ≈ 2.742 * E(B-V)_SFD 等價量，
# 而 Bayestar 的單位約等於 SFD 的 E(B-V)。
BAYESTAR_TO_AV = 2.742


def query(ra, dec):
    body = json.dumps({"ra": [ra], "dec": [dec], "coordsys": "equ",
                       "mode": "full"}).encode()
    req = urllib.request.Request(
        ARGONAUT, data=body,
        headers={"Content-Type": "application/json", "User-Agent": net.UA})
    with urllib.request.urlopen(req, timeout=120,
                                context=net.ssl_context()) as r:
        return json.loads(r.read().decode())


def main():
    print(f"查詢 M45 方向 (RA={RA:.4f}, Dec={DEC:.4f})…")
    try:
        d = query(RA, DEC)
    except Exception as e:
        print(f"查詢失敗：{type(e).__name__}: {e}")
        print("\nArgonaut API 若不可用，替代方案：")
        print("  - dustmaps 套件（需下載約 500 MB 的 Bayestar 資料檔）")
        print("  - Lallement 等人的 EXPLORE G-Tomo（另一個三維塵埃圖服務）")
        return

    print(f"回傳欄位：{list(d)}")
    dm = np.asarray(d["distmod"], float)      # 距離模數格點
    dist = 10 ** (dm / 5.0 + 1.0)             # 換成 pc
    samples = np.asarray(d["samples"], float)  # (1, n_sample, n_dist)
    best = np.asarray(d["best"], float)        # (1, n_dist)

    print(f"\n距離格點 {len(dist)} 個，{dist.min():.0f} – {dist.max():.0f} pc")
    print(f"後驗樣本 {samples.shape[1]} 組")
    print(f"可靠度旗標 converged={d.get('converged')}")

    i = int(np.argmin(np.abs(dist - DIST_PC)))
    print(f"\n最接近 M45 距離 {DIST_PC} pc 的格點：{dist[i]:.1f} pc")
    col = samples[0, :, i]
    q = np.percentile(col, [16, 50, 84])
    print(f"該處累積消光（Bayestar 單位）："
          f"中位 {q[1]:.4f}  [{q[0]:.4f}, {q[2]:.4f}]")
    print(f"換算 A_V ≈ {q[1]*BAYESTAR_TO_AV:.3f}  "
          f"[{q[0]*BAYESTAR_TO_AV:.3f}, {q[2]*BAYESTAR_TO_AV:.3f}]")

    print(f"\n沿視線的累積消光（看塵埃分布在哪裡）：")
    for j in range(0, len(dist), max(1, len(dist) // 12)):
        v = np.median(samples[0, :, j]) * BAYESTAR_TO_AV
        bar = "#" * int(v * 40)
        print(f"  {dist[j]:>7.0f} pc  A_V={v:>6.3f} {bar}")

    np.savez(HERE / "results" / "dustmap.npz",
             dist_pc=dist, samples=samples[0], best=best[0],
             av_factor=BAYESTAR_TO_AV, dist_target=DIST_PC)
    print(f"\n寫入 results/dustmap.npz")

    print("\n判讀：若 M45 距離處的 A_V 不確定度明顯小於 CMD 擬合給的範圍，")
    print("      就能當成有效的先驗把年齡-金屬量-消光的簡併稜線截斷。")


if __name__ == "__main__":
    main()
