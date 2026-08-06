// GeoAtlas 線索圖鑑 — Service Worker（離線快取）
// 發布新版時把版本號往上加一，瀏覽器會重新 precache 並清掉舊快取。
const VER = 'v3';
const SHELL = `geo-shell-${VER}`;   // 程式與資料：小、可以整包留著
const IMGS = `geo-img-${VER}`;      // 圖鑑照片：大，另開一個快取並限量

// 圖鑑照片全站 817MB、9000 多張。全部隨看隨存會把手機空間吃光，
// 所以照片獨立一個快取並限制筆數，超過就從最舊的開始砍。
// Cache API 的 keys() 是照寫入順序回傳的，先進先出剛好夠用。
const IMG_MAX = 400;

// App shell：離線時最起碼要能開站的核心檔。
// 相對路徑，GitHub Pages 放在 /geoguessr-guide/ 子路徑底下也能對。
const CORE = [
  './',
  './index.html',
  './app.js',
  './manifest.json',
  './icon.svg',
  './icon-192.png',
  './icon-512.png',
  './data/site/index.json',
  './data/site/country_zh.json',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(SHELL)
      .then(c => Promise.all(CORE.map(u => c.add(u).catch(() => {}))))  // 個別失敗不影響整體
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== SHELL && k !== IMGS).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function trim(cache) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - IMG_MAX; i++) await cache.delete(keys[i]);
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;  // 略過 chrome-extension 等
  if (url.origin !== self.location.origin) return;                    // 外站（街景連結）不碰

  const isImg = req.destination === 'image';
  const box = isImg ? IMGS : SHELL;

  // 資料檔改用「先連網、失敗才回快取」。這幾個檔（題庫、索引、各國攻略）會隨著
  // 補資料與翻譯反覆重建，用快取優先的話，裝過 PWA 的人即使伺服器上換了新題庫
  // 也永遠拿到舊的，除非每次改資料都記得把 VER 加一——那遲早會忘。
  // app.js 的 load() 本來就帶 cache:'no-cache' 想讓瀏覽器每次回源驗證，
  // 這裡快取優先等於把那個意圖攔掉了。圖片維持快取優先，那些不會變。
  if (url.pathname.includes('/data/site/')) {
    e.respondWith(
      fetch(req).then(res => {
        const copy = res.clone();
        caches.open(SHELL).then(c => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => caches.match(req, { ignoreSearch: true }))
    );
    return;
  }

  // 其餘快取優先。ignoreSearch 讓 app.js?v=28 這種帶查詢字串的檔也命中，
  // 版本一升 CACHE 名稱就變了，不會卡在舊版。
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then(hit => {
      if (hit) return hit;
      return fetch(req).then(res => {
        const copy = res.clone();
        caches.open(box).then(async c => {
          await c.put(req, copy);
          if (isImg) await trim(c);
        }).catch(() => {});
        return res;
      }).catch(() => {
        // 離線又沒快取：導覽請求退回首頁，其餘讓它失敗
        if (req.mode === 'navigate') return caches.match('./index.html');
      });
    })
  );
});
