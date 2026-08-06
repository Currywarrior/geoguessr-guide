#!/usr/bin/env python3
"""從國旗 SVG 抽出配色，寫成 data/site/flag_colors.json，給國家頁頂端的色帶用。

為什麼不用點陣圖取色：258 面國旗全是 SVG，這台沒有 cairosvg 之類的 rasterizer，
而且真要裝一個只為了數像素也不划算。國旗 SVG 的顏色本來就寫在檔案裡，直接讀就好。

為什麼取「配色序列」而不是「單一主色」：單色色帶認不出是哪國（很多國家都是紅），
照 SVG 裡出現的順序保留前幾個顏色做成分段色條，日本就是白配紅、德國是黑紅金，
一眼就對得起來。順序有意義是因為 SVG 通常由底層畫到上層，底色會先出現。

另外挑一個 accent：色帶裡彩度與亮度綜合最好的那個，給互動高亮用
（不能直接拿第一個，那常常是白或黑，在深色底上不是變隱形就是刺眼）。

產出 data/site/flag_colors.json： { file: { band: [色...], accent: "#rrggbb" } }
"""

import json
import os
import re
import colorsys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, 'assets', 'img')
OUT = os.path.join(ROOT, 'data', 'site', 'flag_colors.json')

MAX_BAND = 4      # 色帶最多幾段，再多就變成看不清的細條紋

# SVG 裡顏色會用這幾種寫法出現，順序不重要，最後統一按在檔案中的位置排
COLOR_RE = re.compile(
    r'(?:fill|stop-color|flood-color)\s*[:=]\s*["\']?\s*'
    r'(#[0-9a-fA-F]{3,8}|rgb\([^)]*\)|[a-zA-Z]+)', re.I)

NAMED = {
    'red': '#ff0000', 'white': '#ffffff', 'black': '#000000', 'blue': '#0000ff',
    'green': '#008000', 'yellow': '#ffff00', 'orange': '#ffa500', 'gold': '#ffd700',
    'navy': '#000080', 'maroon': '#800000', 'lime': '#00ff00', 'aqua': '#00ffff',
    'cyan': '#00ffff', 'silver': '#c0c0c0', 'gray': '#808080', 'grey': '#808080',
    'purple': '#800080', 'teal': '#008080', 'olive': '#808000', 'fuchsia': '#ff00ff',
    'magenta': '#ff00ff', 'crimson': '#dc143c', 'darkgreen': '#006400',
    'darkblue': '#00008b', 'darkred': '#8b0000', 'skyblue': '#87ceeb',
}


def to_hex(tok):
    """把一個顏色 token 正規化成 #rrggbb，認不得的（none、currentColor、url(#…)）回 None。"""
    t = tok.strip().lower()
    if t.startswith('#'):
        h = t[1:]
        if len(h) == 3:
            return '#' + ''.join(c * 2 for c in h)
        if len(h) in (6, 8):     # 8 碼是帶 alpha，透明度對色帶沒意義，砍掉
            return '#' + h[:6]
        return None
    if t.startswith('rgb('):
        nums = re.findall(r'[\d.]+%?', t)
        if len(nums) < 3:
            return None
        vals = []
        for n in nums[:3]:
            v = float(n[:-1]) * 2.55 if n.endswith('%') else float(n)
            vals.append(max(0, min(255, int(round(v)))))
        return '#%02x%02x%02x' % tuple(vals)
    return NAMED.get(t)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def score(h):
    """挑 accent 用的分數。彩度要高、亮度要落在中間，
    白色跟純黑在深色頁面上都不能用來當高亮色。"""
    r, g, b = rgb(h)
    hh, l, s = colorsys.rgb_to_hls(r, g, b)
    # 亮度離 0.5 越遠扣越多，彩度直接當主項
    return s * 1.6 + (1 - abs(l - 0.52) * 2) * 0.9


def near(a, b, tol=0.10):
    """兩色是否幾乎一樣。很多國旗 SVG 同一個色會寫成 #FFF 跟 #FFFFFF 或差一階，
    不合併的話色帶會出現兩段看起來一模一樣的顏色。"""
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return abs(ra - rb) < tol and abs(ga - gb) < tol and abs(ba - bb) < tol


def band_of(svg):
    seen = []
    for m in COLOR_RE.finditer(svg):
        h = to_hex(m.group(1))
        if not h:
            continue
        if any(near(h, s) for s in seen):
            continue
        seen.append(h)
        if len(seen) >= MAX_BAND:
            break
    return seen


def main():
    with open(os.path.join(ROOT, 'data', 'site', 'index.json'), encoding='utf-8') as f:
        countries = json.load(f)['countries']

    out, empty = {}, []
    for c in countries:
        flag = c.get('flag')
        if not flag:
            empty.append(c['name'])
            continue
        path = os.path.join(IMG, flag.replace('/', os.sep))
        try:
            with open(path, encoding='utf-8', errors='ignore') as f:
                svg = f.read()
        except OSError:
            empty.append(c['name'])
            continue
        band = band_of(svg)
        if not band:
            empty.append(c['name'])
            continue
        accent = max(band, key=score)
        out[c['file']] = {'band': band, 'accent': accent}

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(OUT) / 1024
    print(f'寫出 {OUT}  {size:.1f} KB，{len(out)} 國有配色')
    if empty:
        print(f'抽不到顏色 {len(empty)} 國：{", ".join(empty[:20])}')


if __name__ == '__main__':
    main()
