"""Compare PeTar runs from the same IC built with original / patch v1 / v2 / v2-instrumented.
usage: validate_patch.py <out.json> label=dir [label=dir ...]   (first label is the reference = original)"""
import sys, json, glob, hashlib, os
import numpy as np

def snaps(d):
    out = {}
    for f in glob.glob(d + "/data.[0-9]*"):
        k = f.rsplit(".", 1)[1]
        if k.isdigit():
            out[int(k)] = f
    return out

def physic(d):
    rows, audit = [], []
    for ln in open(d + "/petar.log", errors="replace"):
        if ln.startswith("Physic:"):
            rows.append([float(x) for x in ln.split()[1:]])
        elif ln.startswith("FrameShiftAudit:"):
            f = ln.split()[1:]
            audit.append([[float(f[5 * s + j]) for j in range(1, 5)] for s in range(5)])  # per site: cnt, dm, de, half_dm_V2
    return np.array(rows), np.array(audit)

def load(f):
    hdr = open(f).readline().split()
    a = np.loadtxt(f, skiprows=1, ndmin=2)
    return hdr, a

def lagr(a, fr=(0.1, 0.5, 0.9)):
    m, x = a[:, 0], a[:, 1:4]
    c = (m[:, None] * x).sum(0) / m.sum()
    r = np.linalg.norm(x - c, axis=1); o = np.argsort(r); cm = np.cumsum(m[o]) / m.sum()
    return [float(r[o][np.searchsorted(cm, q)]) for q in fr]

out_path, specs = sys.argv[1], [s.split("=", 1) for s in sys.argv[2:]]
ref_label, ref_dir = specs[0]
ref_snaps = snaps(ref_dir)
res = {"reference": ref_label, "dynamics": {}, "audit": {}}
for label, d in specs[1:]:
    sn = snaps(d); common = sorted(set(sn) & set(ref_snaps))
    rec = {"n_snapshots_compared": len(common), "bitwise_identical_snapshots": 0, "first_difference": None}
    for k in common:
        if hashlib.sha256(open(sn[k], "rb").read()).digest() == hashlib.sha256(open(ref_snaps[k], "rb").read()).digest():
            rec["bitwise_identical_snapshots"] += 1
            continue
        (h0, a0), (h1, a1) = load(ref_snaps[k]), load(sn[k])
        diff = {"snapshot": k, "header_ref": h0[:3], "header": h1[:3], "n_ref": len(a0), "n": len(a1)}
        if len(a0) == len(a1):
            diff["max_abs_diff_mass"] = float(np.abs(a0[:, 0] - a1[:, 0]).max())
            diff["max_abs_diff_pos"] = float(np.abs(a0[:, 1:4] - a1[:, 1:4]).max())
        diff["lagr_ref"], diff["lagr"] = lagr(a0), lagr(a1)
        if rec["first_difference"] is None:
            rec["first_difference"] = diff
        rec["last_difference"] = diff
    res["dynamics"][label] = rec
    ph, au = physic(d)
    ph0, _ = physic(ref_dir)
    if len(au):
        n = min(len(ph), len(ph0), len(au))
        # cumulative energy-error shift vs original, and per-site cumulative corrections
        derr = ph0[:n, 2] - ph[:n, 2]
        de_sites = au[:n, :, 2]
        m_snap = {k: np.loadtxt(ref_snaps[k], skiprows=1, usecols=0, ndmin=1).sum() for k in sorted(ref_snaps) if k < n}
        ks = sorted(m_snap)
        dm_snap = [m_snap[k] - m_snap[ks[0]] for k in ks]
        res["audit"][label] = {
            "n_outputs": int(n),
            "per_site_final": {f"S{s+1}": {"count": au[n-1, s, 0], "dm": au[n-1, s, 1], "de": au[n-1, s, 2],
                                            "half_dm_V2": au[n-1, s, 3],
                                            "de_over_half_dm_V2": (au[n-1, s, 2] / au[n-1, s, 3]) if au[n-1, s, 3] else None}
                               for s in range(5)},
            "errcum_ref_minus_this": derr.tolist(),
            "sum_site_de": de_sites.sum(1).tolist(),
            "max_abs_mismatch_errshift_vs_sum_de": float(np.abs(derr - de_sites.sum(1)).max()),
            "max_abs_mismatch_errshift_vs_minus_sum_de": float(np.abs(derr + de_sites.sum(1)).max()),
            "errcum_ref_final": float(ph0[n-1, 2]), "errcum_this_final": float(ph[n-1, 2]), "etot0": float(ph0[0, 3]),
            "snapshot_mass_change_cum": [float(x) for x in dm_snap],
            "sum_site_dm_at_snapshots": [float(au[k, :, 1].sum()) for k in ks],
        }
json.dump(res, open(out_path, "w"), indent=1, default=float)
for label, r in res["dynamics"].items():
    print(label, "identical", r["bitwise_identical_snapshots"], "/", r["n_snapshots_compared"], "first diff:", r["first_difference"])
for label, a in res["audit"].items():
    print(label, json.dumps(a["per_site_final"], default=float))
    print("  errshift vs +sum de:", a["max_abs_mismatch_errshift_vs_sum_de"], " vs -sum de:", a["max_abs_mismatch_errshift_vs_minus_sum_de"])
    print("  Error_cum ref/this/E0:", a["errcum_ref_final"], a["errcum_this_final"], a["etot0"])
    print("  mass change snapshots:", a["snapshot_mass_change_cum"][-3:], " sum site dm:", a["sum_site_dm_at_snapshots"][-3:])
