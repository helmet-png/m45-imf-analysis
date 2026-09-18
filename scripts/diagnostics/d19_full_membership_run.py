# -*- coding: utf-8 -*-
"""D19 Stage 2：G<20 全樣本 pyUPMASK 重跑（正式規模，非可行性測試）。

`scripts/diagnostics/pyupmask_feasibility.py` 已經在 gcp1 上驗證過
provisioning＋聚類的完整路徑能跑（300 顆星、OL_runs=3，耗時 2.6 秒，
外推正式規模約 5.8 小時，見 `WORK_BOARD.md` pyupmask_cloud_feasibility）。
這支程式是可行性測試通過後的下一步：用完整的 9,278 顆星（G<20）、
產線的 `OL_runs=25` 真的跑一次。

**這不是分析腳本**——只負責 provisioning＋跑聚類＋把結果放到
`results/`，不做 P(member) 可靠度 vs G 的分析（那一步依賴這裡的輸出，
是後續獨立的工作，見 `LIMITATIONS.md` D19 Stage 2）。

**輸入檔為什麼在 `data/` 不在 `prepared/`**：`prepared/` 整個被
`.gitignore` 排除，SSH worker 的 `git pull` 不會帶到裡面的檔案。
`data/m45_g20_full.dat` 是 `prepared/m45_g20.dat` 的版本化副本（跟
`pyupmask_feasibility.py` 對 300 顆星子集的做法一致），source_id 跟
`data/m45_r5_g20_plx4.csv` 逐一核對過完全吻合（9,278/9,278）。

用法（在 worker 上，repo 根目錄執行）：
    python scripts/diagnostics/d19_full_membership_run.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INPUT_SOURCE = HERE / "data" / "m45_g20_full.dat"
INPUT_NAME = "m45_g20_full.dat"
OUT = HERE / "results" / "d19_full_membership_run.json"
RUN_NAME = "d19_g20_full"


def run(cmd):
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=HERE, text=True,
                          capture_output=True)


def main():
    report = {"steps": [], "ok": False}

    def record(name, ok, detail=""):
        report["steps"].append({"step": name, "ok": ok, "detail": detail})
        print(f"[{'OK' if ok else 'FAIL'}] {name}"
              f"{'：' + detail if detail else ''}")
        return ok

    if not INPUT_SOURCE.is_file():
        record("輸入檔存在", False, f"找不到 {INPUT_SOURCE}")
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        sys.exit(1)
    n_rows = sum(1 for _ in INPUT_SOURCE.open(encoding="utf-8")) - 1
    record("輸入檔存在", True, f"{INPUT_SOURCE.name}，{n_rows} 顆星")

    prepared = HERE / "prepared"
    prepared.mkdir(exist_ok=True)
    shutil.copyfile(INPUT_SOURCE, prepared / INPUT_NAME)
    record("複製進 prepared/", True, str(prepared / INPUT_NAME))

    # 沿用可行性測試驗證過的 provisioning——冪等（已套用時安全跳過），
    # 不會影響 gcp1 上已經修好的 venv，只是防禦性地確保環境完整。
    t0 = time.time()
    r = run(["bash", str(HERE / "setup" / "setup_pyupmask.sh"), sys.executable])
    ok = r.returncode == 0
    if not record("provisioning（冪等，已套用時安全跳過）", ok,
                  f"耗時 {time.time() - t0:.1f}s"):
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        sys.exit(1)

    # OL_runs=25：產線設定（見 pyUPMASK/params.ini 預設值，README.md
    # 的 baseline 呼叫沒有覆寫這個旗標，也就是用它的預設 25）。
    t0 = time.time()
    r = run([sys.executable, str(HERE / "scripts" / "drivers" /
                                 "run_variant.py"),
             "--name", RUN_NAME,
             "--input", INPUT_NAME,
             "--ol-runs", "25"])
    elapsed = time.time() - t0
    ok = r.returncode == 0
    if not record(f"跑聚類（{n_rows} 顆星、OL_runs=25）", ok,
                  f"耗時 {elapsed / 3600:.2f} 小時"):
        print(r.stdout[-4000:])
        print(r.stderr[-4000:])

    out_dat = HERE / "results" / f"{RUN_NAME}.dat"
    record("輸出檔產生", out_dat.exists(),
          f"{out_dat.name}" if out_dat.exists() else "沒有產出檔案")

    report["ok"] = all(s["ok"] for s in report["steps"])
    report["elapsed_sec"] = elapsed
    report["n_stars"] = n_rows
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n寫入 {OUT.relative_to(HERE)}")
    if report["ok"]:
        print(f"\n完成。{out_dat.relative_to(HERE)} 是下一步（P(member) 可靠度"
              f" vs G 分析、跟 control field 比對）的輸入，見 LIMITATIONS.md"
              f" D19 Stage 2。")
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
