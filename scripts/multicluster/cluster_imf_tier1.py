# -*- coding: utf-8 -*-
"""多星團擴展 Tier 1：借 HR23 現成成員表 + HR23 自己的年齡/消光/距離模數，
跑傳統法雙星修正變體比較（見 PLAN_多星團擴展.md 第四節）。

**這是 Tier 1，不是 Tier 2**——跟 M45 不是同等深度，差異記在
LIMITATIONS.md「多星團 Tier 1 vs M45 Tier 2 的差距」那一節，這裡只重複
最關鍵的一點：**沒有注入回收**（做不到——注入回收要用前向模型
`JointModel` 生成假資料，那需要星團自己的測光誤差模型與選擇函數，
Tier 1 沒有校準這些，只用 HR23 現成的成員表 + 星等直接跑傳統法）。
所以這裡只跑三個不需要注入回收、直接對真實資料算的東西：
全當單星／CMD剔除／文獻解析修正（曲率誤差），RUWE／NSS 剔除
（bootstrap 誤差，跟 M45 版一樣）。

**資料來源**：Hunt & Reffert (2023, A&A 673, A114) 的 VizieR 目錄，
`members` 表（每顆星的成員機率、Gaia DR3 測光、RUWE、NSS）與
`clusters` 表（每個星團的 HR23 自己擬合出的年齡/消光/距離模數）。
用 HR23 自己的年齡而非另外查文獻值，是刻意的：成員表跟星團參數
來自同一個homogeneous pipeline，比混用不同來源更一致，也更適合
「同一套方法跑很多星團」這種系統性比較。

**金屬量固定 MH=0.00（太陽金屬量）**：HR23 的 clusters 表沒有金屬量，
Tier 1 先用太陽值當近似——跟 M45 的傳統法一樣，這是刻意對傳統法有利的
簡化（見 traditional_accounting.py 的一貫做法），不是本專案自己的新假設。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import types
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline.table_compat import Table as _CompatTable  # noqa: E402
_a = types.ModuleType("astropy")
_t = types.ModuleType("astropy.table")
_t.Table = _CompatTable
_a.table = _t
sys.modules.setdefault("astropy", _a)
sys.modules.setdefault("astropy.table", _t)

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline.step3_age import _Ext                            # noqa: E402
from traditional_accounting import (                           # noqa: E402
    traditional_alpha, bootstrap_alpha_err, INJ_VARIANTS, REAL_ONLY_VARIANTS)
from pipeline.step5_imf import main_sequence_mass_luminosity    # noqa: E402

VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"


def vizier_query(adql: str) -> dict:
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": adql}).encode()
    req = urllib.request.Request(VIZIER, data=body,
                                 headers={"User-Agent": "m45-pipeline/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())


def fetch_cluster_params(name: str) -> dict:
    d = vizier_query(
        'SELECT "Name","logAge50","AV50","dist50","MOD50" FROM '
        f'"J/A+A/673/A114/clusters" WHERE "Name"=\'{name}\'')
    if not d["data"]:
        raise SystemExit(f"HR23 clusters 表找不到 {name!r}")
    return dict(zip([m["name"] for m in d["metadata"]], d["data"][0]))


def fetch_members(name: str, prob_min: float) -> dict:
    d = vizier_query(
        'SELECT "GaiaDR3","Prob","Gmag","BPmag","RPmag","RUWE","NSS" FROM '
        f'"J/A+A/673/A114/members" WHERE "Name"=\'{name}\' '
        f'AND "Prob">={prob_min}')
    cols = [m["name"] for m in d["metadata"]]
    arr = {c: np.array([row[i] for row in d["data"]]) for i, c in enumerate(cols)}
    return arr


def local_paths(name: str) -> tuple[Path, Path]:
    """Return the checked-in HR23 cache files for a cluster."""
    return (HERE / "data" / f"hr23_{name}_params.json",
            HERE / "data" / f"hr23_{name}_members.csv")


def load_local(name: str, prob_min: float) -> tuple[dict, dict] | None:
    """Load the checked-in HR23 snapshot instead of requiring live VizieR.

    The original Tier-1 entry point always queried VizieR even though the exact
    inputs were already committed.  That made a reproduced run depend on the
    network and, in practice, fail on certificate-chain problems.  Prefer the
    immutable local snapshot; ``--refresh`` remains available for an explicit
    catalogue refresh.
    """
    params_path, members_path = local_paths(name)
    if not (params_path.exists() and members_path.exists()):
        return None
    params = json.loads(params_path.read_text(encoding="utf-8"))
    rows = []
    with members_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if float(row["Prob"]) >= prob_min:
                rows.append(row)
    cols = ("GaiaDR3", "Prob", "Gmag", "BPmag", "RPmag", "RUWE", "NSS")
    members = {}
    for col in cols:
        if col == "GaiaDR3":
            members[col] = np.array([row[col] for row in rows], dtype=str)
        else:
            members[col] = np.array([
                float(row[col]) if row[col] not in ("", "null", "NaN") else np.nan
                for row in rows], dtype=float)
    return params, members


def load_inputs(name: str, prob_min: float, refresh: bool) -> tuple[dict, dict, str]:
    if not refresh:
        cached = load_local(name, prob_min)
        if cached is not None:
            return cached[0], cached[1], "checked-in HR23 snapshot"
    return (fetch_cluster_params(name), fetch_members(name, prob_min),
            "live VizieR query")


def load_prepared(name: str) -> dict:
    """Load the cluster-specific G<=18 and photometric-quality sample."""
    path = HERE / "data" / f"cluster_{name}_cmd_members.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} not found; run prepare_cluster_tier2.py first")
    table = _CompatTable.read(path, format="csv")
    return {
        "GaiaDR3": np.asarray(table["source_id"]),
        "Prob": np.asarray(table["membership_probability"], float),
        "Gmag": np.asarray(table["phot_g_mean_mag"], float),
        "BPmag": np.asarray(table["phot_bp_mean_mag"], float),
        "RPmag": np.asarray(table["phot_rp_mean_mag"], float),
        "RUWE": np.asarray(table["ruwe"], float),
        "NSS": np.asarray(table["hr23_nss"], float),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hr23-name", required=True,
                    help="HR23 目錄裡的星團名稱，例如 NGC_3532、NGC_2632")
    ap.add_argument("--grid", required=True,
                    help="isochrones/ 底下要用的網格檔名")
    ap.add_argument("--prob-min", type=float, default=0.7)
    ap.add_argument("--mass-min", type=float, default=0.50)
    ap.add_argument("--mass-max", type=float, default=2.50)
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--tag", default="")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore checked-in HR23 files and query VizieR again")
    ap.add_argument("--prepared", action="store_true",
                    help="use the cluster-specific G<=18 quality-cut sample")
    args = ap.parse_args()

    print(f"載入 HR23 星團資料：{args.hr23_name}")
    params, mem, source = load_inputs(args.hr23_name, args.prob_min,
                                      args.refresh)
    if args.prepared:
        mem = load_prepared(args.hr23_name)
        source = "cluster-specific G<=18 quality-cut sample"
    print(f"  來源：{source}")
    logage = float(params["logAge50"])
    av = float(params["AV50"])
    dm = float(params["MOD50"])
    age_myr = 10 ** logage / 1e6
    print(f"  logAge50={logage:.4f}（{age_myr:.1f} Myr）  "
          f"AV50={av:.3f}  MOD50={dm:.3f}（dist50={float(params['dist50']):.1f} pc）")

    print(f"\n成員表門檻：Prob >= {args.prob_min}")
    n0 = len(mem["GaiaDR3"])
    print(f"  取回 {n0:,} 顆")

    color = mem["BPmag"] - mem["RPmag"]
    mag = mem["Gmag"]
    ruwe = mem["RUWE"]
    # VizieR JSON uses null for missing NSS values.  Convert before np.isfinite
    # so a refreshed catalogue cannot turn this into an object-array TypeError.
    nss_values = np.asarray(mem["NSS"], dtype=float)
    nss = np.isfinite(nss_values) & (nss_values != 0)
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag, ruwe, nss = color[ok], mag[ok], ruwe[ok], nss[ok]
    n_obs = len(color)
    print(f"  測光完整的 {n_obs:,} 顆（去掉 {n0 - n_obs} 顆缺值）")

    grid = isomod.load_grid(isomod.CACHE / args.grid)
    ages_avail = np.unique(np.asarray(grid["logAge"], float))
    print(f"\n網格 {args.grid}：實際涵蓋 logAge "
          f"{ages_avail.min():.2f}–{ages_avail.max():.2f}")
    if not (ages_avail.min() <= logage <= ages_avail.max()):
        print(f"  警告：星團的 logAge={logage:.3f} 超出網格涵蓋範圍，"
              f"argmax/isochrone_at 會吸附到邊界，結果不可信！")
    iso = isomod.isochrone_at(grid, logage, 0.0)
    used_logage = float(np.unique(np.asarray(iso["logAge"], float))[0])
    c2 = cfgmod.load().step2_cmd
    ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)

    m_lo, m_hi = args.mass_min, args.mass_max
    _, ms_mass = main_sequence_mass_luminosity(iso, dm, av, ext)
    turnoff_mass = float(np.nanmax(ms_mass))
    turnoff_ok = m_hi <= turnoff_mass
    print(f"\n質量範圍 {m_lo}–{m_hi} M☉，isochrone logAge={logage:.3f} "
          f"A_V={av:.3f}（HR23 自己的估計值，MH 固定 0.00）\n")
    print(f"  實際採用網格 logAge={used_logage:.3f}；單調主序上限 "
          f"{turnoff_mass:.3f} M☉："
          f"{'涵蓋分析上限' if turnoff_ok else '未涵蓋 2.50 M☉，結果不可採用'}\n")

    print(f"{'變體':>16}{'alpha':>8}{'誤差':>8}{'誤差核算':>10}{'星數':>7}{'剔除':>6}")
    out = {}
    for variant, tag in INJ_VARIANTS:
        a, n, n_rm, err = traditional_alpha(
            color, mag, iso, dm, av, ext, m_lo, m_hi, variant=variant)
        out[tag] = (a, err, "曲率", n, n_rm)
        print(f"{tag:>16}{a:>8.3f}{err:>8.3f}{'曲率':>10}{n:>7}{n_rm:>6}")
    for variant, tag in REAL_ONLY_VARIANTS:
        a, n, n_rm, _ = traditional_alpha(
            color, mag, iso, dm, av, ext, m_lo, m_hi, variant=variant,
            ruwe=ruwe, nss=nss, ruwe_threshold=1.4)
        _, boot_err = bootstrap_alpha_err(
            color, mag, iso, dm, av, ext, m_lo, m_hi, variant,
            ruwe=ruwe, nss=nss, ruwe_threshold=1.4, n_boot=args.n_boot)
        out[tag] = (a, boot_err, "bootstrap", n, n_rm)
        print(f"{tag:>16}{a:>8.3f}{boot_err:>8.3f}{'bootstrap':>10}{n:>7}{n_rm:>6}")

    print("\n**Tier 1 提醒**：這些誤差棒是曲率/bootstrap，不是注入回收——")
    print("跟 M45 的表 3 數字不是同一把尺，只能看方法間的相對方向跟量級，")
    print("不能直接拿來跟 M45 的 alpha 相減比較「大小」。")

    tag = args.tag or (args.hr23_name + ("_clean" if args.prepared else ""))
    np.savez(HERE / "results" / f"cluster_tier1_{tag}.npz",
             hr23_name=args.hr23_name, logage=logage, av=av, dm=dm,
             grid_logage=used_logage, turnoff_mass=turnoff_mass,
             turnoff_ok=turnoff_ok, n_members=n0, n_obs=n_obs,
             **{f"{k}::alpha": v[0] for k, v in out.items()},
             **{f"{k}::err": v[1] for k, v in out.items()},
             **{f"{k}::n_fit": v[3] for k, v in out.items()},
             **{f"{k}::n_removed": v[4] for k, v in out.items()})
    print(f"\n寫入 results/cluster_tier1_{tag}.npz")


if __name__ == "__main__":
    main()
