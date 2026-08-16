# -*- coding: utf-8 -*-
"""把文獻引用的論文（開放取用版，優先 arXiv）下載並同步進 Zotero
（2026-08-15，使用者要求）。

**只處理有開放取用版本（主要是 arXiv 預印本）的文獻**——LIMITATIONS.md／
PAPER_OUTLINE.md／docs/ 引用的文獻裡，付費牆後面、找不到 arXiv 或其他
開放版本的（例如 Salpeter 1955 這種前 arXiv 時代的經典論文、Spitzer 1987
是一本書不是論文），不強行下載，留在 SKIPPED 清單裡讓使用者自己決定
要不要透過機構帳號取得。

ARXIV_IDS 是手動核對過的清單（每個 id 都用 arXiv API 查過標題、確認
跟 docs/ 裡的作者+年份引用對得上，過程見對話紀錄，不是盲目搜尋结果）。

用法：
    python scripts/tools/zotero_literature_sync.py            # 實際下載+同步
    python scripts/tools/zotero_literature_sync.py --dry-run  # 只列出會做什麼
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import httpx
from pyzotero import zotero

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent.parent.parent  # m45_membership/
ENV_PATH = HERE / ".env"
LIT_DIR = HERE / "literature"
TOP_COLLECTION = "M45 IMF 專案"
LIT_COLLECTION = "文獻"

# 每一項是 (arXiv id, 對應 docs/ 裡的引用寫法) ——後面那個純粹是給人看的
# 註解，程式不會用到，方便之後有人要核對引用是否漏掉。
ARXIV_IDS = [
    ("astro-ph/0009005", "Kroupa 2001"),
    ("astro-ph/0304382", "Chabrier 2003"),
    ("astro-ph/0406581", "Moraux+2003"),
    ("astro-ph/0211471", "Baumgardt & Makino 2003"),
    ("1002.2229", "Converse & Stahler 2010"),
    ("1007.0414", "Raghavan+2010"),
    ("1508.02120", "Gieles & Zocchi 2015（LIMEPY）"),
    ("1804.09368", "Evans+2018"),
    ("1811.04931", "Meingast & Alves 2019"),
    ("2004.07274", "Cantat-Gaudin & Anders 2020"),
    ("2008.04684", "Li+2020"),
    ("2012.03380", "Lindegren+2021"),
    ("2101.01660", "Pera+2021（pyUPMASK）"),
    ("2101.11641", "Rybizki+2022"),
    ("2106.07669", "Gentile Fusillo+2021"),
    ("2209.08259", "Bhattacharya+2022（M45 潮汐尾）"),
    ("2303.13424", "Hunt & Reffert 2023"),
    ("2403.08850", "Pang+2024（93 星團）"),
    ("2503.13280", "Liu, Shao & Li 2025"),
    ("2603.15779", "Rosen 2026"),
    ("2604.20722", "Mikhnevich+2026"),
    ("2606.05762", "Li+2026（PeTar）"),
    ("0801.3772", "Maíz Apellániz 2008"),
    ("1208.4498", "Bressan+2012"),
]

# 找過但沒確認到開放版本的——記在這裡不是因為懶得找，是找過而且列出
# 已知的付費／不存在管道，讓使用者自己判斷要不要用機構帳號取得。
SKIPPED = [
    ("Salpeter 1955, ApJ 121, 161",
     "前 arXiv 時代論文，沒有官方免費 PDF；NASA ADS 摘要頁"
     "（ui.adsabs.harvard.edu/abs/1955ApJ...121..161S）可查，"
     "全文需機構訂閱或 ADS 掃描檔付費/受限存取"),
    ("Sana et al. 2012, Science 337, 444",
     "查無 arXiv 預印本，Science 論文本身在付費牆後"),
    ("Adams et al. 2001, AJ 121",
     "查無 arXiv 預印本"),
    ("Jeffries 2007, MNRAS 381, 1169",
     "查無 arXiv 預印本"),
    ("Spitzer 1987",
     "這是一本書（Dynamical Evolution of Globular Clusters），不是單篇論文，"
     "沒有 PDF 可下載"),
]


def load_env(path: Path) -> dict:
    if not path.exists():
        print(f"錯誤：找不到 {path}")
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


def fetch_arxiv_meta(arxiv_id: str, client: httpx.Client) -> dict:
    """呼叫 arXiv API 拿標題/作者/摘要。arXiv 對這個 API 有速率限制
    （這次同步過程中實測連續呼叫會被 429），呼叫端自己控制間隔，
    這支函式只負責單次查詢＋重試。"""
    for attempt in range(5):
        try:
            resp = client.get("https://export.arxiv.org/api/query",
                              params={"id_list": arxiv_id})
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"    arXiv API 429（速率限制），等 {wait}s 重試...",
                      flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"    警告：查詢 {arxiv_id} 中繼資料失敗：{exc}")
            return {}
        xml = resp.text
        if "<entry>" not in xml:
            # arXiv API 對不存在／格式錯誤的 id 會回 HTTP 200 但沒有
            # <entry>，不是丟錯誤——不擋這個情況的話，下面會用
            # arxiv_id 字串本身當標題造出一筆假資料寫進 Zotero。
            print(f"    警告：{arxiv_id} 查無結果（arXiv 回傳空 feed，"
                  f"id 可能打錯或不存在），跳過這篇。")
            return {}
        title = re.search(r"<entry>.*?<title>(.*?)</title>", xml, re.S)
        authors = re.findall(r"<author>\s*<name>(.*?)</name>", xml, re.S)
        summary = re.search(r"<summary>(.*?)</summary>", xml, re.S)
        published = re.search(r"<published>(\d{4})-", xml)
        return {
            "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else arxiv_id,
            "authors": authors,
            "summary": re.sub(r"\s+", " ", summary.group(1)).strip() if summary else "",
            "year": published.group(1) if published else "",
        }
    print(f"    警告：{arxiv_id} 重試 5 次仍被限速，跳過這篇。")
    return {}


def get_or_create_collection(zot: zotero.Zotero, name: str,
                             parent_key: str | None) -> str:
    for c in zot.everything(zot.collections()):
        data = c["data"]
        if data["name"] == name and data.get("parentCollection", False) == (
                parent_key or False):
            return c["key"]
    payload = {"name": name}
    if parent_key:
        payload["parentCollection"] = parent_key
    resp = zot.create_collections([payload])
    key = list(resp["successful"].values())[0]["key"]
    print(f"  建立 collection：{name}（{key}）")
    return key


def item_exists(zot: zotero.Zotero, collection_key: str, title: str) -> bool:
    # zot.everything() 自動翻頁——這個 collection 目前遠小於單頁上限，
    # 但不加翻頁的話，一旦文獻累積超過一頁，找不到的項目會被誤判成
    # 「不存在」而重複建立，不如一開始就寫對。
    for it in zot.everything(zot.collection_items(collection_key,
                                                   itemType="journalArticle")):
        if it["data"].get("title") == title:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = load_env(ENV_PATH)
    zot = zotero.Zotero(env["ZOTERO_LIBRARY_ID"], env["ZOTERO_LIBRARY_TYPE"],
                        env["ZOTERO_API_KEY"])
    LIT_DIR.mkdir(exist_ok=True)

    top_key = None
    lit_key = None
    if not args.dry_run:
        top_key = get_or_create_collection(zot, TOP_COLLECTION, None)
        lit_key = get_or_create_collection(zot, LIT_COLLECTION, top_key)

    n_new, n_skip, n_fail = 0, 0, 0
    with httpx.Client(timeout=30.0) as client:
        for i, (arxiv_id, label) in enumerate(ARXIV_IDS):
            print(f"\n[{i+1}/{len(ARXIV_IDS)}] {label}（{arxiv_id}）")
            # arXiv 對 export.arxiv.org 的建議間隔是 3 秒一次請求，這次
            # 同步過程實測連續呼叫幾次就被 429——保守起見拉到 4 秒。
            if i > 0:
                time.sleep(4)

            pdf_path = LIT_DIR / f"{arxiv_id.replace('/', '_')}.pdf"
            if args.dry_run:
                print(f"    [dry-run] 會下載 {pdf_path.name}，同步進 Zotero")
                continue

            meta = fetch_arxiv_meta(arxiv_id, client)
            if not meta:
                n_fail += 1
                continue
            title = meta["title"]

            if item_exists(zot, lit_key, title):
                print(f"    已存在，跳過：{title}")
                n_skip += 1
                continue

            if not pdf_path.exists():
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
                try:
                    r = client.get(pdf_url, follow_redirects=True)
                    r.raise_for_status()
                except httpx.HTTPError as exc:
                    # 跟其餘失敗路徑（arXiv 中繼資料查詢、Zotero 建立
                    # 項目）一致：單篇失敗計入 n_fail 後跳過，不中斷
                    # 整批同步——一篇論文暫時的 4xx/5xx 不該讓後面
                    # 二十幾篇全部處理不到。
                    print(f"    錯誤：下載 {pdf_url} 失敗：{exc}")
                    n_fail += 1
                    continue
                pdf_path.write_bytes(r.content)
                print(f"    下載：{pdf_path.name}（{len(r.content)/1024:.0f} KB）")
            else:
                print(f"    已有本機檔案，重用：{pdf_path.name}")

            tmpl = zot.item_template("journalArticle")
            tmpl["title"] = title
            tmpl["creators"] = [
                {"creatorType": "author", "name": a} for a in meta["authors"]
            ] or tmpl.get("creators", [])
            tmpl["abstractNote"] = meta["summary"]
            tmpl["date"] = meta["year"]
            tmpl["url"] = f"https://arxiv.org/abs/{arxiv_id}"
            tmpl["archive"] = "arXiv"
            tmpl["archiveLocation"] = arxiv_id
            tmpl["collections"] = [lit_key]
            resp = zot.create_items([tmpl])
            if resp.get("failed"):
                print(f"    錯誤：Zotero 建立項目失敗：{resp['failed']}")
                n_fail += 1
                continue
            item_key = list(resp["successful"].values())[0]["key"]
            zot.attachment_simple([str(pdf_path)], item_key)
            print(f"    新增：{title}（{item_key}）")
            n_new += 1

    print(f"\n{'='*60}")
    print(f"{'[dry-run] ' if args.dry_run else ''}"
          f"完成：新增 {n_new}、跳過（已存在）{n_skip}、失敗 {n_fail}")
    print(f"\n以下 {len(SKIPPED)} 篇找不到開放取用版本，沒有下載："
          "（可用機構帳號自行取得）")
    for label, reason in SKIPPED:
        print(f"  - {label}：{reason}")


if __name__ == "__main__":
    main()
