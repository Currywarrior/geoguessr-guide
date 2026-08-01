"""產生 PWA 用的 PNG 圖示，內容跟 icon.svg 一致。

為什麼不直接讓瀏覽器把 SVG 轉檔：那要多裝一個 rasterizer 或開 headless 瀏覽器，
而這個圖示只有圓、弧線與格線，用 Pillow 畫出來一樣，還能隨時重跑。

放大四倍畫再縮回去（supersampling）。Pillow 的 ellipse/arc 沒有反鋸齒，
直接畫 192px 的話弧線會有階梯。

    python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent
SS = 4  # supersampling 倍率

BG = (17, 20, 26)        # --bg   #11141a
LINE = (43, 51, 64)      # --line #2b3340
GOLD = (201, 162, 39)    # --gold #c9a227


def render(size, globe_ratio, grid):
    """globe_ratio 是地球外圈直徑佔整張圖的比例。
    maskable 圖示會被系統裁成圓形或圓角方形，只保證中央 80% 不被切到，
    所以那一版要把地球縮小、格線也拿掉，免得裁完剩一團色塊。"""
    n = size * SS
    im = Image.new("RGB", (n, n), BG)
    d = ImageDraw.Draw(im)

    if grid:
        step = n / 8
        for i in range(1, 8):
            p = round(i * step)
            d.line([(p, 0), (p, n)], fill=LINE, width=max(1, round(n / 256)))
            d.line([(0, p), (n, p)], fill=LINE, width=max(1, round(n / 256)))

    c = n / 2
    r = n * globe_ratio / 2
    w = max(2, round(n * 0.031))          # 線寬，跟 SVG 的 stroke-width 16/512 對齊
    box = [c - r, c - r, c + r, c + r]

    d.ellipse(box, outline=GOLD, width=w)                      # 外圈
    d.line([(c - r, c), (c + r, c)], fill=GOLD, width=w)       # 赤道
    d.ellipse([c - r * 0.42, c - r, c + r * 0.42, c + r],      # 經線（壓扁的橢圓當球面透視）
              outline=GOLD, width=w)

    # 兩條緯線。畫成完整的扁橢圓，寬度取該緯度在球面上的實際弦長
    # （半弦長 = sqrt(r² - dy²)），左右兩端剛好落在外圈上，不會凸出去。
    # 不用 arc()：Pillow 的角度是以外接矩形算的，弧要貼合球面得先解一堆三角，
    # 而完整橢圓本來就是球面上一圈緯線的正投影，直接畫反而正確。
    for sign in (-1, 1):
        dy = r * 0.5 * sign
        rx = (r * r - dy * dy) ** 0.5
        ry = rx * 0.3
        d.ellipse([c - rx, c + dy - ry, c + rx, c + dy + ry], outline=GOLD, width=w)

    # 中心的定位釘：先挖一塊底色把交會的線切斷，再點上金色圓點
    rp = r * 0.2
    d.ellipse([c - rp, c - rp, c + rp, c + rp], fill=BG)
    rp = r * 0.113
    d.ellipse([c - rp, c - rp, c + rp, c + rp], fill=GOLD)

    return im.resize((size, size), Image.LANCZOS)


for name, size, ratio, grid in [
    ("icon-192.png", 192, 0.586, True),
    ("icon-512.png", 512, 0.586, True),
    ("icon-maskable-512.png", 512, 0.44, False),
]:
    render(size, ratio, grid).save(OUT / name)
    print("寫出", name)
