# GeoAtlas — GeoGuessr 線索圖鑑

把 plonkit.net 與 geohints.com 的攻略資料整合成同一份資料庫，提供兩種索引方式：

- **按國家查** — 賽前複習某一國的完整辨識特徵
- **按線索查** — 遊戲中看到一根沒見過的電線桿，反查是哪些國家會有

資料為個人自用，內容與圖片版權屬原站。

## 跑起來

```
python -m http.server 8781
```

然後開 http://localhost:8781 。必須透過 HTTP，直接開 index.html 會因為 fetch 限制讀不到資料。

> 不要用 8765，那個 port 上有 japan-travel 的 service worker，會攔截請求回傳它自己的頁面。

## 目前規模

| 項目 | 數量 |
|---|---|
| 國家與地區 | 258（其中 136 有完整攻略） |
| 攻略說明 | 5272 條 |
| 線索圖鑑 | 3545 張，分 23 類 |
| 線索類型 | 33 種 |
| 圖片體積 | 約 0.6 GB |

## 目錄

```
scripts/                    抓取與建置
  fetch_plonkit.py            139 個國家頁的內嵌 JSON
  fetch_plonkit_images.py     圖片下載並轉 WebP
  fetch_geohints.py           線索圖鑑（各國實例照片）
  fetch_geohints_tables.py    跨國對照表（左駕右駕、區碼、網域…）
  fetch_geohints_images.py    圖鑑圖片，每國每類取 5 張
  build_data.py               合併成網站資料
  translate.py                批次中譯

data/raw/                   原始抓取結果
data/site/                  網站讀的資料
  index.json                  首頁索引（44KB）
  countries/*.json            一國一檔
  clues/*.json                一類線索一檔
  country_zh.json             國名中譯
data/translations.json      內文中譯（translate.py 產生）
assets/img/                 圖片
```

所有抓取腳本都支援中斷續跑，已抓過的會跳過。

## 翻譯

內文翻譯需要 API 金鑰，用環境變數傳入，不要寫進檔案：

```
$env:GROQ_API_KEY="你的金鑰"        # PowerShell
python scripts/translate.py --limit 50   # 先試 50 條
python scripts/translate.py              # 翻全部
python scripts/build_data.py             # 把譯文併進網站資料
```

規模：待翻 7838 條、115 萬字元，切成 784 批，約 96 萬 token。

服務商可換，兩家都是 OpenAI 相容格式，模型會自動偵測（不寫死，因為官方會下架
模型——`llama-3.3-70b-versatile` 已於 2026-06 棄用）：

| | 每日限制 | 全站跑完要多久 |
|---|---|---|
| Groq（預設） | token 上限低 | 約 10 天，每天跑一次 |
| Gemini | 只限 1500 請求／天，我們只要 784 次 | **約 80 分鐘** |

改用 Gemini：

```
$env:GROQ_BASE="https://generativelanguage.googleapis.com/v1beta/openai"
$env:GROQ_API_KEY="你的 Gemini 金鑰"
```

撞到當日配額會自動存檔收工，隔天重跑從斷點接續。

譯文存在 `data/translations.json`，與網站資料分離，所以重建資料不會弄丟翻譯，
翻譯本身也可以隨時中斷續跑。前端是逐條 fallback：某條沒翻就顯示該條英文原文，
不必等全部翻完才能用。

國名與段落標題已經全部中文化，不需要走翻譯管線。

## 部署

repo 約 790MB，主要是圖片。全站都是相對路徑，部署在子目錄也不會壞。

**GitHub Pages**：Settings → Pages → Source 選 master / root。注意 Pages 有 1GB 的
站台大小硬限制，目前 840MB 還在範圍內，但補圖前要留意。

**Cloudflare Pages**（可搭配私有 repo）：Workers & Pages → Create → Pages →
Connect to Git，framework preset 選 None、build command 留空、output directory 填 `/`。
沒有 1GB 限制。若要限制只有自己看得到，再到 Zero Trust → Access → Applications
加一個 self-hosted 應用指向該網域，policy 設成只允許自己的 email。

`robots.txt` 與頁面的 `noindex` 都已設好，不會被搜尋引擎收錄而跟原站競爭。

## 幾個踩過的坑

**Cloudflare 只擋沒有瀏覽器 headers 的請求。** plonkit 的 HTML 加個 User-Agent
就過，但 `/images/` 路徑更嚴格，少了 `Referer` 或 `Sec-Fetch-Dest` 會拿到 HTTP 200
但內容是 challenge 頁。所以下載後一定要驗 Content-Type 真的是圖片才寫檔。

**下載慢的原因不是頻寬。** 單張實測 7-8 MB/s，但整批跑只有 0.6 張/秒 —— 瓶頸是
Cloudflare 邊緣沒快取、每張都要回源 GCS，偶發 9 到 18 秒的尖峰。靠併發隱藏延遲有效，
但 12 執行緒會踩到限流（失敗率 11.7%，全是 429），6 執行緒才穩。

**資料端與圖片端的篩選規則必須共用。** 圖鑑只下載「每國每類 5 張」，如果資料端輸出
全部 11315 張，頁面上就會出現破圖。兩邊的 PER_GROUP 要一致。

**geohints 的旗幟與品牌 logo 是 SVG。** Pillow 開不了向量檔，直接存原檔即可，
不要轉點陣。

**plonkit 只有 24.4% 的條目自帶線索標籤**，其餘靠 `build_data.py` 的 KEYWORD_RULES
從內文補標，補完覆蓋率 73%。補標結果會標記 `tagged` 區分原站標的與推測的。

**兩站的國名寫法不一致**，且 geohints 有幾頁的解析會把國名切壞（含 and 的國名被拆斷、
多區碼國家混入雜訊、年份被當成國名）。解法是拿 geohints 自己的國家清單頁當白名單校正。
