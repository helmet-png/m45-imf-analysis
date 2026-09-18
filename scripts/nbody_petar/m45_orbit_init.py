#!/usr/bin/env python
"""算 M45 在 N-body 模擬起始時刻（現在往前 t_myr）的銀河系座標。

功能：把 M45 現時觀測到的天球座標、視差、自行、視向速度，轉成
`petar.init -c x[pc],y,z,vx[km/s],vy,vz` 需要的六個數字——星團質心在
銀心直角坐標系裡的初始位置與速度。這是整條 N-body 鏈唯一需要處理「銀河
座標系」的地方，獨立成一支檔案是因為這裡有兩個容易犯錯、犯錯了也不會
立刻報錯的單位/慣例陷阱：

1. `petar.init -c` 吃的六個數字，位置是 pc、速度是 km/s（見 PeTar 官方
   `sample/star_cluster_bse_galpy.sh` 的註解：
   `-c x[pc],y,z,vx[km/s],vy,vz`），但 PeTar 內部（`--galpy-set` 生效
   之後）實際用的是 pc/Myr，不是 galpy 官方習慣的 8 kpc/220 km/s 單位
   （PeTar README「Unit conversion for Galpy」一節）。這裡只需要產生
   `-c` 要的那六個「輸入」數字，單位轉換交給 `petar.init` 自己做，
   不要在這支程式裡提前轉換，否則會轉兩次。
2. 銀心座標系的「太陽在哪裡、太陽怎麼動」這組假設，PeTar 自己的分析
   工具（`tools/analysis/data.py` 的 `toSkyCoord()`）明確採用
   `galcen_distance=8.0 kpc, z_sun=15 pc, galcen_v_sun=(10.0, 235.0,
   7.0) km/s`，不是 astropy `Galactocentric` frame 的預設值（本次直接
   讀 PeTar GitHub 原始碼確認，見該函式的 docstring 與預設 `parameters`
   dict）。用這裡算出的初始座標去模擬，後續用同一套工具讀回快照時
   若假設不一致，星團在銀河系裡的位置會對不起來——所以這支程式的
   `Galactocentric` 呼叫**必須**跟 PeTar 那三個參數逐字相同。

方法：
1. 用 `astropy.coordinates.SkyCoord` 把現時觀測量（RA/Dec/距離/自行/
   視向速度，ICRS 座標系）包成一個帶速度的座標物件。
2. `.transform_to(Galactocentric(galcen_distance=8.0*u.kpc,
   z_sun=15.*u.pc, galcen_v_sun=CartesianDifferential([10.0,235.,7.]
   *u.km/u.s)))`，得到現在時刻的銀心直角座標 (x,y,z,vx,vy,vz)——這一步
   本身不需要 galpy，是 astropy 座標系間的解析轉換。
3. 把這個現時銀心座標**直接**餵給 `galpy.orbit.Orbit()` 建構子（galpy
   支援吃一個 astropy `SkyCoord`，見 `galpy/orbit/Orbits.py` 的
   `__init__` docstring）——不手動換成柱座標、不手動指定 galpy 的
   `ro`/`zo`/`solarmotion`，讓 galpy 自己從 SkyCoord 帶的 frame 資訊
   解讀，避免自己重新指定一次 galpy 內部太陽運動慣例、跟步驟 2 的
   假設兜不起來的風險。
4. `orbit.integrate(ts, MWPotential2014)`，`ts` 從 0 積分到 −t_myr
   （galpy 用負時間表示往過去積分），取最後一個時間點的
   `.x()/.y()/.z()/.vx()/.vy()/.vz()`（`use_physical=True`，galpy 對
   SkyCoord 輸入預設回傳物理單位，見上面的原始碼引用）。
5. 輸出 JSON（含中間量與可信度聲明）＋一行可直接貼進
   `petar.init -c` 的字串。

執行環境：這支程式需要 `galpy`／`astropy`，本機（Windows ARM64）主環境
（Python 3.14）裝不進去——galpy 1.10.2 沒有 win_arm64 wheel，win_amd64
wheel 也只到 cp313。要另開一個獨立 venv，版本組合與走過的錯路記在
`nbody_setup/requirements_orbit_init.txt`（astropy 太新、numpy 太新都會
在載入或初始化階段直接炸掉，不是隨便哪個新版都能用）。真正跑 N-body
主鏈的 Linux 機器上 `setup_linux_nbody.sh` 會裝另一份 galpy venv，
跟這裡互不影響。

自我測試（`--self-test`）：
- **往返一致性**：往過去積分 t_myr、再往未來積分回 t_myr，回到 t=0 的
  座標跟原始值的相對誤差應 < 1e-5（實測：`method="odeint"`、1001 個
  取樣點，250 Myr 來回積分的殘留誤差約 1.3e-6，這是這組積分設定本身
  的數值精度地板，不是物理上「本來就該」有的誤差，但比 1e-6 稍寬，
  門檻定 1e-5 留一點安全邊際，不是隨便選的整數）。
- **t=0 量級檢查**：算出的**現在**銀心距離 |R(t=0)| 應落在 7.5-8.7 kpc
  （M45 在太陽鄰域，實測 ~8.12 kpc；離這個範圍太遠幾乎必定是單位搞錯，
  例如誤用 pc 當 kpc、或誤用 km/s 當 pc/Myr）；|z(t=0)| 應 < 100 pc
  （M45 銀緯不高）。**t=-t_myr 之後的 R 不能用同一個窄窗口檢查**——
  125 Myr 內星團會掃過銀河公轉軌道相當大一段角度（銀河公轉週期
  ~220-230 Myr），R 本身也會有正常的本輪（epicyclic）振盪，實測
  t=-125 Myr 時 R 降到 ~7.71 kpc，屬於預期範圍內的真實軌道動力學，
  不是 bug；t=-t_myr 只檢查沒有離譜到量級不對（6-10 kpc 這種寬鬆
  範圍），量級檢查的重點放在 t=0，因為那才是最直接反映單位有沒有
  搞錯的地方。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent.parent.parent  # scripts/nbody_petar/ 往上三層是 repo 根目錄

# PeTar 官方 tools/analysis/data.py 的 toSkyCoord() 用的太陽位置/運動
# 假設，逐字對照過的三個參數；改這裡要同時確認 PeTar 端有沒有跟著改。
GALCEN_DISTANCE_KPC = 8.0
Z_SUN_PC = 15.0
GALCEN_V_SUN_KMS = (10.0, 235.0, 7.0)

# M45 現時觀測量的預設值。除了 t_myr 之外都可以用旗標覆寫，但預設值
# 直接由 data/cmd_members.csv 現場算出（不是寫死的快照數字），確保跟
# 主分析管線用的是同一份資料算出來的中心/距離。
DEFAULT_RV_KMS = 5.343  # bulk_rv，config.toml 的 step1_membership.bulk_rv，取自 HR23
DEFAULT_T_MYR = 125.0  # 對齊 petar_m45_grid.py 的 -t 125.0（M45 公認年齡）


def _members_defaults(members_csv: Path) -> dict:
    """從 cmd_members.csv 現場算出 RA/Dec/距離/自行的樣本中位數當預設值。"""
    import pandas as pd

    d = pd.read_csv(members_csv)
    plx = np.asarray(d["parallax"], float)
    # 與 pipeline/config.toml 的 parallax_zero_point 一致（-0.017），
    # 跟 fit_real.py、petar_pdmf_analysis.py 算距離用同一個公式。
    zp = -0.017
    dist_pc = 1000.0 / (np.median(plx) - zp)
    return {
        "ra_deg": float(np.median(d["ra"])),
        "dec_deg": float(np.median(d["dec"])),
        "distance_pc": float(dist_pc),
        "pmra_masyr": float(np.median(d["pmra"])),
        "pmdec_masyr": float(np.median(d["pmdec"])),
    }


def backward_orbit(
    ra_deg: float,
    dec_deg: float,
    distance_pc: float,
    pmra_masyr: float,
    pmdec_masyr: float,
    rv_kms: float,
    t_myr: float,
):
    """從現時 ICRS 觀測量算出 t_myr 前的銀心直角座標 (x,y,z,vx,vy,vz)。

    回傳 dict，位置單位 pc、速度單位 km/s（`petar.init -c` 要的單位）。
    """
    import astropy.units as u
    from astropy.coordinates import (
        CartesianDifferential,
        Galactocentric,
        SkyCoord,
    )
    from galpy.orbit import Orbit
    from galpy.potential import MWPotential2014

    galcen_frame = Galactocentric(
        galcen_distance=GALCEN_DISTANCE_KPC * u.kpc,
        z_sun=Z_SUN_PC * u.pc,
        galcen_v_sun=CartesianDifferential(list(GALCEN_V_SUN_KMS) * u.km / u.s),
    )

    icrs = SkyCoord(
        ra=ra_deg * u.deg,
        dec=dec_deg * u.deg,
        distance=distance_pc * u.pc,
        pm_ra_cosdec=pmra_masyr * u.mas / u.yr,
        pm_dec=pmdec_masyr * u.mas / u.yr,
        radial_velocity=rv_kms * u.km / u.s,
        frame="icrs",
    )
    galcen_now = icrs.transform_to(galcen_frame)

    orbit = Orbit(galcen_now)
    # t=0（現在）的銀心距離，是最直接的單位/慣例檢查——如果這裡不在
    # 7.5-8.7 kpc（太陽鄰域的合理範圍），幾乎必定是單位搞錯（實測
    # M45 現時參數應得 ~8.12 kpc）。t=-t_myr 之後的值不能用同樣窄的
    # 窗口檢查，見下面的說明。
    r_now_kpc = float(orbit.R(quantity=True).to(u.kpc).value)
    # galpy 用負時間積分表示往過去走；步數與相對誤差容許值取
    # galpy 常見預設，1001 個取樣點在 125 Myr 尺度上遠比軌道週期
    # （銀河系公轉週期 ~230 Myr）密集。
    n_steps = 1001
    ts = np.linspace(0.0, -t_myr, n_steps) * u.Myr
    orbit.integrate(ts, MWPotential2014, method="odeint")

    # quantity=True 明確要求回傳帶單位的 Quantity，不依賴「SkyCoord
    # 輸入會自動打開物理輸出」這個隱含行為（實測發現：即使 Orbit 是用
    # SkyCoord 初始化，.x()/.y()/... 預設仍回傳去掉單位的 float，要
    # 明確傳 quantity=True 才拿得到 Quantity，不能只看 docstring 假設）。
    x_kpc = float(orbit.x(ts[-1], quantity=True).to(u.kpc).value)
    y_kpc = float(orbit.y(ts[-1], quantity=True).to(u.kpc).value)
    z_kpc = float(orbit.z(ts[-1], quantity=True).to(u.kpc).value)
    vx_kms = float(orbit.vx(ts[-1], quantity=True).to(u.km / u.s).value)
    vy_kms = float(orbit.vy(ts[-1], quantity=True).to(u.km / u.s).value)
    vz_kms = float(orbit.vz(ts[-1], quantity=True).to(u.km / u.s).value)

    return {
        "position_pc": [x_kpc * 1000.0, y_kpc * 1000.0, z_kpc * 1000.0],
        "velocity_kms": [vx_kms, vy_kms, vz_kms],
        "galactocentric_radius_kpc": math.hypot(x_kpc, y_kpc),
        "z_kpc": z_kpc,
        "galactocentric_radius_now_kpc": r_now_kpc,
    }


def petar_init_c_flag(position_pc: list[float], velocity_kms: list[float]) -> str:
    parts = [f"{v:.6f}" for v in position_pc] + [f"{v:.6f}" for v in velocity_kms]
    return "-c " + ",".join(parts)


def run_self_test() -> dict:
    """往返積分一致性 + 量級檢查，不需要真實觀測資料。"""
    import astropy.units as u
    from astropy.coordinates import CartesianDifferential, Galactocentric, SkyCoord
    from galpy.orbit import Orbit
    from galpy.potential import MWPotential2014

    # 用 M45 現時觀測量的合理量級（不依賴 data/cmd_members.csv 是否存在，
    # 讓這個自我測試在任何環境都能跑）。
    ra_deg, dec_deg = 56.75, 24.12
    distance_pc = 135.5
    pmra_masyr, pmdec_masyr = 19.95, -45.46
    rv_kms = DEFAULT_RV_KMS
    t_myr = DEFAULT_T_MYR

    forward = backward_orbit(
        ra_deg, dec_deg, distance_pc, pmra_masyr, pmdec_masyr, rv_kms, t_myr
    )

    # 量級檢查：t=0 用窄窗口（單位檢查），t=-t_myr 用寬窗口（真實軌道
    # 動力學會讓 R 偏離 t=0 的值，見檔頭 docstring 的說明）。
    r_now_kpc = forward["galactocentric_radius_now_kpc"]
    r_past_kpc = math.hypot(forward["position_pc"][0], forward["position_pc"][1]) / 1000.0
    z_pc = forward["z_kpc"] * 1000.0
    checks = {
        "galactocentric_radius_now_in_range": 7.5 <= r_now_kpc <= 8.7,
        "galactocentric_radius_past_plausible": 6.0 <= r_past_kpc <= 10.0,
        "z_offset_small": abs(z_pc) < 100.0,
    }

    # 往返一致性：從 t=-t_myr 的狀態出發，往未來積分 t_myr，應回到現在
    # 的銀心座標。直接重用 Orbit 物件，從積分過的終點狀態取值，
    # 用它當「新的初始條件」再積分回來一次。
    galcen_frame = Galactocentric(
        galcen_distance=GALCEN_DISTANCE_KPC * u.kpc,
        z_sun=Z_SUN_PC * u.pc,
        galcen_v_sun=CartesianDifferential(list(GALCEN_V_SUN_KMS) * u.km / u.s),
    )
    icrs_now = SkyCoord(
        ra=ra_deg * u.deg,
        dec=dec_deg * u.deg,
        distance=distance_pc * u.pc,
        pm_ra_cosdec=pmra_masyr * u.mas / u.yr,
        pm_dec=pmdec_masyr * u.mas / u.yr,
        radial_velocity=rv_kms * u.km / u.s,
        frame="icrs",
    )
    galcen_now = icrs_now.transform_to(galcen_frame)
    o_now = Orbit(galcen_now)
    x0 = float(o_now.x(quantity=True).to(u.kpc).value)
    y0 = float(o_now.y(quantity=True).to(u.kpc).value)
    z0 = float(o_now.z(quantity=True).to(u.kpc).value)

    ts_back = np.linspace(0.0, -t_myr, 1001) * u.Myr
    o_now.integrate(ts_back, MWPotential2014, method="odeint")
    # 用帶單位的 Quantity 重建第二個 Orbit（不用 ro/vo 換算，galpy 對
    # Quantity 列表輸入直接按物理單位解讀，見 Orbits.py __init__ 的
    # docstring「Regular or Quantity arrays」段落），避免去碰
    # galpy 內部的 _ro/_vo 私有屬性。
    o_past = Orbit(
        [
            o_now.R(ts_back[-1], quantity=True),
            o_now.vR(ts_back[-1], quantity=True),
            o_now.vT(ts_back[-1], quantity=True),
            o_now.z(ts_back[-1], quantity=True),
            o_now.vz(ts_back[-1], quantity=True),
            o_now.phi(ts_back[-1], quantity=True),
        ]
    )
    ts_fwd = np.linspace(0.0, t_myr, 1001) * u.Myr
    o_past.integrate(ts_fwd, MWPotential2014, method="odeint")
    x1 = float(o_past.x(ts_fwd[-1], quantity=True).to(u.kpc).value)
    y1 = float(o_past.y(ts_fwd[-1], quantity=True).to(u.kpc).value)
    z1 = float(o_past.z(ts_fwd[-1], quantity=True).to(u.kpc).value)

    r0 = math.sqrt(x0**2 + y0**2 + z0**2)
    d = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)
    rel_err = d / r0 if r0 > 0 else float("inf")
    checks["round_trip_relative_error_below_1e-5"] = rel_err < 1e-5

    summary = {
        "status": "synthetic_validation_only",
        "inputs": {
            "ra_deg": ra_deg,
            "dec_deg": dec_deg,
            "distance_pc": distance_pc,
            "pmra_masyr": pmra_masyr,
            "pmdec_masyr": pmdec_masyr,
            "rv_kms": rv_kms,
            "t_myr": t_myr,
        },
        "backward_orbit_result": forward,
        "round_trip_relative_error": rel_err,
        "checks": checks,
    }
    if not all(checks.values()):
        raise AssertionError(f"m45_orbit_init self-test failed: {checks}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--members-file", type=Path, default=HERE / "data/cmd_members.csv")
    parser.add_argument("--ra-deg", type=float)
    parser.add_argument("--dec-deg", type=float)
    parser.add_argument("--distance-pc", type=float)
    parser.add_argument("--pmra-masyr", type=float)
    parser.add_argument("--pmdec-masyr", type=float)
    parser.add_argument("--rv-kms", type=float, default=DEFAULT_RV_KMS)
    parser.add_argument("--t-myr", type=float, default=DEFAULT_T_MYR)
    parser.add_argument("--output", type=Path, default=HERE / "results/m45_orbit_init.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        summary = run_self_test()
        print(json.dumps(summary, indent=2))
        return

    overrides = {
        "ra_deg": args.ra_deg,
        "dec_deg": args.dec_deg,
        "distance_pc": args.distance_pc,
        "pmra_masyr": args.pmra_masyr,
        "pmdec_masyr": args.pmdec_masyr,
    }
    if any(v is None for v in overrides.values()):
        if not args.members_file.exists():
            parser.error(
                f"{args.members_file} 不存在，且未用旗標提供完整的 "
                "ra/dec/distance/pmra/pmdec——沒有預設值可用"
            )
        defaults = _members_defaults(args.members_file)
        for key, value in overrides.items():
            if value is None:
                overrides[key] = defaults[key]

    result = backward_orbit(
        overrides["ra_deg"],
        overrides["dec_deg"],
        overrides["distance_pc"],
        overrides["pmra_masyr"],
        overrides["pmdec_masyr"],
        args.rv_kms,
        args.t_myr,
    )
    # t=0（現在）用窄窗口檢查單位，t=-t_myr（實際要用的輸出值）用寬窗口——
    # 見檔頭 docstring「t=0 量級檢查」一節，125 Myr 的真實軌道動力學
    # 會讓 R 合理地偏離現在值，不能拿窄窗口套用在輸出值上。
    r_now_kpc = result["galactocentric_radius_now_kpc"]
    r_past_kpc = result["galactocentric_radius_kpc"]
    z_pc = result["z_kpc"] * 1000.0
    now_ok = 7.5 <= r_now_kpc <= 8.7
    past_ok = 6.0 <= r_past_kpc <= 10.0
    z_ok = abs(z_pc) < 100.0
    plausible = now_ok and past_ok and z_ok

    summary = {
        "status": "orbit_init" if plausible else "orbit_init_implausible",
        "inputs": {**overrides, "rv_kms": args.rv_kms, "t_myr": args.t_myr},
        "frame_assumptions": {
            "galcen_distance_kpc": GALCEN_DISTANCE_KPC,
            "z_sun_pc": Z_SUN_PC,
            "galcen_v_sun_kms": list(GALCEN_V_SUN_KMS),
            "source": "PeTar tools/analysis/data.py toSkyCoord() 預設參數，逐字對照",
        },
        "result": result,
        "petar_init_c_flag": petar_init_c_flag(
            result["position_pc"], result["velocity_kms"]
        ),
        "plausibility_check": {
            "galactocentric_radius_now_kpc": r_now_kpc,
            "expected_range_now_kpc": [7.5, 8.7],
            "galactocentric_radius_past_kpc": r_past_kpc,
            "expected_range_past_kpc": [6.0, 10.0],
            "z_offset_pc": z_pc,
            "expected_abs_max_pc": 100.0,
            "passed": plausible,
        },
    }
    if not plausible:
        print(
            "警告：算出的銀心座標超出 M45 合理量級（現在 |R| 應在 7.5-8.7 kpc、"
            "t=-t_myr 的 |R| 應在 6-10 kpc、|z| 應 < 100 pc），先檢查單位再"
            "使用，不要直接餵給 petar.init。",
            file=sys.stderr,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
