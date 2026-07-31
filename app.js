'use strict';

// 資料是分檔的：首頁只載 index.json（44KB），點進某國或某類線索才載該檔，
// 載過的留在 cache 裡，返回時不重打。
const DATA = 'data/site/';
const IMG = 'assets/img/';
const cache = new Map();

let index = null;
let zh = {};   // 國名中譯，缺的就顯示英文原名

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

async function load(path) {
  if (cache.has(path)) return cache.get(path);
  // 資料檔會隨著補圖與翻譯反覆重建，讓瀏覽器每次都回伺服器驗證（命中就 304，很快）
  const p = fetch(DATA + path, { cache: 'no-cache' }).then(r => {
    if (!r.ok) throw new Error(path + ' ' + r.status);
    return r.json();
  });
  cache.set(path, p);
  return p;
}

// ---------------------------------------------------------------- 工具

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// plonkit 的說明是 markdown，只用到粗體與連結兩種
function md(s) {
  return esc(s)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, t, u) =>
      /^https?:\/\//.test(u) ? `<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>` : t)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

const cname = c => zh[c.key] || zh[c.name] || c.name;

// 原站用兩種前綴標記段落：NOTE 是補充說明（壓低一階），
// !! 是「容易跟鄰國搞混」的對照提醒（反而要突顯）
function para(t) {
  const s = (t || '').trim();
  if (s.startsWith('!!')) return `<p class="warn">${md(s.slice(2).trim())}</p>`;
  return `<p class="${/^(NOTE|註)[:：]/i.test(s) ? 'note' : ''}">${md(s)}</p>`;
}

// 翻譯是逐條累積的，某一條還沒翻就顯示該條英文原文，不用整篇等
const bodyText = t => (t.text || []).map((s, i) => para((t.text_zh || [])[i] || s)).join('');

function shots(list, label) {
  return list.map(g => `
    <figure class="shot">
      <img loading="lazy" src="${IMG}${esc(g.image)}" alt="" data-full="${IMG}${esc(g.image)}">
      <figcaption class="cap">
        <span>${esc(label ? label(g) : '')}</span>
        ${g.link ? `<a href="${esc(g.link)}" target="_blank" rel="noopener">實景</a>` : ''}
      </figcaption>
    </figure>`).join('');
}

// ---------------------------------------------------------------- 國家一覽

const CONTINENT_ZH = {
  'Europe': '歐洲', 'Asia': '亞洲', 'Africa': '非洲',
  'North America': '北美洲', 'South America': '南美洲',
  'Oceania': '大洋洲', 'Antarctica': '南極', 'General Guide': '通用指南',
};

// 國旗小標。alt 留空是刻意的：旁邊就是國名，讓螢幕閱讀器念兩次反而吵
const flagImg = c => c.flag
  ? `<img class="flag" src="${IMG}${c.flag}" alt="" loading="lazy">` : '';

function viewCountries() {
  const withGuide = index.countries.filter(c => !c.no_guide);
  const groups = {};
  withGuide.forEach(c => (groups[c.continent || '其他'] ||= []).push(c));

  const order = ['Europe', 'Asia', 'North America', 'South America', 'Africa', 'Oceania', 'Antarctica', 'General Guide'];
  const keys = [...new Set([...order.filter(k => groups[k]), ...Object.keys(groups)])];

  const thin = index.countries.filter(c => c.no_guide);

  $('#v-countries').innerHTML = `
    <p class="lead">收錄 ${withGuide.length} 個國家與地區的完整辨識攻略，共 ${index.countries.reduce((a, c) => a + c.tips, 0)} 條線索說明。
    賽前複習用這裡，遊戲中反查請切到「按線索」。</p>
    ${keys.map(k => `
      <div class="rule"><h2>${CONTINENT_ZH[k] || k}</h2><span class="count">${groups[k].length}</span></div>
      <div class="grid">
        ${groups[k].map(c => `
          <a class="card" href="#/country/${c.file}">
            ${flagImg(c)}
            <div class="nm">${esc(cname(c))}</div>
            <div class="meta">${c.tips} 條說明${c.gallery ? ` · ${c.gallery} 張圖鑑` : ''}</div>
          </a>`).join('')}
      </div>`).join('')}
    <div class="rule"><h2>僅有硬線索</h2><span class="count">${thin.length}</span></div>
    <p class="lead">這些國家沒有完整攻略，但仍可查行車方向、電話區碼、網域、貨幣等可直接鎖定答案的硬線索。</p>
    <div class="grid">
      ${thin.map(c => `<a class="card thin" href="#/country/${c.file}">${flagImg(c)}<div class="nm">${esc(cname(c))}</div></a>`).join('')}
    </div>`;
}

// ---------------------------------------------------------------- 線索一覽

function viewClues() {
  $('#v-clues').innerHTML = `
    <p class="lead">遊戲進行中最實用的入口：看到一根沒見過的電線桿、一種沒看過的路樁，
    從這裡挑對應類型，比對各國實例。</p>
    <div class="rule"><h2>線索類型</h2><span class="count">${index.clues.length}</span></div>
    <div class="grid">
      ${index.clues.map(c => `
        <a class="card" href="#/clue/${c.key}">
          <div class="nm">${esc(c.zh)}</div>
          <div class="meta">${c.gallery ? `${c.gallery} 張圖鑑` : ''}${c.gallery && c.tips ? ' · ' : ''}${c.tips ? `${c.tips} 條說明` : ''}</div>
        </a>`).join('')}
    </div>`;
}

// ---------------------------------------------------------------- 國家頁

const FACT_LABEL = {
  driving_side: '行車方向', phone_numbers: '電話區碼', domains: '網域',
  currencies: '貨幣', lines: '道路標線', years: '街景年份', street_suffix: '街道後綴',
};

function factValue(k, v) {
  if (k === 'driving_side') return v === 'left' ? '靠左行駛' : '靠右行駛';
  if (k === 'domains') return v.join('　');
  if (k === 'currencies') return v.map(c => `${esc(c.symbol || c.code)} <small>${esc(c.name)}</small>`).join('<br>');
  if (k === 'years') return v.length ? `${v[0]}–${v[v.length - 1]} <small>共 ${v.length} 年</small>` : '無';
  if (k === 'lines') {
    return `<div class="road">${v.map(g =>
      `<span class="grp">${g.map(c => `<i style="background:${/^[a-z]+$|^#[0-9a-f]{3,6}$/i.test(c) ? c : '#fff'}"></i>`).join('')}</span>`
    ).join('')}</div>`;
  }
  if (k === 'street_suffix') return v.slice(0, 4).map(e => esc(e.forms)).join('<br>');
  return esc(String(v));
}

async function viewCountry(file) {
  const el = $('#v-country');
  el.innerHTML = '<p class="empty">載入中…</p>';
  let c;
  try {
    c = await load(`countries/${file}.json`);
  } catch {
    el.innerHTML = '<p class="empty">找不到這個國家的資料</p>';
    return;
  }

  const facts = c.facts || {};
  const factKeys = Object.keys(FACT_LABEL).filter(k => facts[k] != null &&
    !(Array.isArray(facts[k]) && !facts[k].length));

  const gal = c.gallery || {};
  const clueName = k => (index.clues.find(x => x.key === k) || {}).zh || k;

  el.innerHTML = `
    <div class="page-head">
      <a class="back" href="#/">← 全部國家</a>
      <h1>${esc(cname(c))}</h1>
      <div class="sub">${esc(c.name)}${c.code ? ` · ${esc(c.code)}` : ''}${c.continent ? ` · ${CONTINENT_ZH[c.continent] || c.continent}` : ''}</div>
    </div>

    ${factKeys.length ? `<div class="facts">${factKeys.map(k => `
      <div class="fact"><div class="lb">${FACT_LABEL[k]}</div><div class="vl">${factValue(k, facts[k])}</div></div>
    `).join('')}</div>` : ''}

    ${(c.sections || []).map(s => `
      <section class="sec">
        <div class="rule"><h2>${esc(s.title_zh || s.title)}</h2><span class="count">${s.items.length}</span></div>
        ${s.items.map(t => `
          <article class="tip${t.important ? ' imp' : ''}">
            ${t.image ? `<div class="fig">
              <img loading="lazy" src="${IMG}${esc(t.image)}" alt="" data-full="${IMG}${esc(t.image)}">
              ${t.link ? `<a href="${esc(t.link)}" target="_blank" rel="noopener">在 Google 街景開啟</a>` : ''}
            </div>` : ''}
            <div class="bd">
              ${bodyText(t)}
              ${t.clues.length ? `<div class="tags">${t.clues.map(k =>
                `<a class="tag" href="#/clue/${k}">${esc(clueName(k))}</a>`).join('')}</div>` : ''}
            </div>
          </article>`).join('')}
      </section>`).join('')}

    ${Object.keys(gal).length ? `
      <div class="rule"><h2>實例圖鑑</h2></div>
      ${Object.entries(gal).map(([k, list]) => `
        <section class="sec">
          <h3><a href="#/clue/${k}">${esc(clueName(k))}</a> <span class="count">${list.length}</span></h3>
          <div class="gal">${shots(list, () => '')}</div>
        </section>`).join('')}` : ''}

    ${!c.sections?.length && !Object.keys(gal).length && !factKeys.length
      ? '<p class="empty">這個國家目前只有基本資料</p>' : ''}`;
}

// ---------------------------------------------------------------- 線索頁

async function viewClue(key) {
  const el = $('#v-clue');
  el.innerHTML = '<p class="empty">載入中…</p>';
  let c;
  try {
    c = await load(`clues/${key}.json`);
  } catch {
    el.innerHTML = '<p class="empty">找不到這個線索類型</p>';
    return;
  }

  // 圖鑑按國家分組，同一國的實例排在一起才好比對。
  // 分組鍵用正規化後的 country，才對得上中譯表。
  const byCountry = {};
  c.gallery.forEach(g => {
    const k = g.country || g.country_name;
    (byCountry[k] ||= { name: g.country_name, list: [] }).list.push(g);
  });
  const countries = Object.keys(byCountry)
    .sort((a, b) => (zh[a] || byCountry[a].name).localeCompare(zh[b] || byCountry[b].name, 'zh-Hant'));

  el.innerHTML = `
    <div class="page-head">
      <a class="back" href="#/clues">← 全部線索</a>
      <h1>${esc(c.zh)}</h1>
      <div class="sub">${esc(c.en)} · ${c.gallery_count} 張圖鑑 · ${c.tip_count} 條說明</div>
    </div>

    ${countries.length ? `
      <div class="rule"><h2>各國實例</h2><span class="count">${countries.length} 國</span></div>
      ${countries.map(k => `
        <section class="sec">
          <h3><a href="#/country/${esc(k.replace(/ /g, '-'))}">${esc(zh[k] || byCountry[k].name)}</a>
            <span class="count">${byCountry[k].list.length}</span></h3>
          <div class="gal">${shots(byCountry[k].list, () => '')}</div>
        </section>`).join('')}` : ''}

    ${c.tips.length ? `
      <div class="rule"><h2>攻略說明</h2><span class="count">${c.tips.length}</span></div>
      ${c.tips.map(t => `
        <article class="tip">
          ${t.image ? `<div class="fig">
            <img loading="lazy" src="${IMG}${esc(t.image)}" alt="" data-full="${IMG}${esc(t.image)}">
            ${t.link ? `<a href="${esc(t.link)}" target="_blank" rel="noopener">在 Google 街景開啟</a>` : ''}
          </div>` : ''}
          <div class="bd">
            <p><a href="#/country/${esc(t.country.replace(/ /g, '-'))}"><strong>${esc(zh[t.country] || t.country_name)}</strong></a></p>
            ${bodyText(t)}
          </div>
        </article>`).join('')}` : ''}

    ${!countries.length && !c.tips.length ? '<p class="empty">這個類型還沒有資料</p>' : ''}`;
}

// ---------------------------------------------------------------- 搜尋

function search(term) {
  const box = $('#qr');
  const t = term.trim().toLowerCase();
  if (t.length < 1) { box.classList.remove('show'); return; }

  const hits = [];
  for (const c of index.countries) {
    const n = cname(c);
    if (n.toLowerCase().includes(t) || c.name.toLowerCase().includes(t) || c.code.toLowerCase() === t) {
      hits.push({ href: `#/country/${c.file}`, name: n, kind: c.no_guide ? '硬線索' : `${c.tips} 條` });
    }
    if (hits.length > 40) break;
  }
  for (const c of index.clues) {
    if (c.zh.includes(t) || c.en.toLowerCase().includes(t)) {
      hits.push({ href: `#/clue/${c.key}`, name: c.zh, kind: '線索' });
    }
  }

  box.innerHTML = hits.length
    ? hits.slice(0, 24).map(h => `<a href="${h.href}">${esc(h.name)}<span class="k">${esc(h.kind)}</span></a>`).join('')
    : '<a>沒有符合的結果</a>';
  box.classList.add('show');
}

// ---------------------------------------------------------------- 路由

function route() {
  const h = location.hash.replace(/^#\/?/, '');
  const [seg, arg] = h.split('/');

  $$('.view').forEach(v => v.classList.remove('on'));
  $$('nav a').forEach(a => a.classList.remove('on'));

  if (seg === 'country' && arg) {
    $('#v-country').classList.add('on');
    viewCountry(arg);
  } else if (seg === 'clue' && arg) {
    $('#v-clue').classList.add('on');
    viewClue(arg);
  } else if (seg === 'clues') {
    $('#v-clues').classList.add('on');
    $('nav a[data-nav=clues]').classList.add('on');
    viewClues();
  } else {
    $('#v-countries').classList.add('on');
    $('nav a[data-nav=countries]').classList.add('on');
    viewCountries();
  }
  $('#qr').classList.remove('show');
  window.scrollTo(0, 0);
}

// ---------------------------------------------------------------- 啟動

(async function () {
  try {
    index = await load('index.json');
  } catch {
    document.querySelector('main').innerHTML =
      '<p class="empty">讀不到資料。這個網站需要透過 HTTP 開啟，請在專案目錄執行 python -m http.server 8765 再瀏覽 localhost:8765</p>';
    return;
  }
  try { zh = await load('country_zh.json'); } catch { zh = {}; }

  window.addEventListener('hashchange', route);
  route();

  $('#q').addEventListener('input', e => search(e.target.value));
  document.addEventListener('click', e => {
    if (!e.target.closest('.search')) $('#qr').classList.remove('show');
    const img = e.target.closest('img[data-full]');
    if (img) {
      $('#lb img').src = img.dataset.full;
      $('#lb').classList.add('on');
    }
    if (e.target.closest('#lb')) $('#lb').classList.remove('on');
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { $('#lb').classList.remove('on'); $('#qr').classList.remove('show'); }
    if (e.key === '/' && document.activeElement !== $('#q')) { e.preventDefault(); $('#q').focus(); }
  });
})();
