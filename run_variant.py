# -*- coding: utf-8 -*-
"""跑一組 pyUPMASK 變因，把結果收到 results/<name>.dat。

pyUPMASK 會把 input/ 底下所有檔案都跑一遍，且 params.ini 從 CWD 讀，
所以每次只放一個輸入檔進去，並在 pyUPMASK 目錄下執行。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
PY = HERE / "pyUPMASK"
PREPARED = HERE / "prepared"
RESULTS = HERE / "results"
LOGS = HERE / "logs"


def set_param(text, key, value):
    """換掉 params.ini 裡某個 key 的值，保留註解與排版。

    尾端用 [^\\S\\n] 而不是 \\s —— \\s 會吃掉換行，讓每跑一次就吞掉一行空行。
    """
    pat = re.compile(rf"^([^\S\n]*{re.escape(key)}[^\S\n]*=[^\S\n]*)(.*)$", re.M)
    new, n = pat.subn(lambda m: f"{m.group(1)}{value}", text, count=1)
    if n == 0:
        raise KeyError(f"params.ini 裡找不到 {key}")
    return new


def main():
    ap = argparse.ArgumentParser(description="跑一組 pyUPMASK 變因")
    ap.add_argument("--name", required=True, help="這組變因的名字，決定輸出檔名")
    ap.add_argument("--input", required=True, help="prepared/ 底下的 .dat 檔名")
    ap.add_argument("--ol-runs", type=int, default=25)
    ap.add_argument("--resample", default="True", choices=["True", "False"])
    ap.add_argument("--pca", default="True", choices=["True", "False"])
    ap.add_argument("--pca-dims", type=int, default=2)
    ap.add_argument("--seed", default=None,
                    help="亂數種子；換種子可量出純粹的 run-to-run 雜訊底線")
    ap.add_argument("--kdep", default="True", choices=["True", "False"],
                    help="False = 關掉 KDE 後驗，機率退回原始 UPMASK 的"
                         "「25 輪中被判為成員的次數比例」")
    ap.add_argument("--indep-resample", action="store_true",
                    help="誤差重抽改成每個維度獨立（否則沿用 pyUPMASK 原本的相關抽樣）")
    a = ap.parse_args()

    src = PREPARED / a.input
    if not src.exists():
        sys.exit(f"找不到 {src}")

    for d in (RESULTS, LOGS):
        d.mkdir(exist_ok=True)

    # input/ 每次只留這一個檔
    inp = PY / "input"
    inp.mkdir(exist_ok=True)
    for old in inp.glob("*.dat"):
        old.unlink()
    shutil.copy(src, inp / src.name)

    ini = PY / "params.ini"
    text = ini.read_text(encoding="utf-8")
    params = [("OL_runs", a.ol_runs), ("resampleFlag", a.resample),
              ("PCAflag", a.pca), ("PCAdims", a.pca_dims),
              ("KDEP_flag", a.kdep)]
    if a.seed is not None:
        params.append(("rnd_seed", a.seed))
    for k, v in params:
        text = set_param(text, k, v)
    ini.write_text(text, encoding="utf-8")

    env = dict(os.environ)
    if a.indep_resample:
        env["PYUPMASK_INDEP_RESAMPLE"] = "1"

    log = LOGS / f"{a.name}.log"
    print(f"[{a.name}] 輸入={src.name} OL={a.ol_runs} resample={a.resample} "
          f"PCA={a.pca}/{a.pca_dims} indep={a.indep_resample}")
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as fh:
        r = subprocess.run([sys.executable, "-u", "pyUPMASK.py"], cwd=PY,
                           stdout=fh, stderr=subprocess.STDOUT, env=env)
    if r.returncode != 0:
        sys.exit(f"[{a.name}] pyUPMASK 失敗，看 {log}")

    out = PY / "output" / src.name
    dest = RESULTS / f"{a.name}.dat"
    shutil.move(out, dest)
    print(f"[{a.name}] 完成，{(time.time()-t0)/60:.1f} 分鐘 -> {dest.name}")


if __name__ == "__main__":
    main()
