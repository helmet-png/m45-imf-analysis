# -*- coding: utf-8 -*-
"""跑一組 pyUPMASK 變因，把結果收到 results/<name>.dat。

pyUPMASK 會把 input/ 底下所有檔案都跑一遍，且 params.ini 從 CWD 讀，
所以每次只放一個輸入檔進去，並在 pyUPMASK 目錄下執行。

======================================================================
【這支程式在做什麼】
======================================================================
成員分類本身是外部程式 pyUPMASK 做的；這支程式只是「操作員」：把輸入檔
放到 pyUPMASK 指定的位置、改好設定檔、執行它、再把輸出搬回 results/。
正式流程的指令（見 README）：
  python scripts/drivers/run_variant.py --name baseline --input m45_raw.dat
輸出：results/baseline.dat（每顆星一列，含成員機率 probs_final）
      logs/baseline.log（pyUPMASK 執行過程的完整輸出）

pyUPMASK 怎麼判定成員（摘要，細節見 README「pyUPMASK 分群參數」）：
  重複 25 輪（外圈）；每一輪：
    1. 用每顆星的天測誤差把自行、視差隨機擾動一次（重抽）
    2. 用 PCA 把自行＋視差三維壓成兩維
    3. 用 MiniBatchKMeans 把星分成很多小群（約每群 25 顆）
    4. 檢查每一小群在天空上是不是比隨機分布更集中（Ripley's K 檢定）；
       集中的小群裡的星判為「這一輪的成員」
    5. 用位置＋自行＋視差建「成員」與「場星」兩個核密度分布，
       每顆星的成員機率 = 1 / (1 + 場星密度 / 成員密度)
  25 輪平均就是最後的成員機率。之後 run_pipeline.py 取機率 ≥ 0.7 的星。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
全部是 Python 標準庫：
  argparse    讀命令列參數
  os          複製目前的環境變數，再加上要傳給 pyUPMASK 的設定
  re          正規表示式：在 params.ini 裡找到某個設定並換掉它的值
  shutil      shutil.copy 複製輸入檔；shutil.move 把輸出搬到 results/
  subprocess  subprocess.run 執行另一支程式（pyUPMASK.py）並等它結束
  sys         sys.executable（目前這個 Python 的路徑）、sys.exit（報錯結束）
  time        計時
  pathlib     路徑
外部程式：
  pyUPMASK/pyUPMASK.py   成員判定程式本體，放在 repo 根目錄的 pyUPMASK/ 底下；
                         讀 pyUPMASK/params.ini 與 pyUPMASK/input/*.dat，
                         寫 pyUPMASK/output/*.dat

======================================================================
【(b) 用到的參數與意義】
======================================================================
  --name            這次執行的名字，決定輸出檔名（正式流程用 baseline）
  --input           prepared/ 底下的輸入檔名（prep.py 產生，正式流程用 m45_raw.dat）
  --ol-runs         外圈輪數，預設 25；成員機率是這些輪的平均
  --resample        是否用天測誤差重抽，預設 True（pyUPMASK 原始預設是 False，
                    等於不用誤差，務必保持 True）
  --pca, --pca-dims 是否用 PCA 降維、降到幾維，預設 True、2
  --seed            亂數種子；不給就沿用 params.ini 原本的值
  --kdep            True：機率用核密度後驗（預設）；False：用「25 輪中被判為
                    成員的比例」
  --indep-resample  重抽時三個維度各自獨立擾動（否則沿用 pyUPMASK 原本
                    「三維共用一個亂數」的作法）
寫入 params.ini 的鍵名對照：
  OL_runs ← --ol-runs、resampleFlag ← --resample、PCAflag ← --pca、
  PCAdims ← --pca-dims、KDEP_flag ← --kdep、rnd_seed ← --seed

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 100–116 行｜set_param()：在設定檔裡換掉一個鍵的值，不動其他排版
  核心 2｜第 136–172 行｜準備輸入：清空 input/、放入這次的檔案、改寫 params.ini
  核心 3｜第 174–195 行｜執行 pyUPMASK 並把輸出搬到 results/

======================================================================
【(d) 整體流程】
======================================================================
  讀參數 → 確認 prepared/<輸入檔> 存在
    → 清空 pyUPMASK/input/ 裡所有 .dat，只放入這次的輸入檔
      （pyUPMASK 會把 input/ 裡每個檔都跑一遍）
    → 讀 params.ini，把各個參數換成這次的值，寫回
    → 在 pyUPMASK/ 資料夾裡執行 pyUPMASK.py，輸出全部寫進 logs/<名字>.log
    → 失敗就報錯結束；成功就把 pyUPMASK/output/<輸入檔> 搬到 results/<名字>.dat
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ↓ repo 根目錄（本檔在 scripts/drivers/，往上三層）
HERE = Path(__file__).resolve().parent.parent.parent
# ↓ pyUPMASK 程式所在資料夾
PY = HERE / "pyUPMASK"
# ↓ prep.py 的輸出資料夾（本程式的輸入來源）
PREPARED = HERE / "prepared"
# ↓ 成員判定結果與執行紀錄的存放位置
RESULTS = HERE / "results"
LOGS = HERE / "logs"


# ═══════════════ 核心 1：改寫設定檔中的一個值 ═══════════════
def set_param(text, key, value):
    """換掉 params.ini 裡某個 key 的值，保留註解與排版。

    尾端用 [^\\S\\n] 而不是 \\s —— \\s 會吃掉換行，讓每跑一次就吞掉一行空行。
    """
    # ↓ 正規表示式：比對「某一行開頭 (空白) key (空白) = (空白)」這段，
    #   放進第 1 組；等號後面到行尾的舊值放進第 2 組。
    #   [^\S\n] 意思是「空白字元但不含換行」；re.M 讓 ^ 和 $ 以行為單位
    pat = re.compile(rf"^([^\S\n]*{re.escape(key)}[^\S\n]*=[^\S\n]*)(.*)$", re.M)
    # ↓ 保留第 1 組（key = 的部分），把舊值換成新值；只換第一個出現的（count=1）。
    #   n 是實際替換了幾次
    new, n = pat.subn(lambda m: f"{m.group(1)}{value}", text, count=1)
    # ↓ 一次都沒換到 → 設定檔裡沒有這個 key，報錯而不是默默略過
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

    # ═══════════════ 核心 2：準備輸入檔與設定檔 ═══════════════
    # ↓ 輸入檔不存在就直接結束
    src = PREPARED / a.input
    if not src.exists():
        sys.exit(f"找不到 {src}")

    # ↓ 確保 results/、logs/ 存在
    for d in (RESULTS, LOGS):
        d.mkdir(exist_ok=True)

    # input/ 每次只留這一個檔
    # ↓ 刪掉 pyUPMASK/input/ 裡所有舊的 .dat，再複製這次的輸入檔進去
    inp = PY / "input"
    inp.mkdir(exist_ok=True)
    for old in inp.glob("*.dat"):
        old.unlink()
    shutil.copy(src, inp / src.name)

    # ↓ 讀 params.ini 全文
    ini = PY / "params.ini"
    text = ini.read_text(encoding="utf-8")
    # ↓ 這次要改的設定：(params.ini 裡的鍵名, 新值)
    params = [("OL_runs", a.ol_runs), ("resampleFlag", a.resample),
              ("PCAflag", a.pca), ("PCAdims", a.pca_dims),
              ("KDEP_flag", a.kdep)]
    # ↓ 有給種子才改種子
    if a.seed is not None:
        params.append(("rnd_seed", a.seed))
    # ↓ 逐一改寫，最後寫回 params.ini
    for k, v in params:
        text = set_param(text, k, v)
    ini.write_text(text, encoding="utf-8")

    # ↓ 「三維獨立重抽」不在 params.ini 裡，改用環境變數告訴 pyUPMASK
    env = dict(os.environ)
    if a.indep_resample:
        env["PYUPMASK_INDEP_RESAMPLE"] = "1"

    # ═══════════════ 核心 3：執行 pyUPMASK 並收回結果 ═══════════════
    log = LOGS / f"{a.name}.log"
    print(f"[{a.name}] 輸入={src.name} OL={a.ol_runs} resample={a.resample} "
          f"PCA={a.pca}/{a.pca_dims} indep={a.indep_resample}")
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as fh:
        # ↓ 用目前這個 Python 執行 pyUPMASK.py：
        #     "-u"            不緩衝輸出，log 會即時寫入
        #     cwd=PY          在 pyUPMASK/ 資料夾裡執行（它從目前資料夾讀 params.ini）
        #     stdout=fh, stderr=subprocess.STDOUT  一般輸出與錯誤訊息都寫進 log
        #     env=env         帶上剛剛準備的環境變數
        r = subprocess.run([sys.executable, "-u", "pyUPMASK.py"], cwd=PY,
                           stdout=fh, stderr=subprocess.STDOUT, env=env)
    # ↓ 回傳碼不是 0 = pyUPMASK 出錯
    if r.returncode != 0:
        sys.exit(f"[{a.name}] pyUPMASK 失敗，看 {log}")

    # ↓ pyUPMASK 的輸出檔跟輸入檔同名，放在 pyUPMASK/output/；搬到 results/<名字>.dat
    out = PY / "output" / src.name
    dest = RESULTS / f"{a.name}.dat"
    shutil.move(out, dest)
    print(f"[{a.name}] 完成，{(time.time()-t0)/60:.1f} 分鐘 -> {dest.name}")


if __name__ == "__main__":
    main()
