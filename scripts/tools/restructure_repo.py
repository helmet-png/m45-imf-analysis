# -*- coding: utf-8 -*-
"""2026-11 目錄重整（方案 B）的搬遷腳本：搬檔＋同步改所有路徑引用。

為什麼寫成腳本而不是手動搬：重整當下有十幾個 PR 還開著，它們大多改到
被搬的檔案。手動搬一次，等那些 PR 合併後就得逐一解衝突；寫成腳本，
合併前可以在最新的 main 上重跑一次，搬遷結果永遠以當下的 main 為準。

用法（在 repo 根目錄、乾淨的工作目錄上）：
    python scripts/tools/restructure_repo.py           # 實際搬遷
    python scripts/tools/restructure_repo.py --check   # 只檢查搬遷後的路徑是否都存在

每一條針對程式碼的修改都斷言「原本的寫法確實存在」，找不到就整支停下，
不會靜默跳過——main 上的程式若已被別人改過寫法，要人工確認後再更新本檔。
"""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[2]

CORE = ["fit_real.py", "injection_recovery.py", "inject_lowmass.py",
        "inject_massdep_fbin.py", "measure_overconfidence.py",
        "profile_lowmass.py", "profile_outlierfrac.py"]
OPS = ["cloud_queue.py", "gcp_vm_lifecycle.py", "iap_tunnel_manager.py",
       "kaggle_accounts.py", "kaggle_queue.py", "kaggle_smoketest.py",
       "kaggle_sync.py", "run_queue.py", "ssh_sync.py", "ssh_workers.py",
       "queue.txt", "kaggle_queue.txt", "kaggle_accounts.json.example",
       "ssh_workers.json.example", "restart_queue_on_boot.ps1", "run_hidden.vbs"]

# 舊路徑 → 新路徑。以 "/" 結尾的是整個資料夾。
MOVES: dict[str, str] = {
    **{f: f"scripts/core/{f}" for f in CORE},
    **{f: f"ops/{f}" for f in OPS},
    "PAPER_OUTLINE.md": "docs/paper/PAPER_OUTLINE.md",
    "MULTICLUSTER_VALIDATION.md": "docs/paper/MULTICLUSTER_VALIDATION.md",
    "NBODY_PREREGISTRATION.md": "docs/paper/NBODY_PREREGISTRATION.md",
    "RESOLVED.md": "docs/paper/RESOLVED.md",
    "WORK_BOARD.md": "docs/project/WORK_BOARD.md",
    "WORK_BOARD_DONE.md": "docs/project/WORK_BOARD_DONE.md",
    "STATE.md": "docs/project/STATE.md",
    "NEXT_PROMPT.md": "docs/project/NEXT_PROMPT.md",
    "QUEUE_ALERTS.md": "docs/project/QUEUE_ALERTS.md",
    "CHANGELOG.md": "docs/project/CHANGELOG.md",
    "petar_m45_grid.csv": "scripts/nbody_petar/grids/petar_m45_grid.csv",
    "petar_m45_training_grid.csv": "scripts/nbody_petar/grids/petar_m45_training_grid.csv",
    "nbody_setup/analyze_alpha_r.py": "scripts/nbody_petar/analyze_alpha_r.py",
    "nbody_setup/": "setup/nbody/",
}

# 這些檔案是歷史紀錄：只修會失效的 markdown 連結，不改內文提到的檔名。
# RESULTS_LOG.md 有 append-only CI，連一行都不能改，完全跳過。
SKIP_ENTIRELY = ("results/", "_archive/")
HISTORICAL = ("docs/planning/", "docs/reports/", "docs/project/CHANGELOG.md",
              "docs/project/WORK_BOARD_DONE.md", "docs/paper/RESOLVED.md")
# 其他 PR 改得很頻繁的大檔：同樣只修連結，內文的檔名留給之後順手改，
# 避免這次重整跟每一個開著的 PR 都衝突。
HIGH_CHURN = ("LIMITATIONS.md", "docs/paper/PAPER_OUTLINE.md",
              "docs/project/WORK_BOARD.md")


def git(*args: str) -> str:
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=ROOT,
                          check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout


def map_path(old: str) -> str:
    """repo 相對路徑（posix）→ 搬遷後的路徑；沒搬就原樣回傳。"""
    if old in MOVES:
        return MOVES[old]
    for src, dst in MOVES.items():
        if not src.endswith("/"):
            continue
        if old.startswith(src):
            return dst + old[len(src):]
        if old + "/" == src:
            return dst.rstrip("/")
    return old


# ---------------------------------------------------------------- 文字改寫
LINK_RE = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
REFDEF_RE = re.compile(r"^(\s*\[[^\]]+\]:\s*)(\S+)", re.M)


def rewrite_links(text: str, old_file: str, new_file: str, old_tree: set[str]) -> str:
    old_dir, new_dir = posixpath.dirname(old_file), posixpath.dirname(new_file)

    def fix(target: str) -> str:
        if re.match(r"^[a-z][a-z0-9+.-]*:|^#|^/", target, re.I):
            return target
        path, frag = (target.split("#", 1) + [""])[:2]
        encoded = "%" in path
        raw = unquote(path) if encoded else path
        resolved = posixpath.normpath(posixpath.join(old_dir, raw))
        exists = resolved in old_tree or any(p.startswith(resolved + "/") for p in old_tree)
        if not exists:
            return target                      # 原本就壞的連結不動
        new_target = posixpath.relpath(map_path(resolved), new_dir or ".")
        if raw.endswith("/") and not new_target.endswith("/"):
            new_target += "/"
        if new_target == raw:
            return target
        out = quote(new_target) if encoded else new_target
        return out + ("#" + frag if frag else "")

    text = LINK_RE.sub(lambda m: m.group(1) + fix(m.group(2)) + m.group(3), text)
    return REFDEF_RE.sub(lambda m: m.group(1) + fix(m.group(2)), text)


def _root_names() -> list[str]:
    return [o for o in MOVES if "/" not in o]


def rewrite_commands(text: str) -> str:
    """`python fit_real.py` 這類可以直接複製執行的指令，改成新路徑。"""
    for old in _root_names():
        if not old.endswith(".py"):
            continue
        text = re.sub(rf"(\b(?:python3?|py)(?:\s+-[a-zA-Z]+)*\s+|--script[ =]){re.escape(old)}\b",
                      rf"\g<1>{MOVES[old]}", text)
    return text.replace("nbody_setup/", "setup/nbody/")


def rewrite_mentions(text: str) -> str:
    """內文提到的檔名（含反引號內）改成新路徑。只用在常駐文件上。"""
    text = text.replace("nbody_setup/", "setup/nbody/")
    for old in _root_names():
        text = re.sub(rf"(?<![\w/.\[(-]){re.escape(old)}(?![\w-])", MOVES[old], text)
    return text


# ---------------------------------------------------------------- 程式碼修改
# (檔案（搬遷後路徑）, 原字串, 新字串)。原字串必須剛好出現至少一次。
CORE_HERE_OLD = "HERE = Path(__file__).resolve().parent\n"
CORE_HERE_NEW = ("# 本檔在 scripts/core/；Kaggle 會把腳本拍平到工作目錄根（config.toml 在同層），\n"
                 "# 兩種擺法都以找得到 config.toml 的那層當 repo 根目錄。\n"
                 "_SELF_DIR = Path(__file__).resolve().parent\n"
                 "HERE = _SELF_DIR if (_SELF_DIR / \"config.toml\").is_file() else _SELF_DIR.parents[1]\n")
OPS_HERE_OLD = CORE_HERE_OLD
OPS_HERE_NEW = ("HERE = Path(__file__).resolve().parents[1]  # repo 根目錄（本檔在 ops/）\n"
                "OPS_DIR = Path(__file__).resolve().parent\n")
CORE_PATH_LINE = '    sys.path.insert(0, str(HERE / "scripts" / "core"))  # injection_recovery 等主程式\n'

EDITS: list[tuple[str, str, str]] = [
    *[(f"scripts/core/{f}", CORE_HERE_OLD, CORE_HERE_NEW) for f in CORE],
    *[(f"ops/{f}", OPS_HERE_OLD, OPS_HERE_NEW) for f in
      ["cloud_queue.py", "iap_tunnel_manager.py", "kaggle_accounts.py",
       "kaggle_queue.py", "kaggle_sync.py", "run_queue.py", "ssh_sync.py",
       "ssh_workers.py"]],
    ("ops/run_queue.py", 'QUEUE = HERE / "queue.txt"', 'QUEUE = OPS_DIR / "queue.txt"'),
    ("ops/run_queue.py", 'ALERTS = HERE / "QUEUE_ALERTS.md"',
     'ALERTS = HERE / "docs" / "project" / "QUEUE_ALERTS.md"'),
    ("ops/run_queue.py", "    if script not in PREFLIGHT_AWARE_SCRIPTS:\n        return True\n"
     "    stem = script[:-3] if script.endswith(\".py\") else script\n",
     "    if Path(script).name not in PREFLIGHT_AWARE_SCRIPTS:\n        return True\n"
     "    stem = Path(script).stem\n"),
    ("ops/kaggle_queue.py", 'QUEUE = HERE / "kaggle_queue.txt"', 'QUEUE = OPS_DIR / "kaggle_queue.txt"'),
    ("ops/kaggle_queue.py", '[sys.executable, "kaggle_sync.py", "push",',
     '[sys.executable, "ops/kaggle_sync.py", "push",'),
    ("ops/kaggle_accounts.py", 'EXAMPLE_FILE = HERE / "kaggle_accounts.json.example"',
     'EXAMPLE_FILE = OPS_DIR / "kaggle_accounts.json.example"'),
    ("ops/ssh_workers.py", 'EXAMPLE_FILE = HERE / "ssh_workers.json.example"',
     'EXAMPLE_FILE = OPS_DIR / "ssh_workers.json.example"'),
    ("ops/restart_queue_on_boot.ps1", "$repo = $PSScriptRoot",
     "$repo = Split-Path -Parent $PSScriptRoot   # 本檔在 ops/，上一層才是 repo 根目錄"),
    ("ops/restart_queue_on_boot.ps1", "$scriptPath = Join-Path $repo $ScriptName",
     "$scriptPath = Join-Path $PSScriptRoot $ScriptName"),
    # 從別的資料夾 import 主程式的腳本：多加 scripts/core 到 sys.path
    *[(f, "sys.path.insert(0, str(HERE))\n",
       "sys.path.insert(0, str(HERE))\n" + CORE_PATH_LINE.lstrip())
      for f in ["scripts/diagnostics/sensitivity_sweep.py",
                "scripts/diagnostics/traditional_accounting.py",
                "scripts/diagnostics/verify_binary_detection.py",
                "scripts/multicluster/cluster_forward_validation.py"]],
    ("scripts/tools/preflight.py", "HERE = _find_repo_root()\nsys.path.insert(0, str(HERE))\n",
     "HERE = _find_repo_root()\nsys.path.insert(0, str(HERE))\n"
     "sys.path.insert(0, str(HERE / \"scripts\" / \"core\"))  # injection_recovery 等主程式\n"
     "sys.path.insert(0, str(HERE / \"ops\"))               # run_queue（佇列工具）\n"),
    ("scripts/diagnostics/prepare_bp15_paired_dispatch.py", "sys.path.insert(0, str(ROOT))\n",
     "sys.path.insert(0, str(ROOT))\nsys.path.insert(0, str(ROOT / \"ops\"))  # kaggle_sync\n"),
    ("scripts/diagnostics/prepare_bp15_paired_dispatch.py",
     'extras = ["measure_overconfidence.py", "injection_recovery.py"]',
     'extras = ["scripts/core/measure_overconfidence.py", "scripts/core/injection_recovery.py"]'),
    ("scripts/diagnostics/prepare_bp15_paired_dispatch.py",
     'build_payload("fit_real.py", ', 'build_payload("scripts/core/fit_real.py", '),
    ("scripts/nbody_petar/analyze_alpha_r.py",
     "REPO_ROOT = Path(__file__).resolve().parent.parent",
     "REPO_ROOT = Path(__file__).resolve().parents[2]"),
    *[(f"setup/nbody/{f}", 'REPO_ROOT="$(cd "$HERE/.." && pwd)"',
       'REPO_ROOT="$(cd "$HERE/../.." && pwd)"  # 本檔在 setup/nbody/')
      for f in ["add_galpy_support_linux.sh", "setup_linux_nbody.sh", "setup_windows_nbody.sh"]],
    ("status_dashboard/app.py",
     'CLOUD_QUEUE_ROOT = Path(os.environ.get("CLOUD_QUEUE_ROOT", str(REPO_ROOT)))',
     'CLOUD_QUEUE_ROOT = Path(os.environ.get("CLOUD_QUEUE_ROOT", str(REPO_ROOT / "ops")))'),
    ("status_dashboard/app.py", 'path = REPO_ROOT / "WORK_BOARD.md"',
     'path = REPO_ROOT / "docs" / "project" / "WORK_BOARD.md"'),
    ("status_dashboard/app.py", '_doc_url("WORK_BOARD.md", task["line"])',
     '_doc_url("docs/project/WORK_BOARD.md", task["line"])'),
    ("status_dashboard/app.py", "_doc_url('WORK_BOARD.md')",
     "_doc_url('docs/project/WORK_BOARD.md')"),
    (".coderabbit.yaml", '- path: "injection_recovery.py"',
     '- path: "scripts/core/injection_recovery.py"'),
]

# N-body 網格 CSV 的預設路徑（REPO_ROOT / "petar_m45_grid.csv" 這類寫法）
GRID_RE = re.compile(r'\b(REPO_ROOT|HERE) / "(petar_m45_(?:training_)?grid\.csv)"')


def apply_edits() -> None:
    for rel, old, new in EDITS:
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        if old not in text:
            sys.exit(f"找不到要改的寫法，請人工確認後更新本腳本：{rel}\n  {old!r}")
        p.write_text(text.replace(old, new), encoding="utf-8", newline="")
    for p in (ROOT / "scripts" / "nbody_petar").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        new = GRID_RE.sub(r'\1 / "scripts" / "nbody_petar" / "grids" / "\2"', text)
        if new != text:
            p.write_text(new, encoding="utf-8", newline="")


def rewrite_queues() -> None:
    """佇列檔：腳本欄、依賴欄、參數裡剛好等於舊路徑的字詞都換新。"""
    def tok(t: str) -> str:
        return map_path(t)

    for rel, kind in (("cloud_queue.txt", "pipe"), ("ops/kaggle_queue.txt", "pipe"),
                      ("ops/queue.txt", "cmd")):
        p = ROOT / rel
        out = []
        for line in p.read_text(encoding="utf-8").splitlines(keepends=True):
            body = line.rstrip("\r\n")
            nl = line[len(body):]
            if not body.strip() or body.lstrip().startswith("#") or "|" not in body:
                out.append(line)
                continue
            f = body.split("|")
            if kind == "pipe" and len(f) >= 4:
                f[1] = tok(f[1].strip()) if f[1].strip() else f[1]
                f[2] = " ".join(tok(t) for t in f[2].split(" "))
                f[3] = ",".join(tok(t) for t in f[3].split(",")) if f[3] else f[3]
            elif kind == "cmd":
                f[1] = " ".join(tok(t) for t in f[1].split(" "))
            out.append("|".join(f) + nl)
        p.write_text("".join(out), encoding="utf-8", newline="")


def rewrite_stage_map() -> None:
    for rel in ("status_dashboard/stage_map.py", "status_dashboard/categorization.json"):
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        for old in MOVES:
            if old.endswith("/"):
                continue
            new = MOVES[old]
            text = text.replace(f'"{old}"', f'"{new}"').replace(f"'{old}'", f"'{new}'")
        p.write_text(text, encoding="utf-8", newline="")


def rewrite_text_files(old_tree: set[str]) -> None:
    new_of = {o: map_path(o) for o in old_tree}
    old_of = {n: o for o, n in new_of.items()}
    for new_rel in sorted(old_of):
        if new_rel.startswith(SKIP_ENTIRELY) or new_rel == "scripts/tools/restructure_repo.py":
            continue
        old_rel = old_of[new_rel]
        p = ROOT / new_rel
        ext = p.suffix.lower()
        if ext not in {".md", ".py", ".sh", ".ps1", ".txt", ".yml", ".yaml", ".toml"}:
            continue
        text = p.read_text(encoding="utf-8")
        orig = text
        if ext == ".md":
            text = rewrite_links(text, old_rel, new_rel, old_tree)
            if not new_rel.startswith(HISTORICAL):
                text = rewrite_commands(text)
                if not new_rel.startswith(HIGH_CHURN):
                    text = rewrite_mentions(text)
        elif ext in {".py", ".sh", ".ps1"}:
            text = rewrite_commands(text)
        if text != orig:
            p.write_text(text, encoding="utf-8", newline="")


def move_files() -> set[str]:
    old_tree = set(git("ls-files").splitlines())
    for old, new in MOVES.items():
        src, dst = ROOT / old.rstrip("/"), ROOT / new.rstrip("/")
        if old.endswith("/"):
            # 資料夾：逐檔搬，已經單獨列過的檔案（analyze_alpha_r.py）不重複
            for f in sorted(x for x in old_tree if x.startswith(old)):
                if f in MOVES:
                    continue
                d = ROOT / map_path(f)
                d.parent.mkdir(parents=True, exist_ok=True)
                git("mv", f, str(d.relative_to(ROOT).as_posix()))
            continue
        if not src.exists():
            sys.exit(f"要搬的檔案不存在：{old}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        git("mv", old, new)
    return old_tree


def check() -> int:
    """搬遷後的健檢：佇列裡的腳本與額外檔案都要存在。"""
    sys.path.insert(0, str(ROOT / "scripts" / "tools"))
    import check_queue_paths
    return check_queue_paths.main()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()
    if git("status", "--porcelain", "--untracked-files=no").strip():
        sys.exit("工作目錄有未 commit 的修改，先處理掉再跑。")
    old_tree = move_files()
    apply_edits()
    rewrite_queues()
    rewrite_stage_map()
    rewrite_text_files(old_tree)
    return check()


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())
