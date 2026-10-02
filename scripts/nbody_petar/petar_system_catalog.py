#!/usr/bin/env python
"""Export PeTar processed single/multiple catalogs to a definition-bridge NPZ.

Run ``petar.data.process`` first, then provide every object catalog produced for
the snapshot.  Binary trees are flattened recursively, so binary, hierarchical
triple and binary-binary quadruple files all become component rows sharing one
``system_id``.  Omitting a non-empty multiplicity catalog changes the scientific
definition, so the command records every supplied path and requires an explicit
``--confirm-complete`` acknowledgement.

2026-09 新增（供 observe_snapshot.py 使用）：當 ``--interrupt-mode`` 含
``bse`` 時，PeTar 的 ``Particle`` 物件會多帶一個 ``star``
(``SSEStarParameter``) 子物件，內含 ``star.type``（SSE 恆星型態編號，
1=主序星，>=10 為白矮星／中子星／黑洞等演化終態，見 PeTar
``tools/analysis/bse.py`` 的 ``SSEStarParameter`` 定義，本次已逐字核對
過欄位存在）與 ``star.mass``（恆星演化後的目前質量，可能小於出生質量）。
這兩個欄位用 ``getattr`` 保護性讀取——沒有 ``star`` 屬性（例如
``interrupt_mode='none'`` 或自我測試用的假資料）就退回
``star_type=1``、``current_mass=mass``，不會因為缺欄位而炸掉。

2026-09-18 新增 ``--external-mode``：``petar_m45_grid.render_commands()``
固定用 ``petar.data.process -t galpy`` 產檔（見該檔案）。PeTar 的
``Particle`` 建構子在 ``external_mode`` 不是 ``'none'`` 時，會在 soft
particle 的欄位定義多插入 ``pot_ext`` 這一欄（見 PeTar
``tools/analysis/data.py`` 的 ``Particle.__init__``，pinned commit
84b81a8c339c49291de53f7a72829dd80e188182 逐字核對過）。如果這裡讀檔時
沒有傳同一個 ``external_mode``，讀出來的欄位 schema 會跟寫檔時少一欄，
後面的欄位全部錯位——尤其是巢狀 binary/triple/quadruple 的內層粒子，
``star.type``／``mass``／``pos`` 會讀到別的欄位的數值而不自知。因此
``--external-mode`` 必須跟產生輸入檔那次 ``petar.data.process -t`` 用的
值完全一致，預設 ``none`` 只適用於沒有加 Galpy 銀河潮汐的舊快照。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def _load_ascii(data, path: Path):
    data.loadtxt(str(path))
    return data


def _particle(petar, interrupt_mode: str, external_mode: str = "none"):
    kwargs = {}
    if interrupt_mode != "none":
        kwargs["interrupt_mode"] = interrupt_mode
    if external_mode != "none":
        kwargs["external_mode"] = external_mode
    return petar.Particle(**kwargs)


def _multiple_reader(petar, structure: str, interrupt_mode: str, external_mode: str):
    """建立空的 binary/triple/quadruple 讀檔物件。

    2026-10-02 修正：以前用 ``petar.Binary(空實例, 空實例)`` 組巢狀結構，
    PeTar 的 ``Binary.__init__`` 拿到兩個實例時會立刻呼叫
    ``particleToSemiEcc`` 算軌道參數；巢狀時一邊是空 Binary（pos 形狀
    (0,3)）、一邊是空 Particle（pos 形狀 (0,)），直接 broadcast 錯誤——
    以前從沒餵過 triple/quadruple 檔所以沒被發現。改成跟 PeTar 自己
    （``tools/analysis/data.py`` 的 ``findMultiple()``）一樣，用成員「型別」
    建構：triple 是 ``member_particle_type_one=Particle``、
    ``member_particle_type_two=[Particle, Particle]``，quadruple 是
    ``member_particle_type=[Particle, Particle]``。``simple_mode`` 用預設
    True，欄數對得上 ``petar.data.process -M`` 的輸出（bse+galpy：
    單星 35、雙星 10+2×35=80、三合星 10+35+80=125、四合星 10+80+80=170 欄，
    2026-10-02 用實際檔案逐一核對過）。
    """
    initargs = _particle(petar, interrupt_mode, external_mode).initargs
    P = petar.Particle
    if structure == "binary":
        return petar.Binary(member_particle_type=P, **initargs)
    if structure == "triple":
        return petar.Binary(member_particle_type_one=P, member_particle_type_two=[P, P], **initargs)
    if structure == "quadruple":
        return petar.Binary(member_particle_type=[P, P], **initargs)
    raise ValueError(structure)


def _leaves(node):
    if hasattr(node, "p1") and hasattr(node, "p2"):
        yield from _leaves(node.p1)
        yield from _leaves(node.p2)
    else:
        yield node


def _leaf_star_type(leaf, n: int) -> np.ndarray:
    """SSE 恆星型態編號，沒有 `.star` 屬性（非 bse 模式）就當全部主序星。"""
    star = getattr(leaf, "star", None)
    if star is None:
        return np.ones(n, np.int64)
    return np.asarray(star.type, np.int64)


def _leaf_current_mass(leaf, mass: np.ndarray) -> np.ndarray:
    """恆星演化後的目前質量，沒有 `.star` 屬性就等於出生質量。"""
    star = getattr(leaf, "star", None)
    if star is None:
        return mass.copy()
    return np.asarray(star.mass, float)


def _append_category(
    node,
    category: str,
    system_offset: int,
    particle_ids: list,
    masses: list,
    positions: list,
    system_ids: list,
    star_types: list,
    current_masses: list,
):
    leaves = list(_leaves(node))
    if not leaves:
        return system_offset, {"category": category, "n_systems": 0, "multiplicity": 0}
    sizes = {int(leaf.size) for leaf in leaves}
    if len(sizes) != 1:
        raise ValueError(f"{category} leaf arrays have inconsistent sizes: {sizes}")
    n_systems = sizes.pop()
    for leaf in leaves:
        leaf_mass = np.asarray(leaf.mass, float)
        particle_ids.append(np.asarray(leaf.id))
        masses.append(leaf_mass)
        positions.append(np.asarray(leaf.pos, float))
        system_ids.append(np.arange(system_offset, system_offset + n_systems))
        star_types.append(_leaf_star_type(leaf, n_systems))
        current_masses.append(_leaf_current_mass(leaf, leaf_mass))
    return system_offset + n_systems, {
        "category": category,
        "n_systems": n_systems,
        "multiplicity": len(leaves),
        "n_components": n_systems * len(leaves),
    }



def _merge_shared_components(particle_id, mass, position, system_id, star_type, current_mass):
    """同一顆星出現在多個系統時，把那些系統合併成一個，重複的星只留一份。

    2026-10-02 加入。``petar.data.process`` 配對雙星用「每顆星找最近鄰」，
    不要求互為最近：A、C 都以 B 為最近鄰時會產生 (A,B)、(B,C) 兩對共用 B 的
    雙星；開 ``-M`` 後這兩對再被配成一個「四合星」，B 在裡面出現兩次
    （實測 mb_train_0005_s40006 的 ID 786、mb_train_0007_s40008 的 ID 550，
    物理上都是一個階層式三合星）。共用成員的系統物理上本來就是同一個束縛
    系統，所以用 union-find 合併 system_id；重複列必須在每個欄位都一致才
    丟掉（同一張快照的同一顆星不可能不一致），不一致就報錯而不是猜。
    """
    order = np.argsort(particle_id, kind="stable")
    pid_sorted = particle_id[order]
    dup_mask = np.r_[False, pid_sorted[1:] == pid_sorted[:-1]]
    if not dup_mask.any():
        return particle_id, mass, position, system_id, star_type, current_mass, []

    parent = {int(x): int(x) for x in np.unique(system_id)}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    keep = np.ones(len(particle_id), bool)
    merged = []
    for j in np.where(dup_mask)[0]:
        a, b = order[j - 1], order[j]
        # 往回找這個 id 第一次出現的列（可能出現 3 次以上）
        k = j - 1
        while k > 0 and dup_mask[k]:
            k -= 1
        a = order[k]
        same = (np.isclose(mass[a], mass[b]) and np.allclose(position[a], position[b])
                and star_type[a] == star_type[b] and np.isclose(current_mass[a], current_mass[b]))
        if not same:
            raise ValueError(
                f"Component {int(particle_id[a])} appears twice with different values; "
                "refusing to merge")
        ra, rb = find(int(system_id[a])), find(int(system_id[b]))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
        keep[b] = False
        merged.append(int(particle_id[b]))
    new_sys = np.array([find(int(x)) for x in system_id])
    sel = keep
    return (particle_id[sel], mass[sel], position[sel], new_sys[sel], star_type[sel],
            current_mass[sel], sorted(set(merged)))

def export_catalog(args) -> dict:
    if args.petar_package_path is not None:
        sys.path.insert(0, str(args.petar_package_path.resolve()))
    import petar

    particle_ids, masses, positions, system_ids = [], [], [], []
    star_types, current_masses = [], []
    categories = []
    offset = 0

    single = _load_ascii(_particle(petar, args.interrupt_mode, args.external_mode), args.single)
    n_single = int(single.size)
    single_mass = np.asarray(single.mass, float)
    particle_ids.append(np.asarray(single.id))
    masses.append(single_mass)
    positions.append(np.asarray(single.pos, float))
    system_ids.append(np.arange(offset, offset + n_single))
    star_types.append(_leaf_star_type(single, n_single))
    current_masses.append(_leaf_current_mass(single, single_mass))
    categories.append(
        {
            "category": "single",
            "n_systems": n_single,
            "multiplicity": 1,
            "n_components": n_single,
            "path": str(args.single),
        }
    )
    offset += n_single

    specs = [
        (kind, getattr(args, kind),
         lambda kind=kind: _multiple_reader(petar, kind, args.interrupt_mode, args.external_mode))
        for kind in ("binary", "triple", "quadruple")
    ]
    for category, path, constructor in specs:
        if path is None:
            continue
        node = _load_ascii(constructor(), path)
        offset, accounting = _append_category(
            node,
            category,
            offset,
            particle_ids,
            masses,
            positions,
            system_ids,
            star_types,
            current_masses,
        )
        accounting["path"] = str(path)
        categories.append(accounting)

    particle_id = np.concatenate(particle_ids)
    mass = np.concatenate(masses)
    position = np.concatenate(positions)
    system_id = np.concatenate(system_ids)
    star_type = np.concatenate(star_types)
    current_mass = np.concatenate(current_masses)
    (particle_id, mass, position, system_id, star_type, current_mass,
     merged_ids) = _merge_shared_components(
        particle_id, mass, position, system_id, star_type, current_mass)
    if not np.all(np.isfinite(mass)) or np.any(mass <= 0):
        raise ValueError("Processed component masses must be finite and positive")
    if not np.all(np.isfinite(position)):
        raise ValueError("Processed component positions must be finite")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        id=particle_id,
        mass=mass,
        pos=position,
        system_id=system_id,
        time_myr=np.array([args.time_myr]),
        star_type=star_type,
        current_mass=current_mass,
    )
    metadata = {
        "status": "physical_system_catalog",
        "output": str(args.output),
        "time_myr": args.time_myr,
        "interrupt_mode": args.interrupt_mode,
        "external_mode": args.external_mode,
        "confirmed_complete": bool(args.confirm_complete),
        "n_components": int(len(particle_id)),
        "n_systems": int(len(np.unique(system_id))),
        "shared_component_ids_merged": merged_ids,
        "categories": categories,
        "warning": (
            "Scientific use is valid only if every non-empty single/binary/"
            "triple/quadruple catalog from the same processed snapshot was supplied."
        ),
    }
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    metadata["metadata_output"] = str(metadata_path)
    return metadata


def run_self_test() -> dict:
    def leaf(ids, masses):
        ids = np.asarray(ids)
        return SimpleNamespace(
            id=ids,
            mass=np.asarray(masses, float),
            pos=np.column_stack((ids, np.zeros((len(ids), 2)))),
            size=len(ids),
        )

    # Two hierarchical triples: one outer leaf plus two inner leaves.
    tree = SimpleNamespace(
        p1=leaf([1, 4], [1.0, 0.8]),
        p2=SimpleNamespace(
            p1=leaf([2, 5], [0.7, 0.6]),
            p2=leaf([3, 6], [0.5, 0.4]),
        ),
    )
    particle_ids, masses, positions, system_ids = [], [], [], []
    star_types, current_masses = [], []
    offset, accounting = _append_category(
        tree, "triple", 10, particle_ids, masses, positions, system_ids,
        star_types, current_masses,
    )
    ids = np.concatenate(particle_ids)
    groups = np.concatenate(system_ids)
    checks = {
        "recursive_leaf_count": accounting["multiplicity"] == 3,
        "two_systems": accounting["n_systems"] == 2 and offset == 12,
        "all_components_preserved": sorted(ids.tolist()) == [1, 2, 3, 4, 5, 6],
        "grouping_preserved": (
            sorted(ids[groups == 10].tolist()) == [1, 2, 3]
            and sorted(ids[groups == 11].tolist()) == [4, 5, 6]
        ),
    }
    # 共用成員合併：系統 20=(1,2)、21=(3,2) 共用 2 → 合併成一個系統、2 只留一份
    pid = np.array([1, 2, 3, 2, 9]); sysid = np.array([20, 20, 21, 21, 22])
    m = np.array([1.0, 2.0, 3.0, 2.0, 5.0]); pos = np.c_[pid, pid * 0, pid * 0].astype(float)
    st = np.ones(5, int); cm = m.copy()
    out = _merge_shared_components(pid, m, pos, sysid, st, cm)
    checks["shared_member_merged"] = (
        sorted(out[0].tolist()) == [1, 2, 3, 9]
        and len(set(out[3][np.isin(out[0], [1, 2, 3])].tolist())) == 1
        and out[6] == [2])
    m_bad = m.copy(); m_bad[3] = 2.5
    try:
        _merge_shared_components(pid, m_bad, pos, sysid, st, m_bad)
        checks["inconsistent_duplicate_rejected"] = False
    except ValueError:
        checks["inconsistent_duplicate_rejected"] = True
    if not all(checks.values()):
        raise AssertionError(f"System catalog self-test failed: {checks}")
    return {"status": "synthetic_validation_only", "self_test": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--triple", type=Path)
    parser.add_argument("--quadruple", type=Path)
    parser.add_argument("--time-myr", type=float)
    parser.add_argument(
        "--interrupt-mode", choices=("none", "bse", "mobse", "bseEmp"), default="bse"
    )
    parser.add_argument(
        "--external-mode", choices=("none", "galpy"), default="none",
        help="必須跟產生這批輸入檔那次 `petar.data.process -t` 用的值完全"
             "一致（petar_m45_grid.render_commands() 固定用 -t galpy），"
             "否則 pot_ext 欄位錯位會讓後面所有欄位讀到錯的值",
    )
    parser.add_argument("--petar-package-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-complete", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return
    if args.single is None or args.time_myr is None or args.output is None:
        parser.error("--single, --time-myr and --output are required")
    if not args.confirm_complete:
        parser.error(
            "--confirm-complete is required after checking that every non-empty "
            "multiplicity catalog for this snapshot is supplied"
        )
    for path in (args.single, args.binary, args.triple, args.quadruple):
        if path is not None and not path.is_file():
            parser.error(f"input file does not exist: {path}")
    metadata = export_catalog(args)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
