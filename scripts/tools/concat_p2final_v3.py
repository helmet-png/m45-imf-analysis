"""一次性腳本：把 headline p2_final2_v3 的 10 個 rep*.npz（各 1 次重複，
因 Kaggle 12 小時上限拆分派工）沿 axis=0 串接成單一 fit_real_p2final_v3.npz，
等價於一次 --repeats 10 的完整輸出。只讀 rep*.npz，不覆寫它們。"""
import numpy as np
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent.parent / "results"  # 2026-08-26 檔案搬到 scripts/tools/, 往上三層才是 repo 根目錄; 先 resolve() 避免相對路徑呼叫時算錯
reps = []
for i in range(10):
    d = np.load(RESULTS / f"fit_real_p2final_v3_rep{i}.npz")
    c = d["C"]
    assert c.shape == (1, 7), f"rep{i} 形狀異常: {c.shape}"
    reps.append(c[0])

C = np.array(reps)
assert C.shape == (10, 7)
out_path = RESULTS / "fit_real_p2final_v3.npz"
np.savez(out_path, C=C)

alpha = C[:, 3]
print(f"headline p2_final2_v3：10 次重複 alpha 平均 {alpha.mean():.3f}"
      f"、散布(population std) {alpha.std():.3f}")
print("逐次:", "  ".join(f"{v:.3f}" for v in alpha))
print("已存成", out_path)
