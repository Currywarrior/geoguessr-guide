"""下載 geohints 圖鑑照片並壓成 WebP。

圖鑑共 11315 張，但同一國同一類線索往往有十幾張同質照片（例如日本的路樁
拍了 21 張），對學習沒有邊際效益。因此每個「國家 x 線索類型」最多取 PER_GROUP
張，約留下三分之一。

與 plonkit 不同，這裡的圖放在獨立的 storage 網域，沒有 Cloudflare 挑戰，
原圖已是 1280x800 的 JPEG，所以只要轉檔不用縮放。
"""

import io
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "assets" / "img" / "geohints"

PER_GROUP = 5
MAX_WIDTH = 1280
QUALITY = 82
WORKERS = 6
DELAY = 0.3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://geohints.com/",
}

_local = threading.local()
lock = threading.Lock()
counter = {"ok": 0, "skipped": 0, "failed": 0}
failures = []


def session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    return _local.s


def pick_urls():
    """每個國家每類線索最多取 PER_GROUP 張"""
    data = json.loads((RAW / "geohints.json").read_text(encoding="utf-8"))
    picked, seen = [], set()
    for path, items in data.items():
        c = Counter()
        for it in items:
            url = it.get("image")
            if not url or url in seen:
                continue
            k = it.get("country", "")
            if c[k] >= PER_GROUP:
                continue
            c[k] += 1
            seen.add(url)
            picked.append(url)
    return picked


def dest_for(url):
    """.../storage/bollards/bollard_2.jpg -> assets/img/geohints/bollards/bollard_2.webp

    旗幟與品牌 logo 是 SVG，向量檔不該轉點陣，原樣保留即可。
    """
    rel = url.split("/storage/", 1)[-1].lstrip("/")
    p = OUT / rel
    return p if p.suffix.lower() == ".svg" else p.with_suffix(".webp")


def process(url, total):
    dest = dest_for(url)
    if dest.exists():
        with lock:
            counter["skipped"] += 1
        return

    raw = None
    for i in range(4):
        try:
            r = session().get(url, headers=HEADERS, timeout=45)
        except requests.RequestException:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 429:
            time.sleep(15 * (i + 1))
            continue
        if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/"):
            raw = r.content
            break
        if r.status_code != 200:
            break

    if raw is None:
        with lock:
            failures.append(url)
            counter["failed"] += 1
        return

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.suffix.lower() == ".svg":
            dest.write_bytes(raw)
        else:
            im = Image.open(io.BytesIO(raw))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            if im.width > MAX_WIDTH:
                im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
            im.save(dest, "WEBP", quality=QUALITY, method=5)
    except Exception:
        with lock:
            failures.append(url)
            counter["failed"] += 1
        return

    with lock:
        counter["ok"] += 1
        if counter["ok"] % 200 == 0:
            print(f"已完成 {counter['ok']}/{total}", flush=True)
    time.sleep(DELAY)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    urls = pick_urls()
    print(f"精選後待下載 {len(urls)} 張（原始 11315 張），{WORKERS} 執行緒\n", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(lambda u: process(u, len(urls)), urls))

    (RAW / "geohints_images_failed.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    mb = sum(p.stat().st_size for p in OUT.rglob("*.webp")) / 1024 / 1024
    print(f"\n完成：新增 {counter['ok']}，跳過 {counter['skipped']}，失敗 {counter['failed']}")
    print(f"總體積 {mb:.0f} MB，耗時 {(time.time() - t0) / 60:.0f} 分鐘")


if __name__ == "__main__":
    main()
