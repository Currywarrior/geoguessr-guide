"""把 plonkit 的英文說明批次翻成繁體中文。

譯文存在獨立的 data/translations.json（原文 -> 譯文），build_data.py 再把它
併進網站資料。這樣拆開的好處是：重建資料不會弄丟翻譯，翻譯也可以隨時中斷續跑。

用法（PowerShell）：
    $env:GROQ_API_KEY="你的金鑰"
    python scripts/translate.py --limit 50   先翻 50 條試水溫
    python scripts/translate.py              翻全部

金鑰請用環境變數，不要寫進檔案裡。

服務商可換，兩家都是 OpenAI 相容格式，模型會自動偵測：

    Groq   （預設）免費層每日 token 上限低，全站要分約 10 天跑完
    Gemini  沒有每日 token 上限、只限 1500 次請求／天，而全站只需 784 次，
            約 80 分鐘就能跑完。改成這樣即可：
              $env:GROQ_BASE="https://generativelanguage.googleapis.com/v1beta/openai"
              $env:GROQ_API_KEY="你的 Gemini 金鑰"

不論用哪家，撞到當日配額都會自動存檔收工，隔天重跑會從斷點接續。
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

BASE = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")
API = BASE + "/chat/completions"

# 服務商會汰換模型（llama-3.3-70b-versatile 已於 2026-06 棄用），所以不寫死：
# 啟動時查一次可用清單，照偏好順序挑第一個存在的。
# 清單同時涵蓋 Groq 與 Gemini，換服務商只要改 GROQ_BASE。
MODEL_PREFS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
]

# 備援挑選時要避開的：實驗版、預覽版，以及根本不是拿來對話的模型
AVOID = (
    "preview", "experimental", "exp-", "thinking", "antigravity",
    "image", "vision", "tts", "audio", "embedding", "whisper", "guard", "learnlm",
)
MODEL = os.environ.get("GROQ_MODEL", "")

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


def list_models(key):
    try:
        r = requests.get(BASE + "/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        if r.status_code != 200:
            print(f"查詢模型失敗 HTTP {r.status_code}: {r.text[:160]}")
            return []
        return [m["id"] for m in r.json().get("data", [])]
    except requests.RequestException as e:
        print(f"查詢模型失敗 {type(e).__name__}")
        return []


def pick_model(key):
    """查一次帳號可用的模型，照 MODEL_PREFS 挑，避免寫死的名字被官方下架"""
    if MODEL:
        return MODEL
    ids = list_models(key)
    # Gemini 的 OpenAI 相容端點回傳 "models/gemini-2.5-flash" 這種帶前綴的 id，
    # 直接比對會全部落空，要先把前綴剝掉再對。
    bare = {}
    for i in ids:
        bare.setdefault(i.rsplit("/", 1)[-1], i)

    for m in MODEL_PREFS:
        if m in bare:
            return bare[m]
        if m.rsplit("/", 1)[-1] in bare:
            return bare[m.rsplit("/", 1)[-1]]

    # 偏好清單全都不在，就挑一個穩定的對話模型（避開預覽版與非對話模型）
    for name in sorted(bare):
        low = name.lower()
        if any(k in low for k in AVOID):
            continue
        if "flash" in low or "gpt-oss" in low or "qwen" in low or "llama" in low:
            return bare[name]
    for name in sorted(bare):
        if not any(k in name.lower() for k in AVOID):
            return bare[name]
    return MODEL_PREFS[0]


def show_limits(r):
    """把剩餘額度印出來，免費層每日上限會先撞到，要讓使用者看得見"""
    h = r.headers
    parts = []
    for k, label in (("x-ratelimit-remaining-tokens", "本分鐘剩餘 token"),
                     ("x-ratelimit-remaining-requests", "今日剩餘請求")):
        if h.get(k):
            parts.append(f"{label} {h[k]}")
    return "，".join(parts)


def call_groq(key, batch, model, no_system=False):
    payload = json.dumps(batch, ensure_ascii=False)
    if no_system:
        # 有些模型不吃 system role，就把規則併進使用者訊息
        msgs = [{"role": "user", "content": SYSTEM + "\n\n輸入：\n" + payload}]
    else:
        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": payload},
        ]
    body = {"model": model, "messages": msgs, "temperature": 0.2}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    for attempt in range(5):
        try:
            r = requests.post(API, json=body, headers=headers, timeout=120)
        except requests.RequestException as e:
            print(f"    連線失敗 {type(e).__name__}，等 5 秒", flush=True)
            time.sleep(5)
            continue

        if r.status_code == 429:
            msg = r.text[:200]
            # 每日配額用盡就別再空轉，直接收工，明天重跑會從斷點接續
            if "per day" in msg or "TPD" in msg or "daily" in msg.lower():
                print(f"    今日配額已用完：{msg[:120]}", flush=True)
                return "QUOTA"
            wait = int(float(r.headers.get("retry-after", 0))) or 20 * (attempt + 1)
            print(f"    限流，等 {wait} 秒（{show_limits(r)}）", flush=True)
            time.sleep(wait)
            continue
        if r.status_code != 200:
            body_txt = r.text[:200]
            # 該模型不支援 system role，改把規則併進 user 訊息重來
            if r.status_code == 400 and "instruction" in body_txt.lower() and not no_system:
                return "NO_SYSTEM"
            print(f"    HTTP {r.status_code}: {body_txt[:160]}", flush=True)
            if r.status_code in (401, 403):
                sys.exit("金鑰無效，請確認 GROQ_API_KEY")
            if r.status_code == 404:
                sys.exit(f"模型 {model} 不存在，可用 GROQ_MODEL 指定，或跑 --list-models 看有哪些")
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
    ap.add_argument("--list-models", action="store_true", help="列出帳號可用的模型就結束")
    args = ap.parse_args()

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("請先設定環境變數 GROQ_API_KEY")

    if args.list_models:
        ids = list_models(key)
        print(f"可用模型 {len(ids)} 個：")
        for i in sorted(ids):
            print("   ", i)
        print(f"\n自動會挑：{pick_model(key)}")
        return

    texts = collect_texts()
    store = load_store()
    todo = [t for t in texts if t not in store]
    if args.limit:
        todo = todo[: args.limit]

    model = pick_model(key)
    print(f"原文共 {len(texts)} 條，已翻 {len(store)} 條，這次要翻 {len(todo)} 條")
    print(f"模型 {model}，每批 {BATCH} 條\n")
    if not todo:
        return

    done = failed = 0
    no_system = False
    t0 = time.time()
    i = 0
    while i < len(todo):
        batch, chars = [], 0
        while i < len(todo) and len(batch) < BATCH and chars < MAX_CHARS:
            batch.append(todo[i])
            chars += len(todo[i])
            i += 1

        got = call_groq(key, batch, model, no_system)
        if got == "NO_SYSTEM":
            no_system = True
            print("    這個模型不吃 system 角色，改把規則併進訊息重試", flush=True)
            got = call_groq(key, batch, model, True)
        if got == "QUOTA":
            save_store(store)
            print(f"\n今日免費額度用完，已存檔（新譯 {done} 條，累計 {len(store)} 條）")
            print("明天再跑一次同樣的指令就會從斷點接續")
            return
        if got is None and len(batch) > 1:
            # 整批失敗就逐條再試一次，避免一顆老鼠屎壞掉十條
            got = []
            for one in batch:
                r = call_groq(key, [one], model, no_system)
                got.append(r[0] if r and r != "QUOTA" else None)

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
