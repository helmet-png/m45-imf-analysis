# -*- coding: utf-8 -*-
"""Run the M45 JointModel on a prepared non-M45 cluster.

This is a portability test, not a claim that HR23 age/extinction or solar
metallicity are final astrophysical measurements.  It reuses the production
JointModel, Hess likelihood, binary population and IMF sampling, while routing
all data/error/selection inputs through cluster-specific filenames.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline.table_compat import Table as _CompatTable  # noqa: E402

_a = types.ModuleType("astropy")
_t = types.ModuleType("astropy.table")
_t.Table = _CompatTable
_a.table = _t
sys.modules.setdefault("astropy", _a)
sys.modules.setdefault("astropy.table", _t)

from pipeline import config as cfgmod, isochrones as isomod  # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline.step3_age import draw_randoms                   # noqa: E402
from injection_recovery import (                              # noqa: E402
    check_walls, make_fake, multi_stage_best)

Table = _CompatTable


def _axis(lo: float, hi: float, step: float) -> np.ndarray:
    values = np.arange(lo, hi + step * 0.25, step)
    values = values[values <= hi + 1e-9]
    if values[-1] < hi - 1e-9:
        values = np.append(values, hi)
    return values


def build_axes(grid, logage: float, av: float, fit_age_av: bool,
               alpha_min: float, alpha_max: float,
               age_min: float | None = None, age_max: float | None = None,
               av_min: float | None = None, av_max: float | None = None,
               age_stride: int = 1, fbin_step: float = 0.10,
               alpha_step: float = 0.20, qgamma_step: float = 0.50,
               fixed_logage: float | None = None,
               fixed_av: float | None = None, fit_mh: bool = False,
               mh_min: float = -0.3, mh_max: float = 0.4):
    ages = np.unique(np.asarray(grid["logAge"], float))
    metallicities = np.unique(np.asarray(grid["MH"], float))
    used_age = float(ages[np.argmin(np.abs(ages - logage))])
    if fit_age_av:
        alo = logage - 0.16 if age_min is None else age_min
        ahi = logage + 0.16 if age_max is None else age_max
        vlo = max(0.0, av - 0.20) if av_min is None else av_min
        vhi = min(0.60, av + 0.20) if av_max is None else av_max
        age_axis = ages[(ages >= alo - 1e-9) & (ages <= ahi + 1e-9)]
        age_axis = age_axis[::max(1, age_stride)]
        av_axis = _axis(vlo, vhi, 0.10)
    else:
        requested_age = logage if fixed_logage is None else fixed_logage
        age_axis = np.array([
            float(ages[np.argmin(np.abs(ages - requested_age))])])
        av_axis = np.array([av if fixed_av is None else fixed_av])
    if fit_mh:
        mh_axis = metallicities[(metallicities >= mh_min - 1e-9)
                                & (metallicities <= mh_max + 1e-9)]
    else:
        mh_axis = np.array([
            float(metallicities[np.argmin(np.abs(metallicities))])])
    axes = [age_axis, av_axis,
            _axis(0.00, 1.00, fbin_step),
            _axis(alpha_min, alpha_max, alpha_step),
            mh_axis,
            _axis(-1.50, 1.50, qgamma_step)]
    return axes, used_age


def configure_for_grid(cfg, axes, n_synthetic: int):
    # JointModel constructs its isochrone cache from these bounds.  The M45
    # defaults ended at logAge=8.30, so leaving them untouched silently removes
    # both target clusters from the model cache.
    j = cfg._data["joint_fit"]
    j["logage_min"], j["logage_max"] = float(axes[0].min()), float(axes[0].max())
    j["av_min"], j["av_max"] = float(axes[1].min()), float(axes[1].max())
    j["mh_min"], j["mh_max"] = float(axes[4].min()), float(axes[4].max())
    j["mh_prior_sigma"] = 0.0
    j["fbin_min"], j["fbin_max"] = float(axes[2].min()), float(axes[2].max())
    j["alpha_min"], j["alpha_max"] = float(axes[3].min()), float(axes[3].max())
    j["qgamma_min"], j["qgamma_max"] = float(axes[5].min()), float(axes[5].max())
    cfg._data["step3_age"]["n_synthetic"] = int(n_synthetic)


def fit_once(base, axes, selection, seed: int, refines, n_proc: int):
    model = copy.copy(base)
    model.selection = selection
    model.draws = draw_randoms(model.n_syn, np.random.default_rng(seed))
    started = time.time()
    # Zero differential-extinction scatter is an allowed physical boundary.
    # Other boundary solutions are retained only as diagnostics, never IMF fits.
    allowed_wall = (6,) if len(axes) > 6 else ()
    best, lp, bounds = multi_stage_best(
        model, [np.asarray(x) for x in axes], refines, n_proc,
        allow_wall=allowed_wall, raise_on_wall=False, no_refine=(0, 4))
    names = joint_fit.PARAM_NAMES + (["dav"] if len(best) > 6 else [])
    unexpected_hits = check_walls(best, bounds, names, allow=allowed_wall)
    wall_hits = [{"kind": kind, "message": message}
                 for kind, message in unexpected_hits]
    return (model, best, float(lp), bounds, wall_hits, bool(wall_hits),
            time.time() - started)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hr23-name", required=True)
    ap.add_argument("--grid", required=True)
    ap.add_argument("--n-syn", type=int, default=15000)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--injection-trials", type=int, default=3)
    ap.add_argument("--refines", default="3,3")
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--fit-age-av", action="store_true",
                    help="fit age and A_V locally instead of fixing HR23 values")
    ap.add_argument("--alpha-min", type=float, default=0.8)
    ap.add_argument("--alpha-max", type=float, default=3.5)
    ap.add_argument("--age-min", type=float, default=None)
    ap.add_argument("--age-max", type=float, default=None)
    ap.add_argument("--av-min", type=float, default=None)
    ap.add_argument("--av-max", type=float, default=None)
    ap.add_argument("--age-stride", type=int, default=1,
                    help="use every Nth isochrone age in the coarse search")
    ap.add_argument("--fbin-step", type=float, default=0.10)
    ap.add_argument("--alpha-step", type=float, default=0.20)
    ap.add_argument("--qgamma-step", type=float, default=0.50)
    ap.add_argument("--fixed-logage", type=float, default=None)
    ap.add_argument("--fixed-av", type=float, default=None)
    ap.add_argument("--fit-mh", action="store_true")
    ap.add_argument("--mh-min", type=float, default=-0.3)
    ap.add_argument("--mh-max", type=float, default=0.4)
    ap.add_argument("--tag", default="",
                    help="optional output suffix, e.g. _age_extended")
    ap.add_argument("--fit-dav", action="store_true",
                    help="fit differential-extinction scatter as a seventh parameter")
    ap.add_argument("--dav-max", type=float, default=0.6)
    ap.add_argument("--dav-step", type=float, default=0.15)
    args = ap.parse_args()
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    n_proc = args.procs or (os.cpu_count() or 1)

    tag = args.hr23_name
    params = json.loads((HERE / "data" / f"hr23_{tag}_params.json")
                        .read_text(encoding="utf-8"))
    clean = Table.read(HERE / "data" / f"cluster_{tag}_cmd_members.csv",
                       format="csv")
    errmodel = dict(np.load(HERE / "data" / f"cluster_{tag}_errmodel.npz"))
    selection = selmod.load(HERE / "data" / f"cluster_{tag}_selection.npz")
    grid = isomod.load_grid(isomod.CACHE / args.grid)
    axes, used_age = build_axes(
        grid, float(params["logAge50"]), float(params["AV50"]),
        args.fit_age_av, args.alpha_min, args.alpha_max,
        args.age_min, args.age_max, args.av_min, args.av_max,
        args.age_stride, args.fbin_step, args.alpha_step,
        args.qgamma_step, args.fixed_logage, args.fixed_av, args.fit_mh,
        args.mh_min, args.mh_max)

    cfg = cfgmod.load()
    configure_for_grid(cfg, axes, args.n_syn)
    c3 = cfg.step3_age
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    in_hess = (np.isfinite(color) & np.isfinite(mag)
               & (color >= c3.hess_color_range[0])
               & (color <= c3.hess_color_range[1])
               & (mag >= c3.hess_mag_range[0])
               & (mag <= c3.hess_mag_range[1]))
    color, mag = color[in_hess], mag[in_hess]
    dm = float(params["MOD50"])
    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    base.use_native_bprp_err = True
    if args.fit_dav:
        base.enable_dav_fit(0.0, args.dav_max)
        axes.append(_axis(0.0, args.dav_max, args.dav_step))
    print(f"{tag}：觀測 {len(clean):,} 顆，Hess 範圍內 {len(color):,} 顆；"
          f"DM={dm:.3f}，n_synthetic={args.n_syn:,}")
    print(f"HR23 logAge={float(params['logAge50']):.4f}，最近網格 "
          f"{used_age:.3f}；A_V={float(params['AV50']):.3f}")
    print("年齡/A_V：" + ("局部自由擬合" if args.fit_age_av
                         else f"固定為 {axes[0][0]:.3f}/{axes[1][0]:.3f}"))
    print("金屬量：" + (f"自由擬合 {axes[4].min():+.2f}–{axes[4].max():+.2f}"
                       if args.fit_mh else "固定 [M/H]=0.00"))

    configs = {"A": None, "B": selection}
    fitted = {}
    diagnostics = {}
    for key, sel in configs.items():
        print(f"\n{'='*70}\n{key}："
              f"{'套用星團專屬選擇函數' if sel is not None else '不套選擇函數'}\n"
              f"{'='*70}", flush=True)
        rows = []
        diagnostics[key] = []
        for repeat in range(args.repeats):
            _, best, lp, bounds, wall_hits, has_unexpected_wall, elapsed = fit_once(
                base, axes, sel, 8200 + 101 * repeat, refines, n_proc)
            rows.append(best)
            diagnostics[key].append({
                "log_posterior": lp,
                "wall_hits": wall_hits,
                "has_unexpected_wall": has_unexpected_wall,
                "valid_for_imf": not has_unexpected_wall,
                "diagnostic_only": has_unexpected_wall,
                "elapsed_s": elapsed})
            walls = [hit["message"] for hit in wall_hits]
            line = (f"第 {repeat+1} 次：alpha={best[3]:.3f}，"
                    f"f_bin={best[2]:.3f}，q_gamma={best[5]:.3f}，"
                    f"logAge={best[0]:.3f}，A_V={best[1]:.3f}，")
            if len(best) > 6:
                line += f"dav={best[6]:.3f}，"
            print(line + f"{elapsed:.1f}s", flush=True)
            if walls:
                print("  邊界：" + "；".join(walls), flush=True)
        fitted[key] = np.asarray(rows)
        print(f"{key} alpha={fitted[key][:, 3].mean():.3f} ± "
              f"{fitted[key][:, 3].std():.3f}（模型亂數重現性）")

    fit_validity = {
        key: np.asarray([not row["has_unexpected_wall"]
                         for row in diagnostics[key]], dtype=bool)
        for key in fitted}
    valid_fitted = {key: fitted[key][fit_validity[key]] for key in fitted}

    injection = []
    if args.injection_trials > 0 and len(valid_fitted["B"]):
        truth = valid_fitted["B"].mean(axis=0)
        print(f"\n{'='*70}\n注入回收：以 B 平均最佳解為已知真值\n{'='*70}")
        for trial in range(args.injection_trials):
            gen = copy.copy(base)
            gen.selection = selection
            fake_color, fake_mag = make_fake(
                gen, truth, len(color), 9300 + trial,
                dav=(float(truth[6]) if len(truth) > 6 else 0.0),
                selection=selection, n_gen=max(100000, len(color) * 250))
            fake_base = base.with_observations(fake_color, fake_mag)
            _, got, lp, bounds, wall_hits, has_unexpected_wall, elapsed = fit_once(
                fake_base, axes, selection, 10200 + 101 * trial,
                refines, n_proc)
            if has_unexpected_wall:
                raise RuntimeError(
                    "Injection-recovery fit reached an unexpected boundary; "
                    "do not use this recovery trial: "
                    + "; ".join(hit["message"] for hit in wall_hits))
            injection.append(got)
            print(f"第 {trial+1} 次：alpha 真值 {truth[3]:.3f} -> "
                  f"{got[3]:.3f}（差 {got[3]-truth[3]:+.3f}），"
                  f"{elapsed:.1f}s", flush=True)
        injection = np.asarray(injection)
        print(f"注入回收 alpha 偏差 {np.mean(injection[:,3]-truth[3]):+.3f}，"
              f"散布 {np.std(injection[:,3]-truth[3]):.3f}")
    else:
        if args.injection_trials > 0:
            print("Skipping injection recovery: no valid selection-model fit.",
                  flush=True)
        truth = np.full(len(axes), np.nan)
        injection = np.empty((0, len(axes)))

    mode = "free_age_av" if args.fit_age_av else "fixed_age_av"
    if args.fit_mh:
        mode += "_free_mh"
    if args.fit_dav:
        mode += "_free_dav"
    mode += args.tag
    npz_path = HERE / "results" / f"cluster_forward_{tag}_{mode}.npz"
    json_path = HERE / "results" / f"cluster_forward_{tag}_{mode}.json"
    parameter_names = joint_fit.PARAM_NAMES + (["dav"] if args.fit_dav else [])
    effective_axes = {name: np.asarray(axis, float).tolist()
                      for name, axis in zip(parameter_names, axes)}
    np.savez(npz_path, A=fitted["A"], B=fitted["B"], truth=truth,
             injection=injection, n_obs=len(color), n_clean=len(clean),
             parameter_names=np.asarray(parameter_names),
             effective_axes_json=json.dumps(effective_axes),
             valid_for_imf_A=fit_validity["A"],
             valid_for_imf_B=fit_validity["B"],
             diagnostic_only_A=~fit_validity["A"],
             diagnostic_only_B=~fit_validity["B"],
             hr23_logage=float(params["logAge50"]),
             hr23_av=float(params["AV50"]), dm=dm,
             n_synthetic=args.n_syn)
    summary = {
        "hr23_name": tag, "mode": mode, "n_clean": len(clean),
        "n_hess": len(color), "n_synthetic": args.n_syn,
        "grid": args.grid, "hr23_logage": float(params["logAge50"]),
        "hr23_av": float(params["AV50"]), "effective_axes": effective_axes,
        "dm": dm,
        "fits": {k: {"n_valid_runs": int(len(valid_fitted[k])),
                     "mean": (valid_fitted[k].mean(axis=0).tolist()
                              if len(valid_fitted[k]) else None),
                     "std": (valid_fitted[k].std(axis=0).tolist()
                             if len(valid_fitted[k]) else None),
                     "runs": fitted[k].tolist(),
                     "diagnostics": diagnostics[k]} for k in fitted},
        "injection": {
            "truth": (truth.tolist() if len(injection) else None),
            "runs": injection.tolist(),
            "alpha_bias": (float(np.mean(injection[:, 3] - truth[3]))
                           if len(injection) else None),
            "alpha_scatter": (float(np.std(injection[:, 3] - truth[3]))
                              if len(injection) else None)},
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"\n寫入 {npz_path.relative_to(HERE)}、{json_path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
