# -*- coding: utf-8 -*-
"""D19 Stage 2／D2：pyUPMASK 能不能在這台機器上真的跑起來。

**這支程式是排上雲端 worker 用的小規模可行性測試**，不是正式的 G<20
成員判定重跑。目的只有一個：在花時間跑完整的 9,278 顆星之前，先用
300 顆星的子集＋很少的外圈重複次數確認整條路徑（provisioning、
匯入、實際跑一次聚類、產出檔案）在這台機器上真的走得通。

**背景**：全專案至今沒有任何 worker 驗證過 pyUPMASK 能跑
（`sensitivity_sweep.py --target stars_per_cluster` 的可行性檢查停在
「沒有 pyUPMASK/ 就沒法測」，見 LIMITATIONS.md D2、D19）。深入查發現
本機的 `pyUPMASK/` 帶有三處從未進版控的本機修改，其中一處是必要的
Python 3.12+ 相容性補丁（`distutils.strtobool` 在 3.12 被移除）——
不補這個，任何用現代 Python 的 worker 直接 clone 原版第一步就會崩潰。
`setup/setup_pyupmask.sh` 把 clone＋套 patch 這兩步固定下來。

用法（在 worker 上，repo 根目錄執行）：
    python scripts/diagnostics/pyupmask_feasibility.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
SUBSET = HERE / "prepared" / "m45_g20_feasibility_subset.dat"
OUT = HERE / "results" / "d19_pyupmask_feasibility.json"


def run(cmd, **kw):
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=HERE, text=True,
                          capture_output=True, **kw)


def main():
    report = {"steps": [], "ok": False}

    def record(name, ok, detail=""):
        report["steps"].append({"step": name, "ok": ok, "detail": detail})
        print(f"[{'OK' if ok else 'FAIL'}] {name}"
              f"{'：' + detail if detail else ''}")
        return ok

    if not SUBSET.exists():
        record("子集輸入檔存在", False, f"找不到 {SUBSET}")
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        sys.exit(1)
    record("子集輸入檔存在", True, f"{SUBSET.name}")

    t0 = time.time()
    r = run(["bash", str(HERE / "setup" / "setup_pyupmask.sh"), sys.executable])
    ok = r.returncode == 0
    if not record("provisioning（clone + patch + 匯入驗證）", ok,
                  f"耗時 {time.time() - t0:.1f}s"):
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        sys.exit(1)

    t0 = time.time()
    r = run([sys.executable, str(HERE / "scripts" / "drivers" /
                                 "run_variant.py"),
             "--name", "d19_feasibility",
             "--input", SUBSET.name,
             "--ol-runs", "3"])
    elapsed = time.time() - t0
    ok = r.returncode == 0
    if not record("跑一次聚類（300 顆星、OL_runs=3）", ok,
                  f"耗時 {elapsed:.1f}s"):
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])

    out_dat = HERE / "results" / "d19_feasibility.dat"
    record("輸出檔產生", out_dat.exists(),
          f"{out_dat.name}" if out_dat.exists() else "沒有產出檔案")

    report["ok"] = all(s["ok"] for s in report["steps"])
    report["elapsed_300stars_ol3_sec"] = elapsed
    # 300 顆、OL_runs=3 的耗時，粗略外推到 9,278 顆、OL_runs=25（正式規模）
    # 給個量級參考。pyUPMASK 內圈成本大致隨 N^2 成長（README 已有此說法），
    # 外圈次數是線性——這只是排隊前的量級估計，不是正式耗時預測。
    if report["ok"]:
        n_ratio = (9278 / 300) ** 2
        ol_ratio = 25 / 3
        report["rough_full_scale_estimate_hours"] = (
            elapsed * n_ratio * ol_ratio / 3600.0)
        print(f"\n粗略外推到 G<20 正式規模（9,278 顆、OL_runs=25）："
              f"約 {report['rough_full_scale_estimate_hours']:.1f} 小時"
              f"（N^2 × OL_runs 線性外推，量級參考用，不是正式估計）")

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n寫入 {OUT.relative_to(HERE)}")
    print(f"\n結論：{'可行性測試通過，可以排正式規模' if report['ok'] else '可行性測試沒過，不要排正式規模，先查上面哪一步失敗'}")
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
