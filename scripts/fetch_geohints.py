"""抓取 geohints.com 的線索圖鑑。

geohints 與 plonkit 互補：plonkit 按國家組織（適合賽前複習某國），
geohints 按線索類型組織（適合遊戲中看到一根怪電線桿反查是哪國）。

站台用 htmx，但預設內容直接寫在 HTML 裡，純 HTTP 就能解析。
每個條目的結構固定：
    <div class="text-white text-md p-2">
      <span class="font-bold">國名</span>
      <img src="...storage/bollards/bollard_2.jpg">
      <a href="https://goo.gl/maps/...">Open in Google Maps</a>
    </div>
"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://geohints.com"
OUT = Path(__file__).resolve().parent.parent / "data" / "raw"
DELAY = 0.7

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def get(session, url, tries=3):
    for i in range(tries):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.text
            print(f"    HTTP {r.status_code}，重試 {i + 1}/{tries}")
        except requests.RequestException as e:
            print(f"    {type(e).__name__}，重試 {i + 1}/{tries}")
        time.sleep(2 * (i + 1))
    return None


def list_categories(html):
    """從首頁導覽取出所有 /meta/... 類別路徑，不寫死清單"""
    soup = BeautifulSoup(html, "html.parser")
    paths = set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if h.startswith("/meta/"):
            paths.add(h)
    return sorted(paths)


def parse_page(html):
    """解析單一類別頁，回傳條目清單"""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id="search-results") or soup
    items = []
    for div in root.select("div.text-white.text-md.p-2"):
        img = div.find("img")
        if not img or not img.get("src") or "/storage/" not in img["src"]:
            continue
        name = div.find("span", class_="font-bold")
        link = div.find("a", href=True)
        items.append(
            {
                "country": name.get_text(strip=True) if name else "",
                "image": img["src"],
                "maps_link": link["href"] if link else "",
                "width": img.get("width"),
                "height": img.get("height"),
            }
        )
    return items


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    print("取得類別清單...")
    home = get(session, BASE + "/")
    if not home:
        raise SystemExit("拿不到首頁")
    cats = list_categories(home)
    print(f"共 {len(cats)} 個類別頁\n")

    result = {}
    total = 0
    for i, path in enumerate(cats, 1):
        html = get(session, BASE + path)
        if not html:
            print(f"[{i}/{len(cats)}] {path} 失敗")
            continue
        items = parse_page(html)
        result[path] = items
        total += len(items)
        print(f"[{i}/{len(cats)}] {path:<34} {len(items):>4} 條")
        time.sleep(DELAY)

    (OUT / "geohints.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    imgs = {it["image"] for items in result.values() for it in items}
    print(f"\n完成：{len(result)} 個類別，{total} 條，不重複圖片 {len(imgs)} 張")


if __name__ == "__main__":
    main()
