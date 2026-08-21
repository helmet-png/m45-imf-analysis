# -*- coding: utf-8 -*-
"""續傳／存檔共用邏輯（B3，見 docs/reference/PREFLIGHT.md）。

**這裡解決的問題跟 preflight.py 不同**：preflight.py 防的是「設定錯了
沒人發現」，這裡防的是「設定對，但中途被砍（斷電、重開機、手動中止）
就要從頭重算」——兩者互不重疊，一套完整的保護兩個都要有。

**動機**：`fit_real.py` 從 2026-08-15 起就有這套續傳機制（見 PR #55 起的
一系列修正），但另外四支診斷腳本（`profile_lowmass.py`／
`profile_outlierfrac.py`／`inject_lowmass.py`／`injection_recovery.py`）
要嘛完全沒有（只在最後 `np.savez` 一次），要嘛只做到一半
（`inject_lowmass.py` 每跑完一個注入真值存一次，但重啟時不會讀回既有
進度，一樣會重算已經跑完的部分）。本機曾經因為 Windows 連續四天強制
重開機四次，讓沒有續傳保護的 `profile_lowmass.py` 空轉四天一次都沒
跑完（`p6_lowmass_v2`），是這套機制存在的直接理由。

抽成共用模組而不是讓五支腳本各寫一份的理由跟 `preflight.audit_common()`
完全一樣：`fit_real.py` 原本自己維護一份 A1/A2/A3，`preflight.py` 建好
共用版本後有一次沒改到 `fit_real.py` 自己那份，兩份不同步了一輪才發現。
續傳邏輯一旦分裂成五份，同樣的事只是換個地方重演。

**用法**（兩種腳本都適用）：

    manifest = {"n_syn": args.n_syn, "refines": args.refines, ...}
    partial = checkpoint.load_partial(out_path)
    checkpoint.check_manifest(out_path, manifest, partial)

    for scan_val in scan_points:
        key = f"p{scan_val}"
        results, attempted = checkpoint.load_progress(partial, key)
        for t in range(n_repeats):
            if t < attempted:
                continue                       # 已經跑過（不管成功與否）
            ... 算一次 ...
            if 失敗:
                attempted = t + 1
                results = checkpoint.save_progress(
                    out_path, key, results, manifest, attempted=attempted)
                continue
            results.append(best)
            attempted = t + 1
            results = checkpoint.save_progress(
                out_path, key, results, manifest, attempted=attempted)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# 存在輸出 npz 裡的保留鍵，記錄「這批部分結果是用什麼設定算出來的」。
# 用雙底線包住避免跟 scan_key（設定名稱／掃描值字串化後的鍵）撞名。
MANIFEST_KEY = "__manifest__"


def _retry_permission_error(fn, *, attempts: int = 12):
    """對 `fn()` 做有上限的重試，只吞 `PermissionError`（Windows 上防毒／
    索引服務對剛寫完／剛要讀的檔案短暫佔用的已知現象，見 `atomic_savez()`
    的說明）。重試次數用完仍失敗就把最後一次的例外原樣往上拋，不會無限期
    忽略；任何非 `PermissionError` 的例外直接原樣拋出、不重試——那類錯誤
    重試沒有意義，只會拖慢真正失敗的訊號。

    **重試預算（12 次、每次間隔遞增到最多 1 秒，總計最壞情況約 6.5 秒）
    是實測調出來的，不是隨手訂的數字**：一開始用 6 次、每次最多 0.5 秒
    （總計約 1.5 秒），在這台機器背景同時跑著其他計算工作（CPU 滿載）
    時仍然重現到重試次數用完仍失敗——代表防毒／索引服務在系統忙碌時
    掃描一個剛寫完的小檔案，可能需要比 1.5 秒更長。6.5 秒對單次擬合
    動輒數分鐘的真實產線來說仍然可忽略，但給了明顯更多餘裕撐過系統
    忙碌的窗口。"""
    for attempt in range(attempts):
        try:
            return fn()
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(min(0.1 * (attempt + 1), 1.0))


def atomic_savez(out_path: Path, **arrays) -> None:
    """np.savez 不是原子操作——寫到一半被中斷（斷電、被砍行程）會留下
    截斷或空的檔案，蓋掉前一次跑成功的 checkpoint。改成寫到同目錄的
    暫存檔，成功才用 os.replace() 原子性地換過去；`os.replace()` 在
    POSIX 與 Windows 都保證是單一系統呼叫等級的原子操作，不會有
    「新檔案寫一半、舊檔案已經被砍」的中間狀態。寫入中途失敗時清掉
    暫存檔，不留半成品在 results/ 底下。

    （原本 fit_real.py 與 inject_lowmass.py 各自有一份幾乎逐字相同的
    實作，2026-08-20 收斂成這一份共用版本。）

    **`os.replace()` 在 Windows 上偶發 `PermissionError: [WinError 5]`**：
    自動化測試裡用高速迴圈連續存檔時重現過（同一組程式碼三次裡有一次
    炸掉，另外兩次正常）——不是邏輯錯誤，是 Windows 上防毒軟體即時掃描
    或索引服務短暫佔用剛寫完的暫存檔，`os.replace()` 撞上那個窗口就會
    被拒絕，過幾十毫秒鎖就放開了。這跟 `acquire_write_lock()`
    對付另一個行程持有鎖檔是同一類「等一下再試」的問題，這裡比照辦理：
    對 `PermissionError` 做有上限的重試，不是無限期忽略錯誤——重試次數
    用完仍然失敗就真的往上拋，不會把持續性的權限問題（例如檔案真的被
    唯讀鎖定）吞掉裝作沒事。"""
    # 檔名一定要用 .npz 結尾——np.savez() 對不是以 .npz 結尾的路徑會自動
    # 補一個 .npz 副檔名（實測過：傳 "x.npz.tmp" 會真的寫成
    # "x.npz.tmp.npz"），沒注意到這個行為的話 os.replace() 會找錯檔案。
    tmp_path = out_path.with_name(out_path.stem + ".tmp.npz")
    try:
        np.savez(tmp_path, **arrays)
        _retry_permission_error(lambda: os.replace(tmp_path, out_path))
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def acquire_write_lock(out_path: Path, timeout_s: float = 1800.0) -> Path:
    """對 out_path 的存檔操作加互斥鎖，避免兩個行程同時讀-改-寫同一份
    npz。O_CREAT|O_EXCL 原子建立模式跟 run_queue.py 的 acquire_lock()
    同一套，該檔已用這個模式解決過同一類競態，這裡不重新發明。"""
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
                # **一定要重設 t0**（2026-08-21 CodeRabbit review）：不重設
                # 的話，逾時之後每一輪迴圈的 `time.time() - t0 > timeout_s`
                # 都仍然成立——若另一個行程在我們刪掉鎖檔後立刻建立它，
                # 這裡會馬上再刪一次，而且完全不等待。互斥保護在第一次
                # 逾時之後就永久失效，兩個行程可以同時進入 save_progress()
                # 的讀-改-寫區段，正是這個鎖要防的事。重設之後每次強制
                # 接管都重新計時，最壞情況是慢，不是失去保護。
                t0 = time.time()
                continue
            time.sleep(0.5)


def release_write_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _read_npz_dict(out_path: Path) -> dict:
    """實際讀檔的共用邏輯：回傳 out_path 裡除了 MANIFEST_KEY 以外的全部
    鍵值。呼叫端必須自己處理「檔案不存在」（這裡不判斷）與讀取例外——
    寬鬆版本（`load_partial()`）跟嚴格版本（`_load_partial_strict()`）
    對這兩種情況的處置完全不同，見兩者各自的說明。

    **一定要用 `with` 關掉 `np.load()` 回傳的 `NpzFile`**：實測踩到的
    Windows 專屬 bug——`NpzFile` 內部持有的 `zipfile.ZipFile` 有循環參照，
    光靠函式返回時區域變數 `d` 的 refcount 歸零不保證立刻關檔（CPython
    的世代垃圾回收要等一輪循環偵測才會真的關閉底層檔案控制代碼）。這支
    函式常常在很短時間內被連續呼叫（`save_progress()` 每存一次檔就呼叫
    一次），沒關乾淨的控制代碼會卡住 Windows 的 `os.replace()`——同一個
    路徑被换成新檔案時，作業系統不允許任何控制代碼還開著（不像 POSIX
    允許 rename 一個仍被打開的檔案），直接丟
    `PermissionError: [WinError 5] 存取被拒`（2026-08-20 用高速迴圈重複
    存檔的自動化測試重現到，實機上跑得比較慢、GC 有更多機會介入，
    平常不容易踩到，但這是真實存在的競態，不是測試環境特有的假象）。"""
    with np.load(out_path, allow_pickle=False) as d:
        return {k: np.asarray(d[k]) for k in d.files if k != MANIFEST_KEY}


def load_partial(out_path: Path) -> dict:
    """載入上次中斷前已經存檔的部分結果（不含 MANIFEST_KEY），供「只是
    想看一眼跑到哪裡」的呼叫端用（例如 `preflight.workload_audit()` 要
    印進度、或腳本要決定跳過哪些已完成的重複）。**讀取失敗（不管是檔案
    真的不存在，還是存在但讀不出來）一律印警告、回傳 `{}`，視為沒有
    進度可續傳**——這個寬鬆行為只適用於「讀」的情境，不能被拿去給
    `save_progress()` 內部判斷要不要覆寫檔案用，見
    `_load_partial_strict()` 的說明為什麼那裡需要嚴格版本。"""
    if not out_path.exists():
        return {}
    try:
        return _read_npz_dict(out_path)
    except Exception as e:                                        # noqa: BLE001
        print(f"警告：讀取既有部分結果 {out_path} 失敗（{e}），"
              f"視為沒有可續傳的進度，從頭開始。", flush=True)
        return {}


def _load_partial_strict(out_path: Path) -> dict:
    """`save_progress()` 專用的嚴格版本：檔案不存在回傳 `{}`（合法情況，
    第一次存檔本來就沒有舊檔），但**檔案存在卻讀不出來時直接把例外往上
    拋，不吞掉**（對 `PermissionError` 先重試幾次，見
    `_retry_permission_error()`，重試用完仍失敗才真的拋出）。

    這跟 `load_partial()` 刻意不同：`save_progress()` 讀完 `fresh` 之後，
    會拿讀到的內容當「磁碟上其餘 scan_key 的既有結果」原封不動寫回去
    （只覆寫自己這次要存的那個 key）。如果讀取失敗被吞成 `{}`（跟
    `load_partial()` 一樣的寬鬆行為），`save_progress()` 會誤判成
    「磁碟上什麼都沒有」，接著用「只含當前這一個 scan_key」的內容原子性
    覆蓋掉整個檔案——磁碟上其他 scan_key 已經算完的結果就永久消失了。
    這正是這整個 PREFLIGHT／checkpoint 機制想防的「看起來成功（`exit
    0`、有寫出檔案），資料卻不是我們以為的那樣」的失敗形狀，換個地方在
    自己身上重演一次，所以這裡必須用會出聲的嚴格版本
    （2026-08-20 CodeRabbit review）。"""
    if not out_path.exists():
        return {}
    return _retry_permission_error(lambda: _read_npz_dict(out_path))


def load_manifest(out_path: Path) -> dict | None:
    """回傳既有存檔裡的 manifest dict；沒有存檔或沒有 manifest 回傳 None。

    同 `load_partial()`：用 `with` 確保 `NpzFile` 立刻關閉，見該函式的
    說明。"""
    if not out_path.exists():
        return None
    try:
        with np.load(out_path, allow_pickle=False) as d:
            if MANIFEST_KEY not in d.files:
                return None
            return json.loads(str(d[MANIFEST_KEY]))
    except Exception:                                             # noqa: BLE001
        return None


def check_manifest(out_path: Path, manifest: dict, partial: dict,
                   legacy_defaults: dict | None = None) -> None:
    """比對這次的執行設定跟既有部分結果的 manifest 是否一致，不一致就
    `sys.exit(1)`（原本是 fit_real.py main() 內嵌的邏輯，逐字抽成共用
    函式）。`partial` 為空（沒有既有部分結果）時不檢查，直接放行。

    `legacy_defaults`：manifest 裡缺鍵不等於「設定不同」——那個旗標
    當時根本不存在，舊檔案必定是用它的預設值算出來的（同 fit_real.py
    的 MANIFEST_LEGACY_DEFAULTS）。

    **完全沒有 manifest 的舊檔則是另一回事，一律擋下不放行**（2026-08-21
    修正，理由與實際案例見函式內註解）：`legacy_defaults` 處理的是「這個
    旗標當時不存在」，而沒有 manifest 代表「整份設定都不知道」，兩者不能
    用同一套寬容邏輯。"""
    if not partial:
        return
    old_manifest = load_manifest(out_path)
    legacy_defaults = legacy_defaults or {}
    if old_manifest is None:
        # **不能「視為信任沿用」**（2026-08-21 實際踩到，案例見下）。
        # 沒有 manifest 的舊檔正是最不該信任的那一種：它是加 manifest
        # 檢查之前存的，而那個「之前」涵蓋了 multi_stage_best() 精修
        # bug 還在的整段時期（見 LIMITATIONS.md A1）。信任沿用等於讓
        # 「專門為了修精修 bug 而排的重跑」把壞結果當成已完成的工作
        # 直接跳過，跑完 exit 0、什麼都沒算——正是 docs/reference/
        # PREFLIGHT.md 開宗明義要防的那個失敗形狀，在 preflight 自己
        # 身上重演。
        #
        # **實際案例**：results/profile_lowmass.npz（2026-08-15 存，
        # 無 manifest）裡 15 次擬合的 alpha 只有 4 個相異值
        # （2.1/2.3/2.5/2.7），相異值最小間距正好 0.2 = COARSE 網格
        # 間距，是「完全沒精修」的量化簽章。p6_lowmass_v2 就是為了
        # 取代它而排的，但舊邏輯判定「既有結果已滿足重複次數」，
        # 會讓那次重跑立刻結束。
        #
        # 改成擋下來並說明選項：沿用舊檔必須是人明確決定的動作，
        # 不能是預設行為。
        print(f"錯誤：{out_path.name} 有既有結果，但**沒有 manifest**"
              f"（是加 manifest 檢查之前存的舊檔），無法確認它是用什麼"
              f"設定、什麼版本的程式碼算出來的。\n"
              f"  不自動沿用的理由：沒有 manifest 的舊檔涵蓋了 "
              f"multi_stage_best() 精修 bug 還在的那段時期，沿用會讓"
              f"「為了修那個 bug 而排的重跑」直接跳過、什麼都不算，"
              f"卻回報成功（見 LIMITATIONS.md A1、"
              f"docs/reference/PREFLIGHT.md）。\n"
              f"  三個選項擇一：\n"
              f"    1. 這次要重算 -> 把 {out_path.name} 移開"
              f"（例如改名成 {out_path.stem}_legacy_no_manifest.npz）"
              f"再跑；\n"
              f"    2. 這次要另存 -> 加一個不同的 --tag；\n"
              f"    3. 確定舊檔可信 -> 自己核對過它的算法與設定之後，"
              f"手動補上 manifest 再跑。", flush=True)
        sys.exit(1)

    def _old(k):
        return old_manifest.get(k, legacy_defaults.get(k))

    diffs = {k: (_old(k), v) for k, v in manifest.items() if _old(k) != v}
    if diffs:
        print(f"錯誤：{out_path.name} 已有部分結果，但執行設定跟這次不同"
              f"（{diffs}）。沿用會把兩種不可比的設定混進同一個檔案——"
              f"換一個 --tag，或確認要不要刪掉舊檔重跑。", flush=True)
        sys.exit(1)


def load_progress(partial: dict, key: str) -> tuple[list, int]:
    """從 load_partial() 的回傳值取出某個 scan_key 目前的進度。

    回傳 (已成功的結果 list, 已嘗試次數)。「已嘗試」可能大於「已成功」——
    部分腳本（inject_lowmass.py／injection_recovery.py）遇到貼牆例外會
    跳過該次、不計入結果，但那個試驗索引真的跑過一次，續傳時不該重跑
    （重跑只會用同一組亂數種子再得到同一個失敗結果，白工）。永遠成功
    的腳本（fit_real.py／profile_lowmass.py／profile_outlierfrac.py）
    不需要在意這個區別，兩個數字本來就相等。"""
    results = list(partial[key]) if key in partial else []
    # 前綴（不是後綴）"__"：preflight.gate_c() 用 `not k.startswith("__")`
    # 篩出「真正的結果鍵」（跟既有的 "__manifest__" 同一個排除規則）。
    # 用後綴會讓這個記帳用的陣列被 gate_c 誤判成一個真正的結果維度去做
    # 精修/散布檢查，印出跟這個鍵毫無關係的假警告。
    att_key = f"__attempted_{key}"
    if att_key in partial:
        attempted = int(np.asarray(partial[att_key]).reshape(-1)[-1])
    else:
        attempted = len(results)          # 舊格式檔案／永遠成功的腳本
    return results, attempted


def save_progress(out_path: Path, key: str, results: list, manifest: dict,
                  *, attempted: int | None = None,
                  extra_arrays: dict | None = None) -> list:
    """存一個 scan_key 目前的部分結果＋已嘗試次數，回傳實際要沿用的
    result list（可能被磁碟上更新的版本取代）。

    每算完一次（不管成功或失敗）就呼叫一次——跟 fit_real.py 原本「每次
    重複算完立刻存檔」同一個顆粒度，中途被砍時最多損失最後一次未存檔
    的嘗試，不是整批。

    **競態保護跟 fit_real.py 原本內嵌的邏輯相同**：存檔前重新讀一次磁碟
    上的最新版本，如果磁碟已經比手上這份更進，代表有另一個行程平行在
    寫同一個輸出檔且比較快，改採用磁碟版本，不要用自己比較舊的覆蓋
    過去。這只解決「檔案不會被覆蓋壞掉」，不解決「兩個行程各自算了
    重複的一份卻只留得住一份」——真要跨機器平行擴充，還是要用不重疊的
    索引分開跑（各自的 --tag），這裡的鎖只是最後一道防線。"""
    if attempted is None:
        attempted = len(results)
    att_key = f"__attempted_{key}"
    lock_path = acquire_write_lock(out_path)
    try:
        # 用嚴格版本，不是 load_partial()：讀取失敗（不管是暫時的
        # PermissionError 還是真的損毀）在這裡絕對不能被吞成「當作沒有
        # 進度」——那會讓下面的 atomic_savez() 拿只含這個 key 的內容
        # 覆蓋掉磁碟上其他 scan_key 已經算完的結果，見
        # _load_partial_strict() 的說明。
        fresh = _load_partial_strict(out_path)
        disk_attempted = int(np.asarray(fresh[att_key]).reshape(-1)[-1]) \
            if att_key in fresh else len(fresh.get(key, []))
        if disk_attempted > attempted:
            print(f"  [注意] 磁碟上 {key} 已嘗試 {disk_attempted} 次，比這個"
                  f"行程手上的 {attempted} 次多（可能有另一個行程平行在跑同一個"
                  f"輸出檔），改沿用磁碟版本繼續。", flush=True)
            results = list(fresh[key]) if key in fresh else []
            attempted = disk_attempted
        out = {k: v for k, v in fresh.items() if k != key and k != att_key}
        if results:
            out[key] = np.array(results)
        out[att_key] = np.array([attempted])
        if extra_arrays:
            out.update(extra_arrays)
        manifest_arr = np.array(json.dumps(manifest, sort_keys=True))
        atomic_savez(out_path, **out, **{MANIFEST_KEY: manifest_arr})
    finally:
        release_write_lock(lock_path)
    return results
