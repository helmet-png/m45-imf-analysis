# -*- coding: utf-8 -*-
"""把第 1–3 步串起來跑完。所有參數讀自 config.toml。

用法：
    python run_pipeline.py                 # 全跑
    python run_pipeline.py --steps 2 3     # 只跑第 2、3 步
    python run_pipeline.py --config other.toml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod          # noqa: E402
from pipeline import isochrones as isomod      # noqa: E402
from pipeline import step2_cmd, step3_age      # noqa: E402
from pipeline import step4_binaries, step5_imf  # noqa: E402


def banner(text):
    print(f"\n{'=' * 68}\n{text}\n{'=' * 68}")


def load_members(cfg) -> Table:
    """讀第 1 步的結果，套用成員機率門檻，並接回完整的測光欄位。

    pyUPMASK 的輸出只帶了分群用的欄位，測光品質欄位還在原始 CSV 裡，
    所以要用 source_id 接回來。
    """
    c1 = cfg.step1_membership
    res = Table.read(HERE / "results" / "baseline.dat", format="ascii")
    p = np.asarray(res["probs_final"], float)
    sel = res[p >= c1.membership_threshold]
    print(f"成員：{len(sel):,} 顆（門檻 P >= {c1.membership_threshold}）")

    tag = cfg.target.name.lower().replace(" ", "")
    raw_path = (HERE / "data" /
                f"{tag}_r{c1.radius_deg:g}_g{c1.g_mag_max:g}"
                f"_plx{c1.parallax_min_mas:g}.csv")
    raw = Table.read(raw_path, format="csv")

    idx = {int(s): i for i, s in enumerate(np.asarray(raw["source_id"], np.int64))}
    rows = [idx[int(s)] for s in np.asarray(sel["source_id"], np.int64)
            if int(s) in idx]
    merged = raw[rows]
    merged["probs_final"] = np.asarray(sel["probs_final"], float)[
        [i for i, s in enumerate(np.asarray(sel["source_id"], np.int64))
         if int(s) in idx]]
    print(f"接回測光欄位：{len(merged):,} 顆")
    return merged


def distance_modulus(cfg, members: Table) -> float:
    c3 = cfg.step3_age
    plx = np.asarray(members["parallax"], float)
    if c3.distance_mode == "parallax":
        plx_corr = np.median(plx) - c3.parallax_zero_point
        d_pc = 1000.0 / plx_corr
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
    cfg = cfgmod.load(a.config)
    print(f"設定檔：{cfg.path}")

    members = None
    if 1 in a.steps:
        banner("第 1 步：成員判定")
        members = load_members(cfg)

    if 2 in a.steps:
        banner("第 2 步：測光品質篩選與 CMD")
        if members is None:
            members = load_members(cfg)
        clean, errmodel = step2_cmd.run(cfg, members)
        np.savez(HERE / "data" / "errmodel.npz", **errmodel)
        clean.write(HERE / "data" / "cmd_members.csv", format="csv",
                    overwrite=True)
        print(f"寫入 data/cmd_members.csv")
    else:
        clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
        errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))

    if 3 in a.steps:
        banner("第 3 步：前向模型擬合年齡與消光")
        c3 = cfg.step3_age
        grid_path = isomod.download_grid(
            c3.logage_min, c3.logage_max, c3.logage_step,
            c3.mh_min, c3.mh_max, c3.mh_step)
        grid = isomod.load_grid(grid_path)
        print(f"isochrone 網格：{len(grid):,} 列")

        dm = distance_modulus(cfg, clean)
        color = np.asarray(clean["bp_rp"], float)
        mag = np.asarray(clean["phot_g_mean_mag"], float)
        ok = np.isfinite(color) & np.isfinite(mag)
        print(f"參與擬合的星：{ok.sum():,} 顆\n")

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
        grid = isomod.load_grid(isomod.CACHE / (
            f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
            f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat"))
        dm = distance_modulus(cfg, clean)
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
        ext = step3_age._Ext(cfg.step2_cmd.ext_coeff_g,
                             cfg.step2_cmd.ext_coeff_bp,
                             cfg.step2_cmd.ext_coeff_rp)

    if 4 in a.steps:
        banner("第 4 步：雙星比例與多方法比較")
        res4 = step4_binaries.fit_with_binaries(
            cfg, color[ok], mag[ok], grid, errmodel, dm)
        print(f"\n族群層級最佳解：")
        print(f"  年齡 {res4['age_myr']:.1f} Myr (logAge {res4['logage']:.3f})")
        print(f"  A_V  {res4['av']:.3f}")
        print(f"  雙星比例 f_bin = {res4['fbin']:.2f}")

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
        pb = step4_binaries.per_star_binary_prob(color[ok], mag[ok], pop, cfg)
        sub = clean[ok]
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
        step4_binaries.compare_methods(flags).pprint(max_width=-1)

        out = Table({"source_id": sub["source_id"], "binary_prob": pb})
        for k, v in flags.items():
            out[k] = v.astype(int)
        out.write(HERE / "results" / "step4_binaries.csv", format="csv",
                  overwrite=True)
        np.savez(HERE / "results" / "step4_fit.npz",
                 logage=res4["logage"], av=res4["av"], fbin=res4["fbin"],
                 ages=res4["ages"], avs=res4["avs"], fbins=res4["fbins"],
                 loglike=res4["loglike_grid"])
        print(f"\n寫入 results/step4_binaries.csv 與 step4_fit.npz")

    if 5 in a.steps:
        banner("第 5 步：質量函數與 IMF 斜率")
        f4 = np.load(HERE / "results" / "step4_fit.npz")
        logage, av, fbin = float(f4["logage"]), float(f4["av"]), float(f4["fbin"])
        one = isomod.isochrone_at(grid, logage, cfg.step3_age.metallicity_mh)
        c5 = cfg.step5_imf

        print("方法 A：把每顆星當單星指派質量，再做 MLE 冪律擬合")
        masses = step5_imf.assign_masses(mag[ok], one, dm, av, ext,
                                         obs_color=color[ok])
        fitA = step5_imf.mle_powerlaw(masses, c5.mass_min, c5.mass_max)
        print(f"  alpha = {fitA['alpha']:.3f} +/- {fitA['alpha_err']:.3f}"
              f"  (n={fitA['n']:,}，質量 {c5.mass_min}-{c5.mass_max} M_sun)")

        print("\n方法 B：把 IMF 斜率當前向模型的自由參數")
        fitB = step5_imf.fit_imf_forward(
            cfg, color[ok], mag[ok], one, errmodel, dm, av, fbin,
            verbose=False)
        print(f"  alpha = {fitB['alpha']:.3f}")

        bias = fitA["alpha"] - fitB["alpha"]
        print(f"\n兩法差距 = {bias:+.3f}")
        print(f"  Salpeter 參考值 2.35，Kroupa 高質量端 2.30")

        print("\n質量函數隨半徑的變化（質量分層）：")
        # 真正的天球角距，不能直接用 RA 相減（dec=24 度處 RA 一度只有 0.91 天球度）
        ra = np.radians(np.asarray(clean["ra"], float)[ok])
        dec = np.radians(np.asarray(clean["dec"], float)[ok])
        ra0 = np.radians(np.median(np.asarray(clean["ra"], float)))
        dec0 = np.radians(np.median(np.asarray(clean["dec"], float)))
        cosr = (np.sin(dec0) * np.sin(dec)
                + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0))
        r = np.degrees(np.arccos(np.clip(cosr, -1, 1)))
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
