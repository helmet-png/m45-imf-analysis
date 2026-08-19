# -*- coding: utf-8 -*-
"""Prepare cluster-specific inputs for the M45 forward model.

The M45 pipeline assumes that step 1 already produced a Gaia table limited to
G <= 18.  HR23's published member snapshots only contain magnitudes, RUWE and
NSS, so they are sufficient for the traditional estimator but not for the
photometric error model or the quality-cut selection function.  This script
joins the checked-in HR23 source IDs back to Gaia DR3, applies the same cuts as
M45, and writes one independent clean table/error model/selection model per
cluster.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import ssl
import sys
import time
import types
import urllib.parse
import urllib.request
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

from pipeline import config as cfgmod, selection as selmod  # noqa: E402
from pipeline.step2_cmd import (                            # noqa: E402
    apply_quality_cuts, bp_rp_excess_expected, bp_rp_excess_sigma,
    photometric_error_model)

Table = _CompatTable

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
GAIA_COLUMNS = (
    "source_id", "ra", "dec", "parallax", "parallax_error",
    "phot_g_mean_mag", "phot_g_mean_flux_over_error",
    "phot_bp_mean_mag", "phot_bp_mean_flux_over_error",
    "phot_rp_mean_mag", "phot_rp_mean_flux_over_error",
    "phot_bp_rp_excess_factor", "bp_rp", "ruwe")


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _post_csv(query: str, retries: int = 3) -> list[dict]:
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
        "QUERY": query}).encode()
    req = urllib.request.Request(
        GAIA_TAP, data=body,
        headers={"User-Agent": "m45-pipeline/1.0 (academic research)"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(
                    req, timeout=240, context=_ssl_context()) as response:
                return list(csv.DictReader(io.StringIO(
                    response.read().decode("utf-8", "replace"))))
        except Exception as exc:  # network retry, then preserve the real error
            last = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Gaia TAP query failed after {retries} attempts") from last


def fetch_gaia(source_ids: list[str], chunk_size: int = 200) -> list[dict]:
    rows = []
    cols = ",".join(GAIA_COLUMNS)
    for start in range(0, len(source_ids), chunk_size):
        chunk = source_ids[start:start + chunk_size]
        query = (f"SELECT {cols} FROM gaiadr3.gaia_source WHERE source_id IN ("
                 + ",".join(chunk) + ")")
        part = _post_csv(query)
        rows.extend(part)
        print(f"  Gaia {min(start + chunk_size, len(source_ids)):,}/"
              f"{len(source_ids):,}（取回累計 {len(rows):,}）", flush=True)
    return rows


def fetch_control_field(raw: Table, max_rows: int = 1000) -> Table:
    """Fetch a local Gaia sample for the survey-selection calibration.

    HR23 members do not span Gaia's full colour/SNR distribution.  Selection is
    a survey property, so the SNR regression uses nearby field sources too.
    """
    ra = np.asarray(raw["ra"], float)
    dec = np.asarray(raw["dec"], float)
    finite = np.isfinite(ra) & np.isfinite(dec)
    if finite.sum() == 0:
        raise ValueError("cannot define a control field without finite RA/Dec")
    ra0, dec0 = float(np.median(ra[finite])), float(np.median(dec[finite]))
    query = (
        f"SELECT TOP {int(max_rows)} {','.join(GAIA_COLUMNS)} "
        "FROM gaiadr3.gaia_source "
        "WHERE 1=CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra0:.8f}, {dec0:.8f}, 1.5)) "
        "AND phot_g_mean_mag <= 18 ORDER BY source_id")
    rows = _post_csv(query)
    member_ids = set(np.asarray(raw["source_id"], np.int64).tolist())
    rows = [row for row in rows if int(row["source_id"]) not in member_ids]
    if len(rows) < 100:
        raise RuntimeError(
            f"control field has only {len(rows)} non-member stars; need at least 100")
    names = ("source_id",) + tuple(c for c in GAIA_COLUMNS if c != "source_id")
    return Table({name: np.asarray([
        int(row[name]) if name == "source_id" else _float(row[name])
        for row in rows]) for name in names})


def read_hr23(name: str, prob_min: float) -> tuple[dict, list[dict]]:
    params_path = HERE / "data" / f"hr23_{name}_params.json"
    members_path = HERE / "data" / f"hr23_{name}_members.csv"
    if not (params_path.exists() and members_path.exists()):
        raise FileNotFoundError(
            f"missing checked-in HR23 inputs for {name}: {params_path.name}, "
            f"{members_path.name}")
    params = json.loads(params_path.read_text(encoding="utf-8"))
    with members_path.open(newline="", encoding="utf-8") as fh:
        members = [r for r in csv.DictReader(fh)
                   if float(r["Prob"]) >= prob_min]
    return params, members


def _float(value):
    return (float(value) if value not in (None, "", "null", "NaN")
            else np.nan)


def merge_rows(hr23: list[dict], gaia_rows: list[dict]) -> Table:
    by_id = {str(r["source_id"]): r for r in gaia_rows}
    merged = []
    for member in hr23:
        sid = str(member["GaiaDR3"])
        gaia = by_id.get(sid)
        if gaia is None:
            continue
        row = {c: _float(gaia[c]) for c in GAIA_COLUMNS if c != "source_id"}
        row["source_id"] = int(sid)
        row["membership_probability"] = float(member["Prob"])
        row["hr23_ruwe"] = _float(member["RUWE"])
        row["hr23_nss"] = _float(member["NSS"])
        merged.append(row)
    # Keep source_id first for readable, stable CSV output.
    names = ("source_id",) + tuple(c for c in GAIA_COLUMNS if c != "source_id") + (
        "membership_probability", "hr23_ruwe", "hr23_nss")
    return Table({name: np.asarray([r[name] for r in merged]) for name in names})


def build_excess_curve(raw: Table, c2, bin_width: float = 1.0):
    g = np.asarray(raw["phot_g_mean_mag"], float)
    bp = np.asarray(raw["phot_bp_mean_mag"], float)
    rp = np.asarray(raw["phot_rp_mean_mag"], float)
    colour = np.asarray(raw["bp_rp"], float)
    e = np.asarray(raw["phot_bp_rp_excess_factor"], float)
    snr_g = np.asarray(raw["phot_g_mean_flux_over_error"], float)
    snr_bp = np.asarray(raw["phot_bp_mean_flux_over_error"], float)
    snr_rp = np.asarray(raw["phot_rp_mean_flux_over_error"], float)
    finite = np.isfinite(g) & np.isfinite(bp) & np.isfinite(rp)
    snr_ok = (finite & (snr_g >= c2.min_flux_snr_g)
              & (snr_bp >= c2.min_flux_snr_bp)
              & (snr_rp >= c2.min_flux_snr_rp))
    resid = e - bp_rp_excess_expected(colour)
    excess_ok = (np.isfinite(resid)
                 & (np.abs(resid) < c2.bp_rp_excess_sigma
                    * bp_rp_excess_sigma(g)))
    if snr_ok.sum() < 10:
        return np.array([np.nanmedian(g)]), np.array([1.0])
    lo, hi = np.floor(np.nanmin(g[snr_ok])), np.ceil(np.nanmax(g[snr_ok]))
    edges = np.arange(lo, hi + bin_width, bin_width)
    if len(edges) < 2:
        edges = np.array([lo, lo + bin_width])
    n_all, _ = np.histogram(g[snr_ok], edges)
    n_keep, _ = np.histogram(g[snr_ok & excess_ok], edges)
    centres = 0.5 * (edges[:-1] + edges[1:])
    good = n_all >= 10
    if not good.any():
        return np.array([np.nanmedian(g[snr_ok])]), np.array([
            float(excess_ok[snr_ok].mean())])
    frac = np.ones(len(centres))
    frac[good] = n_keep[good] / n_all[good]
    frac = np.interp(centres, centres[good], frac[good])
    return centres, np.clip(frac, 0.0, 1.0)


def validate_selection(model, raw: Table, clean: Table) -> dict:
    g = np.asarray(raw["phot_g_mean_mag"], float)
    bp = np.asarray(raw["phot_bp_mean_mag"], float)
    rp = np.asarray(raw["phot_rp_mean_mag"], float)
    sid = np.asarray(raw["source_id"], np.int64)
    kept_ids = set(np.asarray(clean["source_id"], np.int64).tolist())
    finite = np.isfinite(g) & np.isfinite(bp) & np.isfinite(rp)
    g, bp, rp, sid = g[finite], bp[finite], rp[finite], sid[finite]
    observed = np.array([x in kept_ids for x in sid], float)
    predicted = np.zeros(len(g))
    rng = np.random.default_rng(7102)
    for _ in range(100):
        predicted += model.keep(g, bp, rp, rng.normal(size=len(g)),
                                rng.random(len(g)))
    predicted /= 100
    overall_error = float(predicted.mean() - observed.mean())
    worst = 0.0
    used_bins = 0
    for lo in np.arange(np.floor(g.min()), np.ceil(g.max()), 1.0):
        mask = (g >= lo) & (g < lo + 1)
        if mask.sum() >= 20:
            worst = max(worst, abs(float(predicted[mask].mean()
                                        - observed[mask].mean())))
            used_bins += 1
    faint = g >= 17.0
    if faint.sum() >= 20:
        colour = bp - rp
        split = float(np.median(colour[faint]))
        red, blue = faint & (colour > split), faint & (colour <= split)
        if red.any() and blue.any():
            observed_red, observed_blue = float(observed[red].mean()), float(observed[blue].mean())
            predicted_red, predicted_blue = float(predicted[red].mean()), float(predicted[blue].mean())
            colour_difference_error = ((predicted_red - predicted_blue)
                                       - (observed_red - observed_blue))
            pass_colour_split = abs(colour_difference_error) < 0.10
        else:
            observed_red = observed_blue = np.nan
            predicted_red = predicted_blue = colour_difference_error = np.nan
            pass_colour_split = False
    else:
        split = observed_red = observed_blue = np.nan
        predicted_red = predicted_blue = colour_difference_error = np.nan
        pass_colour_split = False
    passed = (abs(overall_error) < 0.02 and used_bins > 0 and worst < 0.08
              and pass_colour_split)
    return {
        "observed_survival": float(observed.mean()),
        "predicted_survival": float(predicted.mean()),
        "overall_error": overall_error,
        "worst_mag_bin_error": worst,
        "n_validation_bins": used_bins,
        "pass_overall": abs(overall_error) < 0.02,
        "pass_mag_bins": used_bins > 0 and worst < 0.08,
        "faint_colour_split_bp_rp": split,
        "observed_survival_red": observed_red,
        "observed_survival_blue": observed_blue,
        "predicted_survival_red": predicted_red,
        "predicted_survival_blue": predicted_blue,
        "red_minus_blue_error": colour_difference_error,
        "pass_faint_colour_split": pass_colour_split,
        "passed": passed,
    }


def save_selection(path: Path, model) -> None:
    np.savez(path,
             **{f"{band}_{key}": np.asarray(model.fits[band][key])
                for band in selmod.BANDS
                for key in ("mag", "level", "colour_coef", "scatter")},
             **{f"thr_{band}": model.thr[band] for band in selmod.BANDS},
             excess_g=model.excess_curve[0], excess_f=model.excess_curve[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hr23-name", required=True)
    ap.add_argument("--prob-min", type=float, default=0.7)
    ap.add_argument("--refresh-gaia", action="store_true")
    ap.add_argument("--control-max-rows", type=int, default=1000,
                    help="maximum nearby field stars used to calibrate selection")
    args = ap.parse_args()

    params, members = read_hr23(args.hr23_name, args.prob_min)
    tag = args.hr23_name
    raw_path = HERE / "data" / f"cluster_{tag}_gaia.csv"
    clean_path = HERE / "data" / f"cluster_{tag}_cmd_members.csv"
    err_path = HERE / "data" / f"cluster_{tag}_errmodel.npz"
    sel_path = HERE / "data" / f"cluster_{tag}_selection.npz"
    control_path = HERE / "data" / f"cluster_{tag}_control_field.csv"
    report_path = HERE / "results" / f"cluster_tier2_prep_{tag}.json"

    if raw_path.exists() and not args.refresh_gaia:
        raw_all = Table.read(raw_path, format="csv")
        print(f"使用 Gaia 快取：{raw_path.name}（{len(raw_all):,} 顆）")
    else:
        ids = [str(r["GaiaDR3"]) for r in members]
        print(f"查詢 Gaia DR3：{tag}，{len(ids):,} 個 source_id")
        raw_all = merge_rows(members, fetch_gaia(ids))
        raw_all.write(raw_path, format="csv", overwrite=True)
        print(f"寫入 {raw_path.name}（成功 crossmatch {len(raw_all):,}/"
              f"{len(ids):,}）")

    cfg = cfgmod.load()
    c1, c2 = cfg.step1_membership, cfg.step2_cmd
    g = np.asarray(raw_all["phot_g_mean_mag"], float)
    in_range = np.isfinite(g) & (g <= c1.g_mag_max)
    raw = raw_all[in_range]
    clean, cut_stats = apply_quality_cuts(raw, c2)
    errmodel = photometric_error_model(clean)

    if control_path.exists() and not args.refresh_gaia:
        control = Table.read(control_path, format="csv")
        print(f"using cached control field: {control_path.name} ({len(control):,} stars)")
    else:
        if args.control_max_rows < 100:
            raise ValueError("--control-max-rows must be at least 100")
        control = fetch_control_field(raw, args.control_max_rows)
        control.write(control_path, format="csv", overwrite=True)
        print(f"wrote control field: {control_path.name} ({len(control):,} stars)")

    calibration = Table({name: np.concatenate((np.asarray(raw[name]),
                                                np.asarray(control[name])))
                         for name in GAIA_COLUMNS})
    mags = {"g": np.asarray(calibration["phot_g_mean_mag"], float),
            "bp": np.asarray(calibration["phot_bp_mean_mag"], float),
            "rp": np.asarray(calibration["phot_rp_mean_mag"], float)}
    snrs = {"g": np.asarray(calibration["phot_g_mean_flux_over_error"], float),
            "bp": np.asarray(calibration["phot_bp_mean_flux_over_error"], float),
            "rp": np.asarray(calibration["phot_rp_mean_flux_over_error"], float)}
    colour = np.asarray(calibration["bp_rp"], float)
    thresholds = {"g": c2.min_flux_snr_g, "bp": c2.min_flux_snr_bp,
                  "rp": c2.min_flux_snr_rp}
    selection = selmod.build(mags, colour, snrs, thresholds, verbose=True)
    selection.excess_curve = build_excess_curve(raw, c2)
    validation = validate_selection(selection, raw, clean)

    clean.write(clean_path, format="csv", overwrite=True)
    np.savez(err_path, **errmodel)
    save_selection(sel_path, selection)

    report = {
        "hr23_name": tag,
        "params": params,
        "n_hr23": len(members),
        "n_gaia_crossmatch": len(raw_all),
        "n_g_le_18": len(raw),
        "n_control_field": len(control),
        "n_selection_calibration": len(calibration),
        "n_clean": len(clean),
        "quality_cut_stats": cut_stats,
        "selection_validation": validation,
        "files": {"raw": raw_path.name, "clean": clean_path.name,
                  "errmodel": err_path.name, "selection": sel_path.name,
                  "control_field": control_path.name},
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"G<=18：{len(raw_all):,} -> {len(raw):,}；測光品質："
          f"{len(raw):,} -> {len(clean):,}")
    print("選擇函數驗證：整體誤差 "
          f"{validation['overall_error']:+.3f}，逐星等最大誤差 "
          f"{validation['worst_mag_bin_error']:.3f}；"
          f"{'通過' if validation['pass_overall'] and validation['pass_mag_bins'] else '未通過'}")
    print(f"寫入 {report_path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
