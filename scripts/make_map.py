#!/usr/bin/env python3
"""把 Natural Earth 的國界資料壓成前端能直接畫的 data/site/world.json。

為什麼不直接下載現成的世界地圖 SVG：那些 SVG 的 path id 各家命名不同
（有的用 ISO2、有的用英文名、有的自創編號），對不上這站的 258 個 country key，
校對成本比自己生還高。自己投影的話 key 就是我們自己的 key，一次對齊永久有效。

用 map_subunits 圖層而不是 admin_0_countries：後者把法屬圭亞那、瓜地洛普、
留尼旺畫進 France 的 polygon，把阿拉斯加、夏威夷畫進 United States，
點南美洲那塊會跳到法國頁，是錯的。subunits 圖層有把它們拆開。

投影用 Equal Earth（2018）：等面積，所以格陵蘭不會像 Mercator 那樣脹成非洲大小，
choropleth 用等面積投影才不會騙人；形狀也比圓柱投影好看。公式是純多項式，很短。

產出：data/site/world.json
  { w, h, land: "背景陸地（沒有對應頁面的地區，不可點）", c: { key: {d, p:[質心]} } }
"""

import json
import math
import os
import re
import sys
import unicodedata
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_map_subunits.geojson'
CACHE = os.path.join(ROOT, 'data', 'raw', 'ne_50m_map_subunits.geojson')
OUT = os.path.join(ROOT, 'data', 'site', 'world.json')

WIDTH = 1000          # 輸出座標系寬度，前端用 viewBox 等比縮放
TOLERANCE = 0.30      # 簡化容差（像素）。0.30 在 1000 寬下肉眼看不出差異
MIN_AREA = 0.12       # 小於這個面積（像素平方）的島直接丟掉，但每國至少留最大的一塊

# Natural Earth 的名字跟我們的 country key 對不上的，人工補。
# 左邊是我們 index.json 的 name，右邊是 NE 任一名稱欄位的值。
ALIAS = {
    'Antarctica (McMurdo Station)': 'Antarctica',
    'Israel & the West Bank': 'Israel',
    'South Georgia & Sandwich Islands': 'South Georgia and the Islands',
    'Svalbard and Jan Mayen': 'Svalbard',
    'US Virgin Islands': 'United States Virgin Islands',
    'US Minor Outlying Islands': 'United States Minor Outlying Islands',
}

# 預期會落在地圖之外的，跑腳本時不用當成錯誤。兩種原因：
#   一是 NE 50m 根本沒收（梵蒂岡、直布羅陀這種城市級的地方）
#   二是我們自己的資料有兩個 key 指同一塊地，本體上圖後另一個就沒地方擺
# 前端會把這些國家另外列在地圖底下，不會變成點不到的孤兒。
OFF_MAP = {'Gibraltar', 'Vatican City', 'Bouvet Island',
           'United States Minor Outlying Islands', 'US Minor Outlying Islands',
           'Svalbard and Jan Mayen', 'United States Virgin Islands'}

# 名稱欄位要分層比對，不能攤成一張大表先到先得。
# NE 的每個 subunit 都帶 SOVEREIGNT，亞速爾那筆的 SOVEREIGNT 也是 Portugal，
# 攤平之後 by_name['portugal'] 會指到亞速爾，等真正的 Portugal 來查時
# 那塊地已經被認領走 → 葡萄牙本土整個從地圖上消失（英國、美國、格陵蘭同理）。
# 分層之後精確欄位先配，粗欄位只當最後的救援。
NAME_TIERS = (
    ('SUBUNIT',),
    ('NAME', 'GEOUNIT', 'NAME_LONG', 'BRK_NAME', 'NAME_CIAWF', 'NAME_SORT'),
    ('ADMIN',),
    ('SOVEREIGNT',),
)

DOT_R = 2.2   # 投影後小於一個像素的國家，畫成這個半徑的圓點才點得到


def norm(s):
    """比名字用的正規化：去重音、去空白標點、轉小寫。

    São Tomé 的 ã é 不處理的話會跟 NE 的 Sao Tome 對不上（我們的資料帶重音、
    NE 那欄不帶），NFKD 拆成基底字母＋組合符號再濾掉非 a-z 就一致了。
    """
    s = unicodedata.normalize('NFKD', s or '')
    return re.sub(r'[^a-z]', '', s.lower())


# ---------------------------------------------------------------- 投影

A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
SQRT3 = math.sqrt(3)


def equal_earth(lon, lat):
    lam = math.radians(lon)
    phi = math.radians(lat)
    th = math.asin(max(-1.0, min(1.0, SQRT3 / 2 * math.sin(phi))))
    t2 = th * th
    x = 2 * SQRT3 * lam * math.cos(th) / (3 * (9 * A4 * t2**4 + 7 * A3 * t2**3 + 3 * A2 * t2 + A1))
    y = th * (A1 + A2 * t2 + t2**3 * (A3 + A4 * t2))
    return x, y


# ---------------------------------------------------------------- 幾何

def simplify(pts, tol):
    """Douglas-Peucker。用明確的 stack 而不是遞迴，長海岸線的環有上萬點會爆 stack。"""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    t2 = tol * tol
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        ax, ay = pts[i]
        bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        far, fd = -1, -1.0
        for k in range(i + 1, j):
            px, py = pts[k]
            if den == 0:
                d = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / den
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > fd:
                far, fd = k, d
        if fd > t2:
            keep[far] = True
            stack.append((i, far))
            stack.append((far, j))
    return [p for p, k in zip(pts, keep) if k]


def ring_area(pts):
    """鞋帶公式取絕對面積，用來判斷這個島值不值得畫。"""
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def rings_of(geom):
    """MultiPolygon 與 Polygon 統一攤成一串外環。內環（湖泊）不畫，choropleth 用不到。"""
    t = geom['type']
    if t == 'Polygon':
        return [geom['coordinates'][0]]
    if t == 'MultiPolygon':
        return [poly[0] for poly in geom['coordinates']]
    return []


def project_ring(ring, ox, oy, scale):
    pts, prev = [], None
    for lon, lat in ring:
        x, y = equal_earth(lon, lat)
        px = (x - ox) * scale
        py = (oy - y) * scale
        # 投影後相鄰點常常疊在一起，先去重省掉大量無效點。
        # 這裡的比較精度要比輸出精度高一位，否則摩納哥這種小國會被自己去重到剩兩點
        cur = (round(px, 2), round(py, 2))
        if cur != prev:
            pts.append(cur)
            prev = cur
    return pts


def fmt(pts):
    return 'M' + 'L'.join(f'{round(x, 1)} {round(y, 1)}' for x, y in pts) + 'Z'


def dot_path(cx, cy, r=DOT_R):
    """兩個半圓弧接成一個圓。給投影後小於一個像素的國家當可點目標——
    摩納哥、諾魯、澳門在等面積投影的世界地圖上本來就只能是一個點。"""
    return (f'M{round(cx - r, 1)} {round(cy, 1)}'
            f'a{r} {r} 0 1 0 {r * 2} 0a{r} {r} 0 1 0 {-r * 2} 0Z')


def build_paths(geom, ox, oy, scale):
    """回傳 (path 字串, 質心, 是否為圓點)。質心取最大那塊的中心，不是所有塊的平均，
    否則美國的標籤會落在太平洋上（本土＋阿拉斯加＋夏威夷平均出來的位置）。"""
    parts, best, best_area = [], None, -1.0
    allpts = []
    for ring in rings_of(geom):
        pts = project_ring(ring, ox, oy, scale)
        allpts.extend(pts)
        if len(pts) < 3:
            continue
        pts = simplify(pts, TOLERANCE)
        if len(pts) < 3:
            continue
        a = ring_area(pts)
        if a < MIN_AREA:
            continue
        parts.append((a, pts))
        if a > best_area:
            best_area, best = a, pts

    if not parts:
        # 整個國家都畫不出來（面積不足一個像素）→ 退化成圓點，不要讓它從地圖消失
        if not allpts:
            return None, None, False
        cx = sum(p[0] for p in allpts) / len(allpts)
        cy = sum(p[1] for p in allpts) / len(allpts)
        return dot_path(cx, cy), [round(cx, 1), round(cy, 1)], True

    parts.sort(key=lambda p: -p[0])
    d = ''.join(fmt(p[1]) for p in parts)
    cx = sum(p[0] for p in best) / len(best)
    cy = sum(p[1] for p in best) / len(best)
    return d, [round(cx, 1), round(cy, 1)], False


# ---------------------------------------------------------------- 主流程

def graticule(ox, oy, scale, step=30):
    """經緯線。Equal Earth 的經線是曲線、緯線是直線，兩者都得照投影公式逐點算，
    前端沒有這組公式（也不該再抄一份），所以在這裡一起產出來。

    回傳 (格線 path, 經緯度標記)。標記給地圖邊緣標 60°N、30°E 這種刻度用。
    """
    # 每 3 度取一點就夠平滑了（經線是很緩的曲線），逐度取樣會讓格線佔掉 48KB
    lines, marks = [], []
    for lon in range(-180, 181, step):
        pts = [equal_earth(lon, lat) for lat in range(-90, 91, 3)]
        lines.append('M' + 'L'.join(
            f'{(x - ox) * scale:.1f} {(oy - y) * scale:.1f}' for x, y in pts))
    for lat in range(-60, 61, step):
        pts = [equal_earth(lon, lat) for lon in range(-180, 181, 6)]
        lines.append('M' + 'L'.join(
            f'{(x - ox) * scale:.1f} {(oy - y) * scale:.1f}' for x, y in pts))
        # 緯度標記放在左邊界上，赤道標 0° 不標 N/S
        x, y = equal_earth(-180, lat)
        label = '0°' if lat == 0 else f'{abs(lat)}°{"N" if lat > 0 else "S"}'
        marks.append({'t': label, 'x': round((x - ox) * scale, 1), 'y': round((oy - y) * scale, 1)})
    return ''.join(lines), marks


def fetch_source():
    if os.path.exists(CACHE):
        print(f'用本地快取 {CACHE}')
        with open(CACHE, encoding='utf-8') as f:
            return json.load(f)
    print(f'下載 {SRC}')
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with urllib.request.urlopen(SRC, timeout=300) as r:
        raw = r.read()
    with open(CACHE, 'wb') as f:
        f.write(raw)
    return json.loads(raw.decode('utf-8'))


def main():
    gj = fetch_source()
    feats = gj['features']
    print(f'NE subunits: {len(feats)} 個')

    with open(os.path.join(ROOT, 'data', 'site', 'index.json'), encoding='utf-8') as f:
        countries = json.load(f)['countries']

    # 一層一張索引，精確欄位優先。同一個名字可能對到多筆（阿拉斯加、夏威夷、
    # 美國本土的 GEOUNIT 都是 United States of America），所以存成清單，
    # 查的時候跳過已經被認領的，否則美國本土會永遠被排在前面的阿拉斯加擋住
    tiers = []
    for fields in NAME_TIERS:
        t = {}
        for f_ in feats:
            p = f_['properties']
            for k in fields:
                v = p.get(k)
                if v:
                    t.setdefault(norm(v), []).append(f_)
        tiers.append(t)

    # 投影範圍：先把所有座標投一遍求 bbox，才知道縮放倍率
    xs, ys = [], []
    for lon in range(-180, 181, 5):
        for lat in range(-90, 91, 5):
            x, y = equal_earth(lon, lat)
            xs.append(x)
            ys.append(y)
    ox, oy = min(xs), max(ys)
    scale = WIDTH / (max(xs) - min(xs))
    height = round((max(ys) - min(ys)) * scale, 1)

    grid, marks = graticule(ox, oy, scale)
    out = {'w': WIDTH, 'h': height, 'grid': grid, 'marks': marks, 'c': {}}
    used = set()
    missing = []

    # 兩輪：先讓每個國家在精確層找，全部找完再換下一層。
    # 不能一國一國把四層都試完——那樣 Azores 會在第一國就用 SOVEREIGNT 撈走 Portugal
    pending = list(countries)
    for t in tiers:
        nxt = []
        for c in pending:
            name = ALIAS.get(c['name'], c['name'])
            # 同一塊地只能被認領一次（我們把 Svalbard 與 Svalbard and Jan Mayen 都收了）
            f_ = next((x for x in t.get(norm(name), []) if id(x) not in used), None)
            if not f_:
                nxt.append(c)
                continue
            d, cen, is_dot = build_paths(f_['geometry'], ox, oy, scale)
            if not d:
                nxt.append(c)
                continue
            used.add(id(f_))
            e = {'d': d, 'p': cen}
            if is_dot:
                e['dot'] = 1
            # 用 file 當 key，跟路由 #/country/<file> 一致，前端不必再轉一層
            out['c'][c['file']] = e
        pending = nxt
    missing = [c['name'] for c in pending]

    # 剩下沒被認領的地區合成一張背景陸地，讓地圖是完整的世界而不是缺一塊。
    # 圓點退化的不畫進背景——那些是沒有頁面可去的小島，畫上去只是海上的雜點
    land = []
    for f_ in feats:
        if id(f_) in used:
            continue
        d, _, is_dot = build_paths(f_['geometry'], ox, oy, scale)
        if d and not is_dot:
            land.append(d)
    out['land'] = ''.join(land)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(OUT) / 1024
    print(f'寫出 {OUT}  {size:.0f} KB')
    print(f'上圖 {len(out["c"])} 國，viewBox 0 0 {WIDTH} {height}')
    unexpected = [m for m in missing if m not in OFF_MAP]
    print(f'沒上圖 {len(missing)} 國：{", ".join(missing)}')
    if unexpected:
        print(f'  其中非預期的 {len(unexpected)} 個：{", ".join(unexpected)}', file=sys.stderr)


if __name__ == '__main__':
    main()
