"""下載 plonkit 圖片並壓成 WebP。

原圖多為 1920x1080 PNG，一張約 1.8MB，5629 張會超過 9GB。實測轉成寬 1280 的
WebP 後每張約 64KB，全站約 0.36GB，而 1280 寬對辨識電線桿、路標字體這類細節足夠。

Cloudflare 對 /images/ 路徑比 HTML 更敏感：缺 Referer 或 Sec-Fetch-Dest 會拿到
HTTP 200 但內容是 challenge 頁。所以每個回應都必須驗證真的是圖片才寫檔。
"""

import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "plonkit"
OUT = ROOT / "assets" / "img" / "plonkit"
FAILED = ROOT / "data" / "raw" / "plonkit_images_failed.json"

BASE = "https://www.plonkit.net"
MAX_WIDTH = 1280
QUALITY = 82
DELAY = 0.4      # 每個 worker 兩次請求之間的間隔
# 瓶頸不是頻寬（單張實測 7-8 MB/s）而是 Cloudflare cache MISS 回源 GCS，
# 偶發 9~18 秒的尖峰。純 I/O 等待，靠併發隱藏：實測 4 緒 0.33 張/秒、12 緒 0.72 張/秒。
# 但 12 緒會踩到 Cloudflare 限流（實測失敗率 11.7%，全是 429），降到 6 緒換取穩定。
WORKERS = 6
RETRIES = 5      # 429 要靠夠長的退避等過去，不能三次就放棄

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-origin",
}


def collect_urls():
    """掃過所有國家 JSON，收集 imageUrl 與 heroImage"""
    urls = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("imageUrl", "heroImage") and isinstance(v, str) and v.startswith("/"):
                    urls.add(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in RAW.glob("*.json"):
        walk(json.loads(f.read_text(encoding="utf-8")))
    return sorted(urls)


def dest_for(url):
    """/images/netherlands/Dutch_bollard.png -> assets/img/plonkit/netherlands/Dutch_bollard.webp"""
    rel = url[len("/images/"):] if url.startswith("/images/") else url.lstrip("/")
    return (OUT / rel).with_suffix(".webp")


_local = threading.local()


def get_session():
    """requests.Session 非執行緒安全，每個 worker 各自持有一個"""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def fetch_one(url):
    """回傳 (bytes, None) 或 (None, 錯誤說明)"""
    session = get_session()
    for i in range(RETRIES):
        try:
            r = session.get(BASE + url, headers=HEADERS, timeout=45)
        except requests.RequestException:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 429:
            time.sleep(15 * (i + 1))  # 限流退避：15/30/45/60/75 秒
            continue
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        # 關鍵驗證：Cloudflare challenge 會回 200 + text/html。
        # 但不能只信 Content-Type — .jfif 之類的副檔名伺服器不一定標成 image/*，
        # 所以退一步用檔頭 magic bytes 判斷是不是真的圖片。
        ctype = r.headers.get("Content-Type", "")
        head = r.content[:12]
        looks_like_image = (
            head.startswith(b"\xff\xd8\xff")          # JPEG
            or head.startswith(b"\x89PNG")            # PNG
            or head.startswith(b"GIF8")               # GIF
            or head[:4] == b"RIFF" and head[8:12] == b"WEBP"
        )
        if not ctype.startswith("image/") and not looks_like_image:
            time.sleep(5 * (i + 1))
            continue
        return r.content, None
    return None, "重試三次仍失敗"


counter = {"ok": 0, "skipped": 0, "failed": 0}
failures = []
lock = threading.Lock()


def process(url, total, t0):
    dest = dest_for(url)
    if dest.exists():
        with lock:
            counter["skipped"] += 1
        return

    raw, err = fetch_one(url)
    if raw is None:
        with lock:
            failures.append({"url": url, "error": err})
            counter["failed"] += 1
            print(f"失敗 {err}: {url}", flush=True)
        return

    try:
        im = Image.open(io.BytesIO(raw))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            h = round(im.height * MAX_WIDTH / im.width)
            im = im.resize((MAX_WIDTH, h), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "WEBP", quality=QUALITY, method=5)
    except Exception as e:
        with lock:
            failures.append({"url": url, "error": f"轉檔失敗 {type(e).__name__}"})
            counter["failed"] += 1
            print(f"轉檔失敗: {url}", flush=True)
        return

    with lock:
        counter["ok"] += 1
        done = counter["ok"]
        if done % 100 == 0:
            el = time.time() - t0
            rate = done / el if el else 0
            left = (total - done - counter["skipped"]) / rate / 60 if rate else 0
            print(f"已完成 {done}/{total}，{rate:.1f} 張/秒，預估剩餘 {left:.0f} 分鐘", flush=True)

    time.sleep(DELAY)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    urls = collect_urls()
    print(f"待處理圖片 {len(urls)} 張，{WORKERS} 執行緒\n", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(lambda u: process(u, len(urls), t0), urls))

    ok, skipped, failed = counter["ok"], counter["skipped"], counter["failed"]
    FAILED.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    total_mb = sum(p.stat().st_size for p in OUT.rglob("*.webp")) / 1024 / 1024
    print(f"\n完成：新增 {ok}，跳過 {skipped}，失敗 {failed}")
    print(f"總體積 {total_mb:.0f} MB，耗時 {(time.time() - t0) / 60:.0f} 分鐘")


if __name__ == "__main__":
    main()
