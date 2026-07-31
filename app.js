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
// 產生連結時，網址裡的底線與 target="_blank" 的底線都先換成佔位字串，
// 最後一步再換回來。否則斜體規則會把 Flag_of_the_United_States 當成 _of_ 咬進去；
// 一段話有兩個連結時，兩個 _blank 的底線還會互相配對，把 target 屬性整個吃掉。
// 順序也不能改：連結先換掉，粗體與斜體才吃得到連結文字裡的標記。
const UND = '@@UND@@';

function md(s) {
  return esc(s)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, t, u) =>
      /^https?:\/\//.test(u)
        ? `<a href="${esc(u).replace(/_/g, UND)}" target="${UND}blank" rel="noopener">${t}</a>` : t)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/_([^_\n]+)_/g, '<em>$1</em>')
    .replace(new RegExp(UND, 'g'), '_');
}

const cname = c => zh[c.key] || zh[c.name] || c.name;

// 國家 key 帶空格（united states of america），直接當 HTML id 會讓選取器出錯
const cid = k => k.replace(/[^a-z0-9]+/gi, '-');

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
      <img loading="lazy" class="${/\.svg$/i.test(g.image) ? 'vec' : ''}"
           src="${IMG}${esc(g.image)}" alt="" data-full="${IMG}${esc(g.image)}">
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

// geohints 沒有替每張圖標名稱，唯一能還原的脈絡是它來自哪個子頁。
// 商家品牌那類混了啤酒與郵政兩種完全不同的東西，不標出來只看圖真的認不出在比什麼。
const SUBCAT = {
  '/meta/companies/beer': '啤酒品牌',
  '/meta/companies/post': '郵政',
  '/meta/companies/gasStations': '加油站',
};

// 線索頁的國家排序依據：GeoGuessr 世界地圖裡的出現頻率，大致跟街景道路覆蓋量成正比。
// 這是人工判斷不是官方數據，官方沒有公布出題機率；資料裡的攻略條數也不能拿來替代
// （吉爾吉斯、納米比亞內容多但很少出現，只是特徵獨特所以 plonkit 寫得詳細）。
// 沒列到的國家排在後面，再依該線索的資料量多寡排。順序覺得不對直接調這份清單。
const FREQ_ORDER = [
  'united states of america', 'brazil', 'russia', 'japan', 'france', 'canada',
  'australia', 'united kingdom', 'spain', 'italy', 'mexico', 'argentina',
  'south africa', 'indonesia', 'poland', 'thailand', 'germany', 'sweden',
  'finland', 'norway', 'turkey', 'chile', 'peru', 'colombia', 'philippines',
  'malaysia', 'new zealand', 'netherlands', 'romania', 'czechia', 'portugal',
  'greece', 'hungary', 'bulgaria', 'denmark', 'belgium', 'austria', 'switzerland',
  'ireland', 'india', 'taiwan', 'south korea', 'ukraine', 'kenya', 'nigeria',
  'ghana', 'senegal', 'botswana', 'bangladesh', 'sri lanka', 'israel and the west bank',
  'jordan', 'united arab emirates', 'singapore', 'hong kong', 'estonia', 'latvia',
  'lithuania', 'slovakia', 'slovenia', 'croatia', 'serbia', 'iceland', 'ecuador',
  'bolivia', 'uruguay', 'guatemala', 'dominican republic', 'costa rica', 'panama',
  'cambodia', 'laos', 'vietnam', 'mongolia', 'kazakhstan', 'kyrgyzstan', 'nepal',
  'pakistan', 'tunisia', 'egypt', 'uganda', 'tanzania', 'rwanda', 'eswatini',
  'lesotho', 'namibia', 'madagascar',
];
const FREQ_RANK = Object.fromEntries(FREQ_ORDER.map((k, i) => [k, i]));

// 國旗小標。alt 留空是刻意的：旁邊就是國名，讓螢幕閱讀器念兩次反而吵
const flagImg = c => c.flag
  ? `<img class="flag" src="${IMG}${c.flag}" alt="" loading="lazy">` : '';

// ---------------------------------------------------------------- 首頁猜國家

// 題庫是 build_data.py 產的 [圖片, 國家key, 線索類型]，每國最多 6 題、46KB，
// 只在首頁第一次渲染時載一次。
let quizPool = null;
let quizCur = null;

function pickQuiz() {
  if (!quizPool || !quizPool.length) return;
  let next;
  do {
    next = quizPool[Math.floor(Math.random() * quizPool.length)];
  } while (quizPool.length > 1 && next === quizCur);  // 不要連兩題同一張
  quizCur = next;
}

function renderQuiz(reveal) {
  const el = $('#quiz');
  if (!el || !quizCur) return;
  const [img, key, kind] = quizCur;
  const c = index.countries.find(x => x.key === key);
  if (!c) { pickQuiz(); renderQuiz(false); return; }

  el.innerHTML = `
    <div class="quiz-h"><span class="quiz-k">${esc(kind)}</span><span class="quiz-q">這是哪一國？</span></div>
    <img class="shot-img${/\.svg$/i.test(img) ? ' vec' : ''}" src="${IMG}${esc(img)}" alt=""
         data-full="${IMG}${esc(img)}">
    ${reveal ? `
      <a class="quiz-a" href="#/country/${esc(c.file)}">
        ${c.flag ? `<img class="flag" src="${IMG}${esc(c.flag)}" alt="">` : ''}
        <b>${esc(cname(c))}</b><i>看完整攻略 →</i>
      </a>` : ''}
    <div class="quiz-btns">
      ${reveal ? '' : '<button type="button" data-quiz="reveal">揭曉答案</button>'}
      <button type="button" data-quiz="next">${reveal ? '再來一題' : '換一題'}</button>
    </div>`;
}

async function initQuiz() {
  try {
    quizPool = quizPool || await load('quiz.json');
  } catch {
    $('#quiz')?.remove();   // 題庫載不到就整塊拿掉，不要留一個「載入中」卡在那裡
    return;
  }
  pickQuiz();
  renderQuiz(false);
}

function heroHtml(withGuide) {
  const tips = index.countries.reduce((a, c) => a + c.tips, 0);
  const gal = index.countries.reduce((a, c) => a + c.gallery, 0);
  return `
    <section class="hero">
      <div class="hero-l">
        <div>
        <h1 class="hero-t">GeoGuessr <em>線索圖鑑</em></h1>
        <p class="hero-s">整合 plonkit 與 geohints 兩站的辨識線索，${withGuide} 國完整攻略，全站繁體中文。
        各洲內依常出現的程度排序，愈前面愈值得先記。遊戲中看到沒見過的東西就切「按線索」反查。</p>
        </div>
        <div class="stats">
          <div><b>${index.countries.length}</b><span>國家與地區</span></div>
          <div><b>${tips}</b><span>攻略說明</span></div>
          <div><b>${gal}</b><span>線索圖鑑</span></div>
        </div>
      </div>
      <div class="quiz" id="quiz"><div class="quiz-load">題目載入中…</div></div>
    </section>`;
}

// 跟線索頁同一套順序：常考的排前面，同一級再看攻略條數，最後用中文名收尾
// 確保每次載入順序都一樣不會跳動
const byFreq = (a, b) => {
  const fa = FREQ_RANK[a.key] ?? 999, fb = FREQ_RANK[b.key] ?? 999;
  if (fa !== fb) return fa - fb;
  if (a.tips !== b.tips) return b.tips - a.tips;
  return cname(a).localeCompare(cname(b), 'zh-Hant');
};

function viewCountries() {
  const withGuide = index.countries.filter(c => !c.no_guide);
  const groups = {};
  withGuide.forEach(c => (groups[c.continent || '其他'] ||= []).push(c));
  Object.values(groups).forEach(g => g.sort(byFreq));

  const order = ['Europe', 'Asia', 'North America', 'South America', 'Africa', 'Oceania', 'Antarctica', 'General Guide'];
  const keys = [...new Set([...order.filter(k => groups[k]), ...Object.keys(groups)])];

  const thin = index.countries.filter(c => c.no_guide).sort(byFreq);

  $('#v-countries').innerHTML = `
    ${heroHtml(withGuide.length)}
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

  initQuiz();
}

// ---------------------------------------------------------------- 線索一覽

function viewClues() {
  $('#v-clues').innerHTML = `
    <p class="lead">遊戲進行中最實用的入口：看到一根沒見過的電線桿、一種沒看過的路樁，
    從這裡挑對應類型，比對各國實例。</p>
    <div class="rule"><h2>線索類型</h2><span class="count">${index.clues.length}</span></div>
    <div class="grid">
      ${index.clues.map(c => `
        <a class="card clue-card" href="#/clue/${c.key}">
          <div class="nm">${esc(c.zh)}</div>
          ${c.lead ? `<div class="cl">${esc(c.lead)}</div>` : ''}
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

  // 圖鑑與攻略說明都按國家分組後合併進同一區塊。
  // 原本是先列完 109 國、405 張圖，才在最下面接 164 條說明，等於文字永遠滑不到，
  // 而且看某國的照片時，那一國的解釋在幾千像素外。
  // 分組鍵用正規化後的 country，才對得上中譯表。
  // geohints 有些圖不屬於任何國家，是在展示「這種線索總共有哪幾種長相」的款式圖
  // （路標 60 張、轉彎標誌 5 張…共 85 張）。掛在空白國名底下會變成無標題區塊，
  // 獨立成一節放最前面反而是最好的入門總覽。
  const generic = c.gallery.filter(g => !(g.country || g.country_name));

  const byCountry = {};
  const bucket = (k, name) => (byCountry[k] ||= { name, shots: [], tips: [] });
  c.gallery.forEach(g => {
    const k = g.country || g.country_name;
    if (k) bucket(k, g.country_name).shots.push(g);
  });
  c.tips.forEach(t => bucket(t.country, t.country_name).tips.push(t));

  // 常考的排前面；同一級再看該線索的資料量，最後才用中文名收尾確保順序穩定
  const countries = Object.keys(byCountry).sort((a, b) => {
    const fa = FREQ_RANK[a] ?? 999, fb = FREQ_RANK[b] ?? 999;
    if (fa !== fb) return fa - fb;
    const va = byCountry[a].tips.length + byCountry[a].shots.length;
    const vb = byCountry[b].tips.length + byCountry[b].shots.length;
    if (va !== vb) return vb - va;
    return (zh[a] || byCountry[a].name).localeCompare(zh[b] || byCountry[b].name, 'zh-Hant');
  });

  el.innerHTML = `
    <div class="page-head">
      <a class="back" href="#/clues">← 全部線索</a>
      <h1>${esc(c.zh)}</h1>
      <div class="sub">${esc(c.en)} · ${c.gallery_count} 張圖鑑 · ${c.tip_count} 條說明</div>
    </div>

    ${c.intro ? `
      <section class="intro">
        <h2>${esc(c.intro.lead)}</h2>
        ${c.intro.body.map(p => `<p>${esc(p)}</p>`).join('')}
      </section>` : ''}

    ${countries.length ? '<p class="lead">各國依常出現的程度排序，愈前面愈值得先記。怎麼判讀看上方導言。</p>' : ''}

    ${generic.length ? `
      <div class="rule"><h2>通用款式</h2><span class="count">${generic.length}</span></div>
      <div class="gal">${shots(generic, () => '')}</div>` : ''}

    ${countries.length ? `
      <div class="rule"><h2>各國實例與說明</h2><span class="count">${countries.length} 國</span></div>
      <div class="clue-wrap">
      <div>
      ${countries.map(k => {
        const b = byCountry[k];
        return `
        <section class="sec" id="c-${cid(k)}">
          <h3><a href="#/country/${esc(k.replace(/ /g, '-'))}">${esc(zh[k] || b.name)}</a>
            <span class="count">${[b.tips.length && `${b.tips.length} 說明`, b.shots.length && `${b.shots.length} 圖`]
              .filter(Boolean).join(' · ')}</span></h3>
          ${b.tips.map(t => `
            <article class="tip${t.important ? ' imp' : ''}">
              ${t.image ? `<div class="fig">
                <img loading="lazy" src="${IMG}${esc(t.image)}" alt="" data-full="${IMG}${esc(t.image)}">
                ${t.link ? `<a href="${esc(t.link)}" target="_blank" rel="noopener">在 Google 街景開啟</a>` : ''}
              </div>` : ''}
              <div class="bd">${bodyText(t)}</div>
            </article>`).join('')}
          ${b.shots.length ? `<div class="gal">${shots(b.shots, g => SUBCAT[g.source_page] || '')}</div>` : ''}
        </section>`;
      }).join('')}
      </div>
      <aside class="jump">
        <div class="jump-h">跳到國家</div>
        <input class="jump-f" id="jf" type="search" placeholder="篩選國家" autocomplete="off">
        <div class="jump-list" id="jl">
          ${countries.map(k => `
            <a data-jump="${cid(k)}" data-nm="${esc((zh[k] || byCountry[k].name).toLowerCase())} ${esc(k)}">
              ${esc(zh[k] || byCountry[k].name)}
              <i>${byCountry[k].tips.length || ''}${byCountry[k].tips.length && byCountry[k].shots.length ? '·' : ''}${byCountry[k].shots.length || ''}</i>
            </a>`).join('')}
        </div>
      </aside>
      </div>` : '<p class="empty">這個類型還沒有資料</p>'}`;

  // 111 國的清單用滑的還是慢，加個即時篩選。中英文都比對，打 japan 或 日本 都找得到
  const jf = $('#jf');
  if (jf) {
    jf.addEventListener('input', () => {
      const t = jf.value.trim().toLowerCase();
      let n = 0;
      $$('#jl a').forEach(a => {
        const hit = !t || a.dataset.nm.includes(t);
        a.style.display = hit ? '' : 'none';
        if (hit) n++;
      });
      const none = $('#jl .jump-none');
      if (!n && !none) $('#jl').insertAdjacentHTML('beforeend', '<div class="jump-none">沒有符合的國家</div>');
      if (n && none) none.remove();
    });
  }
}

// ---------------------------------------------------------------- 搜尋

// 內文索引 1MB，只在第一次真的要搜內文時才載，不拖慢首頁
let corpus = null;
let corpusLoading = null;
let searchSeq = 0;   // 打字很快時會有多個搜尋同時在跑，用序號丟掉過期的結果

function snippet(text, t) {
  const i = text.toLowerCase().indexOf(t);
  if (i < 0) return esc(text.slice(0, 70));
  const from = Math.max(0, i - 24);
  const s = (from ? '…' : '') + text.slice(from, i) ;
  return esc(s) + '<mark>' + esc(text.substr(i, t.length)) + '</mark>'
    + esc(text.slice(i + t.length, i + t.length + 46)) + '…';
}

function bodyHits(t) {
  const hits = [];
  for (const [key, text] of corpus) {
    if (text.toLowerCase().includes(t)) {
      hits.push({ key, text });
      // 掃完整份才排得出優先序，但命中太多時排序沒意義，設個上限保護打字延遲
      if (hits.length >= 300) break;
    }
  }
  // 常考的國家排前面，否則搜「路樁」第一筆會是安道爾而不是德國
  hits.sort((a, b) => (FREQ_RANK[a.key] ?? 999) - (FREQ_RANK[b.key] ?? 999));
  // 每國只留一筆。美國光路樁就有 12 條說明，不限制的話 8 筆全是美國，
  // 而搜尋要的是跨國比較不是同一國的細節
  const seen = new Set();
  return hits.filter(h => !seen.has(h.key) && seen.add(h.key)).slice(0, 8);
}

async function searchBody(t, seq) {
  if (!corpus) {
    corpusLoading ||= load('search.json').catch(() => []);
    corpus = await corpusLoading;
  }
  if (seq !== searchSeq) return;   // 使用者已經改字了，這次結果作廢

  const box = $('#qr');
  const old = box.querySelector('.grp-body');
  if (old) old.remove();
  const hits = bodyHits(t);
  if (!hits.length) {
    // 國名與線索名也沒中的話，這時才是真的什麼都沒有
    if (!box.querySelector('a')) box.innerHTML = '<a>沒有符合的結果</a>';
    return;
  }

  box.insertAdjacentHTML('beforeend', `<div class="grp-body">
    <div class="grp">內文 ${hits.length >= 8 ? '常考的前 8 筆' : hits.length + ' 筆'}</div>
    ${hits.map(h => {
      const c = index.countries.find(x => x.key === h.key);
      return `<a href="#/country/${esc(c ? c.file : h.key.replace(/ /g, '-'))}">
        <b>${esc(c ? cname(c) : h.key)}</b>
        <span class="sn">${snippet(h.text, t)}</span></a>`;
    }).join('')}</div>`);
}

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

  const seq = ++searchSeq;
  box.innerHTML = hits.length
    ? hits.slice(0, 12).map(h => `<a href="${h.href}">${esc(h.name)}<span class="k">${esc(h.kind)}</span></a>`).join('')
    : '';
  box.classList.add('show');

  // 兩個字以上才搜內文，一個字命中太多沒有意義
  if (t.length >= 2) {
    if (!corpus) box.insertAdjacentHTML('beforeend',
      '<div class="grp-body"><div class="grp">內文搜尋中…</div></div>');
    searchBody(t, seq);
  } else if (!hits.length) {
    box.innerHTML = '<a>沒有符合的結果</a>';
  }
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

    // 首頁題目的按鈕。用委派是因為首頁每次切回來都會整塊重畫，直接綁會掉
    const qb = e.target.closest('[data-quiz]');
    if (qb) {
      if (qb.dataset.quiz === 'next') pickQuiz();
      renderQuiz(qb.dataset.quiz === 'reveal');
      return;
    }

    // 側欄跳到某一國。不能用 href="#..." 錨點，這站是 hash 路由，改 hash 會被當成換頁
    const jp = e.target.closest('[data-jump]');
    if (jp) {
      // 用瞬間跳不用 smooth：跨越上萬像素的平滑捲動要等很久，而且 smooth 在
      // 開了減少動態效果的系統上本來就會被停用。被版首遮擋的問題交給
      // CSS 的 scroll-margin-top 處理，比在這裡硬減一個像素值可靠
      document.getElementById('c-' + jp.dataset.jump)?.scrollIntoView();
      return;
    }

    const img = e.target.closest('img[data-full]');
    if (img) {
      $('#lb img').src = img.dataset.full;
      $('#lb').classList.add('on');
    }
    if (e.target.closest('#lb')) $('#lb').classList.remove('on');
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { $('#lb').classList.remove('on'); $('#qr').classList.remove('show'); }
    // 打斜線跳到搜尋框，但人在任何輸入欄位裡時不能搶焦點（側欄篩選也是輸入框）
    if (e.key === '/' && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      e.preventDefault();
      $('#q').focus();
    }
  });
})();
