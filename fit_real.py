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
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# 存在輸出 npz 裡的一個保留鍵，記錄「這批部分結果是用什麼設定算出來的」
# （見 build_manifest() / main() 裡的比對邏輯）。用雙底線包住避免跟
# CONFIGS 的單字母鍵（A/B/C/D）或未來可能加的設定名稱撞名。
MANIFEST_KEY = "__manifest__"


def build_manifest(args) -> dict:
    """列出所有會影響擬合結果、續傳時必須跟既有部分結果一致的執行設定。
    2026-08-15 CodeRabbit review 抓到：load_partial() 只看檔名（--tag），
    不驗證其餘設定——用同一個 --tag、換一個 --grid 或 --n-syn 續傳，會把
    舊設定算出的結果當成新設定已經算完，直接跳過重算，兩種不可比的結果
    混進同一個檔案卻看不出來。這裡把「會不會被 load_partial 誤判成同一批」
    的所有輸入都列進來，缺一個都可能造成誤判。"""
    return {
        "grid": args.grid,
        "n_syn": args.n_syn,
        "refines": args.refines,
        "fix_mh": args.fix_mh,
        "free_lowmass": args.free_lowmass,
        "native_bprp_err": args.native_bprp_err,
        "radius_range": args.radius_range,
        # 2026-08-19 CodeRabbit PR #62 抓到：--repeat-offset 會改動每次重複的
        # 亂數種子，所以它跟 --n-syn 一樣是「會改變結果」的輸入。少了它，同一個
        # --tag 先用 offset 0 寫入部分結果、再用 offset 1 續跑時 manifest 完全
        # 相同，rep < len(reps) 會直接跳過重算，把 offset 0 的結果當成 offset 1
        # 的結果沿用。
        "repeat_offset": args.repeat_offset,
    }


# 舊檔案的 manifest 可能缺少後來才加進來的鍵。缺鍵不等於「設定不同」——
# 那個旗標當時根本不存在，所以舊檔案必定是用該旗標的預設值算出來的。
# 這裡明確寫出每個後加鍵的「當時等效值」，讓缺鍵的舊檔案只在這次真的用了
# 非預設值時才判為不相容，不會因為補了一個欄位就逼所有既有部分結果重算。
MANIFEST_LEGACY_DEFAULTS = {
    "repeat_offset": 0,
}

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402
from measure_overconfidence import GRID                       # noqa: E402
from injection_recovery import COARSE, multi_stage_best       # noqa: E402


def atomic_savez(out_path: Path, **arrays):
    """np.savez 不是原子操作，寫到一半被中斷會留下截斷或空檔案。改成寫到
    同目錄的暫存檔，成功才用 os.replace() 原子性換過去（跟
    inject_lowmass.py 的 atomic_savez() 同一個理由、同一套寫法）。"""
    tmp_path = out_path.with_name(out_path.stem + ".tmp.npz")
    try:
        np.savez(tmp_path, **arrays)
        os.replace(tmp_path, out_path)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _acquire_write_lock(out_path: Path, timeout_s: float = 1800.0):
    """對 out_path 的存檔操作加互斥鎖，避免兩個用同一個 --tag 的行程同時
    讀-改-寫同一份 npz（2026-08-15 CodeRabbit review：atomic_savez() 只
    保證單次 os.replace() 不會留下半檔，不保護 load_partial() 到
    atomic_savez() 之間的整段讀-改-寫——兩個行程各自讀到舊快照、各自
    加上自己新算出的重複再存檔，後存的會整批覆蓋掉先存的那些新結果）。

    做法跟 run_queue.py 的 acquire_lock() 同一套 O_CREAT|O_EXCL 原子建立
    模式（該檔已用這個模式解決過同一類競態，這裡不重新發明）。**這只解決
    「檔案不會被覆蓋壞掉」，不解決「兩個行程各算了一份 rep 0 卻只留得住
    一份」**——要跨機器/帳號真正平行擴充同一批 repeats，還是要搭配不重疊
    的 repeat 索引（例如各自用不同 --tag 各出一個分片檔，跑完再手動合併），
    不是這個鎖能單獨補上的，見 fit_real.py 開頭這段留言與 PR #53 review。
    """
    lock_path = out_path.with_name(out_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock_path
        except FileExistsError:
            if time.time() - t0 > timeout_s:
                print(f"警告：等待 {lock_path.name} 超過 {timeout_s:.0f} 秒"
                      f"（可能是上一個行程異常結束沒清掉鎖檔），強制視為"
                      f"可以繼續，手動確認沒有另一個行程還在寫這個檔案。",
                      flush=True)
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            time.sleep(0.5)


def _release_write_lock(lock_path: Path):
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def load_partial(out_path: Path) -> dict:
    """載入上次中斷前已經存檔的部分結果，讓 main() 可以跳過已經算完的
    (config, rep) 組合，不必整批重算（2026-08-15：run_queue.py 需要重啟
    套用電源管理修正時，發現原本的存檔邏輯要等全部 configs/repeats 都跑完
    才存一次，中途被砍全部白工，即使每一次重複本身花好幾小時。改成每跑完
    一次重複就存一次，重跑時先讀回已有的部分結果）。"""
    if not out_path.exists():
        return {}
    try:
        d = np.load(out_path)
        return {k: np.asarray(d[k]) for k in d.files}
    except Exception as e:                                    # noqa: BLE001
        print(f"警告：讀取既有部分結果 {out_path} 失敗（{e}），"
              f"視為沒有可續傳的進度，從頭開始。", flush=True)
        return {}


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
    args = ap.parse_args()
    if args.repeat_offset < 0:
        ap.error("--repeat-offset must be non-negative")
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    n_proc = args.procs or (os.cpu_count() or 1)

    cfg = cfgmod.load()
    c3 = cfg.step3_age
    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
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
    base.use_native_bprp_err = args.native_bprp_err
    if args.native_bprp_err and "e_bp_native" not in errmodel:
        print("錯誤：--native-bprp-err 需要 errmodel.npz 含 e_bp_native/"
              "e_rp_native 鍵，目前載入的檔案沒有，先重建 errmodel.npz")
        sys.exit(1)
    sel = selmod.load(HERE / "data" / "selection.npz")
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
    partial_raw = load_partial(out_path)
    old_manifest_arr = partial_raw.pop(MANIFEST_KEY, None)
    partial = partial_raw
    if partial:
        if old_manifest_arr is None:
            # 舊檔案沒存過 manifest（這個檢查是 2026-08-15 才加的），沒有
            # 東西可比對——信任沿用，不因為缺 manifest 就拒絕續傳既有進度。
            print(f"警告：{out_path.name} 是加 manifest 檢查前存的舊檔，"
                  f"無法自動確認這次的設定跟它一致，視為信任沿用。",
                  flush=True)
        else:
            old_manifest = json.loads(str(old_manifest_arr))

            def _old(k):
                return old_manifest.get(k, MANIFEST_LEGACY_DEFAULTS.get(k))

            diffs = {k: (_old(k), v) for k, v in manifest.items()
                     if _old(k) != v}
            if diffs:
                print(f"錯誤：{out_path.name} 已有部分結果，但執行設定跟"
                      f"這次不同（{diffs}）。沿用會把兩種不可比的設定混進"
                      f"同一個檔案——換一個 --tag，或確認要不要刪掉舊檔"
                      f"重跑。", flush=True)
                sys.exit(1)
        n_done = {k: len(v) for k, v in partial.items()}
        print(f"讀到既有部分結果 {out_path.name}：{n_done}"
              f"（會跳過已經算完的重複，不是從頭重算）\n", flush=True)
    out = {k: list(v) for k, v in partial.items()}
    for key in [k.strip().upper() for k in args.configs.split(",")]:
        if key not in CONFIGS:
            continue
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
            # 重跑時 load_partial() 會讀回來跳過，不會白工。
            #
            # 存檔前先拿鎖、重新讀一次磁碟上的最新版本再合併——如果磁碟上
            # 這個 key 的重複數已經比我們手上這份多（代表有另一個行程用
            # 同一個 --tag 平行在跑，且比我們快），採用磁碟版本，不要用
            # 自己比較舊的覆蓋過去。這解決的是「檔案被覆蓋壞掉／新結果
            # 被舊結果蓋掉」，不解決「兩個行程各自算了一份同樣的 rep 卻
            # 只留得住一份」——真要跨機器平行擴充同一批 repeats，必須用
            # 不重疊的 repeat 索引分開跑（每個行程各自的 --tag），這裡的
            # 鎖只是最後一道防線，見 _acquire_write_lock() 的說明。
            lock_path = _acquire_write_lock(out_path)
            try:
                fresh = {k: v for k, v in load_partial(out_path).items()
                         if k != MANIFEST_KEY}
                if len(fresh.get(key, [])) > len(reps):
                    print(f"  [注意] 磁碟上 {key} 已有 "
                          f"{len(fresh[key])} 次重複，比這個行程手上的 "
                          f"{len(reps)} 次多（可能有另一個行程平行在跑同一個 "
                          f"--tag），改沿用磁碟版本繼續。", flush=True)
                    reps = list(fresh[key])
                out.update({k: v for k, v in fresh.items() if k != key})
                out[key] = np.array(reps)
                manifest_arr = np.array(json.dumps(manifest, sort_keys=True))
                atomic_savez(out_path, **out, **{MANIFEST_KEY: manifest_arr})
            finally:
                _release_write_lock(lock_path)
        arr = out[key]
        if args.repeats > 1:
            print(f"{key} 跨 {args.repeats} 次：alpha 平均 {arr[:,3].mean():.3f}"
                  f"、散布 {arr[:,3].std():.3f}"
                  f"（{'  '.join(f'{v:.3f}' for v in arr[:,3])}）\n", flush=True)

    print(f"{'='*74}\nalpha 隨模型設定的變化\n{'='*74}")
    print(f"{'設定':<6}{'說明':<34}{'alpha 平均':>11}{'散布':>8}{'相對 A':>10}")
    a0 = out["A"][:, 3].mean() if "A" in out else np.nan
    for key in out:
        a = out[key][:, 3]
        print(f"{key:<6}{CONFIGS[key][0]:<34}{a.mean():>11.3f}"
              f"{a.std():>8.3f}{a.mean()-a0:>+10.3f}")
    if "A" in out and "C" in out and args.repeats > 1:
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
