"""抓取 plonkit.net 全站國家攻略資料。

plonkit 是 Vite 打包的 SPA，但每頁 HTML 內嵌了 <script id="__PRELOADED_DATA__">，
裡面就是該頁完整的結構化 JSON，所以不需要跑瀏覽器渲染，純 HTTP 就能取得。

注意：站台掛 Cloudflare，缺少瀏覽器 headers 的請求會拿到 challenge 頁（HTTP 200
但內容是 "Just a moment..."），所以下面的 HEADERS 不能精簡。
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://www.plonkit.net"
OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "plonkit"
DELAY = 0.7  # 每個請求間隔，禮貌爬避免被 ban

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

PRELOAD_RE = re.compile(
    r'<script id="__PRELOADED_DATA__" type="application/json">(.*?)</script>', re.S
)


def extract(html):
    """從頁面 HTML 取出內嵌的 JSON，取不到就回 None（代表被擋或版型變了）"""
    m = PRELOAD_RE.search(html)
    return json.loads(m.group(1)) if m else None


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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    print("取得國家清單...")
    html = get(session, f"{BASE}/guide")
    index = extract(html) if html else None
    if not index:
        sys.exit("拿不到 guide 頁，可能被 Cloudflare 擋了")

    countries = index["data"]
    (OUT.parent / "plonkit_index.json").write_text(
        json.dumps(countries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"共 {len(countries)} 個條目\n")

    ok = skipped = failed = 0
    for i, c in enumerate(countries, 1):
        slug = c["slug"]
        dest = OUT / f"{slug}.json"
        if dest.exists():
            skipped += 1
            continue

        print(f"[{i}/{len(countries)}] {c['title']}")
        html = get(session, f"{BASE}/{slug}")
        data = extract(html) if html else None
        if not data:
            print("    失敗")
            failed += 1
            continue

        dest.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        ok += 1
        time.sleep(DELAY)

    print(f"\n完成：新抓 {ok}，已存在跳過 {skipped}，失敗 {failed}")


if __name__ == "__main__":
    main()
