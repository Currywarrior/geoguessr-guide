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
# 免費層的配額是「每個模型每天 N 次請求」，所以清單裡每個模型都是一桶獨立額度，
# 一桶用完就換下一桶，能把單日產出乘上好幾倍。
MODEL_PREFS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
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

# 免費層卡的是每日請求「次數」（gemini-2.5-flash 只有 20 次／天）而不是 token 量，
# 所以一批要盡量塞滿：實測 100 條／13000 字元仍能完整回傳且不漏譯。
# 真的漏譯也不怕，call 失敗會對半切重試（見 translate_split）。
BATCH = int(os.environ.get("GROQ_BATCH", 100))
MAX_CHARS = int(os.environ.get("GROQ_MAX_CHARS", 13000))

SYSTEM = """你是 GeoGuessr 攻略的專業譯者，把英文說明翻成台灣用語的繁體中文。

規則：
1. 保留 **粗體** 標記與 [文字](網址) 連結格式。
   網址一個字元都不能改（尤其不要把 .org 改成 .com），連結數量也必須與原文相同。
   中括號裡的顯示文字要翻成中文，不要整條連結留著英文不翻。
   粗體只能出現在原文標了 ** 的位置，數量必須與原文完全相同。
   絕對不要自行替術語或你覺得重要的詞加粗，原文沒標就不要標。
   粗體「裡面」的文字同樣要翻成中文，不要因為它被標了粗體就整段留英文。
   例如 **2 green numbers** 要翻成 **兩個綠色數字**、**Beech forests** 翻成 **山毛櫸林**。
   只有地名、標誌牌面上的原文（ALTO、BERHENTI）、語言後綴（-owo、-weiler）
   這類本身就是辨識線索的東西才保留原文。
2. 保留原文的換行與條列符號。
3. 地名用台灣慣用譯名（如 Saudi Arabia 沙烏地阿拉伯、New Zealand 紐西蘭、Laos 寮國）。
4. 固定術語：bollard 路樁、utility pole 電線桿、guardrail 護欄、chevron 轉彎標誌、
   licence plate 車牌、road line 道路標線、coverage 街景覆蓋、Google car Google 車、
   generation/gen 相機世代、rift 接圖裂縫、blur 模糊、trekker 徒步拍攝、
   follow car 跟拍車、meta 線索特徵、eucalyptus 尤加利樹。
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


def call_name(mid):
    """Gemini 列表回傳 models/xxx，但呼叫時要用不含前綴的 xxx。
    Groq 的 openai/gpt-oss-120b 那個斜線是名字的一部分，不能動。"""
    return mid[len("models/"):] if mid.startswith("models/") else mid


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
            return call_name(bare[m])
        if m.rsplit("/", 1)[-1] in bare:
            return call_name(bare[m.rsplit("/", 1)[-1]])

    # 偏好清單全都不在，就挑一個穩定的對話模型（避開預覽版與非對話模型）
    for name in sorted(bare):
        low = name.lower()
        if any(k in low for k in AVOID):
            continue
        if "flash" in low or "gpt-oss" in low or "qwen" in low or "llama" in low:
            return call_name(bare[name])
    for name in sorted(bare):
        if not any(k in name.lower() for k in AVOID):
            return call_name(bare[name])
    return MODEL_PREFS[0]


def candidate_models(key):
    """照偏好順序列出帳號真的有的模型，當日額度用完就換下一個接著跑"""
    if MODEL:
        return [MODEL]
    ids = list_models(key)
    bare = {}
    for i in ids:
        bare.setdefault(i.rsplit("/", 1)[-1], i)

    out = []
    for m in MODEL_PREFS:
        hit = bare.get(m) or bare.get(m.rsplit("/", 1)[-1])
        if hit:
            name = call_name(hit)
            if name not in out:
                out.append(name)
    return out or [pick_model(key)]


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
    # 一批 100 條的譯文約 8 到 11k token，預設上限可能只有 8192 會被截斷成半截 JSON，
    # 開大留餘裕（實測 200 條會漏譯所以沒往上調 BATCH，這裡純粹是保險）
    body = {"model": model, "messages": msgs, "temperature": 0.2, "max_tokens": 32768}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    for attempt in range(5):
        try:
            r = requests.post(API, json=body, headers=headers, timeout=120)
        except requests.RequestException as e:
            print(f"    連線失敗 {type(e).__name__}，等 5 秒", flush=True)
            time.sleep(5)
            continue

        if r.status_code == 429:
            # 每日配額用盡就別再空轉，直接換模型或收工，重跑會從斷點接續。
            # Gemini 現在回的是 quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier，
            # 沒有空格也沒有 daily 字樣，所以認 perday；而且這個欄位在 JSON 後段，
            # 截斷成前 800 字元會剛好把它切掉，一定要比對完整回應。
            low = r.text.lower()
            if "per day" in low or "perday" in low or "tpd" in low or "daily" in low:
                print(f"    這個模型今日配額已用完（{model}）", flush=True)
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


def translate_split(key, batch, model, no_system, depth=0):
    """整批失敗（漏譯、亂序、回傳被截斷）就對半切再試。

    不逐條重試是因為免費層限的是請求次數：100 條逐條重試要燒 100 次，
    對半切最多只多花 log2 次，代價差了兩個數量級。
    """
    got = call_groq(key, batch, model, no_system)
    if got in ("QUOTA", "NO_SYSTEM") or got is not None:
        return got
    if len(batch) == 1 or depth >= 4:
        return None

    mid = len(batch) // 2
    out = []
    for half in (batch[:mid], batch[mid:]):
        r = translate_split(key, half, model, no_system, depth + 1)
        if r in ("QUOTA", "NO_SYSTEM"):
            return r
        out.extend(r if r else [None] * len(half))
    return out


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

    models = candidate_models(key)
    mi = 0
    print(f"原文共 {len(texts)} 條，已翻 {len(store)} 條，這次要翻 {len(todo)} 條")
    print(f"每批 {BATCH} 條，模型依序用：{'、'.join(models)}\n")
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

        got = translate_split(key, batch, models[mi], no_system)
        if got == "NO_SYSTEM":
            no_system = True
            print("    這個模型不吃 system 角色，改把規則併進訊息重試", flush=True)
            got = translate_split(key, batch, models[mi], True)
        if got == "QUOTA":
            save_store(store)
            mi += 1
            if mi < len(models):
                print(f"    換下一個模型 {models[mi]} 接著跑（每個模型有獨立的每日額度）", flush=True)
                i -= len(batch)      # 這批沒翻到，退回去用新模型重跑
                continue
            print(f"\n所有模型今日額度都用完，已存檔（新譯 {done} 條，累計 {len(store)} 條）")
            print("明天再跑一次同樣的指令就會從斷點接續")
            return

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
        print(f"[{i}/{len(todo)}] 已譯 {done}，失敗 {failed}，{rate:.0f} 條/分，"
              f"剩約 {left:.0f} 分（{models[mi]}）", flush=True)

    save_store(store)
    print(f"\n完成：新譯 {done}，失敗 {failed}，累計 {len(store)} 條")
    print("接著跑 python scripts/build_data.py 把譯文併進網站資料")


if __name__ == "__main__":
    main()
