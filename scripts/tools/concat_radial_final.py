# -*- coding: utf-8 -*-
"""把 radial_<組>_final 的 5 個 Kaggle 分片串接成一份完整結果。

**分片檔名全部相同**（fit_real_radial_<組>_final.npz），靠所在目錄名
（radial_<組>_final_rep<N>）對應 repeat_offset，不能只看檔名。

串接前逐項核對 manifest：除了 repeat_offset 之外每個欄位都必須一致，
不一致就中止——那代表某一片是用不同設定跑的，混進來會讓整組數字失去
「只差重複次數」這個前提。
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
group = sys.argv[1] if len(sys.argv) > 1 else "r3"   # r1 / r2 / r3 / rall
n_expect = 5

rows = []
for off in range(n_expect):
    d = REPO / "kaggle_results" / f"radial_{group}_final_rep{off}"
    f = d / "results" / f"fit_real_radial_{group}_final.npz"
    if not f.is_file():
        print(f"缺少分片 offset={off}: {f}")
        sys.exit(1)
    # allow_pickle=False：manifest 是 np.array(json.dumps(...)) 的純
    # unicode 陣列、C 是數值陣列，兩者都不需要 pickle。這支工具讀的是
    # 從 Kaggle 拉回來的檔案，開 allow_pickle 等於讓損毀或被動過手腳的
    # 分片有機會在讀取時執行任意程式碼（2026-08-21 CodeRabbit review，
    # 跟 preflight.gate_c() 當初同一個修正）。
    with np.load(f, allow_pickle=False) as z:
        man = json.loads(str(z["__manifest__"])) if "__manifest__" in z.files else None
        C = np.atleast_2d(z["C"])
    # 每片必須恰好是 (1, 7)——這些分片是用 `--repeats 1` 跑的，一列就是
    # 一次重複，七欄對應 names 那七個量（logage/A_V/f_bin/alpha/MH/
    # q_gamma/dav）。若某片有多列（例如有人手動用 --repeats 2 補跑過），
    # 下面 np.concatenate 會照收，C_all 變成 6 列以上，但 len(rows) 仍是
    # 5，逐片表格也只印 C[0]，最後卻印成「alpha 五次」——串出一份列數
    # 與宣稱不符的正式結果。欄數若不是 7（例如舊版腳本輸出少一欄），
    # 下面 `a = C_all[:, 3]` 仍會照抓第 4 欄當 alpha，但那一欄實際對到
    # 的量可能已經錯位——manifest 不記欄數也不記 repeats 的列數，所以
    # 上面的 manifest 一致性檢查攔不到這兩種情況（2026-08-21／2026-08-23
    # CodeRabbit review）。
    if C.shape != (1, 7):
        print(f"分片 offset={off} 的 C 形狀是 {C.shape}，預期剛好 (1, 7)："
              f"{f}")
        print("中止：每片必須是單次重複、七欄結果，否則串接後的列數／"
              "欄位對應會與宣稱不符。")
        sys.exit(1)
    rows.append((off, C, man, f))

# manifest 一致性檢查（repeat_offset 以外全部要相同）
base = dict(rows[0][2] or {})
base.pop("repeat_offset", None)
for off, _, man, f in rows[1:]:
    cur = dict(man or {})
    cur.pop("repeat_offset", None)
    diff = {k: (base.get(k), cur.get(k)) for k in set(base) | set(cur)
            if base.get(k) != cur.get(k)}
    if diff:
        print(f"manifest 不一致（offset={off}）：{diff}")
        print("中止：這幾片不是同一組設定跑出來的，不能串接。")
        sys.exit(1)
# 每片的 repeat_offset 要真的等於它所在目錄的 offset
for off, _, man, f in rows:
    got = (man or {}).get("repeat_offset")
    if got != off:
        print(f"目錄 rep{off} 的 manifest 卻記 repeat_offset={got}，中止")
        sys.exit(1)

C_all = np.concatenate([C for _, C, _, _ in rows], axis=0)
print(f"radial_{group}_final：{len(rows)} 片串接完成，C shape={C_all.shape}")
names = ["logage", "A_V", "f_bin", "alpha", "MH", "q_gamma", "dav"]
print(f"{'off':>4} " + " ".join(f"{n:>9}" for n in names[:C_all.shape[1]]))
for (off, C, _, _) in rows:
    print(f"{off:>4} " + " ".join(f"{v:9.4f}" for v in C[0]))
a = C_all[:, 3]
print()
print(f"alpha 五次：{np.round(a,4).tolist()}")
print(f"alpha 平均 = {a.mean():.4f}")
print(f"樣本標準差(ddof=1) = {a.std(ddof=1):.4f}")
print(f"平均值標準誤 = {a.std(ddof=1)/np.sqrt(len(a)):.4f}")

out = REPO / "results" / f"fit_real_radial_{group}_final.npz"
# **串接檔的 manifest 要保留「這是串出來的」這個身分**（2026-08-21
# CodeRabbit review）。上面 base 被 pop 掉了 repeat_offset，寫出去之後
# 若有人用同一個 --tag 跑 `fit_real.py`，`check_manifest()` 會拿舊檔缺的
# repeat_offset 套 MANIFEST_LEGACY_DEFAULTS 的 0——結果剛好正確（這 5 列
# 就是 offset 0–4，跟 `--repeats 5 --repeat-offset 0` 產生的那一組完全
# 相同），但那是「碰巧對」不是「明確記載」，而 manifest 存在的意義正是
# 事後查得出來歷。所以明確寫回 repeat_offset=0，並額外記下這是 aggregate
# 與每一列實際的 offset，讓事後拿到這個檔案的人分得出「5 列 = 5 個分片
# 串接」而不是「一台機器連跑 5 次」。
# 多出來的鍵不會干擾續傳：`check_manifest()` 是走訪「這次新建的
# manifest」的鍵去比對，舊檔多出來的鍵會被忽略。
agg = dict(base)
agg["repeat_offset"] = 0
agg["manifest_type"] = "aggregate"
agg["aggregated_repeat_offsets"] = [off for off, _, _, _ in rows]
np.savez(out, C=C_all, __manifest__=json.dumps(agg, ensure_ascii=False))
print(f"\n寫入 {out}")
