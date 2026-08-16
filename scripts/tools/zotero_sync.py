# -*- coding: utf-8 -*-
"""把 docs/ 底下的規劃與教學文件同步進 Zotero（2026-08-15，使用者要求）。

**只處理專案自己寫的文件**（docs/planning、docs/reference、docs/reports、
docs/teaching），不處理文獻引用的論文 PDF——那些本體目前不在這個 repo
裡，需要另外搜尋才能同步，是分開的一項工作。

**冪等（可重複執行）**：每個 docs/ 底下的檔案在 Zotero 裡對應一個
document item + 一個檔案附件，用「同一個 collection 裡標題完全相同」
判斷是否已經同步過。已存在就跳過，不會每跑一次就多一份重複項目——
但也代表如果檔案內容改了，要重新同步同一份文件，必須先手動砍掉
Zotero 裡的舊項目，這支腳本不會自動偵測內容變更、不會自動更新附件
（v1 先求正確可用，比對版本用之後有需要再加）。

用法：
    python scripts/tools/zotero_sync.py            # 實際同步
    python scripts/tools/zotero_sync.py --dry-run  # 只列出會做什麼，不寫入
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyzotero import zotero

# Windows 終端機預設用 cp950（Big5）當 stdout 編碼，中文輸出會亂碼
# （這台機器實測 sys.stdout.encoding 是 cp950）。改成 UTF-8 才會正常顯示。
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent.parent.parent  # m45_membership/
DOCS = HERE / "docs"
ENV_PATH = HERE / ".env"

# docs/ 底下要同步的子資料夾，對應 Zotero 裡的子 collection 名稱。
# 沒列在這裡的子資料夾（例如未來新增的）不會被同步——刻意白名單制，
# 避免哪天 docs/ 底下混進不該同步的東西（草稿、暫存檔）也被一起丟上去。
SUBFOLDERS = {
    "planning": "規劃",
    "reference": "參考資料",
    "reports": "報告",
    "teaching": "教學文件",
}
TOP_COLLECTION = "M45 IMF 專案"


def load_env(path: Path) -> dict:
    """簡易 .env 解析，不依賴 python-dotenv（專案主環境沒裝這個套件，
    為了一支同步腳本額外加依賴不划算）。"""
    if not path.exists():
        print(f"錯誤：找不到 {path}，請先建立（含 ZOTERO_API_KEY／"
              f"ZOTERO_LIBRARY_ID／ZOTERO_LIBRARY_TYPE 三個變數）。")
        sys.exit(1)
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    missing = [k for k in ("ZOTERO_API_KEY", "ZOTERO_LIBRARY_ID",
                            "ZOTERO_LIBRARY_TYPE") if not env.get(k)]
    if missing:
        print(f"錯誤：{path} 缺少或空白：{', '.join(missing)}")
        sys.exit(1)
    return env


def title_of(md_path: Path) -> str:
    """優先取檔案第一行的 H1 標題（# 開頭），沒有就用檔名（去掉副檔名）。"""
    for line in md_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line:
            break
    return md_path.stem


def get_or_create_collection(zot: zotero.Zotero, name: str,
                             parent_key: str | None, dry_run: bool) -> str | None:
    # zot.everything() 自動翻頁——不加的話，collection 數量一旦超過
    # 單頁上限，找不到既有 collection 會被誤判成「不存在」而重複建立。
    existing = zot.everything(zot.collections())
    for c in existing:
        data = c["data"]
        if data["name"] == name and data.get("parentCollection", False) == (
                parent_key or False):
            return c["key"]
    if dry_run:
        print(f"  [dry-run] 會建立 collection：{name}"
              f"{'（子集合，父層 ' + parent_key + '）' if parent_key else ''}")
        return None
    payload = {"name": name}
    if parent_key:
        payload["parentCollection"] = parent_key
    resp = zot.create_collections([payload])
    key = list(resp["successful"].values())[0]["key"]
    print(f"  建立 collection：{name}（{key}）")
    return key


def item_exists(zot: zotero.Zotero, collection_key: str, title: str) -> bool:
    for it in zot.everything(zot.collection_items(collection_key,
                                                   itemType="document")):
        if it["data"].get("title") == title:
            return True
    return False


def sync_file(zot: zotero.Zotero, collection_key: str | None, md_path: Path,
              dry_run: bool):
    title = title_of(md_path)
    if dry_run:
        # dry-run 時 collection 可能還沒真的建立（collection_key 是
        # None），沒有真實 key 可查詢既有項目，只能單純列出檔案本身。
        print(f"    [dry-run] 會新增：{title}（{md_path.relative_to(HERE)}）")
        return
    if item_exists(zot, collection_key, title):
        print(f"    已存在，跳過：{title}")
        return
    tmpl = zot.item_template("document")
    tmpl["title"] = title
    tmpl["abstractNote"] = f"M45 IMF 專案文件，來源檔案 {md_path.relative_to(HERE)}"
    # 直接在建立時把 collections 填進 item template，不要建好後再呼叫
    # addto_collection()——那個方法要吃 create_items() 回傳的完整 item
    # dict（含 version），這裡拿到的只是 item_key 字串，多一趟往返也
    # 多一種要對齊資料格式的方式，不如一開始就指定好。
    tmpl["collections"] = [collection_key]
    resp = zot.create_items([tmpl])
    if resp.get("failed"):
        print(f"    錯誤：Zotero 建立項目失敗：{resp['failed']}")
        return
    item_key = list(resp["successful"].values())[0]["key"]
    zot.attachment_simple([str(md_path)], item_key)
    print(f"    新增：{title}（{item_key}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="只列出會做什麼，不實際寫入 Zotero")
    args = ap.parse_args()

    env = load_env(ENV_PATH)
    zot = zotero.Zotero(env["ZOTERO_LIBRARY_ID"], env["ZOTERO_LIBRARY_TYPE"],
                        env["ZOTERO_API_KEY"])

    if not DOCS.exists():
        print(f"錯誤：找不到 {DOCS}")
        sys.exit(1)

    top_key = get_or_create_collection(zot, TOP_COLLECTION, None, args.dry_run)
    if top_key is None and not args.dry_run:
        print("錯誤：頂層 collection 建立失敗")
        sys.exit(1)

    total_new, total_skip = 0, 0
    for subdir, zh_name in SUBFOLDERS.items():
        folder = DOCS / subdir
        if not folder.exists():
            continue
        md_files = sorted(folder.glob("*.md"))
        if not md_files:
            continue
        print(f"\n{zh_name}（docs/{subdir}/，{len(md_files)} 份）：")
        sub_key = get_or_create_collection(zot, zh_name, top_key, args.dry_run)
        for md in md_files:
            sync_file(zot, sub_key, md, args.dry_run)

    print(f"\n{'[dry-run] ' if args.dry_run else ''}完成。")


if __name__ == "__main__":
    main()
