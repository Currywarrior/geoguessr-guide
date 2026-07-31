"""把 plonkit 與 geohints 的原始資料合併成網站用的統一格式。

輸入有三種形態：
  1. plonkit 國家攻略  — 一國一篇，帶圖說明，少數條目自帶線索標籤
  2. geohints 線索圖鑑 — 一類線索一頁，列出各國的實例照片
  3. geohints 對照表   — 一類線索一頁，列出各國的值（左駕右駕、區碼、網域…）

輸出兩份索引，指向同一批條目：
  countries.json — 按國家查（賽前複習某國）
  clues.json     — 按線索查（遊戲中看到一根怪電線桿反查是哪國）

最麻煩的是線索維度。plonkit 只有 24.4% 的條目自帶標籤，其餘要靠內文關鍵字
補標；而兩站的線索詞彙又不一致（plonkit 13 種、geohints 50 種），所以下面
用 CLUE_TYPES 定義一套統一詞彙，兩站的原生分類各自映射過來。
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "site"

# 必須與 fetch_geohints_images.py 的 PER_GROUP 相同
PER_GROUP = 5


# ---------------------------------------------------------------- 國家正規化

# 兩站對同一國的稱呼不一致，以 plonkit 的寫法為準
# 右邊必須寫成 norm_country 處理過的形式（小寫、& 已展開成 and、無重音）
ALIASES = {
    "czech republic": "czechia",
    "united states": "united states of america",
    "usa": "united states of america",
    "cocos keeling islands": "cocos islands",
    "israel": "israel and the west bank",
    "west bank": "israel and the west bank",
    "south georgia and the south sandwich islands": "south georgia and sandwich islands",
    "south sandwich islands": "south georgia and sandwich islands",
    "macao": "macau",
    "myanmar burma": "myanmar",
    "the bahamas": "bahamas",
    "the gambia": "gambia",
}

# 對照表裡的字面值，不是國家
NOT_A_COUNTRY = {"nothing", "islands", "man", "unknown", ""}

# plonkit 有些頁面不是國家，不該進入國家索引
NON_COUNTRY_SLUGS = {
    "maps", "middle-earth", "spillover-countries",
    "beginners-guide-to-geoguessr", "beginner-s-guide-to-geoguessr",
}


def norm_country(name):
    """統一國名寫法：去重音、去標點、小寫，再套別名表"""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " and ").replace("’", "'")
    s = re.sub(r"[^\w\s'-]", " ", s).lower()
    s = re.sub(r"\s+", " ", s).strip()
    s = ALIASES.get(s, s)
    return "" if s in NOT_A_COUNTRY else s


# ---------------------------------------------------------------- 線索詞彙表

# key 是統一代號，plonkit 與 geohints 的原生分類都映射到這裡
CLUE_TYPES = {
    "bollards":       {"en": "Bollards",        "zh": "路樁"},
    "utility_poles":  {"en": "Utility Poles",   "zh": "電線桿"},
    "lines":          {"en": "Road Lines",      "zh": "道路標線"},
    "chevrons":       {"en": "Chevrons",        "zh": "轉彎標誌"},
    "guardrails":     {"en": "Guardrails",      "zh": "護欄"},
    "license_plates": {"en": "License Plates",  "zh": "車牌"},
    "signs":          {"en": "Signs",           "zh": "路標"},
    "bus_stops":      {"en": "Bus Stops",       "zh": "公車站"},
    "railway":        {"en": "Railway Crossings", "zh": "鐵路平交道"},
    "road_numbering": {"en": "Road Numbering",  "zh": "公路編號"},
    "street_names":   {"en": "Street Name Signs", "zh": "路名牌"},
    "traffic_lights": {"en": "Traffic Lights",  "zh": "紅綠燈"},
    "sidewalks":      {"en": "Sidewalks",       "zh": "人行道"},
    "house_numbers":  {"en": "House Numbers",   "zh": "門牌"},
    "post_boxes":     {"en": "Post Boxes",      "zh": "郵筒"},
    "architecture":   {"en": "Architecture",    "zh": "建築"},
    "nature":         {"en": "Nature",          "zh": "植被與地貌"},
    "scenery":        {"en": "Scenery",         "zh": "景觀"},
    "snow":           {"en": "Snow",            "zh": "積雪"},
    "language":       {"en": "Language",        "zh": "語言文字"},
    "domains":        {"en": "Domains",         "zh": "網域"},
    "phone_numbers":  {"en": "Phone Numbers",   "zh": "電話區碼"},
    "currencies":     {"en": "Currencies",      "zh": "貨幣"},
    "driving_side":   {"en": "Driving Side",    "zh": "行車方向"},
    "flags":          {"en": "Flags",           "zh": "旗幟"},
    "google_vehicles": {"en": "Google Vehicles", "zh": "Google 拍攝載具"},
    "follow_cars":    {"en": "Follow Cars",     "zh": "跟拍車"},
    "camera":         {"en": "Camera Generation", "zh": "相機世代"},
    "rifts":          {"en": "Rifts",           "zh": "接圖裂縫"},
    "coverage":       {"en": "Coverage",        "zh": "街景覆蓋特徵"},
    "companies":      {"en": "Companies",       "zh": "商家品牌"},
    "gas_stations":   {"en": "Gas Stations",    "zh": "加油站"},
    "years":          {"en": "Coverage Years",  "zh": "拍攝年份"},
    "street_suffix":  {"en": "Street Suffixes", "zh": "街道後綴"},
    "animals":        {"en": "Animals",         "zh": "動物"},
}

# plonkit 的 13 種原生標籤 → 統一代號
PLONKIT_TAG_MAP = {
    "pole": "utility_poles",
    "bollard": "bollards",
    "landscape": "scenery",
    "chevron/sign": "chevrons",
    "coverage": "coverage",
    "guardrail": "guardrails",
    "architecture": "architecture",
    "vegetation": "nature",
    "language": "language",
    "roadline": "lines",
    "moving info": "coverage",
    "license plates": "license_plates",
    # "important" 不是線索類型，是 plonkit 用來標記重點條目的，另外處理
}

# geohints 的類別路徑 → 統一代號
GEOHINTS_MAP = {
    "/meta/bollards": "bollards",
    "/meta/utilityPoles": "utility_poles",
    "/meta/lines": "lines",
    "/meta/architecture": "architecture",
    "/meta/nature": "nature",
    "/meta/sceneries": "scenery",
    "/meta/snow": "snow",
    "/meta/sidewalks": "sidewalks",
    "/meta/houseNumbers": "house_numbers",
    "/meta/postBoxes": "post_boxes",
    "/meta/licensePlates": "license_plates",
    "/meta/trafficLights": "traffic_lights",
    "/meta/flags": "flags",
    "/meta/followCars": "follow_cars",
    "/meta/rifts": "rifts",
    "/meta/cameraGens": "camera",
    "/meta/domains": "domains",
    "/meta/phoneNumbers": "phone_numbers",
    "/meta/currencies": "currencies",
    "/meta/drivingSide": "driving_side",
    "/meta/years": "years",
    "/meta/streetSuffix": "street_suffix",
    "/meta/companies": "companies",
    "/meta/companies/beer": "companies",
    "/meta/companies/post": "companies",
    "/meta/companies/gasStations": "gas_stations",
    "/meta/signs": "signs",
    "/meta/signs/chevrons": "chevrons",
    "/meta/signs/busStop": "bus_stops",
    "/meta/signs/railwayCrossing": "railway",
    "/meta/signs/roadNumbering": "road_numbering",
    "/meta/signs/streetNames": "street_names",
    "/meta/signs/animalWarning": "signs",
    "/meta/signs/backOfSigns": "signs",
    "/meta/signs/citySigns": "signs",
    "/meta/signs/directions": "signs",
    "/meta/signs/pedestrian": "signs",
    "/meta/signs/river": "signs",
    "/meta/signs/signPosts": "signs",
    "/meta/signs/speed": "signs",
    "/meta/signs/stop": "signs",
    "/meta/signs/tramSpeed": "signs",
    "/meta/signs/tramStop": "signs",
    "/meta/signs/yield": "signs",
    "/meta/googleVehicles": "google_vehicles",
    "/meta/googleVehicles/animals": "animals",
    "/meta/googleVehicles/atvs": "google_vehicles",
    "/meta/googleVehicles/boats": "google_vehicles",
    "/meta/googleVehicles/cableCars": "google_vehicles",
    "/meta/googleVehicles/cars": "google_vehicles",
    "/meta/googleVehicles/motorcycles": "google_vehicles",
    "/meta/googleVehicles/others": "google_vehicles",
    "/meta/googleVehicles/snowmobiles": "google_vehicles",
    "/meta/googleVehicles/trains": "google_vehicles",
}

# 用來補標 plonkit 那 75% 沒有標籤的條目。
# 順序有意義：越具體的規則放前面，一個條目可命中多個線索。
KEYWORD_RULES = [
    ("bollards",       r"\bbollards?\b"),
    ("utility_poles",  r"\butility pole|\bpower line|\btelephone pole|\bpowerline|\belectric(?:ity)? pole"),
    ("lines",          r"\broad line|\bcentre line|\bcenter line|\broad marking|\blane marking|\bdashed line|\bsolid line"),
    ("chevrons",       r"\bchevron"),
    ("guardrails",     r"\bguardrail|\bguard rail|\bcrash barrier|\barmco"),
    ("license_plates", r"\blicen[cs]e plate|\bnumber plate\b"),
    ("bus_stops",      r"\bbus stop|\bbus shelter"),
    ("railway",        r"\brailway crossing|\blevel crossing|\brailroad crossing"),
    ("road_numbering", r"\broad number|\bhighway number|\broute number|\broad shield"),
    ("street_names",   r"\bstreet name sign|\bstreet sign\b|\broad name sign"),
    ("traffic_lights", r"\btraffic light|\btraffic signal"),
    ("sidewalks",      r"\bsidewalk|\bpavement\b|\bkerb\b|\bcurb\b"),
    ("house_numbers",  r"\bhouse number"),
    ("post_boxes",     r"\bpost box|\bpostbox|\bmailbox|\bletter box"),
    ("domains",        r"\bdomain\b|\btop-level domain|\bTLD\b|\.\w{2,3}\b domain"),
    ("phone_numbers",  r"\bphone number|\bdialling code|\bdialing code|\barea code"),
    ("currencies",     r"\bcurrency\b|\bcurrencies\b"),
    ("driving_side",   r"\bdriv(?:e|es|ing) on the (?:left|right)|\bleft-hand traffic|\bright-hand traffic|\bdriving side"),
    ("flags",          r"\bflags?\b"),
    ("camera",         r"\bcamera gen|\bgen \d\b|\bbad cam|\bblurry cam|\bshitcam"),
    ("rifts",          r"\brift\b|\bstitching"),
    ("follow_cars",    r"\bfollow car"),
    ("google_vehicles", r"\bgoogle car|\bcar blur|\bsnowmobile|\btrekker\b|\bcamera vehicle|\broof rack"),
    ("gas_stations",   r"\bgas station|\bpetrol station|\bfuel station"),
    ("snow",           r"\bsnow\b|\bsnowy\b"),
    ("architecture",   r"\barchitectur|\bbuilding|\bhouses?\b|\broof(?:s|ing)?\b|\bbalcon"),
    ("nature",         r"\bvegetation|\bforest|\btrees?\b|\bpalm\b|\bshrub|\bgrassland|\bdesert\b|\bsavann"),
    ("scenery",        r"\blandscape|\bmountain|\bterrain|\bcoastline|\bscenery"),
    ("language",       r"\blanguage|\balphabet|\bscript\b|\bcyrillic|\barabic\b|\bdiacritic|\blatin script|\bletters?\b"),
    ("signs",          r"\bsigns?\b|\bsignpost"),
]

COMPILED_RULES = [(k, re.compile(p, re.I)) for k, p in KEYWORD_RULES]


def detect_clues(text):
    """從 tip 內文推測線索類型；plonkit 只有兩成多條目自帶標籤，其餘靠這裡"""
    found = []
    for key, rx in COMPILED_RULES:
        if rx.search(text):
            found.append(key)
    return found


# ---------------------------------------------------------------- plonkit

def image_path(url):
    """/images/netherlands/x.png -> plonkit/netherlands/x.webp（對應已下載的檔案）

    有些 imageUrl 根本沒有副檔名，必須跟 fetch_plonkit_images.py 的 dest_for
    用同一種寫法（with_suffix），否則那批圖的路徑會對不上而變成破圖。
    """
    if not url or not url.startswith("/images/"):
        return ""
    return "plonkit/" + str(PurePosixPath(url[len("/images/"):]).with_suffix(".webp"))


def load_translations():
    """translate.py 產生的原文->譯文對照，可能不存在或只翻了一部分"""
    f = ROOT / "data" / "translations.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def load_country_zh():
    f = OUT / "country_zh.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


# 段落標題的變體不多但每頁都看得到，直接對照就好，不必花翻譯額度
SECTION_ZH = {
    "spotlight": "重點地標",
    "maps and resources": "地圖與資源",
    "regional clues": "區域性線索",
    "trekker tips": "徒步街景要點",
    "trekker coverage": "徒步街景",
    "land coverage": "陸地街景",
    "boat coverage": "船拍街景",
    "location": "地點",
}

# 各國對次級行政區的叫法不同，但標題格式一致，統一用一條規則處理
ADMIN_ZH = {
    "province": "省份", "state": "州別", "county": "郡縣", "parish": "教區",
    "prefecture": "都道府縣", "department": "省份", "governorate": "省份",
    "municipality": "市鎮", "district": "行政區", "canton": "州別",
    "region": "區域", "island": "島嶼", "oblast": "州別", "voivodeship": "省份",
    "emirate": "酋長國", "territory": "領地", "commune": "市鎮", "city": "城市",
    "division": "區劃", "governorates": "省份",
}


def section_title_zh(title, country_zh, store=None):
    t = (title or "").strip()
    low = t.lower()
    if low in SECTION_ZH:
        return SECTION_ZH[low]
    # 少數國家有自己的特殊段落（Kampala、National Parks…），走翻譯管線
    if store and store.get(t):
        return store[t]
    if re.match(r"^identifying (?:the )?", low):
        return f"辨識{country_zh}"
    # "Regional and prefecture-specific clues"、"Regional/district-specific clues"、
    # "Region-specific clues"、"Island specific clues" 都歸這條
    m = re.match(r"^(?:regional|region)\b.*?(?:([a-z]+)[\s-])?specific clues$", low)
    if m:
        return (ADMIN_ZH.get(m.group(1), "地區") if m.group(1) else "區域性") + "專屬線索"
    if low.endswith("specific clues"):
        w = re.match(r"^([a-z]+)", low)
        return (ADMIN_ZH.get(w.group(1), "地區") if w else "地區") + "專屬線索"
    return t


def load_plonkit():
    """回傳 {國家key: 國家資料}，以及所有 tip 條目（供線索索引使用）"""
    zh = load_translations()
    cn_zh = load_country_zh()
    countries, all_tips = {}, []
    index = json.loads((RAW / "plonkit_index.json").read_text(encoding="utf-8"))
    meta = {c["slug"]: c for c in index}

    for f in sorted((RAW / "plonkit").glob("*.json")):
        slug = f.stem
        if slug in NON_COUNTRY_SLUGS:
            continue
        pub = json.loads(f.read_text(encoding="utf-8")).get("data", {}).get("public")
        if not pub:
            continue

        m = meta.get(slug, {})
        key = norm_country(pub.get("title", ""))
        # General Guide 底下是通用文章（新手指南之類），不是國家
        if not key or (m.get("cat") or [""])[0] == "General Guide":
            continue

        sections = []
        for step in pub.get("steps", []):
            items = []
            for it in step.get("items", []):
                if it.get("kind") != "tip":
                    continue
                data = it.get("data") or {}
                text = [t for t in (data.get("text") or []) if t and t.strip()]
                if not text:
                    continue
                img = (data.get("image") or {})
                tags = it.get("tags") or []
                clues = [PLONKIT_TAG_MAP[t] for t in tags if t in PLONKIT_TAG_MAP]
                auto = detect_clues(" ".join(text))
                for c in auto:
                    if c not in clues:
                        clues.append(c)
                # 逐條對照，翻到哪就顯示到哪，沒翻的前端 fallback 回英文原文
                text_zh = [zh.get(t, "") for t in text]
                entry = {
                    "id": it.get("id", ""),
                    "text": text,
                    "text_zh": text_zh if any(text_zh) else [],
                    "image": image_path(img.get("imageUrl", "")),
                    "link": img.get("imageLink", "") if str(img.get("imageLink", "")).startswith("http") else "",
                    "clues": clues,
                    "important": "important" in tags,
                    "tagged": bool(clues and tags),  # 原站標的，比關鍵字推測可信
                }
                items.append(entry)
                all_tips.append({**entry, "country": key, "country_name": pub["title"]})
            if items:
                sections.append({
                    "title": step.get("title", ""),
                    "title_zh": section_title_zh(step.get("title", ""), cn_zh.get(key, pub.get("title", "")), zh),
                    "items": items,
                })

        countries[key] = {
            "name": pub.get("title", ""),
            "slug": slug,
            "code": m.get("code", ""),
            "continent": (m.get("cat") or [""])[0],
            "hero": image_path(pub.get("heroImage", "")),
            "updated": m.get("updatedAt", ""),
            "sections": sections,
            "tip_count": sum(len(s["items"]) for s in sections),
        }
    return countries, all_tips


# ---------------------------------------------------------------- geohints

def gh_image_path(url):
    """https://xxx.geohints.com/storage/bollards/bollard_2.jpg -> geohints/bollards/bollard_2.webp

    SVG（旗幟、品牌 logo）維持原副檔名，下載時就沒有轉檔。
    """
    m = re.search(r"/storage/+(.+)$", url or "")
    if not m:
        return ""
    rel = m.group(1)
    if rel.lower().endswith(".svg"):
        return "geohints/" + rel
    return "geohints/" + re.sub(r"\.(png|jpe?g|gif|webp)$", ".webp", rel, flags=re.I)


def load_geohints():
    """圖鑑：{線索key: [條目]}

    只輸出實際下載了的那批圖，篩選規則必須與 fetch_geohints_images.py 的
    PER_GROUP 完全一致（同樣的走訪順序、同樣的跨類去重），否則資料會指向
    沒下載的檔案而在頁面上變成破圖。
    """
    data = json.loads((RAW / "geohints.json").read_text(encoding="utf-8"))
    gallery = defaultdict(list)
    seen = set()
    for path, items in data.items():
        clue = GEOHINTS_MAP.get(path)
        per_country = Counter()
        for it in items:
            img = it.get("image")
            if not img or img in seen:
                continue
            if per_country[it.get("country", "")] >= PER_GROUP:
                continue
            per_country[it.get("country", "")] += 1
            seen.add(img)
            if not clue:
                continue
            gallery[clue].append({
                "country": norm_country(it.get("country", "")),
                "country_name": it.get("country", ""),
                "image": gh_image_path(it["image"]),
                "src": it["image"],
                "link": it.get("maps_link", ""),
                "source_page": path,
            })
    return gallery


def load_tables():
    """對照表：{國家key: {線索key: 值}}"""
    data = json.loads((RAW / "geohints_tables.json").read_text(encoding="utf-8"))
    facts = defaultdict(dict)
    for path, items in data.items():
        clue = GEOHINTS_MAP.get(path)
        if not clue:
            continue
        for it in items:
            key = norm_country(it.get("country", ""))
            if key:
                facts[key][clue] = it.get("value")
                # 留住原始寫法，否則沒有 plonkit 攻略的國家只剩正規化後的 key
                facts[key].setdefault("_name", it.get("country", ""))
    return facts


# ---------------------------------------------------------------- 組裝

def main():
    OUT.mkdir(parents=True, exist_ok=True)

    countries, all_tips = load_plonkit()
    gallery = load_geohints()
    facts = load_tables()

    # 對照表併進國家資料，讓國家頁能顯示「左駕／+31／.nl」這類速查欄
    matched_facts = 0
    for key, f in facts.items():
        name = f.pop("_name", "") or key.title()
        if key in countries:
            countries[key]["facts"] = f
            matched_facts += 1
        else:
            # geohints 涵蓋比 plonkit 廣，這些國家沒有攻略但仍有硬線索
            countries[key] = {
                "name": name, "slug": "", "code": "",
                "continent": "", "hero": "", "sections": [], "tip_count": 0,
                "facts": f, "no_guide": True,
            }

    # 圖鑑併進國家資料
    for clue, items in gallery.items():
        for it in items:
            c = countries.get(it["country"])
            if c is not None:
                c.setdefault("gallery", defaultdict(list))
                c["gallery"][clue].append({"image": it["image"], "link": it["link"]})

    for c in countries.values():
        if isinstance(c.get("gallery"), defaultdict):
            c["gallery"] = dict(c["gallery"])

    # 線索索引：每個線索類型底下同時放 geohints 圖鑑與 plonkit 說明
    clues = {}
    for key, meta in CLUE_TYPES.items():
        tips = [t for t in all_tips if key in t["clues"]]
        tips.sort(key=lambda t: (not t["tagged"], t["country_name"]))
        clues[key] = {
            "en": meta["en"],
            "zh": meta["zh"],
            "gallery": gallery.get(key, []),
            "tips": tips,
            "gallery_count": len(gallery.get(key, [])),
            "tip_count": len(tips),
        }

    # 全部塞成兩個大檔會讓首頁一開就要吃十幾 MB，所以拆成
    # 一份輕量索引 + 每國一檔 + 每類線索一檔，點進去才載。
    cdir, kdir = OUT / "countries", OUT / "clues"
    cdir.mkdir(exist_ok=True)
    kdir.mkdir(exist_ok=True)

    for key, c in countries.items():
        c["key"] = key  # 前端要靠它查中譯，slug 與 key 未必相同（united-states / united states of america）
        (cdir / f"{key.replace(' ', '-')}.json").write_text(
            json.dumps(c, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for key, v in clues.items():
        (kdir / f"{key}.json").write_text(
            json.dumps(v, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 首頁「這是哪一國」的題庫。排除兩種不適合出題的：旗幟類（圖片本身就是答案）、
    # 沒有完整攻略的國家（猜對了點進去也沒東西可看）。每國最多 6 題，且刻意輪流
    # 從不同線索類型抽，否則 6 題會全是 Google 拍攝載具（那類圖最多）。
    by_c = {}
    for ck, cv in clues.items():
        if ck == "flags":
            continue
        for g in cv["gallery"]:
            c = g.get("country")
            if c and g.get("image") and not countries.get(c, {}).get("no_guide"):
                by_c.setdefault(c, {}).setdefault(ck, []).append([g["image"], cv["zh"]])

    quiz = []
    for c, per_clue in sorted(by_c.items()):
        picks, kinds, i = [], sorted(per_clue), 0
        while len(picks) < 6:
            added = False
            for t in kinds:
                if i < len(per_clue[t]):
                    picks.append(per_clue[t][i])
                    added = True
                    if len(picks) >= 6:
                        break
            if not added:
                break
            i += 1
        quiz += [[img, c, kind] for img, kind in picks]
    (OUT / "quiz.json").write_text(
        json.dumps(quiz, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 國旗有兩個來源：geohints 的 flags 圖鑑（220 面），以及補下載的
    # assets/img/flags/（38 面，都是 geohints 沒收的次國家層級地區，
    # 例如阿拉斯加、亞速爾群島；屬地沒有自己旗幟的就用宗主國旗）
    flag_map = {}
    for it in gallery.get("flags", []):
        if it.get("country") and it.get("image"):
            flag_map.setdefault(it["country"], it["image"])
    for f in sorted((ROOT / "assets" / "img" / "flags").glob("*.svg")):
        flag_map.setdefault(f.stem.replace("_", " "), f"flags/{f.name}")

    index = {
        "countries": [
            {
                "key": k,
                "file": k.replace(" ", "-"),
                "name": c["name"],
                "code": c.get("code", ""),
                "continent": c.get("continent", ""),
                "tips": c.get("tip_count", 0),
                "gallery": sum(len(v) for v in (c.get("gallery") or {}).values()),
                "no_guide": c.get("no_guide", False),
                "flag": flag_map.get(k, ""),
            }
            for k, c in sorted(countries.items(), key=lambda x: x[1]["name"])
        ],
        "clues": [
            {
                "key": k,
                "en": v["en"],
                "zh": v["zh"],
                "gallery": v["gallery_count"],
                "tips": v["tip_count"],
            }
            for k, v in sorted(clues.items(), key=lambda x: -(x[1]["gallery_count"] + x[1]["tip_count"]))
            if v["gallery_count"] or v["tip_count"]
        ],
    }
    (OUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---- 統計 ----
    with_guide = [c for c in countries.values() if c.get("sections")]
    tagged = sum(1 for t in all_tips if t["tagged"])
    have_clue = sum(1 for t in all_tips if t["clues"])
    print(f"國家 {len(countries)} 個（有攻略 {len(with_guide)}，只有硬線索 {len(countries) - len(with_guide)}）")
    print(f"對照表對上國家 {matched_facts} 個")
    print(f"tip {len(all_tips)} 條：原站標籤 {tagged} 條，補標後有線索的 {have_clue} 條"
          f"（{have_clue / len(all_tips) * 100:.1f}%）")
    print(f"圖鑑 {sum(len(v) for v in gallery.values())} 張，涵蓋 {len(gallery)} 類線索\n")
    print("各線索類型的資料量：")
    for k, v in sorted(clues.items(), key=lambda x: -(x[1]["gallery_count"] + x[1]["tip_count"])):
        if v["gallery_count"] or v["tip_count"]:
            print(f"   {v['zh']:<12} 圖鑑 {v['gallery_count']:>5}  說明 {v['tip_count']:>4}")


if __name__ == "__main__":
    main()
