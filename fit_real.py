# -*- coding: utf-8 -*-
"""把修好的模型接上真實資料，看 alpha 到底移到哪裡。

**這支程式回答的問題**：注入回收量出模型漏了兩個效應（選擇函數 −0.178、
差異消光 +0.178），但那是在假資料上量的。真實資料上實際會移動多少？

作法是同一批觀測星、同一套搜尋，只換模型設定，逐項加回去：

  A  舊模型（無選擇函數、無差異消光）      <- 現有的 2.26–2.35 從這裡來
  B  只加選擇函數                          <- 預期 alpha 變陡
  C  選擇函數 + 差異消光自由（上界 0.6）    <- 預期抵消掉一部分
  D  同 C，但 dav 上界放到 1.2              <- 檢查 alpha 會不會跟著牆跑

D 是必要的：注入回收顯示 dav 是**不可辨識**的，給多少範圍它就吃多少
（上界 0.6 時跑到 0.600，放寬到 1.2 就跑到 1.200，加大 n_synthetic 也沒用）。
既然 dav 自己會貼牆，就必須確認 alpha 不會跟著牆的位置變 ——
在假資料上確認過（alpha 偏差與對照組完全相同），真實資料上要再確認一次，
因為真實資料還有模型沒描述到的其他不符。

**這裡報出來的 alpha 仍然不是最終值。** isochrone 模型的系統誤差
（PARSEC vs MIST/BHAC15）還沒量過，而注入回收在設計上就看不到它。

**這個 alpha 是哪一種質量函數的冪次**（D14，2026-08-19 補上）：是
**主星質量分布**的冪次，等價於以主星質量標記的 system MF；**不是**把
伴星也算進去的 stellar／single-star MF。理由在 `JointModel.synthesise()`：
合成星團的每一筆是一個**系統**——先抽 n_syn 個主星質量（冪次 = alpha），
再獨立擲 Bernoulli(f_bin) 決定誰帶伴星，伴星質量是 q*m1（q 抽自
p(q) ∝ q^qgamma，**不是抽自 IMF**），最後主星與伴星的流量相加塌縮成
同一個測光點。所以伴星從來沒有進入被擬合的那個質量分布。要換算成
stellar MF 必須把 f_bin 與 q 分布摺積回去，這裡沒有做這一步。

**兩者差多少（實算，不是估計）**：用專案實際參數（alpha=2.35、
q_gamma=-0.50、q_min=0.10、量測窗 0.5-2.5 Msun）做四百萬次蒙地卡羅，
把伴星也算進同一個量測窗後重新做截斷冪律 MLE，stellar MF 比
system MF **陡**：f_bin=0.30 -> +0.046、0.45 -> +0.066、0.60 -> +0.085、
0.75 -> +0.102。我們擬合到的 f_bin 大致落在 0.45-0.62，所以量級是
**+0.05 到 +0.09**——小於統計誤差 0.144，但跟好幾項系統誤差同量級，
跟文獻比對時若一邊報 system 一邊報 stellar，這個差不可忽略。
比對前務必先確認對方報的是哪一種。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts" / "tools"))
import checkpoint                                                 # noqa: E402

# 沿用 checkpoint.py 的保留鍵名（雙底線包住避免跟 CONFIGS 的單字母鍵
# A/B/C/D 或未來可能加的設定名稱撞名）。2026-08-20 起續傳的底層機制
# （atomic_savez／存取鎖／load_partial）搬進 scripts/tools/checkpoint.py
# 共用模組，這裡不再自己維護一份——這支腳本原本是唯一有這套機制的，
# 抽成共用模組後，另外四支診斷腳本才有辦法直接沿用同一套，不用各自
# 重新發明（同一個道理已經在 preflight.audit_common() 上發生過一次：
# fit_real.py 自己另外維護的一份跟共用版本不同步過，見下面
# _preflight_report() 的說明）。
MANIFEST_KEY = checkpoint.MANIFEST_KEY
SEED_SCHEME = "fit-real-offset-v1:2000+13*(rep+repeat_offset)"


def build_manifest(args) -> dict:
    """列出所有會影響擬合結果、續傳時必須跟既有部分結果一致的執行設定。
    2026-08-15 CodeRabbit review 抓到：load_partial() 只看檔名（--tag），
    不驗證其餘設定——用同一個 --tag、換一個 --grid 或 --n-syn 續傳，會把
    舊設定算出的結果當成新設定已經算完，直接跳過重算，兩種不可比的結果
    混進同一個檔案卻看不出來。這裡把「會不會被 load_partial 誤判成同一批」
    的所有輸入都列進來，缺一個都可能造成誤判。"""
    return {
        "tag": args.tag,
        "grid": args.grid,
        "n_syn": args.n_syn,
        "refines": args.refines,
        "fix_mh": args.fix_mh,
        "free_lowmass": args.free_lowmass,
        "native_bprp_err": args.native_bprp_err,
        "radius_range": args.radius_range,
        # 亮端截斷會改變觀測樣本本身，跟 radius_range 一樣是「會讓結果
        # 不可比」的輸入，必須進 manifest（見 MANIFEST_LEGACY_DEFAULTS）。
        "g_bright": args.g_bright,
        # 2026-08-19 CodeRabbit PR #62 抓到：--repeat-offset 會改動每次重複的
        # 亂數種子，所以它跟 --n-syn 一樣是「會改變結果」的輸入。少了它，同一個
        # --tag 先用 offset 0 寫入部分結果、再用 offset 1 續跑時 manifest 完全
        # 相同，rep < len(reps) 會直接跳過重算，把 offset 0 的結果當成 offset 1
        # 的結果沿用。
        "repeat_offset": args.repeat_offset,
        # 續傳安全不只取決於 offset，也取決於 offset 如何換成種子。
        # 規則若改變，即使其他旗標相同，舊 repeats 也不可混入新結果。
        "seed_scheme": SEED_SCHEME,
        "members_file": args.members_file,
        "errmodel_file": args.errmodel_file,
        "selection_file": args.selection_file,
    }


# 舊檔案的 manifest 可能缺少後來才加進來的鍵。缺鍵不等於「設定不同」——
# 那個旗標當時根本不存在，所以舊檔案必定是用該旗標的預設值算出來的。
# 這裡明確寫出每個後加鍵的「當時等效值」，讓缺鍵的舊檔案只在這次真的用了
# 非預設值時才判為不相容，不會因為補了一個欄位就逼所有既有部分結果重算。
MANIFEST_LEGACY_DEFAULTS = {
    "g_bright": None,
    "repeat_offset": 0,
    "members_file": "data/cmd_members.csv",
    "errmodel_file": "data/errmodel.npz",
    "selection_file": "data/selection.npz",
}

sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline import step5_imf                                # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402
from measure_overconfidence import GRID                       # noqa: E402
from injection_recovery import COARSE, multi_stage_best       # noqa: E402


def _preflight_gate(args, model, grid, refines, configs,
                    out_path, partial, n_obs) -> None:
    """開跑前檢查：把「這次到底會算什麼」攤開來。只讀不寫，不碰任何
    結果檔。有阻擋級問題時視 `args.force`／`args.preflight` 決定要不要
    中止（實際的中止/繼續邏輯在 `preflight.mandatory_gate()` 裡，見下）。

    2026-08-20 起分兩段，都改成呼叫共用函式，不再自己維護實作：
      B1（意圖對帳）／B2（輸出衝突） 原本是 fit_real.py 專屬（其餘四支
          腳本旗標介面互不相同，沒有共用），現在透過
          `preflight.workload_audit()`／`output_audit()` 收斂成同一套
          邏輯——那兩支函式不需要認得每支腳本的旗標名稱，呼叫端只要把
          自己的旗標轉換成同一組共同形狀（scan_keys＋repeats）即可，
          fit_real.py 是第一個套用者，另外四支腳本比照辦理。
      A1/A2/A3（解析度／設定對帳／網格涵蓋） 呼叫
          `preflight.mandatory_gate()`（內部呼叫 `audit_common()`）。
          這三段原本在這裡跟 `scripts/tools/preflight.py` 各自獨立實作
          同一套邏輯，CodeRabbit review 抓到「`--refines 1` 沒有實際
          精修效果卻只被當警告放行」這個 bug 時，我只修了共用版本，
          這裡的複本沒有跟著修——兩份各自演化然後不同步，正是這整個
          PREFLIGHT 機制想防的問題形狀，換個地方在自己身上重演。
          `mandatory_gate()` 同時接手中止/繼續/`--force` 的判定，這裡
          不用再自己重複一次同樣的邏輯。
    """
    sys.path.insert(0, str(HERE / "scripts" / "tools"))
    import preflight                                          # noqa: E402

    # --- B1：這次實際會算什麼（意圖對帳）---
    keys = [k.strip().upper() for k in args.configs.split(",")]
    valid = [k for k in keys if k in configs]
    unknown = [k for k in keys if k not in configs]
    # main() 對打錯的設定名稱另外還有一道不能被 --force 繞過的硬阻擋
    # （見 main() 該處註解）；這裡的 unknown 只影響 workload_audit 的
    # fails，走的是跟其餘 A2/A3 問題一樣「可以 --force 略過」的路徑，
    # 兩者用途不同、都要留著。
    partial_counts = {k: len(v) for k, v in partial.items()}
    w_fails, w_warns = preflight.workload_audit(
        scan_keys=valid, repeats=args.repeats, n_syn=args.n_syn,
        n_obs=n_obs, refines=refines, partial_counts=partial_counts,
        unit="次重複", unknown=unknown, known=list(configs),
        scan_label="設定（--configs）")
    if len(valid) > 1:
        w_warns.append(f"會算 {len(valid)} 套設定（{', '.join(valid)}），"
                       f"耗時約為單一設定的 {len(valid)} 倍——"
                       f"若只要 config C，記得帶 --configs C"
                       f"（radial_r1 就是漏帶這個白算了 6 機時）")

    # --- B2：輸出檔狀態 ---
    preflight.output_audit(out_path, partial)

    # --- A1/A2/A3：解析度／設定對帳／網格涵蓋，併入 B1 算出的 fails/warns
    # 一起判定 ---
    # **刻意讓 audit_common() 直接重讀 config.toml 原始檔案，不是傳
    # main() 已經解析好的 cfg 物件**：A2 那個 bug 的形狀正是「cfg 讀進來
    # 之後，程式碼又用 cfg._data[...]=... 動態覆寫掉某個值」。如果改成
    # 跟 model 一樣的 cfg 物件比對，兩邊用的會是同一份已經被覆寫過的值，
    # 永遠對得起來，等於讓這段檢查失去意義。fit_real.py 不像其餘四支
    # 診斷腳本那樣刻意覆寫 mh_prior_sigma，所以不傳 expected_overrides
    # ——如果哪天 fit_real.py 也悄悄多了一行覆寫，這裡會如實抓到。
    preflight.mandatory_gate(
        model, grid, refines, script="fit_real.py",
        force=args.force, dry_run=args.preflight,
        extra_fails=w_fails, extra_warns=w_warns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--n-syn", type=int, default=120_000)
    ap.add_argument("--configs", default="A,B,C,D")
    # 真實資料只有一份，重複擬合時「變的是什麼」必須講清楚：
    # 變的是**模型端的共用亂數**。合成星團是有限筆抽樣，換一批亂數
    # 概似曲面就會微幅改變，最佳解跟著移動。這個移動量就是
    # 「單次擬合的重現性」，A 與 C 的差要大於它才算真的位移。
    ap.add_argument("--repeats", type=int, default=1,
                    help="每個設定重複幾次（每次換一組模型端共用亂數）")
    ap.add_argument("--repeat-offset", type=int, default=0,
                    help="重複次數的起始索引偏移（種子 = 2000 + 13*(rep+offset)）。"
                         "只吃單一整數，不接受逗號清單。用來把同一組 --repeats N "
                         "拆到不同機器/帳號各跑一部分、彼此用不同亂數種子：5 個帳號"
                         "各跑一次時，是各自下 --repeats 1 --repeat-offset 0 / 1 / "
                         "2 / 3 / 4 五道獨立指令。**每個分片必須配一個唯一的 --tag**"
                         "（例如 _p2final_v3_rep0 ... _rep4）——輸出路徑只由 --tag "
                         "決定，共用同一個 --tag 的分片會互相覆寫，atomic_savez() "
                         "不會幫忙合併。全部跑完後把各檔案的 C 陣列依 offset 由小到大"
                         "沿 axis=0 串接，即等於一次 --repeats 5 的結果。"
                         "預設 0，不影響既有行為（見 PR #55）")
    ap.add_argument("--grid", default=GRID,
                    help="isochrone 網格檔名（在 isochrones/ 底下）。"
                         "換成 MIST 的檔案即可量出等時線模型造成的系統誤差")
    ap.add_argument("--tag", default="", help="輸出檔名後綴，避免覆蓋")
    # --- 開跑前檢查（2026-08-20 新增）---
    # 動機見 docs/reference/PREFLIGHT.md：本機佇列累計 103.1 機時裡有 86.6h
    # （84%）是白跑的，而其中 74.9h 是「exit 0、檔案寫出來、數字看起來正常，
    # 但算法不是我們以為的那個」——A1 精修 bug 一個人就吃掉 75 小時。
    # **為什麼這個旗標放在 fit_real.py 裡、而不是另外寫一支檢查腳本**：
    # 檢查腳本必須自己複製一份 argparse 預設值與模型建構流程，兩邊會各自
    # 演化然後不同步——那正是 A1（旗標是對的、旗標的意思變了）與 A2
    # （config.toml 宣告高斯先驗、程式碼寫死關掉）這兩個 bug 的形狀。
    # 用同一支程式的同一個 parser、同一段模型建構，檢查到的就必然是
    # 真正會跑的那組設定，不可能對不上。
    ap.add_argument("--preflight", action="store_true",
                    help="只做開跑前檢查然後結束，不進行任何擬合："
                         "印出解析後的完整參數、模型實際生效的設定"
                         "（對帳 config.toml）、搜尋軸 vs 網格涵蓋、"
                         "輸出檔／manifest 衝突狀態。通過回傳 0，"
                         "有阻擋級問題回傳非 0。**不加這個旗標時，開跑前"
                         "檢查一樣會跑**（2026-08-20 起無條件執行），這個"
                         "旗標只是「只檢查、不要真的算」的乾跑模式")
    ap.add_argument("--force", action="store_true",
                    help="開跑前檢查有阻擋級問題時仍然強行開跑（不建議，"
                         "僅供已經看過警告、確認要略過的情況使用）")
    # 精修階數。預設單階（格距 1/3）會讓 alpha 只落在 2.1/2.3/2.5 這種粗格點上；
    # 要當最終數字報時用 3,3（格距 1/9 = 0.022）才不會被量化污染。
    ap.add_argument("--refines", default="3")
    # P9：把金屬量釘死在指定值，判別表 4 的等時線穩健性是真的、
    # 還是靠 MH 這個自由參數在兩套模型上各自吸收了共同偏差換來的。
    #
    # **必須用兩套網格共有的格點**。isochrone 是離散的，_isochrone() 會
    # 吸附到最近的格點：PARSEC 的 MH 間距 0.05、MIST 只有 0.25，
    # 若指定光譜值 -0.03，PARSEC 吸附到 -0.05、MIST 吸附到 +0.00，
    # 憑空造出 0.05 dex 的差異，正好污染這個檢驗要看的東西。
    # MH=0.00 兩套都有（吸附誤差為零），且距光譜值 -0.03 僅 0.03，
    # 遠比自由擬合跑到的 +0.18 接近，檢驗邏輯成立。
    ap.add_argument("--fix-mh", type=float, default=None,
                    help="把金屬量固定在此值（P9 檢驗用）。"
                         "務必選 PARSEC 與 MIST 共有的格點，預設建議 0.0")
    # 驗證排程項目（2026-08-10，LIMITATIONS.md 待辦分類標準訂定後）：
    # 用 G 查 BP/RP 誤差會低估紅星誤差，這是每次擬合都在用的現役假設，
    # 從未驗證過代價。開這個旗標改用星體自己的 BP/RP 星等查各自波段
    # 的誤差曲線，A/B 跑兩次比較 alpha 有沒有變。
    ap.add_argument("--native-bprp-err", action="store_true",
                    help="改用星體自己的 BP/RP 星等查測光誤差（而非用 G）。"
                         "需要 errmodel.npz 含 e_bp_native/e_rp_native 鍵")
    # P6b（inject_lowmass.py）已驗證低質量段冪次升格為自由參數是可辨識的
    # （p_recovered 對 p_true 跟隨比值 0.92），但那個驗證從沒接回這支
    # 「產出最終數字」的腳本——p2_final2 用的低質量段冪次其實還是寫死
    # 在 -1.3。這個旗標把它接上：呼叫 JointModel.enable_lowmass_fit()，
    # 額外一維搜尋軸掃 0.3-2.3（跟 P6b 同範圍）。只在 config C/D（有 dav
    # 的設定）下有意義——enable_dav_fit() 必須先呼叫，因為
    # enable_lowmass_fit() 是往當下的 bounds 尾端追加一維，順序反了會把
    # p_lowmass 這個維度算成 dav。
    ap.add_argument("--free-lowmass", action="store_true",
                    help="把低質量段冪次(0.08-0.5 Msun)升格為自由參數，"
                         "搜尋範圍 0.3-2.3（P6b 驗證過的範圍）")
    # --- 徑向切片（2026-08-12 新增，PDMF -> IMF 這條線的第一個診斷）---
    # step5_imf.mass_function_by_radius() 已經用傳統法量過 alpha(r)：
    # 0-1度 1.77 -> 3-5.1度 2.29，核心到外圍差 0.515，是統計誤差 0.144 的
    # 3.6 倍、也比目前最大的單一系統誤差 0.248 還大。但那是傳統法量的，
    # 帶著未解析雙星造成的偏平偏差，而 Torres+2025 (ApJL 982, L34) 發現
    # Pleiades 的雙星比例隨半徑是雙峰的、不是常數 —— 所以那個梯度裡有
    # 多少是真的質量分層、多少是雙星比例隨半徑變化造成的假象，分不出來。
    # 這個旗標讓前向模型（會把雙星建模掉）在指定半徑範圍內重跑，
    # 梯度若存活就是真分層，若塌掉就代表原本那 0.515 有相當部分是雙星假象。
    # 距離模數 dm 刻意仍用全樣本算（星團只有一個距離，只讓「徑向選樣」
    # 這一個變因動）。
    ap.add_argument("--radius-range", default=None, metavar="LO,HI",
                    help="只用距星團中心 LO<=r<HI 度的成員擬合（例如 0,2）。"
                         "累積式用 0,r；環帶式用 lo,hi")
    # --- 亮端截斷（2026-08-19 新增，為了 D1 的 BHAC15 比較）---
    # BHAC15 只涵蓋到 1.4 Msun（M45 擬合範圍是 0.30-2.50），合成星團因此
    # 生不出亮於 G=8.88 的星。若不同時砍觀測端，那些只有觀測、模型必為零
    # 的 Hess 格會給出巨大的概似懲罰，擬合會扭曲其他參數去補償——量到的
    # 就不是「換等時線模型的代價」，而是「網格質量涵蓋不足的代價」。
    # 兩邊砍在同一個值才是同基準比較。**用這個旗標跑 BHAC15 時，PARSEC
    # 對照組必須用同一個值再跑一次**，否則比較的是兩個不同的樣本。
    ap.add_argument("--g-bright", type=float, default=None, metavar="MAG",
                    help="亮端截斷：觀測與合成兩邊都只保留 G >= MAG 的星。"
                         "預設 None＝沿用 config.toml 的 g_bright_limit（4.0）、"
                         "且不砍觀測端，行為與加入這個旗標前完全相同。"
                         "用於等時線網格質量涵蓋不足時做同基準比較（D1）")
    ap.add_argument("--members-file", default="data/cmd_members.csv",
                    help="CMD member CSV relative to the repository root")
    ap.add_argument("--errmodel-file", default="data/errmodel.npz",
                    help="Photometric-error NPZ relative to the repository root")
    ap.add_argument("--selection-file", default="data/selection.npz",
                    help="Selection-function NPZ relative to the repository root")
    args = ap.parse_args()
    if args.repeats < 1:
        # --repeats 0（或負數）讓 for rep in range(args.repeats) 完全不
        # 執行，reps 停在空 list，np.array([]) 是 shape (0,) 的一維陣列。
        # 沒有既有部分結果時，後面「alpha 隨模型設定的變化」總表對它做
        # out[key][:, 3] 會丟 IndexError（2026-08-20 CodeRabbit review）。
        # 這是結構性輸入錯誤，不是「已知風險、確認要略過」，--force 不
        # 應該放行。
        ap.error("--repeats must be positive")
    if args.repeat_offset < 0:
        ap.error("--repeat-offset must be non-negative")
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    n_proc = args.procs or (os.cpu_count() or 1)

    cfg = cfgmod.load()
    c3 = cfg.step3_age
    clean = Table.read(HERE / args.members_file, format="csv")
    # 已確認的非成員天體（RV+logg 雙訊號，見 LIMITATIONS.md A6）——顏色跟
    # 真成員無異，assign_masses() 的顏色檢查抓不到，只能靠這份獨立名單
    # 排除。run_pipeline.py（第 4/5 步）與 traditional_accounting.py 都
    # 已經接上這個機制，這支腳本（headline 前向模型數字的來源）先前漏接
    # （2026-09-05 使用者回報查出），會讓 p2_final 系列等既有結果混入這
    # 兩顆已確認非成員。
    excl = step5_imf.exclude_confirmed_non_members(
        np.asarray(clean["source_id"], np.int64))
    if excl.any():
        print(f"排除 {int(excl.sum())} 顆已確認非成員天體（見 "
              f"LIMITATIONS.md A6）")
    clean = clean[~excl]
    errmodel = dict(np.load(HERE / args.errmodel_file))
    grid = isomod.load_grid(isomod.CACHE / args.grid)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    if args.radius_range:
        # 中心與角距離的算法跟 run_pipeline.py 第 5 步完全一致（樣本中位
        # ra/dec + 球面角距），兩邊的 alpha(r) 才比得起來。
        r_lo, r_hi = [float(x) for x in args.radius_range.split(",")]
        ra = np.radians(np.asarray(clean["ra"], float))
        dec = np.radians(np.asarray(clean["dec"], float))
        ra0, dec0 = np.radians(np.median(np.degrees(ra))), np.radians(
            np.median(np.degrees(dec)))
        cosr = (np.sin(dec0) * np.sin(dec)
                + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0))
        rdeg = np.degrees(np.arccos(np.clip(cosr, -1, 1)))
        ok &= (rdeg >= r_lo) & (rdeg < r_hi)
        print(f"徑向切片 {r_lo:.2f} <= r < {r_hi:.2f} 度："
              f"{int(ok.sum()):,} / {len(rdeg):,} 顆", flush=True)
    if args.g_bright is not None:
        ok &= mag >= args.g_bright
        print(f"亮端截斷 G >= {args.g_bright:.2f}："
              f"{int(ok.sum()):,} / {int(np.isfinite(mag).sum()):,} 顆",
              flush=True)
    color, mag = color[ok], mag[ok]

    cfg._data["step3_age"]["n_synthetic"] = args.n_syn
    # P10（2026-08-10 使用者質問後查證，見 LIMITATIONS.md）：這裡曾經寫死
    # mh_prior_sigma=0.0，把 config.toml 宣告的高斯金屬量先驗（中心 -0.03、
    # sigma 0.10，取自 Gaia GSP-Spec/GSP-Phot 交叉驗證）關掉，退回均勻先驗。
    # 對 profile_lowmass.py/injection_recovery.py 這類純診斷腳本，關掉先驗
    # 是對的——先驗會污染那些測試想看的東西。但 fit_real.py 的角色是產出
    # 要寫進論文的最終數字，這裡沒有同等理由關掉，是從診斷腳本複製設定時
    # 沒有重新檢視。移除覆寫，改回讀 config 宣告的高斯先驗。

    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    if args.g_bright is not None:
        # 合成端的亮端截斷，跟上面觀測端砍在同一個值。JointModel 預設從
        # config.toml 讀 g_bright_limit=4.0；這裡覆寫掉。
        base.g_bright = args.g_bright
    base.use_native_bprp_err = args.native_bprp_err
    if args.native_bprp_err and not {"e_bp_native", "e_rp_native"}.issubset(errmodel):
        print(f"錯誤：--native-bprp-err 需要 {args.errmodel_file} 含 "
              "e_bp_native/e_rp_native 鍵，目前載入的檔案沒有，請先重建 "
              f"{args.errmodel_file}")
        sys.exit(1)
    sel = selmod.load(HERE / args.selection_file)
    print(f"真實觀測 {len(color):,} 顆，距離模數 {dm:.4f}，"
          f"n_synthetic {args.n_syn:,}")
    print(f"等時線網格：{args.grid}\n")

    # 第四項是允許貼牆的維度索引。
    #
    # A 與 B 沒有差異消光參數，而注入回收已證實：真實世界有差異消光、
    # 模型沒有時，A_V（索引 1）會被壓到物理下限 0。實測真實資料上確實如此
    # —— 這是這兩個設定**預期的症狀**，不是意外，所以放行但會標示出來。
    # q_gamma（索引 5）注入回收判定不受資料約束（對照組散布 0.157–0.236、
    # 正負亂跳），跟 dav 一樣是 nuisance，會在兩側牆之間遊走 ——
    # 實測 PARSEC 撞下界 −1.2、MIST 撞上界 +0.8。放行，但絕不能當測量值報。
    # C 與 D 是修好的模型，除上述已知項外任何一維貼牆都必須中止。
    CONFIGS = {
        "A": ("舊模型：無選擇函數、無差異消光", None, None, (1, 5)),
        "B": ("只加選擇函數", sel, None, (1, 5)),
        "C": ("選擇函數 + 差異消光（上界 0.6）", sel,
              np.arange(0.0, 0.61, 0.15), (5, 6)),
        "D": ("選擇函數 + 差異消光（上界 1.2）", sel,
              np.arange(0.0, 1.21, 0.20), (5, 6)),
    }

    from pipeline.step3_age import draw_randoms
    out_path = HERE / "results" / f"fit_real{args.tag}.npz"
    manifest = build_manifest(args)
    partial = checkpoint.load_partial(out_path)
    if partial and checkpoint.load_manifest(out_path) is None:
        print(f"錯誤：{out_path.name} 有既有結果但沒有 manifest，無法確認其"
              "亂數種子規則；為避免混合不可比的 repeats，拒絕續傳。請換一個 "
              "--tag，或先明確遷移舊結果。", flush=True)
        sys.exit(1)
    checkpoint.check_manifest(out_path, manifest, partial,
                              legacy_defaults=MANIFEST_LEGACY_DEFAULTS)
    # `__attempted_*` 是 checkpoint.py 內部的記帳鍵（每個 config 存一份，
    # 記「已嘗試次數」，供 inject_lowmass.py 這類會遇到貼牆例外的腳本
    # 續傳時判斷哪些試驗不用重跑），不是這裡要的「設定名稱 -> 結果陣列」
    # ——fit_real.py 一律成功、不需要那層區分，但 checkpoint.save_progress()
    # 仍然統一會寫這個鍵。load_partial() 只排除 MANIFEST_KEY，不排除它，
    # 混進 out 會讓下面 for key in out 的總表迴圈把它當成一個 config 去
    # 取 [:,3]，丟 IndexError／KeyError（2026-08-20 CodeRabbit review 抓到：
    # 續傳時才會觸發，第一次跑因為還沒有既有檔案不會發作）。跟
    # preflight.gate_c() 用同一條 startswith("__") 排除規則。
    partial = {k: v for k, v in partial.items() if not k.startswith("__")}
    if partial:
        n_done = {k: len(v) for k, v in partial.items()}
        print(f"讀到既有部分結果 {out_path.name}：{n_done}"
              f"（會跳過已經算完的重複，不是從頭重算）\n", flush=True)
    # 截到 args.repeats：既有結果比這次要求的 --repeats 多時（例如磁碟
    # 已有 3 次、這次只要 2 次），不截斷的話下面主迴圈會因為
    # rep < len(reps) 全部跳過、out[key] 卻仍帶著全部 3 筆，讓「跨 2 次」
    # 的平均/散布統計、還有 _preflight_gate() 的工作量報表都用了 3 筆，
    # 跟這次實際要求的次數對不上（2026-08-20 CodeRabbit review）。只截
    # 記憶體中這份拷貝，磁碟上的完整結果不動，也不影響「加大 --repeats」
    # 的續傳能力（那是从磁碟重新 load_partial() 讀，不會被這裡截斷過）。
    out = {k: list(v)[:args.repeats] for k, v in partial.items()}
    # **2026-08-20 改成無條件執行，不再只有 --preflight 才做**：這份檢查
    # 原本只在有人記得多打一個旗標時才會發生，但實際會呼叫這支腳本的
    # 地方不只 run_queue.py（那邊確實有記得先呼叫 --preflight）——Kaggle
    # 筆記本、x64 協作機手動下指令，都是直接跑 `python fit_real.py ...`，
    # 完全不經過任何會記得先檢查的中介層。讓檢查本身變成 main() 一部分，
    # 不管從哪台機器、哪種方式呼叫，都跑得到，不依賴呼叫端的記性。
    # 中止/繼續/--force 的判定都在 preflight.mandatory_gate() 裡（見
    # _preflight_gate()），這裡不用再自己重複一次。
    _preflight_gate(args, base, grid, refines, CONFIGS, out_path, out,
                    len(color))
    # 打錯的設定名稱要當場中止，不能像下面迴圈那樣用 `if key not in
    # CONFIGS: continue` 靜默略過——`--configs A,X` 打錯字時，沒有這段
    # 驗證的話會悄悄只算 A，結果檔看起來正常，只是少了一個誰都不知道
    # 該存在的設定，跟 `_preflight_gate()` 那份「意圖對帳」要防的是同一種
    # 錯（2026-08-20 CodeRabbit review：這裡跟 `_preflight_gate()` 各自
    # 過濾一次，preflight 那份只用來報告、可以被 --force 略過，這裡才是
    # 真正會不會跑錯的把關，不能被 --force 繞過）。
    requested = [k.strip().upper() for k in args.configs.split(",")]
    unknown = [k for k in requested if k not in CONFIGS]
    if unknown:
        print(f"錯誤：--configs 有不存在的設定名稱 {unknown}"
              f"（可用：{', '.join(CONFIGS)}）", flush=True)
        sys.exit(1)
    # --free-lowmass 只在有 dav（config C/D）的設定下安全（2026-08-26
    # CodeRabbit 回溯審查抓到）：enable_lowmass_fit() 一律把 p_lowmass
    # 疊加在「目前 bounds 的最後一維」，而 JointModel.synthesise() 是位置
    # 式解讀 theta——len(theta) > 6 時 theta[6] 一律當成 dav。A/B 沒有 dav
    # （extra 是 None，enable_dav_fit() 不會被呼叫），bounds 只有 6 維，
    # 若這裡還呼叫 enable_lowmass_fit()，p_lowmass 會被塞進 bounds 的
    # 索引 6，跑起來卻被 synthesise() 誤讀成 dav；低質量段冪次實際上
    # 全程沒被觸碰、仍是固定值，但輸出欄位會被標成「自由 p_lowmass」
    # 擬合出來的結果，安靜地產生錯的數字。目前程式碼還沒有追蹤到底
    # 疊加的是哪個參數的機制，先直接拒絕這個組合，不要生出誤標的結果。
    if args.free_lowmass:
        no_dav = [k for k in requested if CONFIGS[k][2] is None]
        if no_dav:
            print(f"錯誤：--free-lowmass 目前只支援有 dav 的設定"
                  f"（C／D），{no_dav} 沒有 dav，疊加 p_lowmass 會被"
                  f"synthesise() 誤讀成 dav、產生誤標的結果。請從 "
                  f"--configs 移除 {no_dav}，或不要帶 --free-lowmass。",
                  flush=True)
            sys.exit(1)
    for key in requested:
        desc, s, extra, allow = CONFIGS[key]
        print(f"{'='*74}\n{key}：{desc}\n{'='*74}", flush=True)
        reps = out.get(key, [])
        for rep in range(args.repeats):
            if rep < len(reps):
                print(f"{key} 第 {rep+1} 次：沿用既有結果，跳過重算",
                      flush=True)
                continue
            import copy
            m = copy.copy(base)
            m.obs_h = joint_fit.hess(color, mag, base.nb_c, base.nb_m,
                                     base.crange, base.mrange)
            m.n_obs = len(color)
            m.selection = s
            m.bounds = base.bounds[:6].copy()
            # **2026-08-15 拿掉 `if args.repeats > 1` 這個條件**：原本
            # `--repeats 1` 時完全不換模型端亂數，沿用 base 建構時就固定
            # 的種子（config.toml 的 random_seed）——代表跑十次
            # `--repeats 1` 會得到十個一模一樣的結果，不是十個獨立樣本。
            # 現在一律用 rep 索引換種子，不管這次呼叫的 --repeats 是多少，
            # 同一個 rep 索引永遠對應同一組亂數——這樣才能把一個
            # `--repeats 10` 的工作拆成多次獨立呼叫（例如分散到不同機器），
            # 結果跟一次跑完完全等價，也是這次能續傳的前提（續傳本質上
            # 就是「用同一個索引重跑一次」，種子不能因為 repeats 不同而變）。
            m.draws = draw_randoms(
                m.n_syn,
                np.random.default_rng(2000 + 13 * (rep + args.repeat_offset)))
            if extra is not None:
                m.enable_dav_fit(float(extra.min()), float(extra.max()))
            extra_axes = [extra] if extra is not None else []
            names = joint_fit.PARAM_NAMES + (["dav"] if extra is not None
                                             else [])
            if args.free_lowmass:
                m.enable_lowmass_fit(0.3, 2.3)
                extra_axes.append(np.arange(0.3, 2.301, 0.4))
                names = names + ["p_lowmass"]
            t0 = time.time()
            # P9：固定 MH 時，把該維的搜尋軸換成單一值。用替換座標軸而不是
            # 收窄 bounds 的原因：bounds 只擋先驗，多階段精修仍會在該維
            # 產生格點；換成單元素陣列才能真正讓它不動，且 multi_stage_best
            # 對 len(ax) < 2 的維度會直接沿用、不做精修。
            axes = list(COARSE)
            if args.fix_mh is not None:
                axes[4] = np.array([args.fix_mh])
            # dav（索引 6）不可辨識、貼牆是預期行為；p_lowmass（索引 7，
            # 若啟用）**不放行**——它貼牆正是 P6b 要偵測的失敗模式，跟
            # inject_lowmass.py 用同一個判斷；其餘維度貼牆直接報錯，
            # 因為這支程式產出的是要寫進論文的數字。
            best, lp, bounds = multi_stage_best(
                m, axes, refines, n_proc,
                extra_axis=(extra_axes if extra_axes else None),
                allow_wall=allow)
            # 放行的維度仍要標示出來，否則「允許」會變成「看不見」
            from injection_recovery import check_walls
            noted = check_walls(best, bounds, names)
            if noted:
                print("  [注意] " + "；".join(t for _, t in noted), flush=True)
            tag = f" 第 {rep+1} 次" if args.repeats > 1 else ""
            print(f"{'參數':<10}{'最佳值' + tag:>12}")
            for i, nm in enumerate(names):
                print(f"{nm:<10}{best[i]:>12.3f}")
            print(f"lnP = {lp:.1f}   年齡 {10**best[0]/1e6:.1f} Myr"
                  f"   ({time.time()-t0:.0f}s)\n", flush=True)
            reps.append(best)
            # 跑完一次重複就存一次，不等這個 config 的全部 repeats 或
            # 全部 configs 都跑完——中途被砍（不管是意外還是像這次一樣
            # 為了套用別的修正主動重啟），已經算完的每一次重複都保得住，
            # 重跑時 checkpoint.load_partial() 會讀回來跳過，不會白工。
            # 存檔／跨行程競態保護見 scripts/tools/checkpoint.py 的
            # save_progress()（原本這裡自己拿鎖、重讀磁碟、合併寫回的一段，
            # 2026-08-20 收斂成共用函式，另外四支診斷腳本直接沿用）。
            reps = checkpoint.save_progress(out_path, key, reps, manifest)
        # 迴圈外無條件轉成 ndarray，不能只在迴圈內「有算新的一次」才轉
        # ——若這個 key 的全部 repeats 都被續傳跳過（rep < len(reps) 對
        # 每一次都成立），迴圈本體一次都不會執行，`out[key]` 會停在最初
        # `out = {k: list(v) for k, v in partial.items()}` 那行給的原始
        # list，下面 `arr[:,3]` 這種 ndarray 用法就會丟
        # `TypeError: list indices must be integers or slices, not tuple`
        # （這是既有 bug，續傳測試時發現，跟這次的 checkpoint 重構本身
        # 無關但同一條路徑上，一併修掉）。
        #
        # 再截一次 [:args.repeats]：`checkpoint.save_progress()` 偵測到
        # 磁碟上有另一個行程寫入更新的版本時，會直接回傳磁碟上的完整
        # `reps`（見該函式「改沿用磁碟版本繼續」那段）——那份完整版本
        # 可能比這次 `args.repeats` 要求的多，不截斷的話跨行程競態下
        # 統計筆數又會跟這次要求的次數對不上，同一顆問題（見上面
        # 主迴圈前 `out = {...}[:args.repeats]` 那次修正）在跨行程續傳
        # 這條路徑上重演一次（2026-08-20 CodeRabbit review）。
        out[key] = np.array(reps[:args.repeats])
        arr = out[key]
        if args.repeats > 1:
            print(f"{key} 跨 {args.repeats} 次：alpha 平均 {arr[:,3].mean():.3f}"
                  f"、散布 {arr[:,3].std():.3f}"
                  f"（{'  '.join(f'{v:.3f}' for v in arr[:,3])}）\n", flush=True)

    # 上面 `out[key] = np.array(...)` 的轉型只發生在 `for key in
    # requested:` 迴圈內，只碰得到這次 `--configs` 選到的設定——`out`
    # 裡若還混著這次沒選、只是沿用舊 checkpoint 殘留的設定（例如上例的
    # A），那些鍵仍停在最初 `out = {k: list(v)[:args.repeats] for ...}`
    # 給的原始 list，下面 `out[key][:, 3]` 會丟
    # `TypeError: list indices must be integers or slices, not tuple`
    # ——跟前面那個「全部 repeats 都被續傳跳過」的既有 bug 同一個形狀，
    # 換成「這個 key 這次根本沒被主迴圈碰過」這個變體，一併在這裡收尾
    # 統一轉型修掉，不用在每個可能少碰到某個 key 的分支各自補一次
    # （2026-08-20 CodeRabbit review 抓到「A 混進 C 的統計」才發現）。
    out = {k: np.asarray(v) for k, v in out.items()}
    print(f"{'='*74}\nalpha 隨模型設定的變化\n{'='*74}")
    print(f"{'設定':<6}{'說明':<34}{'alpha 平均':>11}{'散布':>8}{'相對 A':>10}")
    a0 = out["A"][:, 3].mean() if "A" in out else np.nan
    for key in out:
        a = out[key][:, 3]
        print(f"{key:<6}{CONFIGS[key][0]:<34}{a.mean():>11.3f}"
              f"{a.std():>8.3f}{a.mean()-a0:>+10.3f}")
    # 除了 args.repeats > 1，還要求 A／C 兩邊「這次手上的筆數」本身
    # 都 > 1：`out` 裡可能混著這次沒被 --configs 選到、只是沿用舊
    # checkpoint 殘留筆數的設定（例如舊檔只有 A 的 1 筆結果，這次跑
    # `--configs C --repeats 2`，A 完全沒被這次的主迴圈碰過，`out["A"]`
    # 停在 1 筆）——用 `args.repeats > 1` 判斷不出這種情況，`len(out["A"])`
    # 只有 1 時 `var(ddof=1)` 除以 (1-1)=0 會靜默產生 nan，混進看起來
    # 正常的位移報表裡（2026-08-20 CodeRabbit review）。
    if "A" in out and "C" in out and args.repeats > 1 \
            and len(out["A"]) > 1 and len(out["C"]) > 1:
        # 位移要與重現性比較才有意義。兩組各自的散布合併成位移的標準誤。
        na, nc = len(out["A"]), len(out["C"])
        se = np.sqrt(out["A"][:, 3].var(ddof=1) / na
                     + out["C"][:, 3].var(ddof=1) / nc)
        d = out["C"][:, 3].mean() - a0
        print(f"\nA -> C 的 alpha 位移 = {d:+.3f} ± {se:.3f}（標準誤）"
              f" = {abs(d)/se if se > 0 else np.inf:.1f} 倍標準誤")
        print("判讀：位移要明顯大於標準誤，才能說模型修正真的改變了 alpha。")
    if "C" in out and "D" in out:
        print(f"\ndav 上界從 0.6 放到 1.2："
              f"dav {out['C'][:,6].mean():.3f} -> {out['D'][:,6].mean():.3f}，"
              f"alpha {out['C'][:,3].mean():.3f} -> {out['D'][:,3].mean():.3f}")

    # 每一次重複跑完就已經存過檔了（見上面的迴圈），這裡不用再存一次，
    # 只是印出最終確認訊息。
    print(f"\n已寫入 {out_path.relative_to(HERE)}（含全部 config／repeats）")


if __name__ == "__main__":
    main()
