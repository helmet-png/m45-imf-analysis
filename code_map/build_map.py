# -*- coding: utf-8 -*-
"""程式地圖生成器：讀 code_map/catalog.json，產生 code_map/ 底下所有 .md。

要解決的問題：一支程式只能放在一個資料夾，但「它在流程的第幾步」「它是
科學還是基礎設施」「它屬於哪個方法」「它是函式庫還是實驗」「它的結果能
不能引用」是五個獨立的問題。這裡不搬檔案，改成在 catalog.json 替每支
程式貼五種標籤，再由這支程式把同一份登記排成五個檢視頁、一張流程圖、
以及每個結論一頁。

用法（在 repo 根目錄，只用 Python 標準庫）：
    python code_map/build_map.py            重新生成所有頁面
    python code_map/build_map.py --check    不寫檔，只檢查；有問題就以非 0 結束
    python code_map/build_map.py --check --strict
                                            再加兩項：每支 .py 都要登記、
                                            每個輸入檔都要找得到來源

哪些是自動的、哪些靠人：
  自動  import 關係（每次從原始碼重新抽出，不會過期）
  自動  哪些 .py 還沒登記、哪些輸入檔沒有來源（列在 README.md）
  靠人  五種標籤、reads/writes/calls、produces/validates、claims 的內容
  所以新增或搬動程式時要同步改 catalog.json；--check 會擋下路徑對不上、
  標籤值不合法、頁面沒重新生成這三種情況。
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CATALOG = HERE / "catalog.json"
DIMS = ["order", "role", "method", "layer", "trust"]  # 五種標籤，也是五個檢視頁
MULTI = {"order", "method"}                           # 這兩種可以貼多個值
BANNER = "<!-- 由 code_map/build_map.py 依 catalog.json 生成，請勿手改 -->\n"
# 不要求登記的 .py：封存區、套件的 __init__
EXEMPT = ("_archive/",)


def git_files(*patterns: str) -> list[str]:
    """git 追蹤中的檔案。-z 與 quotepath=off：中文檔名才不會被跳脫成八進位碼。"""
    out = subprocess.run(
        ["git", "-C", str(REPO), "-c", "core.quotepath=off", "ls-files", "-z", *patterns],
        capture_output=True, check=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def tracked_py() -> list[str]:
    """git 追蹤中、需要登記的 .py 清單。"""
    return sorted(p for p in git_files("*.py")
                  if not p.startswith(EXEMPT) and not p.endswith("__init__.py"))


def project_imports(path: str, all_py: list[str]) -> list[str]:
    """從原始碼抽出這支程式 import 了哪些本專案的 .py。

    專案裡的腳本用 sys.path.insert() 互相 import（例如 `import checkpoint`
    實際是 scripts/tools/checkpoint.py），所以用「模組名 = 檔名」去對：
    先找同資料夾，再找全專案唯一同名的檔案；對不到或有歧義就略過。
    """
    by_name: dict[str, list[str]] = {}
    for p in all_py:
        by_name.setdefault(Path(p).stem, []).append(p)
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[-1] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[-1])
            # `from pipeline import joint_fit`：被 import 的名字本身可能是模組
            names.update(a.name for a in node.names)
    found = set()
    for name in names:
        cands = by_name.get(name, [])
        same_dir = [c for c in cands if Path(c).parent == Path(path).parent]
        pick = same_dir or (cands if len(cands) == 1 else [])
        found.update(p for p in pick if p != path)
    return sorted(found)


def matches(a: str, b: str) -> bool:
    """兩個路徑（都可能含 *）指的是不是同一批檔案。"""
    return a == b or fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a)


def validate(cat: dict) -> list[str]:
    """登記檔本身的錯誤：路徑不存在、標籤值不合法、指到不存在的結論。"""
    errors = []
    dims, scripts, claims = cat["dimensions"], cat["scripts"], cat["claims"]
    for path, info in scripts.items():
        if not (REPO / path).is_file():
            errors.append(f"{path}：檔案不存在（搬動或改名後要同步改 catalog.json）")
        for dim in DIMS:
            if dim not in info:
                continue
            values = info[dim] if dim in MULTI else [info[dim]]
            for v in values:
                if v not in dims[dim]["values"]:
                    errors.append(f"{path}：{dim} 的值 {v!r} 不在 dimensions 裡")
        if "role" not in info or "trust" not in info or "desc" not in info:
            errors.append(f"{path}：desc、role、trust 是必填")
        for key in ("produces", "validates"):
            for cid in info.get(key, []):
                if cid not in claims:
                    errors.append(f"{path}：{key} 指到不存在的結論 {cid!r}")
        for target in info.get("calls", []):
            if not target.startswith("ext:") and target not in scripts:
                errors.append(f"{path}：calls 指到未登記的程式 {target!r}")
    for cid, claim in claims.items():
        if claim["trust"] not in dims["trust"]["values"]:
            errors.append(f"claims.{cid}：trust 的值不合法")
        for f in claim.get("result_files", []):
            if not (REPO / f).is_file():
                errors.append(f"claims.{cid}：結果檔 {f} 不存在")
    return errors


def orphan_inputs(cat: dict, files: set[str]) -> list[tuple[str, str]]:
    """被讀取、卻找不到來源的檔案：不是登記過的程式寫的、不在 git 裡、
    也沒有標 ext:。通常代表「產生它的那支程式還沒登記」。"""
    scripts = cat["scripts"]
    written = [w for info in scripts.values() for w in info.get("writes", [])]
    out = []
    for path, info in scripts.items():
        for r in info.get("reads", []):
            if r.startswith("ext:") or r in files:
                continue
            if any(matches(r, w) for w in written):
                continue
            out.append((path, r))
    return out


# ---------- Markdown 小工具 ----------

def link(path: str, here: str) -> str:
    """從生成頁所在的資料夾 here（相對 repo 根目錄）連到 repo 內的 path。"""
    up = "../" * len(Path(here).parts)
    return f"[`{path}`]({up}{path})"


def tag_text(cat: dict, info: dict, skip: str) -> str:
    """一支程式除了 skip 以外的標籤，用「、」串成一格。"""
    parts = []
    for dim in DIMS:
        if dim == skip or dim not in info:
            continue
        values = info[dim] if dim in MULTI else [info[dim]]
        labels = cat["dimensions"][dim]["values"]
        parts.append("／".join(labels[v].split("：")[0] for v in values))
    return "、".join(parts)


def render_view(cat: dict, dim: str) -> str:
    """一個檢視頁：依某一種標籤分組，同一支程式可以出現在多組。"""
    spec = cat["dimensions"][dim]
    lines = [BANNER, f"# {spec['title']}", "", spec["note"], ""]
    na = []
    for value, label in spec["values"].items():
        rows = []
        for path, info in cat["scripts"].items():
            values = info.get(dim, []) if dim in MULTI else [info.get(dim)]
            if value in values:
                rows.append(f"| {link(path, 'code_map/views')} | {info['desc']} "
                            f"| {tag_text(cat, info, dim)} |")
        title = f"{value}　{label}" if dim == "order" else label
        lines += [f"## {title}", ""]
        lines += (["| 程式 | 做什麼 | 其他標籤 |", "|---|---|---|", *rows, ""]
                  if rows else ["（目前沒有登記的程式）", ""])
    for path, info in cat["scripts"].items():
        if dim not in info:
            na.append(f"- {link(path, 'code_map/views')}：{info['desc']}")
    if na:
        lines += ["## 不適用", "", *na, ""]
    return "\n".join(lines)


def render_relations(cat: dict, imports: dict[str, list[str]]) -> str:
    """每支程式一段：讀什麼、寫什麼、import 誰、被誰 import、呼叫誰。"""
    scripts = cat["scripts"]
    imported_by: dict[str, list[str]] = {}
    for src, targets in imports.items():
        for t in targets:
            imported_by.setdefault(t, []).append(src)
    here = "code_map/views"
    lines = [BANNER, "# 每支程式的上下游", "",
             "「import」與「被誰 import」是每次從原始碼自動抽出的；"
             "讀、寫、呼叫是 catalog.json 裡登記的。標 ※ 的是還沒登記的程式。", ""]

    def names(paths):
        return "、".join(link(p, here) + ("" if p in scripts else " ※") for p in paths) or "—"

    def files(items):
        return "、".join(f"`{i}`" for i in items) or "—"

    for path, info in scripts.items():
        lines += [f"## {path}", "", info["desc"], "",
                  f"- 讀：{files(info.get('reads', []))}",
                  f"- 寫：{files(info.get('writes', []))}",
                  f"- 呼叫（另開行程執行）：{files(info.get('calls', []))}",
                  f"- import：{names(imports[path])}",
                  f"- 被誰 import：{names(sorted(imported_by.get(path, [])))}", ""]
    return "\n".join(lines)


def render_flow(cat: dict) -> str:
    """流程圖：程式是方框、檔案是圓角框；箭頭方向就是資料流向。"""
    scripts = cat["scripts"]
    order_labels = cat["dimensions"]["order"]["values"]
    ids: dict[str, str] = {}

    def nid(key: str) -> str:
        return ids.setdefault(key, f"n{len(ids)}")

    def file_node(name: str) -> str:
        shape = f'{nid("f:" + name)}(["{name.removeprefix("ext:")}"])'
        return shape + (":::ext" if name.startswith("ext:") else ":::file")

    out = ["flowchart TD"]
    # 每個階段一個子圖；跨多個階段的程式放在它最早的那個階段
    groups: dict[str, list[str]] = {}
    # 只有被 import 的函式庫沒有讀寫檔案，不畫進來（它們在 relations.md）
    for path, info in scripts.items():
        if info.get("reads") or info.get("writes") or info.get("calls"):
            groups.setdefault(min(info.get("order", ["基礎設施"])), []).append(path)
    for key in sorted(groups):
        title = f"{key} {order_labels[key]}" if key in order_labels else key
        out.append(f'  subgraph g{key if key in order_labels else "x"}["{title}"]')
        for path in groups[key]:
            out.append(f'    {nid(path)}["{Path(path).name}"]')
        out.append("  end")
    # 同一批檔案（含 * 的寫法）合併成一個節點：以「寫」的寫法為準
    written = [w for info in scripts.values() for w in info.get("writes", [])]
    for path, info in scripts.items():
        for w in info.get("writes", []):
            out.append(f"  {nid(path)} --> {file_node(w)}")
        for r in info.get("reads", []):
            canon = next((w for w in written if matches(r, w)), r)
            out.append(f"  {file_node(canon)} --> {nid(path)}")
        for c in info.get("calls", []):
            target = nid(c) if c in scripts else file_node(c)
            out.append(f"  {nid(path)} -.->|執行| {target}")
    out += ["  classDef file fill:#eef,stroke:#88a",
            "  classDef ext fill:#fee,stroke:#a88"]
    lines = [BANNER, "# 資料流程圖", "",
             "方框是程式，圓角框是檔案（藍色在 repo 內，紅色是外部來源或外部程式）。"
             "實線箭頭是讀寫檔案，虛線是一支程式執行另一支。"
             "箭頭完全由 catalog.json 的 reads／writes／calls 決定；"
             "只被 import、自己不讀寫檔案的函式庫不在圖上，見 "
             "[每支程式的上下游](views/relations.md)。", "",
             "```mermaid", *out, "```", ""]
    return "\n".join(lines)


def render_claim(cat: dict, cid: str) -> str:
    claim, scripts = cat["claims"][cid], cat["scripts"]
    here = "code_map/claims"
    trust = cat["dimensions"]["trust"]["values"][claim["trust"]]

    def who(key):
        rows = [f"- {link(p, here)}：{i['desc']}" for p, i in scripts.items()
                if cid in i.get(key, [])]
        return rows or ["- （尚未登記）"]

    lines = [BANNER, f"# {claim['title']}", "",
             f"**{claim['value']}**　可信度：{trust}", "",
             "## 誤差怎麼讀", "", *[f"- {u}" for u in claim["uncertainty"]], "",
             "## 怎麼產生的", "", "```", claim["command"], "```", "",
             "結果檔：" + "、".join(link(f, here) for f in claim["result_files"]), "",
             claim["how_to_read"], "",
             "## 產生它的程式", "", *who("produces"), "",
             "## 驗證它的程式", "", *who("validates"), "",
             "## 相關限制", "",
             "見 " + link("LIMITATIONS.md", here) + " 的 "
             + "、".join(claim["limitations"]) + "。", "",
             "## 補充", "", *[f"- {n}" for n in claim["notes"]], ""]
    return "\n".join(lines)


def render_index(cat: dict, all_py: list[str], orphans: list[tuple[str, str]]) -> str:
    scripts = cat["scripts"]
    missing = [p for p in all_py if p not in scripts]
    lines = [BANNER, "# 程式地圖", "",
             "這個資料夾回答「這麼多程式，彼此是什麼關係」。檔案沒有搬動；"
             "每支程式在 [`catalog.json`](catalog.json) 裡貼了五種標籤，"
             "下面每一頁是同一份登記的不同排法。", "",
             "## 從哪裡開始看", "",
             "- [資料流程圖](FLOW.md)：誰的輸出是誰的輸入",
             "- [每支程式的上下游](views/relations.md)：讀、寫、import、被誰 import"]
    for dim in DIMS:
        lines.append(f"- [{cat['dimensions'][dim]['title']}](views/by_{dim}.md)")
    lines += ["", "## 結論", ""]
    for cid, claim in cat["claims"].items():
        lines.append(f"- [{claim['title']}](claims/{cid}.md)：{claim['value']}")
    lines += ["", "## 登記進度", "",
              f"已登記 {len(scripts)} 支，尚未登記 {len(missing)} 支"
              f"（`_archive/` 與 `__init__.py` 不計）。", ""]
    if orphans:
        lines += ["找不到來源的輸入檔（產生它的程式多半還沒登記）：", ""]
        lines += [f"- `{r}`，由 `{p}` 讀取" for p, r in orphans]
        lines.append("")
    if missing:
        lines += ["<details><summary>尚未登記的程式</summary>", ""]
        lines += [f"- `{p}`" for p in missing]
        lines += ["", "</details>", ""]
    lines += ["## 新增或搬動程式時", "",
              "1. 在 `catalog.json` 的 `scripts` 加上或修改那一筆（欄位說明在檔案開頭）。",
              "2. 執行 `python code_map/build_map.py` 重新生成頁面，一起 commit。",
              "3. CI 會跑 `--check`：路徑不存在、標籤值不合法、頁面沒重新生成都會擋下。", ""]
    return "\n".join(lines)


def build(cat: dict) -> tuple[dict[Path, str], list[str]]:
    """回傳（要寫的檔案 → 內容，嚴格模式才算錯的問題）。"""
    all_py = tracked_py()
    imports = {p: project_imports(p, all_py) for p in cat["scripts"] if (REPO / p).is_file()}
    orphans = orphan_inputs(cat, set(git_files()))
    pages = {HERE / "README.md": render_index(cat, all_py, orphans),
             HERE / "FLOW.md": render_flow(cat),
             HERE / "views" / "relations.md": render_relations(cat, imports)}
    for dim in DIMS:
        pages[HERE / "views" / f"by_{dim}.md"] = render_view(cat, dim)
    for cid in cat["claims"]:
        pages[HERE / "claims" / f"{cid}.md"] = render_claim(cat, cid)
    strict = [f"未登記：{p}" for p in all_py if p not in cat["scripts"]]
    strict += [f"找不到來源的輸入檔：{r}（{p} 讀取）" for p, r in orphans]
    return pages, strict


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="生成或檢查程式地圖")
    ap.add_argument("--check", action="store_true", help="不寫檔，只檢查")
    ap.add_argument("--strict", action="store_true",
                    help="（搭配 --check）未登記的 .py 與找不到來源的輸入檔也算錯")
    args = ap.parse_args()

    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    errors = validate(cat)
    if errors:
        print("catalog.json 有錯：\n  " + "\n  ".join(errors))
        return 1
    pages, strict = build(cat)

    if not args.check:
        for path, text in pages.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        print(f"已生成 {len(pages)} 頁；登記 {len(cat['scripts'])} 支程式。")
        return 0

    stale = [str(p.relative_to(REPO)) for p, text in pages.items()
             if not p.is_file() or p.read_text(encoding="utf-8") != text]
    if stale:
        errors.append("頁面跟 catalog.json 不一致，請重跑 python code_map/build_map.py：\n    "
                      + "\n    ".join(stale))
    if args.strict:
        errors += strict
    if errors:
        print("程式地圖檢查沒過：\n  " + "\n  ".join(errors))
        return 1
    print(f"程式地圖檢查通過（登記 {len(cat['scripts'])} 支"
          + ("" if args.strict else f"；嚴格模式下還有 {len(strict)} 項待補") + "）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
