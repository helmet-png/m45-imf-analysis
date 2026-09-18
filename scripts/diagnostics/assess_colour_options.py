# -*- coding: utf-8 -*-
"""D19 Stage 0：低質量段深度延伸的「顏色策略」閘門。

**這支程式不做擬合，也不改任何結果**，只回答一個先決問題：
想把質量下限從 0.30 M☉ 推到 0.10 M☉，該用哪一個顏色取代 BP-RP？

## 為什麼問題是「顏色」而不是「星等」

`LIMITATIONS.md` C16 已經寫明：G = 18 對應 0.173 M☉，而擬合下限 0.30 M☉
只到 G = 16.63，還有 1.4 星等餘裕——**星我們看得到，缺的是可靠的顏色**。
BP 波段在暗紅星上崩潰（本專案實測：G 18-19 只有 12.3% 通過 BP SNR>=20，
同一批星 RP 的通過率是 97.9%），而整條 pipeline 的 Hess 圖建立在 BP-RP 上。
C21 給出第二個獨立理由：M45 泡在反射星雲裡，差異消光 0.634 遠大於平均
消光 0.102，而 BP/RP 孔徑測光被汙染最嚴重的正好是星雲裡的成員星。

## 判準在看到結果之前就寫死（見下方 GATE_*）

這是刻意的：如果先跑完再定標準，等於用結果去挑對自己有利的門檻。
四項判準全過才採用該顏色；按成本由低到高取第一個過關者。四項全滅就
停在 Stage 0，把 D19 寫成負面結果——那是最便宜的收場。

## 三個候選的成本階梯

1. `G-RP`：零新資料，RP SNR 已在現有 CSV 裡。最可能的失敗模式是顏色
   基線太短——低質量端 d(colour)/d(M) 變平，54 mmag 的顏色誤差會放大成
   很大的質量誤差。所以這支程式一定要報 `sigma_M`，不能只報星數。
2. `G-J`（2MASS）／`G-y`（PanSTARRS1）：走 Gaia 內建的交叉比對表
   （`gaiadr3.tmass_psc_xsc_best_neighbour` 等），沿用
   `scripts/data_prep/gaia_astrophys.py` 的批次 source_id 查詢模式。
   需要先跑 `fetch_xmatch_ir.py` 產生 `data/xmatch_ir.csv`；沒有那份檔案
   時這支程式會把該選項標成「資料未備」而不是當成失敗。
3. UKIDSS GCS：Stage 0 **不**建 WFCAM Science Archive 的 client，只在
   前兩個選項全滅時才評估。UKIDSS 不在 Gaia 的外部交叉比對表清單裡，
   這正是它成本高的根本原因。

用法：
    python scripts/diagnostics/assess_colour_options.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod          # noqa: E402
from pipeline import isochrones as isomod      # noqa: E402
from pipeline import step5_imf                 # noqa: E402
from pipeline.step3_age import _Ext            # noqa: E402

# --- 判準：跑之前就固定，不准事後調 -------------------------------------
GATE_M_FLOOR = 0.15        # M☉，質量下限要壓到這裡以下
GATE_DELTA_N = 200         # 顆，比現有 1,078 顆至少要多這麼多
GATE_F_FALSE = 0.02        # 交叉比對假匹配率上限
GATE_C_XM = 0.85           # 交叉比對完整度下限（**每個** G 分箱都要過）
GATE_SIGMA_M = 0.05        # M☉，顏色誤差換算成的質量解析度上限
SIGMA_M_RANGE = (0.10, 0.30)   # M☉，sigma_M 剖面要涵蓋的目標區間
# 取 0.10-0.30：下緣是這次要推進到的新深度，上緣是現行擬合下限。
# 也就是「新增的那一段」——舊區間的解析度本來就夠，新區間才是問題。
# sigma_M 這一項是 G-RP 最可能踩到的地雷：顏色基線短 -> d(colour)/d(M) 平
# -> 同樣的顏色誤差換算出來的質量誤差大。0.05 M☉ 的理由：低質量段要分辨
# 0.08-0.5 這個區間的形狀，質量解析度必須遠小於區間寬度，取 ~1/8 區間寬。

# Gaia 的 flux_over_error 轉星等誤差：sigma_mag = 2.5/ln(10) / (F/sigma_F)
MAG_ERR_COEFF = 2.5 / np.log(10.0)   # = 1.0857

G_BINS = np.arange(16.0, 20.5, 0.5)

# 等時線參數用 config C（現行 headline 前向模型設定）。出處：
# scripts/diagnostics/traditional_accounting.py 的 CURRENT_LOGAGE/CURRENT_AV，
# 來自 p2_final2（results/RESULTS_LOG.md）。這裡只拿來做 G<->質量換算的
# 標尺，不是在重新擬合年齡與消光。
CONFIG_C_LOGAGE = 8.033
CONFIG_C_AV = 0.383


def mag_err(flux_over_error) -> np.ndarray:
    """由 Gaia 的 flux_over_error 換算單波段星等誤差。"""
    foe = np.asarray(flux_over_error, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(foe > 0, MAG_ERR_COEFF / foe, np.inf)


def colour_threshold_mmag(cfg) -> float:
    """品質切門檻換算成星等誤差。

    C16 引用的「54 mmag」不是獨立設定的數字，而是 min_flux_snr_bp = 20
    這個切點換算出來的：1.0857 / 20 = 0.0543 星等。這裡重新算而不寫死，
    避免 config 改了門檻而這支程式還用舊數字。
    """
    return MAG_ERR_COEFF / cfg.step2_cmd.min_flux_snr_bp


def load_isochrone(cfg):
    c3 = cfg.step3_age
    path = isomod.CACHE / (
        f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
        f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat")
    grid = isomod.load_grid(path)
    return isomod.isochrone_at(grid, CONFIG_C_LOGAGE, c3.metallicity_mh)


def mass_resolution(iso, dist_mod, av, ext, colour_name, sigma_colour):
    """把顏色誤差換算成質量解析度 sigma_M = sigma_colour / |d(colour)/dM|。

    這是「這個顏色到底分不分得出質量」的直接量測。星數再多，如果
    d(colour)/dM 在低質量端趨近於零，這個顏色就沒有辨識力。
    回傳沿主序取樣的 (質量, sigma_M)。
    """
    g_ms, m_ms = step5_imf.main_sequence_mass_luminosity(iso, dist_mod, av, ext)
    if colour_name == "BP-RP":
        c_abs = (np.asarray(iso["G_BP_fSBmag"], float)
                 - np.asarray(iso["G_RP_fSBmag"], float) + (ext.bp - ext.rp) * av)
    elif colour_name == "G-RP":
        c_abs = (np.asarray(iso["G_fSBmag"], float)
                 - np.asarray(iso["G_RP_fSBmag"], float) + (ext.g - ext.rp) * av)
    else:
        return None, None
    m_all = np.asarray(iso["Mini"], float)
    order = np.argsort(m_all)
    m_s, c_s = m_all[order], c_abs[order]
    # 只取主序質量範圍，且顏色要單調才談得上「由顏色分辨質量」
    lo, hi = m_ms.min(), m_ms.max()
    sel = (m_s >= lo) & (m_s <= hi) & np.isfinite(c_s)
    m_s, c_s = m_s[sel], c_s[sel]
    if len(m_s) < 5:
        return None, None
    dcdm = np.gradient(c_s, m_s)
    with np.errstate(divide="ignore", invalid="ignore"):
        sig_m = np.where(np.abs(dcdm) > 0, sigma_colour / np.abs(dcdm), np.inf)
    return m_s, sig_m


def per_bin_table(field, colour_err, thr):
    """逐 G 分箱算 N_G_ok 與 N_colour_ok，回傳 DataFrame。"""
    g = np.asarray(field["phot_g_mean_mag"], float)
    g_err = mag_err(field["phot_g_mean_flux_over_error"])
    rows = []
    for lo, hi in zip(G_BINS[:-1], G_BINS[1:]):
        m = (g >= lo) & (g < hi)
        n_g = int(np.sum(m & (g_err < thr)))
        n_c = int(np.sum(m & (g_err < thr) & (colour_err < thr)))
        rows.append({"G_lo": lo, "G_hi": hi, "N_G_ok": n_g,
                     "N_colour_ok": n_c,
                     "frac": (n_c / n_g) if n_g else np.nan})
    return pd.DataFrame(rows)


def floor_magnitude(tab: pd.DataFrame, frac_floor: float = 0.80):
    """找出 N_colour_ok/N_G_ok 首次掉到 frac_floor 以下的 G 分箱下緣。"""
    bad = tab[(tab["N_G_ok"] > 0) & (tab["frac"] < frac_floor)]
    if len(bad) == 0:
        return float(tab["G_hi"].max())
    return float(bad.iloc[0]["G_lo"])


def isochrone_faint_limit(iso, dist_mod, av, ext) -> tuple[float, float]:
    """等時線自己的暗端極限，回傳 (視星等 G, 質量 M☉)。

    這是**模型端**的限制，跟資料深度無關：PARSEC 格點在某個最低質量就
    截止了，比那更暗的星即使觀測得到也查不到質量。當資料深度超過這條
    線時，瓶頸就從「看不看得到」換成「等時線有沒有涵蓋」——兩者要分開
    報，不能混成同一個數字。
    """
    g_ms, m_ms = step5_imf.main_sequence_mass_luminosity(iso, dist_mod, av, ext)
    i = int(np.argmax(g_ms))
    return float(g_ms[i]), float(m_ms[i])


def mass_at_g(iso, dist_mod, av, ext, gmag: float) -> float:
    m = step5_imf.assign_masses(np.array([gmag], float), iso, dist_mod, av, ext)
    return float(m[0])


def assess(name, field, colour_err, cfg, iso, dist_mod, ext, thr,
           xm_stats=None):
    """對一個顏色選項算出五個指標，回傳結果 dict。"""
    tab = per_bin_table(field, colour_err, thr)
    g_data = floor_magnitude(tab)
    g_model, m_model = isochrone_faint_limit(iso, dist_mod, CONFIG_C_AV, ext)
    # 兩條限制取較嚴格者。資料深度超過等時線涵蓋範圍時，瓶頸換人當，
    # 這件事要在輸出裡看得見，不能只報一個合併後的數字。
    limited_by = "資料" if g_data <= g_model else "等時線"
    g_floor = min(g_data, g_model)
    m_floor = mass_at_g(iso, dist_mod, CONFIG_C_AV, ext, g_floor)
    if not np.isfinite(m_floor):
        m_floor = m_model
    m_s, sig_m = mass_resolution(iso, dist_mod, CONFIG_C_AV, ext, name, thr)
    # sigma_M 在**目標質量區間上取剖面**，不在單一點上取值。理由有二：
    # (1) np.gradient 在陣列端點是單邊差分，最低質量那一格的導數不可信
    #     （實測會給出 dC/dM = 0，於是 sigma_M = inf，那是數值假象不是物理）；
    # (2) 判準要問的是「這個顏色在整段低質量區間都分得出質量嗎」，
    #     單點過關但區間中段崩掉一樣沒用。
    prof = None
    if m_s is not None:
        inner = (m_s >= max(m_floor, SIGMA_M_RANGE[0])) & (m_s <= SIGMA_M_RANGE[1])
        # 去掉端點那一格（單邊差分不可信）
        if inner.sum() > 2:
            idx = np.where(inner)[0][1:-1] if inner.sum() > 4 else np.where(inner)[0]
            vals = sig_m[idx]
            vals = vals[np.isfinite(vals)]
            if len(vals):
                prof = {"median": float(np.median(vals)),
                        "worst": float(np.max(vals)),
                        "m_lo": float(m_s[idx].min()),
                        "m_hi": float(m_s[idx].max())}
    return {"name": name, "table": tab, "g_floor": g_floor,
            "g_data": g_data, "g_model": g_model, "m_model": m_model,
            "limited_by": limited_by,
            "m_floor": m_floor, "sigma_prof": prof,
            "xm": xm_stats}


def hybrid_assessment(r_bprp, r_grp, iso, dist_mod, ext, thr):
    """評估分段方案：亮端用 BP-RP、暗端用 G-RP，各取所長。

    交接點取 BP-RP 自己的質量下限——那是它失效的地方，也正是換手的
    自然位置。兩段各自在自己的定義域上算 sigma_M 剖面，再取聯集的最差值。
    """
    m_switch = r_bprp["m_floor"]
    m_bot = r_grp["m_floor"]
    if not (np.isfinite(m_switch) and np.isfinite(m_bot)) or m_bot >= m_switch:
        return None
    worst, med = [], []
    for name, lo, hi in [("G-RP", m_bot, m_switch),
                         ("BP-RP", m_switch, SIGMA_M_RANGE[1])]:
        m_s, sig_m = mass_resolution(iso, dist_mod, CONFIG_C_AV, ext, name, thr)
        if m_s is None:
            return None
        sel = (m_s >= lo) & (m_s <= hi) & np.isfinite(sig_m)
        idx = np.where(sel)[0]
        if len(idx) > 4:
            idx = idx[1:-1]          # 去掉端點的單邊差分
        if not len(idx):
            continue
        worst.append(float(np.max(sig_m[idx])))
        med.append(float(np.median(sig_m[idx])))
    if not worst:
        return None
    return {"name": "分段(BP-RP/G-RP)", "table": r_grp["table"],
            "g_floor": r_grp["g_floor"], "g_data": r_grp["g_data"],
            "g_model": r_grp["g_model"], "m_model": r_grp["m_model"],
            "limited_by": r_grp["limited_by"], "m_floor": m_bot,
            "sigma_prof": {"median": float(np.median(med)),
                           "worst": float(np.max(worst)),
                           "m_lo": m_bot, "m_hi": SIGMA_M_RANGE[1]},
            "switch_at": m_switch, "xm": None}


def print_result(r, thr, n_now):
    print(f"\n{'=' * 68}")
    print(f"顏色選項：{r['name']}")
    print(f"{'=' * 68}")
    print(f"{'G 區間':>12}{'N_G_ok':>10}{'N_colour_ok':>14}{'通過率':>10}")
    for _, row in r["table"].iterrows():
        frac = row["frac"]
        fs = f"{frac * 100:.1f}%" if np.isfinite(frac) else "—"
        print(f"{row['G_lo']:>6.1f}-{row['G_hi']:<5.1f}{int(row['N_G_ok']):>10d}"
              f"{int(row['N_colour_ok']):>14d}{fs:>10}")
    print(f"\n  顏色誤差門檻      {thr * 1000:.1f} mmag")
    print(f"  資料深度上限 G    {r['g_data']:.2f}"
          f"（通過率首次掉到 80% 以下的分箱下緣）")
    print(f"  等時線暗端 G      {r['g_model']:.2f}"
          f"（= {r['m_model']:.3f} M☉，PARSEC 格點自身的最低質量）")
    print(f"  實際瓶頸          {r['limited_by']}")
    print(f"  對應質量下限      {r['m_floor']:.3f} M☉"
          f"   判準 <= {GATE_M_FLOOR}  ->  "
          f"{'過' if r['m_floor'] <= GATE_M_FLOOR else '不過'}")
    p = r["sigma_prof"]
    if p is not None:
        print(f"  質量解析度 sigma_M（{p['m_lo']:.2f}-{p['m_hi']:.2f} M☉ 剖面）")
        print(f"    中位數          {p['median']:.4f} M☉"
              f"   判準 <= {GATE_SIGMA_M}  ->  "
              f"{'過' if p['median'] <= GATE_SIGMA_M else '不過'}")
        print(f"    最差            {p['worst']:.4f} M☉"
              f"   判準 <= {GATE_SIGMA_M}  ->  "
              f"{'過' if p['worst'] <= GATE_SIGMA_M else '不過'}")
    else:
        print(f"  質量解析度 sigma_M  無法計算（顏色非單調或超出主序範圍）")
    if r["xm"] is None:
        print(f"  交叉比對指標      不適用（此選項不需要交叉比對）")
    else:
        print(f"  假匹配率 f_false  {r['xm']['f_false'] * 100:.2f}%"
              f"   判準 <= {GATE_F_FALSE * 100:.0f}%")
        print(f"  完整度 C_xm 最低  {r['xm']['c_xm_min'] * 100:.1f}%"
              f"   判準 >= {GATE_C_XM * 100:.0f}%（逐分箱）")


def main():
    cfg = cfgmod.load(None)
    thr = colour_threshold_mmag(cfg)
    field = pd.read_csv(HERE / "data" / "m45_r5_g20_plx4.csv")
    members = pd.read_csv(HERE / "data" / "cmd_members.csv")
    n_now = len(members)

    plx = np.asarray(members["parallax"], float)
    plx_corr = np.median(plx) - cfg.step3_age.parallax_zero_point
    dist_mod = 5.0 * np.log10(1000.0 / plx_corr) - 5.0

    iso = load_isochrone(cfg)
    ext = _Ext(cfg.step2_cmd.ext_coeff_g, cfg.step2_cmd.ext_coeff_bp,
               cfg.step2_cmd.ext_coeff_rp)

    print("D19 Stage 0：顏色策略閘門")
    print(f"場星樣本 {len(field)} 顆（G<20）／現有成員 {n_now} 顆")
    print(f"距離模數 {dist_mod:.4f}（視差中位數 {np.median(plx):.4f} mas）")
    print(f"等時線 logAge={CONFIG_C_LOGAGE}, A_V={CONFIG_C_AV}（config C）")

    e_g = mag_err(field["phot_g_mean_flux_over_error"])
    e_bp = mag_err(field["phot_bp_mean_flux_over_error"])
    e_rp = mag_err(field["phot_rp_mean_flux_over_error"])

    results = [
        assess("BP-RP", field, np.hypot(e_bp, e_rp), cfg, iso, dist_mod,
               ext, thr),
        assess("G-RP", field, np.hypot(e_g, e_rp), cfg, iso, dist_mod,
               ext, thr),
    ]
    # 分段方案：每顆星只用一個顏色，依質量（等價於星等）決定用哪個。
    # 這不是第三個獨立候選，而是前兩個的組合——會提出來評估，是因為
    # 上面兩個剖面顯示它們的弱點不重疊：BP-RP 在 0.21 M☉ 以下失效，
    # 而 G-RP 的解析度最差點正好落在 0.2-0.3 M☉（dC/dM 在那裡最平），
    # 也就是 BP-RP 還很健康的區間。各自在自己強的那一段用，兩邊的
    # 弱點就都避開了。這正是計畫 Stage 3 要實作的 Hess 圖設計。
    hyb = hybrid_assessment(results[0], results[1], iso, dist_mod, ext, thr)
    if hyb is not None:
        results.append(hyb)

    xm_path = HERE / "data" / "xmatch_ir.csv"
    if not xm_path.exists():
        print(f"\n[註] 找不到 {xm_path.name}，2MASS／PanSTARRS 選項尚未評估。")
        print("     先跑 scripts/data_prep/fetch_xmatch_ir.py 產生該檔案。")
        print("     這不是「不過」，是「資料未備」——若上面的選項已過關，")
        print("     依成本由低到高的原則就不需要做交叉比對。")

    for r in results:
        print_result(r, thr, n_now)

    print(f"\n{'=' * 68}")
    print("判讀")
    print(f"{'=' * 68}")
    for r in results:
        ok_floor = r["m_floor"] <= GATE_M_FLOOR
        p = r["sigma_prof"]
        ok_sigma = p is not None and p["worst"] <= GATE_SIGMA_M
        verdict = "通過" if (ok_floor and ok_sigma) else "不通過"
        sm = f"{p['median']:.4f}/{p['worst']:.4f}" if p else "—"
        print(f"  {r['name']:<8} 質量下限 {r['m_floor']:.3f} M☉，"
              f"sigma_M 中位/最差 {sm} M☉  ->  {verdict}")
    print("\n注意：ΔN_members、f_false、C_xm 三項需要成員判定重跑（Stage 2）")
    print("與交叉比對資料才能算，本輪只結算質量下限與質量解析度兩項。")

    out = HERE / "results" / "d19_colour_gate.npz"
    np.savez(out, **{
        f"{r['name']}_table": r["table"].to_numpy() for r in results
    }, g_bins=G_BINS, thr=thr, dist_mod=dist_mod,
        m_floor=np.array([r["m_floor"] for r in results]),
        sigma_m_median=np.array([r["sigma_prof"]["median"]
                                 if r["sigma_prof"] else np.nan
                                 for r in results]),
        sigma_m_worst=np.array([r["sigma_prof"]["worst"]
                                if r["sigma_prof"] else np.nan
                                for r in results]),
        names=np.array([r["name"] for r in results]))
    print(f"\n寫入 {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
