# -*- coding: utf-8 -*-
"""把第 1–3 步串起來跑完。所有參數讀自 config.toml。

用法：
    python run_pipeline.py                 # 全跑
    python run_pipeline.py --steps 2 3     # 只跑第 2、3 步
    python run_pipeline.py --config other.toml

======================================================================
【這支程式在做什麼】
======================================================================
把 pipeline/ 底下各步驟的函式依序串起來執行，可以用 --steps 挑要跑哪幾步：
  第 1 步：讀 pyUPMASK 的成員判定結果，取機率 ≥ 0.7 的星，接回完整測光欄位
  第 2 步：測光品質篩選＋測光誤差模型 → data/cmd_members.csv、data/errmodel.npz
  第 3 步：前向模型擬合年齡與消光 → results/step3_fit.npz
  第 4 步：加入雙星比例一起擬合，並比較四種雙星判定法
           → results/step4_fit.npz、results/step4_binaries.csv
  第 5 步：質量函數與 IMF 斜率（傳統法 vs 舊版前向模型、分環量 α(r)）
           → results/step5_imf.npz、results/step5_mf_radial.csv
⚠ 目前仍在用的只有第 1、2 步（產出所有後續程式共用的 cmd_members.csv 與
  errmodel.npz）。第 3–5 步是早期「先解年齡、再解雙星、最後解 α」的循序
  流程，結果已被 fit_real.py（聯合前向模型）與 traditional_accounting.py
  取代，不再被引用（results/RESULTS_LOG.md）。預設 --steps 是 1 2 3。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse, sys, pathlib  讀參數、設定 import 路徑
第三方套件：
  numpy（np）            陣列運算；np.savez 把多個陣列存成一個 .npz 檔，
                         np.load 讀回來
  astropy.table.Table    天文表格；讀寫 CSV 與 pyUPMASK 輸出
本專案其他模組（pipeline/）：
  config       cfgmod.load()：讀 config.toml，之後用 cfg.<段落>.<設定> 取值
  isochrones   download_grid()／load_grid()／isochrone_at()：等時線下載、讀取、挑選
  step2_cmd    run()：測光品質篩選＋測光誤差模型（第 2 步本體）
  step3_age    fit()：在 (年齡, 消光) 網格上找最佳解；draw_randoms()、
               synth_populations()：生成合成星團；_Ext：消光係數盒子
  step4_binaries  fit_with_binaries()：(年齡, 消光, 雙星比例) 一起擬合；
               per_star_binary_prob()、flag_ruwe()、flag_cmd_offset()、
               flag_nss()：四種逐星雙星判定；compare_methods()：比較它們
  step5_imf    exclude_confirmed_non_members()、assign_masses()、mle_powerlaw()、
               fit_imf_forward()、mass_function_by_radius()（見該檔說明）

======================================================================
【(b) 用到的參數與意義】
======================================================================
命令列參數：
  --config  設定檔路徑，預設 repo 根目錄的 config.toml
  --steps   要跑的步驟編號，預設 1 2 3
config.toml 裡被讀到的主要設定：
  [target] name = "M45"                 組原始資料檔名用
  [step1_membership]
    membership_threshold = 0.7          成員機率門檻
    radius_deg = 5.0、g_mag_max = 18.0、parallax_min_mas = 4.0
                                        組出原始 Gaia 檔名 m45_r5_g18_plx4.csv
    random_seed = 42                    亂數種子
  [step3_age]
    distance_mode = "parallax"          距離由視差中位數決定
    parallax_zero_point = −0.017        Gaia 視差零點修正（mas）
    logage_min/max/step、mh_min/max/step  等時線網格範圍
    metallicity_mh = 0.0                固定金屬量
    n_synthetic、binary_q_*、imf        合成星團設定
  [step2_cmd] 品質篩選門檻與消光係數；[step4_binaries] 雙星判定門檻；
  [step5_imf] mass_min/max、radius_bins

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 114–148 行｜load_members()：套成員機率門檻，用 source_id 接回測光欄位
  核心 2｜第 151–166 行｜distance_modulus()：視差中位數 → 距離 → 距離模數
  核心 3｜第 178–198 行｜main() 第 1、2 步：產生 cmd_members.csv 與 errmodel.npz（現役）
  核心 4｜第 200–395 行｜main() 第 3–5 步：舊版循序擬合（已不被引用）

======================================================================
【(d) 整體流程】
======================================================================
  讀 config.toml
    → 第 1 步：讀 results/baseline.dat → 機率 ≥ 0.7 → 用 source_id 對回
      data/m45_r5_g18_plx4.csv 取得完整欄位
    → 第 2 步：step2_cmd.run() → 寫 data/cmd_members.csv、data/errmodel.npz
      （沒跑第 2 步時，直接讀這兩個檔）
    → 第 3 步（舊版）：下載等時線網格 → 算距離模數 → 只擬合年齡與消光
    → 第 4、5 步共用準備：讀網格、排除已確認非成員、重算距離模數
    → 第 4 步（舊版）：年齡、消光、雙星比例一起擬合 → 四種雙星判定法比較
    → 第 5 步（舊版）：取第 4 步的年齡／消光／雙星比例 → 傳統法查質量擬合 α
      → 舊版前向模型擬合 α → 兩者差距 → 分環量 α(r)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

# ↓ repo 根目錄（本檔在 scripts/drivers/，往上三層），加進 import 路徑
HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod          # noqa: E402
from pipeline import isochrones as isomod      # noqa: E402
from pipeline import step2_cmd, step3_age      # noqa: E402
from pipeline import step4_binaries, step5_imf  # noqa: E402


def banner(text):
    # ↓ 印一條醒目的分隔標題
    print(f"\n{'=' * 68}\n{text}\n{'=' * 68}")


# ═══════════════ 核心 1：讀成員並接回測光欄位 ═══════════════
def load_members(cfg) -> Table:
    """讀第 1 步的結果，套用成員機率門檻，並接回完整的測光欄位。

    pyUPMASK 的輸出只帶了分群用的欄位，測光品質欄位還在原始 CSV 裡，
    所以要用 source_id 接回來。
    """
    c1 = cfg.step1_membership
    # ↓ 讀 pyUPMASK 的結果（run_variant.py --name baseline 產生）
    res = Table.read(HERE / "results" / "baseline.dat", format="ascii")
    # ↓ probs_final：每顆星的成員機率；≥ 0.7 的才算成員
    p = np.asarray(res["probs_final"], float)
    sel = res[p >= c1.membership_threshold]
    print(f"成員：{len(sel):,} 顆（門檻 P >= {c1.membership_threshold}）")

    # ↓ 依設定組出原始 Gaia 檔名，例如 data/m45_r5_g18_plx4.csv
    tag = cfg.target.name.lower().replace(" ", "")
    raw_path = (HERE / "data" /
                f"{tag}_r{c1.radius_deg:g}_g{c1.g_mag_max:g}"
                f"_plx{c1.parallax_min_mas:g}.csv")
    raw = Table.read(raw_path, format="csv")

    # ↓ 建一張「source_id → 它在原始表格的第幾列」的對照字典
    idx = {int(s): i for i, s in enumerate(np.asarray(raw["source_id"], np.int64))}
    # ↓ 每顆成員在原始表格裡的列號（原始表格找不到的成員略過）
    rows = [idx[int(s)] for s in np.asarray(sel["source_id"], np.int64)
            if int(s) in idx]
    # ↓ 取出那些列 = 成員星的完整欄位
    merged = raw[rows]
    # ↓ 再把成員機率也附上去（同樣只取原始表格找得到的成員，順序對齊）
    merged["probs_final"] = np.asarray(sel["probs_final"], float)[
        [i for i, s in enumerate(np.asarray(sel["source_id"], np.int64))
         if int(s) in idx]]
    print(f"接回測光欄位：{len(merged):,} 顆")
    return merged


# ═══════════════ 核心 2：由視差算距離模數 ═══════════════
def distance_modulus(cfg, members: Table) -> float:
    c3 = cfg.step3_age
    plx = np.asarray(members["parallax"], float)
    if c3.distance_mode == "parallax":
        # ↓ 視差中位數扣掉 Gaia 的系統零點（−0.017 mas，扣掉負數等於加上）
        plx_corr = np.median(plx) - c3.parallax_zero_point
        # ↓ 距離(pc) = 1000 ÷ 視差(mas)
        d_pc = 1000.0 / plx_corr
        # ↓ 距離模數 m − M = 5·log10(距離) − 5
        dm = 5.0 * np.log10(d_pc) - 5.0
        print(f"距離：視差中位數 {np.median(plx):.4f} mas，"
              f"零點修正 {c3.parallax_zero_point:+.4f} -> {plx_corr:.4f} mas")
        print(f"      = {d_pc:.1f} pc，距離模數 {dm:.4f}")
        return dm
    raise NotImplementedError("distance_mode='free' 尚未實作")


def main():
    ap = argparse.ArgumentParser(description="星團分析 pipeline 第 1–3 步")
    ap.add_argument("--config", default=None)
    ap.add_argument("--steps", nargs="+", type=int, default=[1, 2, 3])
    a = ap.parse_args()
    # ↓ 讀設定檔
    cfg = cfgmod.load(a.config)
    print(f"設定檔：{cfg.path}")

    # ═══════════════ 核心 3：第 1、2 步（現役） ═══════════════
    members = None
    if 1 in a.steps:
        banner("第 1 步：成員判定")
        members = load_members(cfg)

    if 2 in a.steps:
        banner("第 2 步：測光品質篩選與 CMD")
        if members is None:
            members = load_members(cfg)
        # ↓ 品質篩選＋誤差模型（pipeline/step2_cmd.py）
        clean, errmodel = step2_cmd.run(cfg, members)
        # ↓ 存檔：誤差模型（字典裡每個陣列存成 .npz 的一個鍵）與乾淨成員表
        np.savez(HERE / "data" / "errmodel.npz", **errmodel)
        clean.write(HERE / "data" / "cmd_members.csv", format="csv",
                    overwrite=True)
        print(f"寫入 data/cmd_members.csv")
    else:
        # ↓ 沒跑第 2 步：讀之前存好的兩個檔
        clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
        errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))

    # ═══════════════ 核心 4：第 3–5 步（舊版循序流程） ═══════════════
    if 3 in a.steps:
        banner("第 3 步：前向模型擬合年齡與消光")
        c3 = cfg.step3_age
        # ↓ 用 config 的年齡、金屬量範圍下載（或沿用快取）等時線網格
        grid_path = isomod.download_grid(
            c3.logage_min, c3.logage_max, c3.logage_step,
            c3.mh_min, c3.mh_max, c3.mh_step)
        grid = isomod.load_grid(grid_path)
        print(f"isochrone 網格：{len(grid):,} 列")

        dm = distance_modulus(cfg, clean)
        # ↓ 觀測的顏色與 G 星等；ok：兩者都不是缺值的星
        color = np.asarray(clean["bp_rp"], float)
        mag = np.asarray(clean["phot_g_mean_mag"], float)
        ok = np.isfinite(color) & np.isfinite(mag)
        print(f"參與擬合的星：{ok.sum():,} 顆\n")

        # ↓ 只擬合年齡與消光（雙星比例、IMF 固定），回傳最佳解與整張概似網格
        res = step3_age.fit(cfg, color[ok], mag[ok], grid, errmodel, dm)
        banner("結果")
        print(f"  年齡      log(t/yr) = {res['logage']:.3f}"
              f"  ->  {res['age_myr']:.1f} Myr")
        print(f"  消光      A_V = {res['av']:.3f}")
        print(f"  距離模數  {dm:.3f}（由視差固定）")
        np.savez(HERE / "results" / "step3_fit.npz",
                 logage=res["logage"], av=res["av"], dm=dm,
                 ages=res["ages"], avs=res["avs"],
                 loglike=res["loglike_grid"])
        print(f"\n寫入 results/step3_fit.npz")

    # 第 4、5 步共用的東西
    if 4 in a.steps or 5 in a.steps:
        c3 = cfg.step3_age
        # ↓ 讀第 3 步下載過的同一份網格（依 config 範圍組出檔名）
        grid = isomod.load_grid(isomod.CACHE / (
            f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
            f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat"))
        color = np.asarray(clean["bp_rp"], float)
        mag = np.asarray(clean["phot_g_mean_mag"], float)
        ok = np.isfinite(color) & np.isfinite(mag)
        # 已確認的非成員天體（RV+logg 雙訊號，見 LIMITATIONS.md A6），
        # 顏色跟真成員無異，assign_masses() 的顏色檢查抓不到，這裡用獨立
        # 名單排除，同時影響第 4 步（雙星判定）與第 5 步（質量函數）。
        excl = step5_imf.exclude_confirmed_non_members(
            np.asarray(clean["source_id"], np.int64))
        if excl.any():
            print(f"排除 {int(excl.sum())} 顆已確認非成員天體（見 "
                  f"LIMITATIONS.md A6）")
        ok &= ~excl
        # dm 用視差中位數，理論上該用排除非成員後的樣本算（雖然單顆星
        # 對上千顆星的中位數影響可忽略不計，這裡仍改成排除之後才算，
        # 避免順序疑慮）。只套用 excl（已確認非成員），不套用完整 ok
        # （那還包含 color/mag 缺值篩選，跟 dm 原本的分母定義無關，
        # 不在這次修正範圍內）。
        dm = distance_modulus(cfg, clean[~excl])
        ext = step3_age._Ext(cfg.step2_cmd.ext_coeff_g,
                             cfg.step2_cmd.ext_coeff_bp,
                             cfg.step2_cmd.ext_coeff_rp)

    if 4 in a.steps:
        banner("第 4 步：雙星比例與多方法比較")
        # ↓ (年齡, 消光, 雙星比例) 三個一起在網格上擬合
        res4 = step4_binaries.fit_with_binaries(
            cfg, color[ok], mag[ok], grid, errmodel, dm)
        print(f"\n族群層級最佳解：")
        print(f"  年齡 {res4['age_myr']:.1f} Myr (logAge {res4['logage']:.3f})")
        print(f"  A_V  {res4['av']:.3f}")
        print(f"  雙星比例 f_bin = {res4['fbin']:.2f}")

        # ↓ 用最佳解生成一群合成星，給「前向模型雙星機率」當參考
        one = isomod.isochrone_at(grid, res4["logage"], cfg.step3_age.metallicity_mh)
        draws = step3_age.draw_randoms(
            cfg.step3_age.n_synthetic,
            np.random.default_rng(cfg.step1_membership.random_seed))
        pop = step3_age.synth_populations(
            one, cfg.step3_age.n_synthetic, dm, res4["av"], res4["fbin"],
            cfg.step3_age.binary_q_gamma, cfg.step3_age.binary_q_min,
            cfg.step3_age.imf, errmodel, ext, draws,
            g_faint=cfg.step1_membership.g_mag_max,
            g_bright=cfg.step2_cmd.g_bright_limit)

        c4 = cfg.step4_binaries
        # ↓ 每顆觀測星是雙星的機率（看它附近的合成星有多少比例是雙星）
        pb = step4_binaries.per_star_binary_prob(color[ok], mag[ok], pop, cfg)
        sub = clean[ok]
        # ↓ 四種逐星判定，各自回傳「是不是雙星」的布林陣列：
        #     前向模型  上面的機率 > 門檻（config：0.5）
        #     RUWE      天測擬合品質 > 門檻（config：1.4；雙星會讓位置擺動）
        #     CMD偏移   比單星主序亮出門檻以上（config：0.375 星等）
        #     GaiaNSS   Gaia 官方非單星目錄有標記
        flags = {
            "前向模型": np.nan_to_num(pb, nan=0.0) > c4.forward_prob_threshold,
            "RUWE": step4_binaries.flag_ruwe(sub, c4.ruwe_threshold),
            "CMD偏移": step4_binaries.flag_cmd_offset(
                color[ok], mag[ok], one, dm, res4["av"], ext,
                c4.cmd_offset_threshold),
            "GaiaNSS": step4_binaries.flag_nss(sub),
        }
        print(f"\n四種雙星判定法（樣本 {ok.sum():,} 顆）：")
        for k, v in flags.items():
            print(f"  {k:<10} 標記 {int(v.sum()):>4} 顆 "
                  f"({v.sum()/ok.sum()*100:.1f}%)")
        print()
        # ↓ 兩兩比較四種方法標記的重疊程度
        step4_binaries.compare_methods(flags).pprint(max_width=-1)

        out = Table({"source_id": sub["source_id"], "binary_prob": pb})
        for k, v in flags.items():
            out[k] = v.astype(int)
        out.write(HERE / "results" / "step4_binaries.csv", format="csv",
                  overwrite=True)
        # ↓ source_ids 一起存，讓第 5 步確認用的是同一批星
        np.savez(HERE / "results" / "step4_fit.npz",
                 logage=res4["logage"], av=res4["av"], fbin=res4["fbin"],
                 ages=res4["ages"], avs=res4["avs"], fbins=res4["fbins"],
                 loglike=res4["loglike_grid"],
                 source_ids=np.asarray(sub["source_id"], np.int64))
        print(f"\n寫入 results/step4_binaries.csv 與 step4_fit.npz")

    if 5 in a.steps:
        banner("第 5 步：質量函數與 IMF 斜率")
        f4 = np.load(HERE / "results" / "step4_fit.npz")
        # CodeRabbit 抓到的真的問題：獨立執行 --steps 5 時，第 4 步的樣本
        # 遮罩（顏色一致性檢查、已確認非成員排除，見上面 excl）可能已經
        # 改變，但這裡讀到的 step4_fit.npz 若是舊遮罩下產生的，fbin/logage/av
        # 就是用不同樣本擬合出來的，跟這裡的 clean[ok] 混用會產生不可比的
        # alpha。用存檔時記錄的 source_id 名單直接比對，不一致就拒絕執行，
        # 不要猜測兩者相容。
        if "source_ids" not in f4.files:
            raise RuntimeError(
                "results/step4_fit.npz 沒有 source_ids（舊版產生的檔案，"
                "早於這次樣本遮罩指紋檢查）。請先用 --steps 4 用目前的"
                "遮罩重跑一次第 4 步，才能執行第 5 步。")
        step4_sids = set(np.asarray(f4["source_ids"], np.int64).tolist())
        step5_sids = set(np.asarray(clean["source_id"], np.int64)[ok].tolist())
        if step4_sids != step5_sids:
            only4 = len(step4_sids - step5_sids)
            only5 = len(step5_sids - step4_sids)
            raise RuntimeError(
                f"results/step4_fit.npz 的擬合樣本跟目前第 5 步的樣本不一致"
                f"（只在第 4 步樣本裡：{only4} 顆；只在目前樣本裡：{only5} 顆）。"
                f"代表 step4_fit.npz 是用不同的遮罩（例如尚未套用顏色一致性"
                f"檢查或已確認非成員排除）產生的，直接混用 fbin/logage/av"
                f"會得到不可比的 alpha。請先用 --steps 4 重新產生 "
                f"step4_fit.npz 再執行第 5 步。")
        # ↓ 年齡、消光、雙星比例直接取第 4 步的結果（固定，不再變動）
        logage, av, fbin = float(f4["logage"]), float(f4["av"]), float(f4["fbin"])
        one = isomod.isochrone_at(grid, logage, cfg.step3_age.metallicity_mh)
        c5 = cfg.step5_imf

        print("方法 A：把每顆星當單星指派質量，再做 MLE 冪律擬合")
        # ↓ 傳統法：每顆星查質量 → 冪律擬合（見 pipeline/step5_imf.py 核心 2、3）
        masses = step5_imf.assign_masses(mag[ok], one, dm, av, ext,
                                         obs_color=color[ok])
        fitA = step5_imf.mle_powerlaw(masses, c5.mass_min, c5.mass_max)
        print(f"  alpha = {fitA['alpha']:.3f} +/- {fitA['alpha_err']:.3f}"
              f"  (n={fitA['n']:,}，質量 {c5.mass_min}-{c5.mass_max} M_sun)")

        print("\n方法 B：把 IMF 斜率當前向模型的自由參數")
        # ↓ 舊版前向模型：只讓 α 變（見 pipeline/step5_imf.py 核心 4）
        fitB = step5_imf.fit_imf_forward(
            cfg, color[ok], mag[ok], one, errmodel, dm, av, fbin,
            verbose=False)
        print(f"  alpha = {fitB['alpha']:.3f}")

        # ↓ 兩法差距 ≈ 傳統法忽略未解析雙星造成的偏差
        bias = fitA["alpha"] - fitB["alpha"]
        print(f"\n兩法差距 = {bias:+.3f}")
        print(f"  Salpeter 參考值 2.35，Kroupa 高質量端 2.30")

        print("\n質量函數隨半徑的變化（質量分層）：")
        # 真正的天球角距，不能直接用 RA 相減（dec=24 度處 RA 一度只有 0.91 天球度）
        # ↓ 每顆星到星團中心（用 RA、Dec 中位數當中心）的球面角距：
        #   cos(角距) = sin δ0 sin δ + cos δ0 cos δ cos(α − α0)
        ra = np.radians(np.asarray(clean["ra"], float)[ok])
        dec = np.radians(np.asarray(clean["dec"], float)[ok])
        ra0 = np.radians(np.median(np.asarray(clean["ra"], float)))
        dec0 = np.radians(np.median(np.asarray(clean["dec"], float)))
        cosr = (np.sin(dec0) * np.sin(dec)
                + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0))
        # ↓ np.clip 把值限制在 [−1, 1]，避免浮點誤差讓 arccos 出錯
        r = np.degrees(np.arccos(np.clip(cosr, -1, 1)))
        # ↓ 依 radius_bins 分環，每環各擬合一次 α
        tbl = step5_imf.mass_function_by_radius(
            masses, r, list(c5.radius_bins), c5.mass_min, c5.mass_max)
        tbl.pprint(max_width=-1)

        np.savez(HERE / "results" / "step5_imf.npz",
                 alpha_naive=fitA["alpha"], alpha_naive_err=fitA["alpha_err"],
                 alpha_forward=fitB["alpha"], bias=bias,
                 alphas=fitB["alphas"], loglike=fitB["loglike_grid"],
                 masses=masses)
        tbl.write(HERE / "results" / "step5_mf_radial.csv", format="csv",
                  overwrite=True)
        print(f"\n寫入 results/step5_imf.npz 與 step5_mf_radial.csv")


if __name__ == "__main__":
    main()
