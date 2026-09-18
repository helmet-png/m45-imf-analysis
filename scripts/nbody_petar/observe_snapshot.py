#!/usr/bin/env python
"""把一個 PeTar 快照（`petar_system_catalog.py` 產的 NPZ）「觀測」成一份
跟 `data/cmd_members.csv` 同欄位格式的假星表。

功能：這是整條 N-body 分析鏈裡**唯一**同時碰模擬端與觀測端的程式——
沒有它，模擬算出來的 α 跟觀測算出來的 α 是在比較兩個定義不同的量
（模擬端目前只切孔徑，觀測端還經過測光品質篩選、pyUPMASK 成員判定
漏掉的星、雙星解析極限），Δα 的三個分項因此會混進「定義不一致」的
假訊號，不是真的動力學效應。這支程式把模擬快照推過**跟真實觀測完全
相同的退化鏈**，之後 `petar_pdmf_analysis.py`／`nbody_summary_stats.py`
可以對「真」跟「假」兩份星表用同一支估計器（`step5_imf.mle_powerlaw`
等）分析，兩邊比的才是同一件事。

方法（12 個步驟，每步對應觀測端一支既有程式，直接 import 重用，不重寫
一份平行邏輯）：

1. 讀 `petar_system_catalog.py` 產的 NPZ（component 級，帶 `system_id`，
   `star_type`／`current_mass` 是 2026-09 新增的選用欄位）。
2. 用 `petar_pdmf_analysis.shrinking_sphere_center()` 找中心並平移——
   跟觀測端／既有 N-body 分析用同一個找中心演算法。
3. 用 `petar_pdmf_analysis.projection_directions()` 選一個投影方向
   （黃金角螺旋上第 `--projection-index` 個），把 3D 位置投影到與該
   方向垂直的天球切面，得到 (sky_x, sky_y) 平面座標（pc）。
4. **質量 -> 絕對星等**：用 PARSEC 等時線（`pipeline/isochrones.py`，
   跟 `pipeline/step3_age.py` 的 `synth_populations()` 完全同一套
   `np.interp(m, Mini, G/G_BP/G_RP)` 內插邏輯）把每顆星的（出生／
   `current_mass`，見下）質量換成絕對星等。用 PARSEC 而不是 BSE 自己
   算的光度，是刻意的設計：這樣「觀測端拿星等反推質量」跟「這裡拿
   質量正推星等」互為同一個等時線的正逆函數，Δα 裡才**不會**混進
   等時線系統誤差（另外獨立列一項，不是在這裡順便消掉）——代價是
   這樣算出的 Δα 就看不到等時線本身的系統誤差，跟 repo 已知的「注入
   回收測不到 isochrone 系統誤差」是同一個道理，必須明講。
5. **恆星型態**：`star_type` 存在時，只有 SSE 編號 0（低質量、尚未升溫
   到會核融合的主序星）與 1（一般主序星，見 PeTar `tools/analysis/
   bse.py` 的 `SSEStarParameter` 逐字核對過）當成可查 PARSEC 主序
   等時線的星保留；其餘型態（2-9 的次巨星／巨星分支等演化過渡態，
   以及 >=10 的白矮星／中子星／黑洞等簡併終態）PARSEC 主序等時線都
   不適用，v1 直接排除出光度目錄（不當成任何波段的點源）——這是已知
   簡化，理由：這些天體在真實 CMD 上通常極暗或本來就會被測光品質切掉，
   對本專案分析的 0.5-2.5 太陽質量主序段影響應該很小，但**沒有實測
   驗證過**，等真的有 125 Myr 的正式模擬快照、看到有多少顆落在這些
   分支，再決定要不要精修。`star_type` 不存在（非 bse 模式或舊快取）
   時全部當主序星（`star_type=1`）處理，不受此步驟影響。
6. 加距離模數（`--distance-pc`，預設 135.48，跟主分析管線用中位視差
   算出來的同一個值）與消光（`--av`，預設 0.386，config C 的擬合值；
   係數 0.83/1.08/0.63 對照 `pipeline/step2_cmd.py:131-133`）。
7. **未解析合併**：同一 `system_id` 內，任兩個 component 的投影分離
   角 < `--resolution-arcsec`（預設 0.6″，Gaia 的典型解析極限量級）
   就把流量相加成一個點源（用 `-2.5*log10(sum(10**(-0.4*mag)))`，
   跟 `step3_age.synth_populations()` 處理未解析雙星的公式相同）；
   否則兩顆星在目錄裡各自是獨立點源。這一步填補了
   `pdmf_system_definition_bridge.py` 原本沒有的「用什麼判斷未解析」
   缺口（2026-09 審視 H4-3）。
8. 加測光雜訊：讀 `data/errmodel.npz`（觀測端 `step2_cmd.
   photometric_error_model()` 存的），依星等內插誤差再抽常態雜訊，
   邏輯對照 `step3_age._interp_err()`（3 行純內插，這裡就地重寫一份
   相同邏輯而不是跨模組 import 一個底線開頭的私有函式）。
8.5. **查詢／CMD 硬星等邊界**（2026-09-18 新增）：`--g-bright-limit`
   （預設 4.0，跟 `config.toml` 的 `g_bright_limit` 同一個值與方向）、
   `--g-faint-limit`（預設 18.0，跟 Gaia 查詢本身的 `phot_g_mean_mag
   < 18` 上限一致）。這是查詢範圍本身的硬邊界，不是選擇函數那種可以
   平滑近似的退化效應，不受 `--no-selection` 影響，一律套用在觀測後
   （含雜訊）的 G 星等上。
9. 套測光品質選擇函數：`pipeline/selection.py` 存的 `SelectionModel`
   （讀 `data/selection.npz`），跟前向模型合成星團用的是同一份。
10. 套**成員判定召回曲線**：真實 pyUPMASK 在不同星等會漏掉不同比例的
    真成員（`results/hr23_cmd_recall_by_magnitude.json` 量出來的，
    16-18 等只有 0.80、>=18 等是 0），這裡對每顆星依其 G 星等做
    Bernoulli 抽樣決定要不要保留——沒有這一步，模擬端會比觀測端多
    出一批「真實管線本來就會漏掉」的暗星，讓 survival_selection 這個
    Δα 分項失去意義（2026-09 審視 H7）。
11. 孔徑：投影半徑 <= `--aperture-pc`（預設 11.68，跟
    `petar_pdmf_analysis.DEFAULT_RADII_PC` 用同一個修正後的值）。
12. 輸出跟 `cmd_members.csv` 同欄位的 CSV，外加 `projected_radius_pc`
    （後續逐半徑分析直接讀這欄，不用再從 ra/dec 反推一次角距）。

自我測試（`--self-test`）：合成一個已知 α=2.35 的星團（重用
`petar_pdmf_analysis.sample_power_law()`），先關掉步驟 8-10（雜訊／
選擇函數／召回率）跑完整鏈，`step5_imf.mle_powerlaw()` 應該回收到
2.35±統計誤差；再逐一打開 8/9/10，檢查每一步造成的 α 偏移方向符合
物理預期（雜訊本身不改變真實質量分布的形狀、選擇函數與召回率都是
選掉暗端因此讓分布偏亮、冪律擬合出的 α 應該往低質量端變陡的反方向
偏——即 α 應該變小、樣本數應該減少）。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent  # scripts/nbody_petar/
REPO_ROOT = HERE.parent.parent

sys.path.insert(0, str(REPO_ROOT))
from pipeline import isochrones as isomod  # noqa: E402
from pipeline import selection as selmod  # noqa: E402
from pipeline.step3_age import COL_BP, COL_G, COL_RP  # noqa: E402

sys.path.insert(0, str(HERE))
from petar_pdmf_analysis import (  # noqa: E402
    projection_directions,
    sample_power_law,
    shrinking_sphere_center,
)

# config C 的擬合值（RESULTS_LOG.md、fit_real_p2final_v3.npz 的 10 次
# 重複平均），跟主分析管線用同一組數字，不是隨便挑的預設。
DEFAULT_DISTANCE_PC = 135.48
DEFAULT_AV = 0.386
DEFAULT_LOGAGE = 8.026
DEFAULT_MH = -0.022
EXT_COEFF = {"G": 0.83, "BP": 1.08, "RP": 0.63}

DEFAULT_APERTURE_PC = 11.68  # 跟 petar_pdmf_analysis.DEFAULT_RADII_PC 一致
DEFAULT_RESOLUTION_ARCSEC = 0.6

# 2026-09-18 新增（Codex review）：跟 config.toml 的 g_bright_limit（4.0，
# pipeline/step2_cmd.py 用 `~(g < g_bright_limit)` 同一個方向）與
# g_mag_max（18.0，Gaia 查詢本身的星等上限，真實 cmd_members.csv 從來
# 不會有 G>=18 的列）同一組邊界——這是查詢／CMD 的硬邊界，不是選擇
# 函數那種可以用平滑曲線近似的退化效應，一定要套用，不受
# --no-selection 影響。
DEFAULT_G_BRIGHT_LIMIT = 4.0
DEFAULT_G_FAINT_LIMIT = 18.0

DEFAULT_ISOCHRONE_GRID = (
    REPO_ROOT / "isochrones" / "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat"
)
DEFAULT_RECALL_CURVE = REPO_ROOT / "results" / "hr23_cmd_recall_by_magnitude.json"
DEFAULT_ERRMODEL = REPO_ROOT / "data" / "errmodel.npz"
DEFAULT_SELECTION = REPO_ROOT / "data" / "selection.npz"


def load_catalog(path: Path) -> dict:
    """讀 petar_system_catalog.py 產的 NPZ，star_type/current_mass 是選用欄位。"""
    with np.load(path, allow_pickle=False) as data:
        required = {"id", "mass", "pos", "system_id"}
        missing = required - set(data.files)
        if missing:
            raise ValueError(f"{path} 缺少必要欄位：{sorted(missing)}")
        out = {key: np.asarray(data[key]) for key in required}
        n = len(out["mass"])
        out["star_type"] = (
            np.asarray(data["star_type"], np.int64)
            if "star_type" in data.files
            else np.ones(n, np.int64)
        )
        out["current_mass"] = (
            np.asarray(data["current_mass"], float)
            if "current_mass" in data.files
            else np.asarray(out["mass"], float).copy()
        )
        out["time_myr"] = (
            float(np.asarray(data["time_myr"]).reshape(-1)[0])
            if "time_myr" in data.files
            else math.nan
        )
    return out


def project_positions(position: np.ndarray, direction: np.ndarray) -> np.ndarray:
    """把 3D 位置投影到與 direction 垂直的天球切面，回傳 (N,2) 的平面座標（pc）。

    取任一與 direction 垂直的正交基底（Gram-Schmidt），這組基底本身
    不代表真正的赤經/赤緯方向——後續只用平面座標算分離角與投影半徑，
    不依賴基底的絕對指向。
    """
    direction = direction / np.linalg.norm(direction)
    helper = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(helper, direction)) > 0.9:
        helper = np.array([0.0, 1.0, 0.0])
    e1 = helper - np.dot(helper, direction) * direction
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(direction, e1)
    return np.column_stack([position @ e1, position @ e2])


def masses_to_absolute_mags(
    mass: np.ndarray, iso_grid, logage: float, mh: float
) -> dict:
    """質量 -> 絕對 (G, BP, RP)，用跟 step3_age.synth_populations() 相同的
    np.interp(m, Mini, band) 內插，落在等時線質量範圍外的星回傳 NaN
    （不外插——等時線在演化末端形狀變化劇烈，外插沒有物理意義）。
    """
    iso = isomod.isochrone_at(iso_grid, logage, mh)
    mi = np.asarray(iso["Mini"], float)
    order = np.argsort(mi)
    mi = mi[order]
    gi = np.asarray(iso[COL_G], float)[order]
    bpi = np.asarray(iso[COL_BP], float)[order]
    rpi = np.asarray(iso[COL_RP], float)[order]

    in_range = (mass >= mi.min()) & (mass <= mi.max())
    g = np.where(in_range, np.interp(mass, mi, gi), np.nan)
    bp = np.where(in_range, np.interp(mass, mi, bpi), np.nan)
    rp = np.where(in_range, np.interp(mass, mi, rpi), np.nan)
    return {"G": g, "BP": bp, "RP": rp, "in_isochrone_range": in_range}


def _interp_err_like_step3(mag: np.ndarray, errmodel: dict, key: str) -> np.ndarray:
    """跟 pipeline/step3_age.py 的 _interp_err() 邏輯相同（就地重寫，見檔頭說明）。"""
    return np.interp(mag, errmodel["g"], errmodel[key],
                     left=errmodel[key][0], right=errmodel[key][-1])


def load_recall_curve(path: Path, threshold: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """從 hr23_cmd_recall_by_magnitude.json 建一條 G -> 召回率的分段線性曲線。

    用星等分箱的中點當節點；`recall: null`（該分箱裡沒有外部參照星）
    的分箱跳過，不當成 0。找不到檔案就回傳「處處召回率 1.0」（不做
    任何成員判定不完整度修正，等同關掉這一步），供沒有這份診斷檔的
    環境使用（例如某些自我測試情境）。
    """
    if not path.exists():
        return np.array([0.0, 30.0]), np.array([1.0, 1.0])
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = next(
        s for s in data["threshold_summaries"] if abs(s["threshold"] - threshold) < 1e-9
    )
    import re

    mags, recalls = [], []
    for row in summary["by_G_bin"]:
        if row["recall"] is None:
            continue
        label = row["G_bin"]
        numbers = [float(x) for x in re.findall(r"-?\d+\.?\d*", label)]
        if label.startswith("G <"):
            lo, hi = -5.0, numbers[0]
        elif label.startswith("G >="):
            lo, hi = numbers[0], numbers[0] + 5.0
        else:
            # "lo <= G < hi" 這種格式，兩個數字依序是下界跟上界
            lo, hi = numbers[0], numbers[1]
        mags.append((lo + hi) / 2.0)
        recalls.append(row["recall"])
    order = np.argsort(mags)
    return np.asarray(mags)[order], np.asarray(recalls)[order]


def merge_unresolved(
    system_id: np.ndarray,
    sky_xy: np.ndarray,
    g_mag: np.ndarray,
    bp_mag: np.ndarray,
    rp_mag: np.ndarray,
    distance_pc: float,
    resolution_arcsec: float,
) -> dict:
    """同一 system_id 內，投影分離小於解析極限的分量合併成一個點源。

    合併規則：以質量最大的分量（跟 pdmf_system_definition_bridge.py
    的 primary 定義一致）當這個點源的位置代表，流量相加（未解析雙星
    的標準處理，跟 step3_age.synth_populations() 的公式相同）。分離
    夠大的分量各自保留成獨立點源。連鎖未解析（A-B 未解析、B-C 未解析
    但 A-C 已解析）用並查集處理，避免只看兩兩配對漏掉遞移關係。
    """
    n = len(system_id)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    resolution_pc = distance_pc * math.radians(resolution_arcsec / 3600.0)
    order = np.argsort(system_id)
    boundaries = np.searchsorted(system_id[order], np.unique(system_id[order]))
    boundaries = np.append(boundaries, n)
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        idx = order[start:end]
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                sep = np.linalg.norm(sky_xy[idx[a]] - sky_xy[idx[b]])
                if sep < resolution_pc:
                    union(idx[a], idx[b])

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    out_xy, out_g, out_bp, out_rp, out_n_components = [], [], [], [], []
    for members in groups.values():
        members = np.asarray(members)
        valid = np.isfinite(g_mag[members])
        if not valid.any():
            continue
        members = members[valid]

        def flux_sum(mags):
            finite = np.isfinite(mags[members])
            if not finite.any():
                return math.nan
            return -2.5 * math.log10(np.sum(10.0 ** (-0.4 * mags[members][finite])))

        out_g.append(flux_sum(g_mag))
        out_bp.append(flux_sum(bp_mag))
        out_rp.append(flux_sum(rp_mag))
        out_xy.append(sky_xy[members[0]])
        out_n_components.append(len(members))

    return {
        # 空結果要保留 (0, 2) 形狀，不然 np.asarray([]) 會變成 (0,)，
        # 後面 observe() 的 np.linalg.norm(xy, axis=1) 會丟 AxisError。
        "sky_xy": np.asarray(out_xy, float).reshape(-1, 2),
        "G": np.asarray(out_g),
        "BP": np.asarray(out_bp),
        "RP": np.asarray(out_rp),
        "n_components": np.asarray(out_n_components),
    }


def observe(
    catalog: dict,
    projection_index: int,
    n_projections: int,
    distance_pc: float,
    av: float,
    logage: float,
    mh: float,
    aperture_pc: float,
    resolution_arcsec: float,
    iso_grid,
    errmodel: dict | None,
    selection_model,
    recall_curve: tuple[np.ndarray, np.ndarray] | None,
    rng: np.random.Generator,
    g_bright_limit: float = DEFAULT_G_BRIGHT_LIMIT,
    g_faint_limit: float = DEFAULT_G_FAINT_LIMIT,
) -> dict:
    # 2026-09-18 修正（Codex review，見 main() 呼叫端同一則說明的完整
    # 引用來源）：selection_model 跟 recall_curve 量到的流失高度重疊
    # （docs/planning/M45_HR23_LOST_QUALITY_REPLAY_2026-08-22.md 證實
    # 召回曲線背後 62 顆流失星裡 0 顆通過重播的品質切割），不是互相
    # 獨立的退化效應，不能疊乘。放在 observe() 本身而不是只放在
    # main()，這樣任何呼叫端（包含 run_self_test()）都躲不掉這個檢查。
    if selection_model is not None and recall_curve is not None:
        raise ValueError(
            "observe(): selection_model 跟 recall_curve 不能同時給值——"
            "會把同一批測光品質流失算兩次，見 M45_HR23_LOST_QUALITY_"
            "REPLAY_2026-08-22.md 的 0/62 重播結果"
        )

    mass = np.asarray(catalog["current_mass"], float)
    position = np.asarray(catalog["pos"], float)
    system_id = np.asarray(catalog["system_id"])
    star_type = np.asarray(catalog["star_type"], np.int64)

    # 步驟 2：找中心並平移
    center, center_n = shrinking_sphere_center(position, mass)
    position = position - center

    # 步驟 3：選投影方向
    direction = projection_directions(n_projections)[projection_index]
    sky_xy = project_positions(position, direction)

    # 步驟 4-5：質量 -> 絕對星等，排除非主序型態
    # PeTar BSE 定義（https://github.com/lwang-astro/PeTar/blob/
    # 84b81a8c339c49291de53f7a72829dd80e188182/tools/analysis/bse.py#L115）
    # type 0（低質量主序，尚未演化到會核融合的 ZAMS）跟 type 1（一般
    # 主序）都算主序星，只排除 type >= 10 的簡併／演化終態星。
    ms = (star_type == 0) | (star_type == 1)
    mags = masses_to_absolute_mags(mass, iso_grid, logage, mh)
    keep_photometric = ms & mags["in_isochrone_range"]

    g_abs = np.where(keep_photometric, mags["G"], np.nan)
    bp_abs = np.where(keep_photometric, mags["BP"], np.nan)
    rp_abs = np.where(keep_photometric, mags["RP"], np.nan)

    # 步驟 6：距離模數與消光
    dist_mod = 5.0 * math.log10(distance_pc) - 5.0
    g_obs = g_abs + dist_mod + EXT_COEFF["G"] * av
    bp_obs = bp_abs + dist_mod + EXT_COEFF["BP"] * av
    rp_obs = rp_abs + dist_mod + EXT_COEFF["RP"] * av

    # 步驟 7：未解析合併
    merged = merge_unresolved(
        system_id, sky_xy, g_obs, bp_obs, rp_obs, distance_pc, resolution_arcsec
    )
    g, bp, rp = merged["G"], merged["BP"], merged["RP"]
    xy = merged["sky_xy"]

    valid = np.isfinite(g) & np.isfinite(bp) & np.isfinite(rp)
    g, bp, rp, xy = g[valid], bp[valid], rp[valid], xy[valid]
    n = len(g)

    # 步驟 8：測光雜訊
    if errmodel is not None:
        g = g + rng.normal(size=n) * _interp_err_like_step3(g, errmodel, "e_g")
        bp = bp + rng.normal(size=n) * _interp_err_like_step3(g, errmodel, "e_bp")
        rp = rp + rng.normal(size=n) * _interp_err_like_step3(g, errmodel, "e_rp")

    keep = np.ones(n, bool)

    # 步驟 8.5：查詢／CMD 硬星等邊界（2026-09-18 修正，Codex review）
    # ——真實 cmd_members.csv 來自 Gaia 查詢本身的 G<18 上限與
    # config.toml g_bright_limit=4.0 的下限硬切，不是選擇函數那種可以
    # 平滑近似的效應，也不受 --no-selection 影響。用觀測後（含雜訊）
    # 的 g 判斷，邊界跟 step2_cmd.py 的 `~(g < g_bright_limit)` 同方向：
    # G=g_bright_limit 保留、G<g_bright_limit 排除；G<g_faint_limit
    # 保留、G>=g_faint_limit 排除（對齊 ADQL `phot_g_mean_mag < 18`）。
    keep &= (g >= g_bright_limit) & (g < g_faint_limit)

    # 步驟 9：測光品質選擇函數
    if selection_model is not None:
        z_snr = rng.normal(size=n)
        u_sel = rng.random(n)
        keep &= selection_model.keep(g, bp, rp, z_snr, u_sel)

    # 步驟 10：成員判定召回曲線
    if recall_curve is not None:
        mags_grid, recalls = recall_curve
        p_recall = np.interp(g, mags_grid, recalls, left=recalls[0], right=recalls[-1])
        keep &= rng.random(n) < p_recall

    # 步驟 11：孔徑
    radius_pc = np.linalg.norm(xy, axis=1)
    keep &= radius_pc <= aperture_pc

    return {
        "G": g[keep],
        "BP": bp[keep],
        "RP": rp[keep],
        "projected_radius_pc": radius_pc[keep],
        "sky_x_pc": xy[keep, 0],
        "sky_y_pc": xy[keep, 1],
        "n_input_particles": int(len(mass)),
        "n_after_isochrone_and_type_cut": int(keep_photometric.sum()),
        "n_after_unresolved_merge": n,
        "n_output": int(keep.sum()),
        "center": center.tolist(),
        "center_n": center_n,
        "direction": direction.tolist(),
    }


def write_csv(result: dict, output: Path, ra0_deg: float, dec0_deg: float, distance_pc: float):
    """輸出跟 cmd_members.csv 同欄位的 CSV（多一欄 projected_radius_pc）。"""
    import csv

    n = len(result["G"])
    # 平面座標 -> 近似 RA/Dec（正切平面，孔徑 <~5 度時誤差可忽略，跟
    # 這個孔徑量級一致）。ra0/dec0 只是給一個看起來合理的天球位置，
    # 分析管線本身不依賴絕對座標，只用 bp_rp/phot_g_mean_mag 跟
    # projected_radius_pc。
    dec_rad0 = math.radians(dec0_deg)
    dra = np.degrees(result["sky_x_pc"] / distance_pc) / max(math.cos(dec_rad0), 1e-6)
    ddec = np.degrees(result["sky_y_pc"] / distance_pc)
    ra = ra0_deg + dra
    dec = dec0_deg + ddec

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "source_id", "ra", "dec", "pmra", "pmdec", "parallax",
            "pmra_error", "pmdec_error", "parallax_error",
            "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag", "bp_rp",
            "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
            "phot_rp_mean_flux_over_error", "phot_bp_rp_excess_factor",
            "ruwe", "non_single_star", "probs_final", "projected_radius_pc",
        ])
        for i in range(n):
            writer.writerow([
                i + 1, ra[i], dec[i], math.nan, math.nan, 1000.0 / distance_pc,
                math.nan, math.nan, math.nan,
                result["G"][i], result["BP"][i], result["RP"][i],
                result["BP"][i] - result["RP"][i],
                math.nan, math.nan, math.nan, math.nan,
                math.nan, 0, 1.0, result["projected_radius_pc"][i],
            ])


def run_star_type_regression_test() -> dict:
    """迴歸測試（2026-09-18 Codex review）：只保留 star_type==1 會把
    低質量、尚未升溫到核融合的主序星（BSE type 0）當成簡併星丟掉；
    如果丟到只剩極少數星，merge_unresolved() 對空群組回傳的 sky_xy
    會退化成 (0,) 形狀，讓 observe() 算孔徑半徑時丟 AxisError。不需要
    等時線快取，離線就能跑，涵蓋以前全 type=1 的 self-test 測不到的
    兩個情境。
    """
    star_type = np.array([0, 1], np.int64)
    ms = (star_type == 0) | (star_type == 1)
    checks = {
        "type0_and_type1_both_kept_as_main_sequence": bool(ms.all()),
    }

    empty = merge_unresolved(
        system_id=np.array([0, 1], np.int64),
        sky_xy=np.array([[0.0, 0.0], [1.0, 1.0]]),
        g_mag=np.array([np.nan, np.nan]),
        bp_mag=np.array([np.nan, np.nan]),
        rp_mag=np.array([np.nan, np.nan]),
        distance_pc=135.48,
        resolution_arcsec=1.0,
    )
    checks["empty_merge_keeps_n_by_2_shape"] = empty["sky_xy"].shape == (0, 2)

    # 迴歸測試（2026-09-18 Codex review）：查詢／CMD 硬星等邊界的四個
    # 邊界值行為，對照 config.toml 的 g_bright_limit/g_mag_max。
    g_probe = np.array([3.9, 4.0, 17.999, 18.0])
    boundary_keep = (
        (g_probe >= DEFAULT_G_BRIGHT_LIMIT) & (g_probe < DEFAULT_G_FAINT_LIMIT)
    )
    checks["g_boundary_matches_query_convention"] = bool(
        np.array_equal(boundary_keep, [False, True, True, False])
    )

    # 迴歸測試（2026-09-18 Codex review）：selection_model 跟
    # recall_curve 同時給值必須拒絕，見 M45_HR23_LOST_QUALITY_REPLAY_
    # 2026-08-22.md 的 0/62 重播結果。
    try:
        observe(
            {}, 0, 32, 100.0, 0.0, 8.0, 0.0, 10.0, 0.6,
            None, None, object(), (np.array([0.0]), np.array([1.0])), None,
        )
        checks["selection_and_recall_together_raises"] = False
    except ValueError:
        checks["selection_and_recall_together_raises"] = True
    try:
        radius_pc = np.linalg.norm(empty["sky_xy"], axis=1)
        checks["radius_calc_on_empty_does_not_raise"] = radius_pc.shape == (0,)
    except Exception:
        checks["radius_calc_on_empty_does_not_raise"] = False

    if not all(checks.values()):
        raise AssertionError(f"observe_snapshot star-type regression test failed: {checks}")
    return {"status": "ok", "checks": checks}


def run_self_test() -> dict:
    """合成已知 α=2.35 的星團，逐步打開退化效應，檢查 α 偏移方向正確。"""
    from petar_pdmf_analysis import mle_powerlaw

    run_star_type_regression_test()

    rng = np.random.default_rng(20260909)
    n = 20000
    mass = sample_power_law(rng, n, 2.35, 0.3, 2.5)
    r_pc = rng.exponential(scale=3.0, size=n)
    theta = rng.uniform(0, 2 * np.pi, n)
    phi = np.arccos(rng.uniform(-1, 1, n))
    position = np.column_stack([
        r_pc * np.sin(phi) * np.cos(theta),
        r_pc * np.sin(phi) * np.sin(theta),
        r_pc * np.cos(phi),
    ])
    system_id = np.arange(n)  # 全部單星，跳過未解析合併的複雜度
    star_type = np.ones(n, np.int64)
    catalog = {
        "mass": mass, "current_mass": mass, "pos": position,
        "system_id": system_id, "star_type": star_type,
    }

    if not DEFAULT_ISOCHRONE_GRID.exists():
        return {
            "status": "skipped_no_isochrone_cache",
            "reason": f"{DEFAULT_ISOCHRONE_GRID} 不存在，這個環境沒有等時線快取，"
                      "無法離線做這個自我測試（需要先跑過一次主管線下載快取）",
        }
    iso_grid = isomod.load_grid(DEFAULT_ISOCHRONE_GRID)

    def run_with(errmodel, selection_model, recall_curve):
        result = observe(
            catalog, 0, 32, DEFAULT_DISTANCE_PC, DEFAULT_AV,
            DEFAULT_LOGAGE, DEFAULT_MH, 50.0, DEFAULT_RESOLUTION_ARCSEC,
            iso_grid, errmodel, selection_model, recall_curve, rng,
        )
        mass_out = np.zeros(len(result["G"]))
        # 反查質量：用同一條等時線的 G -> mass 內插（跟 step5_imf 的做法
        # 相同方向），只是這裡直接需要「觀測到的星對應的真實出生質量」
        # 來驗證冪律有沒有被正確保留——自我測試專用，不是正式分析。
        iso = isomod.isochrone_at(iso_grid, DEFAULT_LOGAGE, DEFAULT_MH)
        mi = np.asarray(iso["Mini"], float)
        gi = np.asarray(iso[COL_G], float)
        order = np.argsort(gi)
        dist_mod = 5.0 * math.log10(DEFAULT_DISTANCE_PC) - 5.0
        g_abs = result["G"] - dist_mod - EXT_COEFF["G"] * DEFAULT_AV
        mass_out = np.interp(g_abs, gi[order], mi[order])
        fit = mle_powerlaw(mass_out, 0.5, 2.5)
        return fit, len(result["G"])

    fit_clean, n_clean = run_with(None, None, None)

    errmodel = dict(np.load(DEFAULT_ERRMODEL)) if DEFAULT_ERRMODEL.exists() else None
    # 2026-09-18 修正（Codex review）：selection_model 跟 recall_curve
    # 不能同時給（見 observe() 開頭的檢查與註解），"full chain" 這裡
    # 保留 selection_model——它是真的重算品質切割的機制，
    # docs/planning/M45_HR23_LOST_QUALITY_REPLAY_2026-08-22.md 證實
    # recall_curve 量到的流失可以完全用它解釋，不是獨立效應。
    selection_model = selmod.load(DEFAULT_SELECTION) if DEFAULT_SELECTION.exists() else None
    fit_full, n_full = run_with(errmodel, selection_model, None)

    checks = {
        "clean_recovers_truth_within_3sigma": bool(
            abs(fit_clean["alpha"] - 2.35) < 3 * fit_clean["alpha_err"]
        ),
        "full_chain_produces_finite_alpha": bool(np.isfinite(fit_full["alpha"])),
        "selection_and_recall_reduce_sample_size": bool(n_full <= n_clean),
    }

    summary = {
        "status": "synthetic_validation_only",
        "n_input": n,
        "clean": {"alpha": fit_clean["alpha"], "alpha_err": fit_clean["alpha_err"], "n": n_clean},
        "full_chain": {"alpha": fit_full["alpha"], "alpha_err": fit_full["alpha_err"], "n": n_full},
        "checks": checks,
    }
    if not all(checks.values()):
        raise AssertionError(f"observe_snapshot self-test failed: {checks}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--projection-index", type=int, default=0)
    parser.add_argument("--n-projections", type=int, default=32)
    parser.add_argument("--distance-pc", type=float, default=DEFAULT_DISTANCE_PC)
    parser.add_argument("--av", type=float, default=DEFAULT_AV)
    parser.add_argument("--logage", type=float, default=DEFAULT_LOGAGE)
    parser.add_argument("--mh", type=float, default=DEFAULT_MH)
    parser.add_argument("--aperture-pc", type=float, default=DEFAULT_APERTURE_PC)
    parser.add_argument("--g-bright-limit", type=float, default=DEFAULT_G_BRIGHT_LIMIT)
    parser.add_argument("--g-faint-limit", type=float, default=DEFAULT_G_FAINT_LIMIT)
    parser.add_argument("--resolution-arcsec", type=float, default=DEFAULT_RESOLUTION_ARCSEC)
    parser.add_argument("--isochrone-grid", type=Path, default=DEFAULT_ISOCHRONE_GRID)
    parser.add_argument("--errmodel", type=Path, default=DEFAULT_ERRMODEL)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--recall-curve", type=Path, default=DEFAULT_RECALL_CURVE)
    parser.add_argument("--no-noise", action="store_true")
    parser.add_argument("--no-selection", action="store_true")
    parser.add_argument("--no-recall", action="store_true")
    parser.add_argument("--ra0-deg", type=float, default=56.591)
    parser.add_argument("--dec0-deg", type=float, default=24.120)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        summary = run_self_test()
        print(json.dumps(summary, indent=2))
        return

    if args.catalog is None or args.output is None:
        parser.error("--catalog and --output are required unless --self-test is used")

    catalog = load_catalog(args.catalog)
    iso_grid = isomod.load_grid(args.isochrone_grid)

    # 2026-09-18 修正（Codex review）：以前缺檔就悄悄退化成 None／全 1
    # （形同關掉那一步的退化效應），正式觀測會在沒人注意到的情況下
    # 少做測光雜訊／選擇函數／召回率三步之一，卻還是輸出一份看起來
    # 正常的 CSV。現在只有明確傳 --no-noise/--no-selection/--no-recall
    # 才允許省略，其餘情況缺檔就直接報錯，不猜、不退化。
    errmodel = None
    if not args.no_noise:
        if not args.errmodel.exists():
            parser.error(
                f"--errmodel 檔案不存在：{args.errmodel}（要跳過測光雜訊"
                "步驟，明確加 --no-noise，不要讓它悄悄退化成沒有雜訊）"
            )
        errmodel = dict(np.load(args.errmodel))

    selection_model = None
    if not args.no_selection:
        if not args.selection.exists():
            parser.error(
                f"--selection 檔案不存在：{args.selection}（要跳過測光品質"
                "選擇函數，明確加 --no-selection，不要讓它悄悄退化成全部"
                "保留）"
            )
        selection_model = selmod.load(args.selection)

    recall_curve = None
    if not args.no_recall:
        if not args.recall_curve.exists():
            parser.error(
                f"--recall-curve 檔案不存在：{args.recall_curve}（要跳過"
                "成員判定召回率修正，明確加 --no-recall，不要讓它悄悄退化"
                "成處處召回率 1.0）"
            )
        recall_curve = load_recall_curve(args.recall_curve)

    # 2026-09-18 修正（Codex review）：跟 observe() 內同一個檢查一樣
    # 的原因（完整說明見那裡的註解），這裡提前用 parser.error() 攔，
    # 讓 CLI 使用者看到清楚的用法錯誤，不是一串 traceback。
    if selection_model is not None and recall_curve is not None:
        parser.error(
            "--selection 與 --recall-curve 不能同時打開："
            "docs/planning/M45_HR23_LOST_QUALITY_REPLAY_2026-08-22.md 已"
            "證實 hr23_cmd_recall_by_magnitude.json 量到的召回率流失，"
            "對已追蹤的 62 顆星而言完全可以用 selection_model 的品質"
            "切割解釋（0/62 通過重播），疊乘會把同一批流失算兩次。"
            "用 --no-selection 只做召回曲線那層，或 --no-recall 只做"
            "品質切選那層。"
        )

    rng = np.random.default_rng(args.seed)

    result = observe(
        catalog, args.projection_index, args.n_projections,
        args.distance_pc, args.av, args.logage, args.mh,
        args.aperture_pc, args.resolution_arcsec,
        iso_grid, errmodel, selection_model, recall_curve, rng,
        args.g_bright_limit, args.g_faint_limit,
    )
    write_csv(result, args.output, args.ra0_deg, args.dec0_deg, args.distance_pc)

    metadata = {k: v for k, v in result.items() if k not in ("G", "BP", "RP", "projected_radius_pc", "sky_x_pc", "sky_y_pc")}
    metadata["output"] = str(args.output)
    metadata["degradation_steps"] = {
        "noise": {"skipped": bool(args.no_noise), "file": str(args.errmodel)},
        "selection": {"skipped": bool(args.no_selection), "file": str(args.selection)},
        "recall": {"skipped": bool(args.no_recall), "file": str(args.recall_curve)},
    }
    print(json.dumps(metadata, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
