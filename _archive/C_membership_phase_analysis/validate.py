# -*- coding: utf-8 -*-
"""把 pyUPMASK 的結果跟 Hunt & Reffert 2023 的成員表交叉比對。

兩邊同為 Gaia DR3，直接用 source_id 對，不需要天球配對。

recall 的分母只算「HR23 成員且有出現在我的輸入樣本裡」的星：落在錐形外、
或被星等/視差切掉的成員，我根本沒機會找到，算進分母只是在懲罰視野而不是演算法。
覆蓋率會另外單獨報。

圖上一律用英文標籤，matplotlib 預設字型沒有中文字，硬寫會變成豆腐方塊。
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).parent
VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
HR23_COLS = ["GaiaDR3", "Prob", "inrt", "Gmag", "BP-RP", "Plx", "pmRA", "pmDE",
             "RA_ICRS", "DE_ICRS", "RUWE"]


def fetch_hr23(cluster, cache):
    """抓 HR23 成員表並快取到本地。"""
    if cache.exists():
        return Table.read(cache, format="csv")
    cols = ", ".join(f'"{c}"' for c in HR23_COLS)
    adql = (f'SELECT {cols} FROM "J/A+A/673/A114/members" '
            f"WHERE \"Name\"='{cluster}'")
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
        "QUERY": adql}).encode()
    req = urllib.request.Request(VIZIER, data=body,
                                 headers={"User-Agent": "m45-membership/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(r.read())
    print(f"抓下 HR23 成員表 -> {cache.name}")
    return Table.read(cache, format="csv")


def metrics(mine, truth, thr):
    """在機率門檻 thr 下的 precision / recall / F1。"""
    pred = mine >= thr
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
    return tp, fp, fn, prec, rec, f1


def main():
    ap = argparse.ArgumentParser(description="pyUPMASK 結果 vs HR23")
    ap.add_argument("--result", default="pyUPMASK/output/m45.dat")
    ap.add_argument("--cluster", default="Melotte_22", help="HR23 裡的星團名")
    ap.add_argument("--ref-prob", type=float, nargs="+", default=[0.5, 0.7],
                    help="HR23 的 Prob 要多高才算「真成員」；給多個值做敏感度檢查")
    a = ap.parse_args()

    res = Table.read(HERE / a.result, format="ascii")
    hr = fetch_hr23(a.cluster, HERE / "data" / f"hr23_{a.cluster}.csv")

    my_id = np.asarray(res["source_id"], dtype=np.int64)
    my_p = np.asarray(res["probs_final"], dtype=float)

    hr_id = np.asarray(hr["GaiaDR3"], dtype=np.int64)
    hr_p = np.asarray(hr["Prob"], dtype=float)

    # probs_final = -1 代表被 pyUPMASK 的離群值遮罩排除，不是機率
    masked = my_p < 0
    print(f"結果檔              : {a.result}")
    print(f"我的樣本            : {len(my_id):,} 顆"
          f"（其中 {masked.sum()} 顆被離群遮罩，機率記為 -1）")
    print(f"HR23 全部成員       : {len(hr_id):,} 顆")

    truth = None
    for ref in a.ref_prob:
        ref_id = hr_id[hr_p >= ref]
        tr = np.isin(my_id, ref_id)
        covered = int(np.isin(ref_id, my_id).sum())
        if truth is None:
            truth = tr

        print(f"\n{'='*72}")
        print(f"參考門檻 HR23 Prob >= {ref}")
        print(f"  該門檻下的成員   : {len(ref_id):,} 顆")
        print(f"  └ 在我樣本裡     : {covered:,} 顆"
              f"（覆蓋率 {covered/len(ref_id)*100:.1f}%，其餘在錐形外或被星等切掉）")
        print(f"  我樣本中真成員   : {int(tr.sum()):,} 顆"
              f"（汙染率 {(1-tr.mean())*100:.1f}%）")

        print(f"\n{'門檻':>6}{'選出':>8}{'TP':>7}{'FP':>7}{'FN':>7}"
              f"{'precision':>11}{'recall':>9}{'F1':>8}")
        best = None
        for thr in (0.3, 0.5, 0.7, 0.9, 0.95, 0.99):
            tp, fp, fn, prec, rec, f1 = metrics(my_p, tr, thr)
            print(f"{thr:>6.2f}{tp+fp:>8,}{tp:>7,}{fp:>7,}{fn:>7,}"
                  f"{prec:>11.4f}{rec:>9.4f}{f1:>8.4f}")
            if best is None or (f1 == f1 and f1 > best[1]):
                best = (thr, f1)
        print(f"  F1 最佳門檻: P>={best[0]:.2f}  (F1={best[1]:.4f})")
        try:
            from sklearn.metrics import roc_auc_score
            ok = ~masked
            print(f"  ROC-AUC     : {roc_auc_score(tr[ok], my_p[ok]):.4f}")
        except Exception as e:
            print(f"  ROC-AUC 算不出來: {e}")

    # 存一份逐星比對結果，方便後續追爭議星
    out = Table({
        "source_id": my_id, "my_prob": my_p, "hr23_member": truth.astype(int),
    })
    for c in ("pmRA", "pmDE", "Plx", "Gmag", "BP_RP", "_x", "_y"):
        if c in res.colnames:
            out[c] = res[c]
    hr_prob_map = dict(zip(hr_id.tolist(), hr_p.tolist()))
    out["hr23_prob"] = [hr_prob_map.get(int(i), np.nan) for i in my_id]
    dest = HERE / "data" / "comparison.csv"
    out.write(dest, format="csv", overwrite=True)
    print(f"\n逐星比對表 -> {dest}")


if __name__ == "__main__":
    main()
