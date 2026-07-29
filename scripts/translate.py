"""把 plonkit 的英文說明批次翻成繁體中文。

譯文存在獨立的 data/translations.json（原文 -> 譯文），build_data.py 再把它
併進網站資料。這樣拆開的好處是：重建資料不會弄丟翻譯，翻譯也可以隨時中斷續跑。

用法：
    set GROQ_API_KEY=你的金鑰        (PowerShell: $env:GROQ_API_KEY="...")
    python scripts/translate.py           翻全部
    python scripts/translate.py --limit 50   先翻 50 條試水溫

金鑰請用環境變數，不要寫進檔案裡。
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "plonkit"
STORE = ROOT / "data" / "translations.json"

API = os.environ.get("GROQ_URL", "https://api.groq.com/openai/v1/chat/completions")
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
BATCH = 10          # 一次送幾條，太多容易讓模型漏譯或亂了順序
MAX_CHARS = 4000    # 單批原文字元上限，避免撞到 TPM

SYSTEM = """你是 GeoGuessr 攻略的專業譯者，把英文說明翻成台灣用語的繁體中文。

規則：
1. 保留 **粗體** 標記與 [文字](網址) 連結格式，網址原封不動。
2. 保留原文的換行與條列符號。
3. 地名用台灣慣用譯名（如 Saudi Arabia 沙烏地阿拉伯、New Zealand 紐西蘭、Laos 寮國）。
4. 固定術語：bollard 路樁、utility pole 電線桿、guardrail 護欄、chevron 轉彎標誌、
   licence plate 車牌、road line 道路標線、coverage 街景覆蓋、Google car Google 車、
   generation/gen 相機世代、rift 接圖裂縫、blur 模糊、trekker 徒步拍攝、
   follow car 跟拍車、meta 線索特徵。
5. 語言、文字、道路標誌等專有名稱若無通用中譯，保留英文原文。
6. 譯文要通順自然，不要逐字硬翻。

輸入是 JSON 陣列，輸出必須是等長的 JSON 陣列，只回傳陣列本身，不要加任何說明。"""


def collect_texts():
    """從原始資料抽出所有待譯字串（去重後保持穩定順序）"""
    seen, out = set(), []

    def add(t):
        if t and t.strip() and t not in seen:
            seen.add(t)
            out.append(t)

    def walk(o):
        if isinstance(o, dict):
            if o.get("kind") == "tip" and isinstance(o.get("data"), dict):
                for t in o["data"].get("text") or []:
                    add(t)
            # 段落標題大多由 build_data.py 的規則直接中文化，
            # 只有各國特有的（Kampala、National Parks…）需要送翻譯
            if "title" in o and "items" in o:
                add(o.get("title"))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in sorted(RAW.glob("*.json")):
        walk(json.loads(f.read_text(encoding="utf-8")))
    return out


def load_store():
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}


def save_store(store):
    STORE.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")


def call_groq(key, batch):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    for attempt in range(5):
        try:
            r = requests.post(API, json=body, headers=headers, timeout=120)
        except requests.RequestException as e:
            print(f"    連線失敗 {type(e).__name__}，等 5 秒", flush=True)
            time.sleep(5)
            continue

        if r.status_code == 429:
            wait = int(r.headers.get("retry-after", 0)) or 20 * (attempt + 1)
            print(f"    限流，等 {wait} 秒", flush=True)
            time.sleep(wait)
            continue
        if r.status_code != 200:
            print(f"    HTTP {r.status_code}: {r.text[:160]}", flush=True)
            if r.status_code in (401, 403):
                sys.exit("金鑰無效，請確認 GROQ_API_KEY")
            time.sleep(5)
            continue

        content = r.json()["choices"][0]["message"]["content"].strip()
        # 模型有時會用 ```json 包起來
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        try:
            out = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", content, re.S)
            if not m:
                print("    回傳不是 JSON，跳過這批", flush=True)
                return None
            try:
                out = json.loads(m.group(0))
            except json.JSONDecodeError:
                return None

        if isinstance(out, list) and len(out) == len(batch):
            return [str(x) for x in out]
        print(f"    數量不符（送 {len(batch)} 回 {len(out) if isinstance(out, list) else '?'}）", flush=True)
        return None

    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只翻前 N 條，用來試水溫")
    args = ap.parse_args()

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("請先設定環境變數 GROQ_API_KEY")

    texts = collect_texts()
    store = load_store()
    todo = [t for t in texts if t not in store]
    if args.limit:
        todo = todo[: args.limit]

    print(f"原文共 {len(texts)} 條，已翻 {len(store)} 條，這次要翻 {len(todo)} 條")
    print(f"模型 {MODEL}，每批 {BATCH} 條\n")
    if not todo:
        return

    done = failed = 0
    t0 = time.time()
    i = 0
    while i < len(todo):
        batch, chars = [], 0
        while i < len(todo) and len(batch) < BATCH and chars < MAX_CHARS:
            batch.append(todo[i])
            chars += len(todo[i])
            i += 1

        got = call_groq(key, batch)
        if got is None and len(batch) > 1:
            # 整批失敗就逐條再試一次，避免一顆老鼠屎壞掉十條
            got = []
            for one in batch:
                r = call_groq(key, [one])
                got.append(r[0] if r else None)

        if got is None:
            failed += len(batch)
        else:
            for src, dst in zip(batch, got):
                if dst:
                    store[src] = dst
                    done += 1
                else:
                    failed += 1
            save_store(store)

        el = time.time() - t0
        rate = done / el * 60 if el else 0
        left = (len(todo) - i) / rate if rate else 0
        print(f"[{i}/{len(todo)}] 已譯 {done}，失敗 {failed}，{rate:.0f} 條/分，剩約 {left:.0f} 分", flush=True)

    save_store(store)
    print(f"\n完成：新譯 {done}，失敗 {failed}，累計 {len(store)} 條")
    print("接著跑 python scripts/build_data.py 把譯文併進網站資料")


if __name__ == "__main__":
    main()
