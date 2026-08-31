# -*- coding: utf-8 -*-
"""開跑前／跑完後的三道關卡。動機與完整數字見 `docs/reference/PREFLIGHT.md`。

一句話：本機佇列累計 103.1 機時裡有 86.6h（84%）白跑，而其中 74.9h 不是
當掉、不是卡死，是**跑完 exit 0、檔案寫出來、數字看起來正常，但算法不是
我們以為的那個**。所以這裡檢查的重點不是「程式有沒有跑完」，是「算出來
的東西是不是我們以為的那個東西」。

    Gate A  程式碼層自我測試（改過搜尋程式碼後跑）
            A1  解析度自我測試——實際跑一次搜尋，量它有沒有照宣稱的階數收斂
            A2  設定對帳 ┐ 這兩項在 `fit_real.py --preflight` 裡（用同一個
            A3  網格涵蓋 ┘ parser、同一段模型建構，不可能跟本體不同步）
    Gate B  排進佇列前（秒級）
            B1  意圖對帳 ┐ 同上，`--preflight` 逐行代跑
            B2  輸出衝突 ┘
            B3  續傳能力——這支腳本撐不撐得過重開機
    Gate C  跑完驗收（秒級）
            C1  量化簽章——最佳點是不是全落在粗網格節點上（＝沒精修）、
                重複間散布是不是精確 0、有沒有貼牆
            C2  manifest 完整性——沒有 manifest 的結果檔無法事後查證設定

用法：
    python scripts/tools/preflight.py --gate a          # 只跑 A1 自我測試
    python scripts/tools/preflight.py --gate b          # 檢查 queue.txt 待跑項
    python scripts/tools/preflight.py --gate c results/fit_real_xxx.npz
    python scripts/tools/preflight.py --all             # A + B，開跑前用這個
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

def _find_repo_root() -> Path:
    """找出專案根目錄（放 config.toml 的那一層）。

    平常這支檔案在 `scripts/tools/preflight.py`，往上兩層就是根目錄。
    **但 Kaggle 派工會把附加檔案的路徑壓平**（`kaggle_sync.py` 的
    `build_payload()` 用 `shutil.copy(src, work_dir / Path(f).name)`，
    kernel 端也是複製到 cwd），所以在 Kaggle 上這支檔案會躺在
    `/kaggle/working/preflight.py`，`parents[2]` 算出來是 `/`，接著
    `open(HERE / "config.toml")` 就會 FileNotFoundError: '/config.toml'。

    2026-08-21 實測踩到：radial_r1_final_rep3/rep4、radial_r2_final_rep0~3
    等 6 個 Kaggle 工作連續在 187-213 秒失敗，錯誤都是這一行。

    改法是「按實際找得到 config.toml 的那一層為準」，依序試：
    往上兩層（正常安裝）-> 這支檔案自己所在的目錄（Kaggle 壓平後）->
    目前工作目錄。全都找不到時退回原本的 parents[2]，讓錯誤訊息維持
    原樣，不要靜默用一個猜的路徑繼續跑。
    """
    here = Path(__file__).resolve()
    for cand in (here.parents[2], here.parent, Path.cwd()):
        if (cand / "config.toml").is_file():
            return cand
    return here.parents[2]


HERE = _find_repo_root()
sys.path.insert(0, str(HERE))


def _force_utf8_stdout() -> None:
    """Windows 主控台預設 cp950。**只能在直接執行這支腳本時呼叫**——
    `run_queue.py` 的 `_postflight()` 會 `import preflight` 在同一個
    process 裡呼叫 `gate_c()`；如果這段留在模組層級（匯入就執行），
    會連帶把 `run_queue.py` 自己的 stdout 編碼改掉，副作用跑到呼叫端
    身上（2026-08-20 CodeRabbit review 抓到）。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- Gate A1

class _QuadModel:
    """log_posterior 是個解析的凹二次函數，峰值位置已知。

    定義在模組層而不是函式內，因為 `grid_best_parallel()` 走
    multiprocessing 時要把 model pickle 給工人，區域類別 pickle 不了。
    """

    def __init__(self, peak, scale):
        self.peak = np.asarray(peak, float)
        self.scale = np.asarray(scale, float)

    def log_posterior(self, th):
        d = (np.asarray(th, float) - self.peak) / self.scale
        return -float(np.dot(d, d))


def gate_a1(verbose=True) -> list[str]:
    """A1：實際跑一次 `multi_stage_best()`，量它有沒有照宣稱的階數收斂。

    **為什麼非得實際跑一次、不能只檢查旗標**：A1 那個吃掉 75 機時的 bug，
    形狀是「`--refines 3` 這個旗標帶了，但它的意思不是我們以為的那個」——
    當時 `refines=[3]` 回傳的是純粗網格 argmax，完全沒精修。任何檢查
    「有沒有帶 --refines」的檢查表都會通過（`p2_final2` 確實帶了
    `--refines 3,3`）。唯一抓得到的方式，是把峰值放在已知位置、實際搜尋
    一次、量誤差有沒有小到只有真的精修才可能達到。

    做法：峰值刻意放在粗格點 + 0.45 格距（接近兩個粗格點的正中間），
    這樣「沒精修」的誤差必然約 0.45 格距，跟「精修一階」的上限
    （格距/6）差了快 3 倍，不可能靠運氣矇混過去。
    """
    from injection_recovery import multi_stage_best

    steps = [0.20, 0.10, 0.50]
    axes = [np.arange(0.0, 1.601, steps[0]),
            np.arange(0.0, 0.801, steps[1]),
            np.arange(-1.20, 0.801, steps[2])]
    # 峰值 = 某個粗格點 + 0.45 格距，落在兩個粗格點中間附近
    peak = [float(ax[len(ax) // 2]) + 0.45 * h for ax, h in zip(axes, steps)]
    model = _QuadModel(peak, [1.0, 1.0, 1.0])
    names = ["p0", "p1", "p2"]
    fails = []

    if verbose:
        print("【A1 解析度自我測試】峰值刻意放在粗格點+0.45格距處")
        print(f"  真值 {np.round(peak, 4)}")
        print(f"  {'refines':<12}{'宣稱格距':>10}{'最大誤差':>10}"
              f"{'容許上限':>10}   判定")

    for refines in ([], [3], [3, 3]):
        best, _lp, _b = multi_stage_best(model, axes, refines, 1,
                                         raise_on_wall=False, names=names)
        err = np.abs(np.asarray(best, float) - np.asarray(peak, float))
        # 每階精修把格距縮 r 倍；最後落在最近格點上，誤差上限是半格
        finals = [h / np.prod(refines) if refines else h for h in steps]
        limit = np.array(finals) / 2 + 1e-9
        worst = float(np.max(err / limit))
        ok = worst <= 1.0
        if verbose:
            lbl = ",".join(str(r) for r in refines) or "(無)"
            print(f"  {lbl:<12}{np.mean(finals):>10.4f}"
                  f"{float(np.max(err)):>10.4f}"
                  f"{float(np.max(limit)):>10.4f}   "
                  f"{'通過' if ok else '**不通過**'}")
        if not ok:
            fails.append(
                f"A1：refines={refines} 沒有收斂到宣稱的解析度"
                f"（最大誤差 {float(np.max(err)):.4f}，容許 "
                f"{float(np.max(limit)):.4f}）——精修可能沒有真的生效，"
                f"這正是吃掉 75 機時的那個 bug 的形狀")

    # 反向對照：確認這個測試本身分得出「有精修」跟「沒精修」。
    # 少了這一段，就算 multi_stage_best 完全不精修、測試也可能因為容許值
    # 訂太寬而全部通過——那種測試比沒有測試更危險。
    b0, _, _ = multi_stage_best(model, axes, [], 1,
                                raise_on_wall=False, names=names)
    b2, _, _ = multi_stage_best(model, axes, [3, 3], 1,
                                raise_on_wall=False, names=names)
    e0 = float(np.max(np.abs(np.asarray(b0) - peak)))
    e2 = float(np.max(np.abs(np.asarray(b2) - peak)))
    if verbose:
        print(f"  反向對照：無精修誤差 {e0:.4f} vs 兩階精修 {e2:.4f}"
              f"（比值 {e0 / max(e2, 1e-12):.1f}x）")
    if e0 <= e2 * 3:
        fails.append("A1 反向對照失敗：無精修與兩階精修的誤差沒有明顯差距，"
                     "代表這個測試本身失去鑑別力（容許值可能訂太寬），"
                     "在修好之前不能拿它當通過依據")

    # 平行路徑一致性：實際跑的都是 --procs 8，序列與平行必須給同一個答案
    big = [np.arange(0.0, 1.601, 0.05), np.arange(0.0, 0.801, 0.025),
           np.arange(-1.20, 0.801, 0.10)]
    s, _, _ = multi_stage_best(model, big, [], 1,
                               raise_on_wall=False, names=names)
    p, _, _ = multi_stage_best(model, big, [], 4,
                               raise_on_wall=False, names=names)
    same = np.allclose(np.asarray(s, float), np.asarray(p, float))
    if verbose:
        n = int(np.prod([len(a) for a in big]))
        print(f"  平行路徑一致性（{n:,} 格點，序列 vs 4 行程）："
              f"{'一致' if same else '**不一致**'}")
    if not same:
        fails.append(f"A1：同一組格點序列搜尋得到 {np.round(s, 4)}、"
                     f"平行搜尋得到 {np.round(p, 4)}，平行版有 bug")
    return fails


# --------------------------------------------------------- Gate A2/A3 共用

def audit_common(model, grid, refines, *, script: str,
                 expected_overrides: dict | None = None) -> tuple[list, list]:
    """A2（設定對帳）＋ A3（網格涵蓋）的通用實作，回傳 (fails, warns)。

    2026-08-20：`fit_real.py` 有自己專屬的 `--preflight`，但其餘四支計算
    腳本（`profile_lowmass.py`／`profile_outlierfrac.py`／
    `inject_lowmass.py`／`injection_recovery.py`）完全沒有這層保護——
    只要不透過 `run_queue.py` 派工（例如在 Kaggle 筆記本或 x64 協作機
    上直接執行），就完全沒人檢查過設定。這支函式讓五支腳本共用同一套
    對帳邏輯，任何一支的模型建構方式改變，五支一起受益，不會有第六支
    腳本重新發明一次又跟其他五支不同步。

    **`expected_overrides` 存在的理由**：`profile_lowmass.py` 等四支
    診斷腳本會刻意 `cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0`
    關掉金屬量高斯先驗——這是設計上的正確行為（先驗會污染這些腳本要
    測的東西），不是 A2 那種「該用先驗卻被悄悄關掉」的 bug。如果直接
    拿這裡跟 `config.toml` 宣告值比對，會對這四支腳本的每一次呼叫都
    誤報成阻擋，訓練使用者養成「看到阻擋就忽略」的習慣，反而讓真正的
    A2 抓不到人注意。傳 `expected_overrides={"mh_prior_sigma": 0.0}`
    這類參數，讓對帳邏輯知道「這個鍵本來就該是這個值」，但仍然檢查
    模型實際生效的值有沒有精確等於這個刻意值——如果哪天覆寫那行被
    不小心刪掉、或值被改動，這裡還是抓得到。
    """
    try:                                # Python < 3.11 沒有 tomllib，
        import tomllib                  # 理由見 pipeline/config.py 同一段
    except ModuleNotFoundError:
        import tomli as tomllib
    from injection_recovery import COARSE
    fails, warns = [], []
    overrides = expected_overrides or {}
    P = lambda s="": print(s, flush=True)                    # noqa: E731

    # --- 解析度：宣稱 vs 實際達成 ---
    span = float(COARSE[3][1] - COARSE[3][0])
    # **2026-08-20 CodeRabbit review 抓到，第二輪又追加**：原本只擋
    # `r<=0`、再靠比較整體 final 跟 span 抓「完全沒精修」，但那只擋得住
    # *全部*倍率加起來都沒效果的情況——`--refines 1,3` 這種**只有其中
    # 一階**是無效倍率（r=1，`step/1==step` 格距完全沒縮小）的情況會被
    # 放過，因為後面那階（r=3）的效果會把整體 final 拉到小於 span，
    # 通過整體比較，但那一階本身是白算的，等於謊報「精修了兩階」。
    # 改成逐一擋每個 `r<=1` 的倍率——不只是排除會除以零或算出負格距的
    # r<=0，`r==1` 本身也不構成精修，兩者都要在計算 final 前一次擋掉。
    bad_r = [r for r in refines if r <= 1]
    if bad_r:
        fails.append(f"--refines 裡有不會精修的倍率 {bad_r}——"
                     f"multi_stage_best() 用 step/r 算下一輪格距，"
                     f"r<=0 會除以零或算出負格距，r==1 則格距完全不縮小，"
                     f"兩者都等於那一階白算，每個倍率都必須 > 1")
        final = span
    else:
        final = span
        for r in refines:
            final /= r
    P("\n【解析度】")
    P(f"  alpha 粗網格格距   {span:.4f}")
    P(f"  精修後實際格距     {final:.4f}"
      f"（{span:.2f} / {' / '.join(str(r) for r in refines) or '1'}）")
    if not bad_r:
        if not refines:
            fails.append(f"--refines 是空的，等於完全不精修，alpha 只會"
                         f"落在 {span:.2f} 間距的粗網格點上")
        elif len(refines) < 2:
            warns.append(f"只精修 {len(refines)} 階，alpha 實際解析度 "
                         f"{final:.4f}——要當最終數字報請確認是否需要更多階")

    # --- 設定對帳：模型實際生效的值 vs config.toml 宣告值（或刻意覆寫值）---
    with open(HERE / "config.toml", "rb") as fh:
        raw = tomllib.load(fh)
    jf = raw.get("joint_fit", {})
    P(f"\n【設定對帳】{script} 模型實際生效 vs config.toml 宣告")
    pairs = [
        ("mh_prior_mean", model._mh_mean, jf.get("mh_prior_mean")),
        ("mh_prior_sigma", model._mh_sigma, jf.get("mh_prior_sigma")),
        ("logage_min", model.bounds[0][0], jf.get("logage_min")),
        ("logage_max", model.bounds[0][1], jf.get("logage_max")),
        ("av_max", model.bounds[1][1], jf.get("av_max")),
        ("fbin_max", model.bounds[2][1], jf.get("fbin_max")),
        ("alpha_min", model.bounds[3][0], jf.get("alpha_min")),
        ("alpha_max", model.bounds[3][1], jf.get("alpha_max")),
        ("mh_min", model.bounds[4][0], jf.get("mh_min")),
        ("mh_max", model.bounds[4][1], jf.get("mh_max")),
    ]
    for name, eff, decl in pairs:
        expect = overrides.get(name)
        if expect is not None:
            same = abs(float(eff) - float(expect)) < 1e-9
            P(f"  {'  ' if same else '!!'} {name:16s} 生效 {float(eff):+8.3f}"
              f"   刻意覆寫為 {float(expect):+8.3f}")
            if not same:
                fails.append(f"{name}：這支腳本應該刻意覆寫成 "
                             f"{float(expect):+.3f}，但模型實際生效值是 "
                             f"{float(eff):+.3f}——覆寫可能被移除或改動了")
            continue
        if decl is None:
            continue
        same = abs(float(eff) - float(decl)) < 1e-9
        P(f"  {'  ' if same else '!!'} {name:16s} 生效 {float(eff):+8.3f}"
          f"   宣告 {float(decl):+8.3f}")
        if not same:
            fails.append(f"{name}：模型實際用 {float(eff):+.3f}，但 "
                         f"config.toml 宣告 {float(decl):+.3f}"
                         f"——程式碼裡有覆寫，且沒有在 expected_overrides "
                         f"裡登記成刻意行為")

    # --- 搜尋軸 vs 等時線網格實際涵蓋 ---
    ages = np.unique(np.asarray(grid["logAge"], float))
    mhs = np.unique(np.asarray(grid["MH"], float))
    P("\n【搜尋軸 vs 網格涵蓋】")
    for label, axis, cov in (("logage", COARSE[0], ages),
                             ("MH", COARSE[4], mhs)):
        ghost = int(((axis < cov.min() - 1e-9)
                     | (axis > cov.max() + 1e-9)).sum())
        P(f"  {label:7s} 搜尋 [{axis.min():+.2f}, {axis.max():+.2f}]"
          f"   網格涵蓋 [{cov.min():+.3f}, {cov.max():+.3f}]"
          f"   幽靈格點 {ghost}/{len(axis)}")
        if ghost:
            warns.append(
                f"{label} 有 {ghost}/{len(axis)} 個粗格點落在網格涵蓋之外，"
                f"會被最近鄰吸附到邊界等時線——不是獨立的模型")
    return fails, warns


def workload_audit(*, scan_keys: list[str], repeats: int, n_syn: int,
                   n_obs: int, refines: list[int], partial_counts: dict,
                   unit: str = "次重複", unknown: list[str] | None = None,
                   known: list[str] | None = None,
                   scan_label: str = "掃描項目") -> tuple[list[str], list[str]]:
    """B1（意圖對帳）的通用實作，回傳 (fails, warns)，印【工作量】段落。

    2026-08-20：原本 B1 只有 `fit_real.py` 有（`_preflight_report()` 裡
    手寫的一段），其餘四支診斷腳本旗標介面互不相同（`--configs` vs
    `--slopes`／`--fracs` vs `--trials`+`--only` vs `--scenarios`），
    沒有共用同一套邏輯。這裡不去認得每支腳本的旗標名稱，而是要求呼叫端
    先把自己的旗標解析成同一組共同形狀——「一串 scan_key（設定名稱、
    冪次、污染比例、真值、情境……字串化後的鍵）＋ 每個 key 重複幾次」，
    這組形狀所有五支腳本都套得上，不用再各寫一份印報表／算 n_new 的
    邏輯（那正是 B1/B2 遲遲沒有推廣的原因——覺得每支腳本都要重寫一份
    不划算，這裡把「重寫」的部分收斂成「轉換成共同形狀」）。

    `partial_counts`：`{scan_key: 已嘗試次數}`，用 `checkpoint.load_progress()`
    算出來的 attempted（不是純成功次數——已經跑過但失敗的也不該重跑，
    見 checkpoint.py 的說明）。"""
    fails, warns = [], []
    if unknown:
        fails.append(f"{scan_label}有不存在的名稱 {unknown}"
                     f"（可用：{', '.join(known or [])}），"
                     f"它們會被靜默略過，實際只會處理已知的那些")
    n_new = sum(max(0, repeats - partial_counts.get(k, 0)) for k in scan_keys)
    print("\n【工作量】", flush=True)
    print(f"  {scan_label}          {', '.join(scan_keys) or '(無)'}"
          f"（{len(scan_keys)} 項）", flush=True)
    print(f"  每項重複           {repeats} {unit}", flush=True)
    print(f"  已完成、會跳過     {partial_counts or '無'}", flush=True)
    print(f"  這次實際要算       {n_new} {unit}", flush=True)
    print(f"  精修階數           {refines}"
          f"（粗網格 + {len(refines)} 階精修）", flush=True)
    print(f"  合成星數 n_syn     {n_syn:,}", flush=True)
    print(f"  觀測星數           {n_obs:,}", flush=True)
    if n_new == 0 and scan_keys:
        warns.append("這次沒有任何新的工作要算（既有結果已滿足重複次數），"
                     "跑起來會立刻結束")
    return fails, warns


def output_audit(out_path: Path, partial: dict,
                 resume_desc: str = "有（每次嘗試算完立刻存檔＋寫入鎖，"
                                    "見 scripts/tools/checkpoint.py）") -> None:
    """B2（輸出狀態）的通用實作，只印報告，不產生 fails——manifest 不相容
    的情況在呼叫這支函式之前，`checkpoint.check_manifest()` 就已經
    `sys.exit(1)` 擋掉了，走到這裡只會是「沒有舊檔」或「舊檔相容」，
    是報告不是判斷（跟 fit_real.py 原本 `_preflight_report()` 的【輸出】
    段落同一個道理）。"""
    print("\n【輸出】", flush=True)
    print(f"  檔案               results/{out_path.name}", flush=True)
    print(f"  目前狀態           "
          f"{'已存在，設定相容，會續傳' if partial else '不存在，從頭開始'}",
          flush=True)
    print(f"  續傳保護           {resume_desc}", flush=True)


def mandatory_gate(model, grid, refines, *, script: str,
                   expected_overrides: dict | None = None,
                   force: bool = False, dry_run: bool = False,
                   extra_fails: list[str] | None = None,
                   extra_warns: list[str] | None = None) -> None:
    """五支計算腳本的 `main()` 都在建好 `model`（`JointModel`）之後、開始
    真正計算之前，無條件呼叫這支函式一次——不是選用旗標，是預設行為。
    這樣不管從哪台機器、用什麼方式呼叫（`run_queue.py`、Kaggle 筆記本、
    x64 協作機手動下指令），檢查都會發生，不依賴呼叫端記得先跑
    `--preflight`。

    `extra_fails`／`extra_warns`：呼叫端先跑過 `workload_audit()`（B1）
    算出的 fails/warns，併入這裡的最終判定與印出的摘要——B1 沒有阻擋
    級問題就不該讓計算被 A2/A3 以外的原因擋下來，反過來也一樣，兩邊
    的 fails 是同一個「通不通過」判定的兩個來源，不能分開判。呼叫端
    應該在呼叫這支函式之前先印好【工作量】／【輸出】兩節（見
    `workload_audit()`／`output_audit()`），這裡只接手 A2/A3 那段報告
    與最終摘要，不重複印一次。

    `dry_run=True`（對應各腳本的 `--preflight` 旗標）：印完報告就結束，
    不管有沒有阻擋都不會繼續往下跑，回傳碼視結果而定——這是「只檢查」
    模式，給 `run_queue.py` 的 Gate B 或人工手動確認用。

    `dry_run=False`（正常執行路徑，預設）：有阻擋級問題時 `sys.exit(1)`
    直接中止，不進入真正的計算，除非 `force=True`（對應 `--force` 旗標，
    僅供已經看過警告、確認要略過的情況使用，不是日常流程）。"""
    print("=" * 74, flush=True)
    print(f"開跑前檢查（{script}"
          f"{' --preflight，只檢查不計算' if dry_run else ' 自動執行，不是選用步驟'}）",
          flush=True)
    print("=" * 74, flush=True)
    fails, warns = audit_common(model, grid, refines, script=script,
                                expected_overrides=expected_overrides)
    fails = list(fails) + list(extra_fails or [])
    warns = list(warns) + list(extra_warns or [])
    print("\n" + "=" * 74, flush=True)
    for w in warns:
        print(f"  注意：{w}", flush=True)
    for f in fails:
        print(f"  阻擋：{f}", flush=True)
    print(f"結論：{'不通過' if fails else '通過'}"
          f"（阻擋 {len(fails)}、注意 {len(warns)}）", flush=True)
    print("=" * 74 + "\n", flush=True)
    if dry_run:
        sys.exit(1 if fails else 0)
    if fails and not force:
        print("開跑前檢查沒通過，中止（用 --force 可以略過，"
              "但要先確認上面每一條阻擋的理由）", flush=True)
        sys.exit(1)
    if fails and force:
        print("警告：用 --force 略過了上面的阻擋，繼續執行", flush=True)


# ----------------------------------------------------------------- Gate B

# 判斷 fit_real.py --preflight 子行程輸出裡哪些行是「這裡要看的」。
# 集中成一個常數，run_queue.py 直接匯入這個，不要各自維護一份會漏同步
# 的複本——`fit_real.py` 的 manifest 不相容時只印「錯誤：...」就
# sys.exit(1)（見 main() 開頭），漏了這個前綴就只看得到退出碼、看不到
# 原因（2026-08-20 CodeRabbit review 抓到這個漏項）。
STATUS_PREFIXES = ("注意：", "阻擋：", "結論：", "錯誤：")


def _has_resume(script: str) -> bool:
    """這支腳本撐不撐得過中途被砍（重開機／卡死重試）。

    用讀原始碼判斷而不是維護一份名單：名單會過期，而且新腳本加進來時
    不會有人記得回來更新。

    2026-08-20：續傳邏輯統一搬進 `scripts/tools/checkpoint.py` 共用模組
    （原本只有 `fit_real.py` 自己一份，`inject_lowmass.py` 部分做到一半，
    `profile_lowmass.py`／`profile_outlierfrac.py`／`injection_recovery.py`
    完全沒有）。找的是有沒有 `import checkpoint`；`load_partial`／
    `MANIFEST_KEY` 這組舊 pattern 留著當備援，涵蓋還沒改用共用模組、
    但自己重新實作了同一套邏輯的腳本。
    """
    p = HERE / script
    if not p.exists():
        return False
    src = p.read_text(encoding="utf-8", errors="replace")
    if re.search(r"^\s*import checkpoint\b", src, re.MULTILINE):
        return True
    return "load_partial" in src and "MANIFEST_KEY" in src


def gate_b(only_pending=True, verbose=True) -> list[str]:
    """B1/B2/B3：對 queue.txt 裡待跑的每一行做檢查。

    **2026-08-20 更新**：`PREFLIGHT_AWARE_SCRIPTS`（`fit_real.py`／
    `profile_lowmass.py`／`profile_outlierfrac.py`／`inject_lowmass.py`／
    `injection_recovery.py`，五支計算腳本全部）的行都會實際呼叫
    `--preflight` 代跑一次（用它自己的 parser 與模型建構，不會跟本體
    不同步），拿到 A2（設定對帳）／A3（網格涵蓋）／B1（意圖對帳）／
    B2（輸出衝突）的完整檢查——五支腳本旗標介面互不相同，但透過
    `preflight.workload_audit()`／`output_audit()` 共用同一套邏輯（見
    該函式說明），不是各自硬寫一份。B3（續傳能力）另外用 `_has_resume()`
    讀原始碼判斷，五支現在都用 `scripts/tools/checkpoint.py`，全部為真。
    名單外（不在 `PREFLIGHT_AWARE_SCRIPTS`）的腳本只做得到 B3 這層靜態
    檢查——**這個涵蓋差異會照實印出來，不會讓人以為每一行都受到同等
    程度的檢查**。
    """
    import run_queue as rq
    items = rq.read_queue()
    done = rq.read_done() if only_pending else set()
    pending = [(l, c) for l, c in items if l not in done]
    fails = []
    if verbose:
        print(f"【Gate B】queue.txt 待跑 {len(pending)} 項"
              f"（總共 {len(items)} 項）\n")
    for label, cmd in pending:
        script = cmd.split()[0]
        resume = _has_resume(script)
        if verbose:
            print(f"  ── {label}  ({script})")
            print(f"     續傳保護 {'有' if resume else '**無**'}")
        if not resume:
            fails.append(
                f"{label}（{script}）沒有逐次存檔／續傳機制，中途被砍就得"
                f"從頭重算。這台機器過去四天被 Windows 強制重開機至少 4 次，"
                f"p6_lowmass_v2 因此空轉了四天一次都沒跑完")
        if script in rq.PREFLIGHT_AWARE_SCRIPTS:
            # 見 run_queue.py 的 _preflight_ok() 同一段註解：子行程要用
            # UTF-8 輸出，否則中文 Windows 下寫 cp950、這邊解出來是亂碼，
            # 下面挑警告行的字串比對會全部挑不到。
            env = {**os.environ, "PYTHONUTF8": "1"}
            r = subprocess.run([sys.executable, script, *cmd.split()[1:],
                                "--preflight"], cwd=str(HERE), env=env,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            tail = [ln for ln in (r.stdout or "").splitlines()
                    if ln.strip().startswith(STATUS_PREFIXES)]
            if verbose:
                for ln in tail:
                    print(f"     {ln.strip()}")
            if r.returncode != 0:
                fails.append(f"{label}：{script} --preflight 不通過"
                             f"（退出碼 {r.returncode}）")
        elif verbose:
            print("     （這支腳本還沒有 --preflight，只做了續傳檢查，"
                  "沒有做設定對帳／解析度／網格涵蓋檢查）")
        if verbose:
            print()
    return fails


# ----------------------------------------------------------------- Gate C

# checkpoint.save_progress() 的 extra_arrays 會把掃描點清單、注入真值這類
# metadata 寫成一般鍵（不能加 "__" 前綴——下游分析程式是用這些名字讀的）。
# gate_c 逐鍵做「落在粗網格節點上沒有」的判定時要跳過它們，否則會對一個
# 根本不是參數向量的陣列做落點判定，產生跟結果無關的假阻擋
# （2026-08-21 CodeRabbit review）。
METADATA_KEYS = frozenset({
    "slopes",          # profile_lowmass.py
    "fracs",           # profile_outlierfrac.py
    "p_true",          # inject_lowmass.py
    "theta_true",      # injection_recovery.py
    "dav_distribution",
})


def gate_c(npz_path: Path, verbose=True) -> list[str]:
    """C1/C2：跑完的結果檔驗收。

    C1 找的是 A1 那個 bug 留在資料裡的簽章：**最佳點全部精確落在粗網格
    節點上**。當年 P11 十二次跑出來的 alpha 全部精確等於 2.500、散布
    0.000，那個簽章一直在檔案裡，只是沒有人系統性地去看——十八個機時
    之後才靠人眼發現。
    """
    # allow_pickle=False：manifest 存的是 np.array(json.dumps(...))，
    # 純 unicode 陣列，其餘鍵都是數值陣列，都不需要 pickle。Gate C 由
    # 無人監看的 run_queue.py 自動呼叫，開 allow_pickle 等於讓惡意/損毀
    # 的 npz 有機會在讀取時執行任意程式碼（2026-08-20 CodeRabbit review）。
    # 用 with 關閉 NpzFile——`scripts/tools/checkpoint.py` 的
    # `_read_npz_dict()` 明文記錄過這條規則：NpzFile 內部 zipfile 的循環
    # 參照會讓底層檔案控制代碼延遲關閉，後續對同一路徑的 os.replace() 在
    # Windows 上丟 PermissionError。gate_c 由 run_queue.py 的 _postflight()
    # 在跑完之後呼叫，緊接著佇列下一項就可能寫同一個檔案，屬於會踩到的
    # 情境（2026-08-21 CodeRabbit review）。
    with np.load(npz_path, allow_pickle=False) as d:
        return _gate_c_body(d, npz_path, verbose)


def _gate_c_body(d, npz_path: Path, verbose: bool) -> list[str]:
    """gate_c() 的本體，拆出來只是為了讓上面那層 `with` 包住整段。"""
    from injection_recovery import COARSE
    import json
    fails = []
    names = ["logage", "A_V", "f_bin", "alpha", "MH", "q_gamma", "dav"]
    if verbose:
        print(f"【Gate C】{npz_path.name}")

    man = d["__manifest__"] if "__manifest__" in d.files else None
    if man is None:
        fails.append(f"{npz_path.name} 沒有 manifest，無法事後查證它是用"
                     f"什麼設定算出來的（radial_r1_prelim 就是這樣，"
                     f"現在分不出它的精修有沒有生效）")
        refines = None
    else:
        m = json.loads(str(man))
        refines = [int(x) for x in str(m.get("refines", "")).split(",")
                   if x.strip()]
        if verbose:
            print(f"  manifest  refines={m.get('refines')}  "
                  f"grid={m.get('grid', '?')[:40]}  "
                  f"radius={m.get('radius_range')}")

    for key in [k for k in d.files if not k.startswith("__")]:
        if key in METADATA_KEYS:
            # 掃描點清單／注入真值這類 metadata（由 checkpoint.save_progress()
            # 的 extra_arrays 寫入），不是「一次擬合的參數向量」，拿去做
            # 落點/散布判定沒有意義，只會產生跟結果無關的雜訊行。
            continue
        arr = np.atleast_2d(d[key])
        nd = arr.shape[1]
        # 每個維度：最佳值是否精確落在粗網格節點上
        on_node = []
        for i in range(min(nd, len(COARSE))):
            ax = COARSE[i]
            hit = [bool(np.any(np.abs(ax - v) < 1e-9)) for v in arr[:, i]]
            on_node.append(all(hit))
        n_on = sum(on_node)
        scatter = arr.std(axis=0) if arr.shape[0] > 1 else None
        if verbose:
            print(f"  {key}: {arr.shape[0]} 次重複，"
                  f"{n_on}/{len(on_node)} 個維度全部落在粗網格節點上")
            if scatter is not None:
                z = [names[i] for i in range(min(nd, len(names)))
                     if scatter[i] == 0.0]
                print(f"     重複間散布精確為 0 的維度："
                      f"{', '.join(z) if z else '無'}")
        # **量化簽章的判定不能取決於有沒有 manifest**（2026-08-21 修）：
        # 原本寫成 `if refines and n_on == len(on_node)`，沒有 manifest 時
        # `refines` 是 None，這道最強的檢查整個被跳過——資訊越少反而檢查
        # 越鬆，方向是反的，跟先前修過的 `_preflight_ok()` 同一類 fail-open。
        # 實際後果：`results/profile_lowmass.npz`（無 manifest）15 次擬合
        # 的 alpha 只有 4 個相異值、間距精確 0.20＝COARSE 格距，是教科書
        # 等級的「完全沒精修」簽章，gate_c 卻只回報「沒有 manifest」，把
        # 「6/6 個維度全部落在粗網格節點上」當成純資訊印出來，要靠人眼
        # 注意到。沒有 manifest 時改成照樣判定量化，只是措辭不能說「宣稱
        # 精修幾階」（那要 manifest 才知道）。
        if on_node and n_on == len(on_node):
            # 用 `man is None` 而不是 `if refines` 來分辨兩種情況
            # （2026-08-21 CodeRabbit review）：manifest 存在但 refines 欄位
            # 缺鍵或是空字串時，`refines` 同樣會是空 list，用 `if refines`
            # 判斷會把這種檔案誤報成「沒有 manifest」，給出錯的診斷方向、
            # 誤導人工核對。
            if man is None:
                fails.append(
                    f"{npz_path.name}[{key}]：最佳點在全部 {n_on} 個維度都"
                    f"精確落在粗網格節點上（A1 的簽章），而且沒有 manifest "
                    f"可以查證當初帶了什麼 --refines——這是最可疑的組合，"
                    f"不是「資訊不足所以放行」，在人工核對確認精修真的有"
                    f"生效之前不要引用這個檔案的數字")
            elif refines:
                fails.append(
                    f"{npz_path.name}[{key}]：宣稱精修 {len(refines)} 階，但"
                    f"最佳點在全部 {n_on} 個維度都精確落在粗網格節點上——"
                    f"精修很可能沒有生效（A1 的簽章）")
            else:
                fails.append(
                    f"{npz_path.name}[{key}]：最佳點在全部 {n_on} 個維度都"
                    f"精確落在粗網格節點上（A1 的簽章）。這個檔案有 manifest，"
                    f"但裡面的 --refines 是空的或缺這個欄位——等於明確記載了"
                    f"「沒有做任何精修」，跟簽章一致，不要引用這個檔案的數字")
        if scatter is not None and nd > 3 and arr.shape[0] >= 3 \
                and float(scatter[3]) == 0.0:
            fails.append(
                f"{npz_path.name}[{key}]：{arr.shape[0]} 次重複的 alpha "
                f"散布精確等於 0.000。每次重複本來就會換一批模型端共用"
                f"亂數，散布不該是 0——P11 當年就是這個症狀（12 次全部"
                f"精確等於 2.500），代表精修沒生效、答案被量化到粗格點")
    return fails


# -------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", choices=["a", "b", "c"])
    ap.add_argument("--all", action="store_true", help="跑 Gate A + B")
    ap.add_argument("npz", nargs="*", type=Path, help="Gate C 要驗收的結果檔")
    a = ap.parse_args()
    # 沒選任何關卡時，原本 fails 是空 list，會印「結論：通過」——但一項
    # 檢查都沒做，呼叫端（人工或腳本）會把這個 0 誤讀成「查過了、沒問題」。
    # 2026-08-20 CodeRabbit review 抓到。
    if not a.all and not a.gate:
        ap.error("要指定 --gate a/b/c 或 --all，否則不會執行任何檢查")
    if a.gate == "c" and not a.npz:
        ap.error("--gate c 需要至少一個結果檔路徑")
    fails = []
    if a.all or a.gate == "a":
        fails += gate_a1()
        print()
    if a.all or a.gate == "b":
        fails += gate_b()
    if a.gate == "c":
        for p in a.npz:
            fails += gate_c(p)
            print()
    print("=" * 74)
    for f in fails:
        print(f"  阻擋：{f}")
    print(f"結論：{'不通過' if fails else '通過'}（阻擋 {len(fails)}）")
    print("=" * 74)
    return 1 if fails else 0


if __name__ == "__main__":
    _force_utf8_stdout()
    sys.exit(main())
