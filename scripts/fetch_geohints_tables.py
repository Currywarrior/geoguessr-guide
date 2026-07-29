"""抓取 geohints 的「跨國對照表」類線索。

geohints 的類別頁有兩種形態。fetch_geohints.py 處理的是圖片圖鑑（bollards、
signs 之類），本腳本處理另一種：沒有圖片、把資料直接排版在頁面上的對照表，
例如左駕右駕、國際電話區碼、頂級網域、街道後綴、貨幣、街景年份。

這些在實戰裡是硬線索（看到招牌上的網址或路牌後綴就能直接鎖定國家），
所以不能因為它們沒圖就跳過。

道路標線（lines）比較特別：它不是圖片也不是文字，而是用 CSS 疊出來的圖形，
顏色寫在 Tailwind 的 bg-[white] 這類 class 裡。解析成顏色陣列之後，
前端可以自己重畫，完全不需要下載圖片。
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

# 側邊選單每頁都一樣，解析內容前要先排除，否則會把選單項當成資料
MENU_END = "Useful Resources"


def get(session, path, tries=3):
    for i in range(tries):
        try:
            r = session.get(BASE + path, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.text
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def content_root(soup):
    return soup.find(id="search-results") or soup.find(id="responsive") or soup.body


def clean(s):
    return " ".join(s.split())


CONTINENTS = (
    "Africa", "Asia", "Europe", "North America", "South America",
    "Oceania", "Antarctica",
)

# geohints 有一頁列出全部國名，拿來當白名單校正其他頁的解析結果。
# 沒有它的話，含 and 的國名（Antigua and Barbuda）會被正則拆斷，
# 多區碼國家（Kazakhstan 的 "+7 (0, 6 or 7)"）也會把雜訊當成國名。
COUNTRY_LIST = []


def parse_country_list(soup):
    names = []
    for d in content_root(soup).select("div.text-sm.text-gray-200"):
        t = clean(d.get_text(" ", strip=True))
        if t and not t.isdigit():
            names.append(t)
    return names


def match_country(text):
    """從一段文字裡認出國名：取白名單中能對上的最長者"""
    t = clean(text)
    best = ""
    low = t.lower()
    for n in COUNTRY_LIST:
        if n.lower() in low and len(n) > len(best):
            best = n
    return best


def strip_continent(name):
    """頁面把洲名當分組標題直接排在國名前面，會被正則一起吃進來"""
    for c in CONTINENTS:
        if name.startswith(c + " "):
            return name[len(c) + 1:]
        if name == c:
            return ""
    return name


def parse_driving_side(soup):
    """全文形態為 "Algeria Driving Side: right"，用正則比 DOM 穩"""
    txt = clean(content_root(soup).get_text(" ", strip=True))
    cut = txt.find("By Continent")
    if cut > 0:
        txt = txt[cut + len("By Continent"):]
    out = []
    for m in re.finditer(
        r"([A-ZÅÄÖÉÈÎÔÇ][\w'’\-\.]*(?:\s+[\w'’\-\.&()]+){0,4}?)\s+Driving Side:\s*(left|right)",
        txt,
    ):
        name = match_country(m.group(1)) or strip_continent(clean(m.group(1)))
        if name:
            out.append({"country": name, "value": m.group(2)})
    return out


def parse_phone_numbers(soup):
    """每格形態為 "+267 Botswana" """
    out = []
    for d in content_root(soup).find_all("div"):
        if d.find("div"):
            continue  # 只要最內層
        t = clean(d.get_text(" ", strip=True))
        if not t.startswith("+"):
            continue
        # 多區碼國家寫成 "+7 (0, 6 or 7) Kazakhstan"，切不乾淨就靠白名單認國名
        name = match_country(t)
        if not name:
            continue
        code = clean(t[: t.lower().rfind(name.lower())])
        out.append({"country": name, "value": code or t})
    return out


def cards(soup):
    """這幾頁的共同版型：一國一張 bg-gray-800 p-4 的卡片"""
    return content_root(soup).select("div.bg-gray-800.p-4")


def card_country(card):
    """國名可能在 h2，也可能只是卡片的第一個子 div"""
    h = card.find("h2")
    if h:
        return clean(h.get_text(" ", strip=True))
    first = card.find("div", recursive=False)
    return clean(first.get_text(" ", strip=True)) if first else ""


def parse_domains(soup):
    out = []
    for card in content_root(soup).select("div.p-4.border.bg-gray-800"):
        divs = card.find_all("div", recursive=False)
        if len(divs) < 2:
            continue
        country = clean(divs[0].get_text(" ", strip=True))
        doms = [clean(d.get_text(strip=True)) for d in divs[1].find_all("div")]
        doms = [d for d in doms if d.startswith(".")]
        if country and doms:
            out.append({"country": country, "value": doms})
    return out


def parse_currencies(soup):
    out = []
    for card in cards(soup):
        country = card_country(card)
        monies = []
        for box in card.select("div.bg-gray-700"):
            h3 = box.find("h3")
            row = {td.get_text(strip=True).rstrip(":"): td.find_next_sibling("td").get_text(strip=True)
                   for td in box.select("td.font-semibold") if td.find_next_sibling("td")}
            monies.append({
                "name": clean(h3.get_text(strip=True)) if h3 else "",
                "symbol": row.get("Symbol", ""),
                "status": row.get("Official Status", ""),
                "code": row.get("Code", ""),
            })
        if country and monies:
            out.append({"country": country, "value": monies})
    return out


def parse_years(soup):
    """這頁除了 By Country 還有 By Year，後者的卡片標題是年份不是國名"""
    out = []
    for card in cards(soup):
        country = card_country(card)
        if not country or re.fullmatch(r"(19|20)\d{2}", country):
            continue
        years = [clean(d.get_text(strip=True)) for d in card.select("div.grid div")]
        years = [y for y in years if re.fullmatch(r"(19|20)\d{2}", y)]
        out.append({"country": country, "value": sorted(set(years))})
    return out


def parse_street_suffix(soup):
    """卡片內先是語言，再是「縮寫形式 / 完整字」成對的列"""
    out = []
    for card in content_root(soup).select("div.bg-gray-800.p-4"):
        divs = card.find_all("div", recursive=False)
        if len(divs) < 2:
            continue
        country = clean(divs[0].get_text(" ", strip=True))
        entries, lang = [], ""
        for row in divs[1].find_all("div", recursive=False):
            cls = row.get("class") or []
            if "font-thin" in cls and "flex" not in cls:
                lang = clean(row.get_text(strip=True))
                continue
            cols = row.find_all("div", recursive=False)
            if len(cols) >= 2:
                entries.append({
                    "language": lang,
                    "forms": clean(cols[0].get_text(strip=True)),
                    "word": clean(cols[1].get_text(strip=True)),
                })
        if country and entries:
            out.append({"country": country, "value": entries})
    return out


def parse_lines(soup):
    """道路標線：解析成左中右各組的顏色，前端可據此重畫"""
    out = []
    for unit in content_root(soup).select("div.text-white.text-md.p-2.grid"):
        span = unit.find("span", class_="font-bold")
        road = unit.find("div", class_="bg-gray-400")
        if not span or not road:
            continue
        groups = []
        for grp in road.find_all("div", recursive=False):
            colors = []
            for bar in grp.find_all("div"):
                for c in bar.get("class") or []:
                    m = re.match(r"bg-\[([^\]]+)\]", c)
                    if m:
                        colors.append(m.group(1))
            if colors:
                groups.append(colors)
        if groups:
            out.append({"country": clean(span.get_text(strip=True)), "value": groups})
    return out


PARSERS = {
    "/meta/drivingSide": parse_driving_side,
    "/meta/phoneNumbers": parse_phone_numbers,
    "/meta/domains": parse_domains,
    "/meta/currencies": parse_currencies,
    "/meta/years": parse_years,
    "/meta/streetSuffix": parse_street_suffix,
    "/meta/lines": parse_lines,
}


def main():
    global COUNTRY_LIST
    session = requests.Session()

    html = get(session, "/meta/countries")
    if html:
        COUNTRY_LIST = parse_country_list(BeautifulSoup(html, "html.parser"))
        # 長的先比，才不會拿 Guinea 去蓋掉 Equatorial Guinea
        COUNTRY_LIST.sort(key=len, reverse=True)
    print(f"國名白名單 {len(COUNTRY_LIST)} 個\n")

    result = {}
    for path, parser in PARSERS.items():
        html = get(session, path)
        if not html:
            print(f"{path:<24} 抓取失敗")
            continue
        try:
            items = parser(BeautifulSoup(html, "html.parser"))
        except Exception as e:
            print(f"{path:<24} 解析錯誤 {type(e).__name__}: {e}")
            continue
        result[path] = items
        sample = items[0] if items else None
        print(f"{path:<24} {len(items):>4} 筆   範例: {json.dumps(sample, ensure_ascii=False)[:90]}")
        time.sleep(DELAY)

    (OUT / "geohints_tables.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已寫入 {OUT / 'geohints_tables.json'}")


if __name__ == "__main__":
    main()
