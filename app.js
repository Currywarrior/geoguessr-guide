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

// 說明列只在真的有字時才出現。國家頁與通用款式區從來不給 label，
// 原本每張圖底下都固定掛一條，結果是一條空白帶右邊浮著一個「實景」，
// 整面圖鑑被那些空條切得很碎。街景連結改成疊在圖片右下角的小徽章。
function shots(list, label) {
  return list.map(g => {
    const cap = label ? label(g) : '';
    return `
    <figure class="shot">
      <img loading="lazy" class="${/\.svg$/i.test(g.image) ? 'vec' : ''}"
           src="${IMG}${esc(g.image)}" alt="" data-full="${IMG}${esc(g.image)}">
      ${g.link ? `<a class="shot-go" href="${esc(g.link)}" target="_blank" rel="noopener">街景</a>` : ''}
      ${cap ? `<figcaption class="cap">${esc(cap)}</figcaption>` : ''}
    </figure>`;
  }).join('');
}

// 進場動效：區塊捲進畫面才淡入上移，捲過就取消觀察不再管它。
// 只觀察容器不觀察每一張卡（首頁有 258 張，逐張掛觀察器不划算），
// 卡片交給容器的 .in 帶著一起進場。
// 這裡用 IntersectionObserver 沒有線索頁那個順序問題——那邊要知道「現在在第幾個區塊」，
// 這邊只要知道「有沒有進來過」，觸發順序錯亂也不影響。
let revealIO = null;

function reveal() {
  if (prefersStill()) return;
  revealIO?.disconnect();
  revealIO = new IntersectionObserver(es => {
    es.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.classList.add('in');
      revealIO.unobserve(e.target);
    });
  }, { rootMargin: '0px 0px -40px 0px' });
  // 只找目前顯示中的那一頁。其他 view 是 display:none，觀察器不會觸發，
  // 那些元素會一直掛著 .rv（opacity:0）；雖然切過去時整塊會重畫不至於出事，
  // 但沒必要留這種「隱形節點」在文件裡
  $$('.view.on .plate, .view.on .rule, .view.on .grid, .view.on .sec, .view.on .vs-g, .view.on .run, .view.on .miss, .view.on .weak')
    .forEach(el => {
      el.classList.add('rv');
      revealIO.observe(el);
    });
}

// ---------------------------------------------------------------- 國家一覽

const CONTINENT_ZH = {
  'Europe': '歐洲', 'Asia': '亞洲', 'Africa': '非洲',
  'North America': '北美洲', 'South America': '南美洲',
  'Oceania': '大洋洲', 'Antarctica': '南極', 'General Guide': '通用指南',
};

// 捲到哪一國，側欄就高亮哪一國。
// 沒有用 IntersectionObserver：一次捲很遠時會同時觸發好幾個區塊，
// 事件順序不保證是由上而下，取最後一筆會標錯（實測捲到法國卻標日本）。
// 直接算「目前捲動位置落在第幾個區塊」才不會錯。
// 每次都重新量 offsetTop 是因為圖片是延遲載入的，載入後版面高度會變。
let secCleanup = null;

function watchSections() {
  secCleanup?.();
  secCleanup = null;

  const list = $('#jl');
  const secs = $$('.sec[id]');
  if (!list || !secs.length) return;
  const links = new Map($$('#jl a').map(a => [a.dataset.jump, a]));

  let cur = -1, ticking = false;

  const apply = () => {
    ticking = false;
    const y = window.scrollY + 96;   // 版首高度再多留一點，讓標題進來才算數
    let i = 0;
    while (i + 1 < secs.length && secs[i + 1].offsetTop <= y) i++;
    if (i === cur) return;
    cur = i;

    $$('#jl a.on').forEach(a => a.classList.remove('on'));
    const link = links.get(secs[i].id.replace(/^c-/, ''));
    if (!link) return;
    link.classList.add('on');
    // 高亮的項目跑到清單可視範圍外時，把清單自己捲過去
    const top = link.offsetTop;
    if (top < list.scrollTop || top + link.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = top - list.clientHeight / 2;
    }
  };

  const onScroll = () => {
    if (!ticking) { ticking = true; requestAnimationFrame(apply); }
  };

  // 圖片是延遲載入的，捲過去之後圖片才載入、版面被撐高，區塊位置整個位移，
  // 但這時不會有捲動事件所以不會重算，高亮就會停在錯的國家。
  // 監聽內容高度變化補上這一段。
  const ro = new ResizeObserver(onScroll);
  ro.observe(list.closest('.clue-wrap'));

  apply();
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  secCleanup = () => {
    ro.disconnect();
    window.removeEventListener('scroll', onScroll);
    window.removeEventListener('resize', onScroll);
  };
}

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
let quizKeys = null;   // 題庫涵蓋的國家，練習模式挑干擾項時只從這裡面挑

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
      <a class="quiz-go" href="#/quiz">十題測驗 →</a>
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

// ---------------------------------------------------------------- 練習模式
// 首頁那張小卡只是閃卡：看圖、揭曉、換一張。沒有作答，也就不會知道自己
// 到底記住多少。這裡做成一輪十題的測驗，四選一、計分，結束後列出答錯的題目。

const RUN_LEN = 10;
let run = null;

// ---------------------------------------------------------------- 練習紀錄
// 純前端、存在瀏覽器裡，沒有帳號也沒有伺服器。做這個是因為原本每一輪都是
// 從零開始，練完就沒了：分數不累積、答錯的國家下次也不會再遇到，
// 等於每次都在隨機翻牌而不是在補自己的弱點。
const STATS_KEY = 'geoatlas.stats';
const REVIEW_MAX = 4;      // 一輪十題最多插幾題複習，太多會變成一直看同幾國
let statsCache = null;

function stats() {
  if (statsCache) return statsCache;
  // 無痕視窗或封鎖第三方儲存時 localStorage 會直接丟例外，不能讓練習頁跟著掛掉
  try { statsCache = JSON.parse(localStorage.getItem(STATS_KEY)); } catch { statsCache = null; }
  if (!statsCache || statsCache.v !== 1) {
    statsCache = { v: 1, runs: 0, total: 0, hits: 0, best: 0, streak: 0, bestStreak: 0, miss: {}, seen: {} };
  }
  return statsCache;
}

function saveStats() {
  try { localStorage.setItem(STATS_KEY, JSON.stringify(statsCache)); } catch { /* 存不了就算了 */ }
}

// 每答一題就記。答對會把該國的錯誤次數減一而不是直接清掉——
// 錯過三次的國家不該答對一次就從弱點清單消失，那不算真的記起來了
function noteAnswer(key, ok) {
  const s = stats();
  s.seen[key] = (s.seen[key] || 0) + 1;
  if (ok) {
    if (s.miss[key]) {
      s.miss[key]--;
      if (s.miss[key] <= 0) delete s.miss[key];
    }
    s.streak++;
    if (s.streak > s.bestStreak) s.bestStreak = s.streak;
  } else {
    s.miss[key] = (s.miss[key] || 0) + 1;
    s.streak = 0;
  }
  saveStats();
}

function finishRun() {
  const s = stats();
  s.runs++;
  s.total += run.queue.length;
  s.hits += run.score;
  run.record = run.score > s.best && s.runs > 1;   // 第一輪本來就一定是最佳，不算破紀錄
  if (run.score > s.best) s.best = run.score;
  saveStats();
}

function clearStats() {
  statsCache = null;
  try { localStorage.removeItem(STATS_KEY); } catch { /* 同上 */ }
}

function shuffle(a) {
  const r = a.slice();
  for (let i = r.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [r[i], r[j]] = [r[j], r[i]];
  }
  return r;
}

// 干擾項要「像是會搞混的國家」才有練習價值：同洲抽兩個、跨洲抽一個。
// 全隨機的話，歐洲的路樁配上三個非洲選項，不用看圖也知道答案。
// 候選只從題庫出現過的國家挑，那些才是遊戲裡真的會遇到的。
function optionsFor(key) {
  const right = index.countries.find(c => c.key === key);
  const pool = index.countries.filter(c => c.key !== key && quizKeys.has(c.key));
  const same = shuffle(pool.filter(c => c.continent === right.continent));
  const rest = shuffle(pool.filter(c => c.continent !== right.continent));
  const wrong = [...same.slice(0, 2), ...rest.slice(0, 1)];
  // 同洲候選不夠（大洋洲那種）就從剩下的補滿三個
  for (const c of [...same.slice(2), ...rest.slice(1)]) {
    if (wrong.length >= 3) break;
    wrong.push(c);
  }
  return shuffle([right, ...wrong]);
}

function startRun() {
  const weak = stats().miss;
  const pool = shuffle(quizPool);
  // 答錯過的國家優先排進來，一輪最多佔四題：練習要能補洞，不然錯過的國家
  // 下次還是隨機才遇得到。剩下的名額照舊隨機，避免一直在複習同幾國
  const rev = pool.filter(q => weak[q[1]]);
  const rest = pool.filter(q => !weak[q[1]]);
  const ordered = [...rev.slice(0, REVIEW_MAX), ...rest, ...rev.slice(REVIEW_MAX)];

  const seen = new Set();
  const queue = [];
  // 一輪裡不重複同一國，否則十題有三題都是美國
  for (const q of ordered) {
    if (seen.has(q[1]) || !index.countries.some(c => c.key === q[1])) continue;
    seen.add(q[1]);
    queue.push(q);
    if (queue.length === RUN_LEN) break;
  }
  // 選完再洗一次，否則複習題永遠固定出現在前四題，一看就知道哪幾題是弱點
  const mixed = shuffle(queue);
  run = { queue: mixed, i: 0, score: 0, wrong: [], picked: null, opts: optionsFor(mixed[0][1]) };
}

function runOptHtml(c, state) {
  return `
    <button type="button" class="run-opt${state}" data-qz="ans" data-key="${esc(c.key)}"${state ? ' disabled' : ''}>
      ${c.flag ? `<img class="flag" src="${IMG}${esc(c.flag)}" alt="">` : '<span class="flag"></span>'}
      <b>${esc(cname(c))}</b>
    </button>`;
}

// 弱點清單：答錯次數最多的前幾國。每國答對一次就扣一次錯誤，
// 所以這份清單會隨著練習自己消下去，不是只進不出的黑名單
function weakHtml() {
  const s = stats();
  const top = Object.entries(s.miss)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8);
  if (!top.length) return '';
  return `
    <div class="rule"><h2>你的弱點</h2><span class="count">${Object.keys(s.miss).length}</span></div>
    <p class="lead">這幾國答錯的次數最多，下一輪會優先出現。答對就會慢慢從這裡消掉。</p>
    <div class="weak">
      ${top.map(([key, n]) => {
        const c = index.countries.find(x => x.key === key);
        if (!c) return '';
        return `
          <a class="weak-c" href="#/country/${esc(c.file)}">
            ${flagImg(c)}<b>${esc(cname(c))}</b><i>錯 ${n} 次</i>
          </a>`;
      }).join('')}
    </div>`;
}

function runResultHtml() {
  const n = run.queue.length;
  const s = stats();
  const say = run.score === n ? '全對。' :
    run.score >= n * 0.7 ? '底子有了，錯的那幾國補一下就好。' :
    run.score >= n * 0.4 ? '一半左右，答錯的那幾國值得回去把攻略看完。' :
    '這批線索還沒進到腦子裡，先從答錯的國家頁看起。';
  const avg = s.total ? (s.hits / s.total * RUN_LEN).toFixed(1) : '0';
  return `
    <div class="run">
      <div class="run-done">
        <div class="run-score-big"><b>${run.score}</b><span>/ ${n}</span></div>
        ${run.record ? '<div class="run-rec">新紀錄</div>' : ''}
        <p class="run-say">${say}</p>
        <div class="run-hist">
          <div><b>${s.runs}</b><span>累計輪數</span></div>
          <div><b>${avg}</b><span>平均分</span></div>
          <div><b>${s.best}</b><span>單輪最佳</span></div>
          <div><b>${s.bestStreak}</b><span>最長連對</span></div>
        </div>
        <button type="button" class="run-again" data-qz="again">再來一輪</button>
      </div>
      ${run.wrong.length ? `
        <div class="rule"><h2>答錯的題目</h2><span class="count">${run.wrong.length}</span></div>
        <div class="miss">
          ${run.wrong.map(w => {
            const [img, key, kind] = w.item;
            const right = index.countries.find(c => c.key === key);
            const pick = index.countries.find(c => c.key === w.picked);
            return `
              <a class="miss-c" href="#/country/${esc(right.file)}">
                <img class="${/\.svg$/i.test(img) ? 'vec' : ''}" src="${IMG}${esc(img)}" alt="" loading="lazy">
                <div class="miss-b">
                  <span class="miss-k">${esc(kind)}</span>
                  <div class="miss-r">${right.flag ? `<img class="flag" src="${IMG}${esc(right.flag)}" alt="">` : ''}<b>${esc(cname(right))}</b></div>
                  <div class="miss-w">你選了 ${esc(pick ? cname(pick) : w.picked)}</div>
                </div>
              </a>`;
          }).join('')}
        </div>` : ''}
      ${weakHtml()}
      <p class="run-reset">練習紀錄只存在這台裝置的瀏覽器裡。
        <button type="button" data-qz="reset">清除紀錄</button></p>
    </div>`;
}

function renderRun() {
  const el = $('#v-quiz');
  if (!el) return;
  if (!run) { el.innerHTML = '<p class="empty">題庫載入中…</p>'; return; }
  // 只有結果頁跑進場動效。答題中每答一題就整塊重畫，每次都淡入一遍會很吵
  if (run.i >= run.queue.length) { el.innerHTML = runResultHtml(); reveal(); return; }

  const [img, key, kind] = run.queue[run.i];
  const done = run.picked !== null;
  const right = index.countries.find(c => c.key === key);

  el.innerHTML = `
    <div class="run">
      <div class="run-top">
        <span class="run-step">第 <b>${run.i + 1}</b> / ${run.queue.length} 題</span>
        <span class="run-kind">${esc(kind)}</span>
        <span class="run-sc">答對 <b>${run.score}</b></span>
        ${stats().streak >= 3 ? `<span class="run-streak">連對 ${stats().streak}</span>` : ''}
      </div>
      <div class="run-bar"><i style="width:${(run.i / run.queue.length) * 100}%"></i></div>
      <div class="run-body">
        <figure class="run-fig">
          <img class="${/\.svg$/i.test(img) ? 'vec' : ''}" src="${IMG}${esc(img)}" alt=""
               data-full="${IMG}${esc(img)}">
        </figure>
        <div class="run-side">
          <p class="run-q">這是哪一國？</p>
          <div class="run-opts">
            ${run.opts.map(c => runOptHtml(c,
              !done ? '' : c.key === key ? ' right' : c.key === run.picked ? ' miss' : ' off')).join('')}
          </div>
          ${done ? `
            <div class="run-next">
              <a class="run-go" href="#/country/${esc(right.file)}">看 ${esc(cname(right))} 的完整攻略 →</a>
              <button type="button" data-qz="next">${run.i + 1 < run.queue.length ? '下一題' : '看結果'}</button>
            </div>` : ''}
        </div>
      </div>
    </div>`;
}

async function viewQuizRun() {
  const el = $('#v-quiz');
  el.innerHTML = '<p class="empty">題庫載入中…</p>';
  try {
    quizPool = quizPool || await load('quiz.json');
  } catch {
    el.innerHTML = '<p class="empty">讀不到題庫</p>';
    return;
  }
  quizKeys = quizKeys || new Set(quizPool.map(q => q[1]));
  startRun();
  renderRun();
}

// 首頁扉頁。整塊包在 .plate 圖框裡：圖版編號、標題、統計、隨機題目、世界地圖，
// 第一屏就是一張完整的地圖集圖版，而不是標題加一片卡片牆。
// 統計數字帶 data-n，進場時會從 0 跑上去（動效在 countUp）。
function heroHtml(withGuide) {
  const tips = index.countries.reduce((a, c) => a + c.tips, 0);
  const gal = index.countries.reduce((a, c) => a + c.gallery, 0);
  const stat = (n, label) => `<div><b data-n="${n}">0</b><span>${label}</span></div>`;
  return `
    <section class="plate hero-plate">
      <div class="plate-no"><b>Plate I</b><span>世界總覽</span></div>
      <div class="hero">
        <div class="hero-l">
          <div>
            <h1 class="hero-t">GeoGuessr<em>線索圖鑑</em></h1>
            <div class="hero-line"></div>
            <p class="hero-s">整合 plonkit 與 geohints 兩站的辨識線索，${withGuide} 國完整攻略，全站繁體中文。
            各洲內依常出現的程度排序，愈前面愈值得先記。遊戲中看到沒見過的東西就切「按線索」反查。</p>
          </div>
          <div class="stats">
            ${stat(index.countries.length, '國家與地區')}
            ${stat(tips, '攻略說明')}
            ${stat(gal, '線索圖鑑')}
          </div>
        </div>
        <div class="quiz" id="quiz"><div class="quiz-load">題目載入中…</div></div>
      </div>
      ${mapHtml()}
    </section>`;
}

// 統計數字從 0 跑到定值。用 rAF 自己算而不是 CSS，因為要的是數字本身在變。
// 尾段刻意放慢（easeOutCubic），數字停下來時比較有「落定」的感覺
function countUp(el) {
  const target = +el.dataset.n;
  // 開場動效只播一次。首頁每次從別頁切回來都會整塊重畫，不擋的話
  // 每回一次首頁就再看一遍數字跑動與掃描光，第三次就開始煩了
  if (!target || prefersStill() || heroPlayed) { el.textContent = target.toLocaleString(); return; }
  const dur = 900;
  const t0 = performance.now();
  const tick = now => {
    const p = Math.min(1, (now - t0) / dur);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(target * e).toLocaleString();
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

const prefersStill = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

// 首頁的開場動效（數字跑動、地圖掃描光）只在這個分頁的第一次進站播
let heroPlayed = false;

// ---------------------------------------------------------------- 世界地圖

// world.json 是 scripts/make_map.py 從 Natural Earth 投影出來的（Equal Earth，
// 等面積）。key 就是路由用的 file，所以點到哪塊地就能直接組出網址。
let world = null;
let mapMode = 'freq';
let byFile = null;

const fileMap = () => (byFile ||= Object.fromEntries(index.countries.map(c => [c.file, c])));

// 熱度分級。頻率模式看 FREQ_ORDER 的名次，攻略模式看說明條數。
// 兩種模式都把「只有硬線索」的國家壓在最低一級——那批點進去只有行車方向可看，
// 不該跟寫了三十條攻略的國家在圖上長得一樣
function mapClass(c) {
  if (!c) return 'm0';
  if (c.no_guide) return 'm0';
  if (mapMode === 'guide') {
    return c.tips >= 60 ? 'm4' : c.tips >= 30 ? 'm3' : c.tips >= 12 ? 'm2' : 'm1';
  }
  const r = FREQ_RANK[c.key];
  if (r === undefined) return 'm1';
  return r < 12 ? 'm4' : r < 30 ? 'm3' : r < 60 ? 'm2' : 'm1';
}

function mapHtml() {
  return `
    <div class="mapwrap">
      <div class="map-bar">
        <h2>世界熱度圖</h2>
        <div class="map-key">
          <span id="map-k0">少見</span>
          <i class="m1"></i><i class="m2"></i><i class="m3"></i><i class="m4"></i>
          <span id="map-k1">常見</span>
        </div>
        <div class="map-sw">
          <button type="button" data-map="freq" class="on">出現頻率</button>
          <button type="button" data-map="guide">攻略份量</button>
        </div>
      </div>
      <div class="map" id="map"><p class="quiz-load">地圖載入中…</p></div>
    </div>`;
}

async function initMap() {
  const host = $('#map');
  if (!host) return;
  // 要在 await 之前判斷：這個函式讓出去之後 viewCountries 會跑完並把 heroPlayed
  // 設成 true，等地圖載回來再讀就永遠是 true，第一次進站反而看不到掃描光
  const playScan = !prefersStill() && !heroPlayed;
  try {
    world = world || await load('world.json');
  } catch {
    $('.mapwrap')?.remove();   // 地圖載不到就整塊拿掉，下面的卡片牆本來就到得了每一國
    return;
  }

  const bf = fileMap();
  const paths = Object.entries(world.c).map(([file, e]) => {
    const c = bf[file];
    if (!c) return '';
    return `<path d="${e.d}" class="${mapClass(c)}" data-f="${file}"${e.dot ? ' data-dot="1"' : ''}/>`;
  }).join('');

  // 50m 精度畫不出來的地方（梵蒂岡、直布羅陀）不能就這樣消失，另外列一行
  const off = index.countries.filter(c => !world.c[c.file] && !c.no_guide);

  // 底部裁掉一截：Equal Earth 會把南極洲攤成橫貫整張圖的長條，不但佔高度，
  // 上色後還變成一條橫在圖下方的色帶，比任何一個國家都搶眼——而南極在這個遊戲裡
  // 幾乎不會出現（我們只有一個 McMurdo 站）。裁到只剩薄薄一線，還在、還點得到
  const vh = (world.h * 0.932).toFixed(1);
  // 經緯線畫在陸地下面（make_map.py 用同一組投影公式產的，前端不必再抄一份），
  // 緯度標記貼在左緣。這兩樣是「這是一張地圖」跟「這是一張填色圖」的差別
  const marks = (world.marks || []).map(m =>
    `<text class="map-mk" x="6" y="${m.y - 3}">${m.t}</text>`).join('');

  host.innerHTML = `
    <svg viewBox="0 0 ${world.w} ${vh}" role="img" aria-label="世界地圖，點國家看該國攻略">
      <path class="map-grid" d="${world.grid || ''}"/>
      <path class="map-land" d="${world.land}"/>
      ${paths}
      ${marks}
    </svg>
    <div class="map-tip" id="map-tip"></div>
    ${playScan ? '<div class="map-scan"></div>' : ''}
    ${off.length ? `<div class="map-foot"><span>地圖上太小：</span>${off.map(c =>
      `<a href="#/country/${c.file}">${esc(cname(c))}</a>`).join('')}</div>` : ''}`;

  const tip = $('#map-tip');
  // 觸控裝置沒有 hover，不能一點就跳：手指壓下去蓋住的範圍比一個小國還大，
  // 常常點到隔壁。這裡改成第一下先選起來看清楚是哪一國，第二下才進去
  const canHover = matchMedia('(hover:hover)').matches;
  let sel = null;

  const showTip = (file, x, y) => {
    const c = bf[file];
    if (!c) return;
    const r = FREQ_RANK[c.key];
    const note = c.no_guide ? '僅有硬線索'
      : r !== undefined ? `常見度第 ${r + 1} 名` : `${c.tips} 條攻略`;
    tip.innerHTML = `${flagImg(c)}<div><b>${esc(cname(c))}</b><span>${note}</span></div>`;
    tip.classList.add('on');
    // 靠右的國家要把提示往左翻，否則俄羅斯、紐西蘭的提示會被切在框外。
    // 手機上地圖是可以左右捲的，可視範圍的右緣要把捲動量算進去
    const w = tip.offsetWidth;
    const max = host.scrollLeft + host.clientWidth;
    tip.style.left = (x + w + 18 > max ? x - w - 14 : x + 14) + 'px';
    tip.style.top = Math.max(0, y - 34) + 'px';
  };

  host.addEventListener('pointermove', e => {
    if (!canHover) return;
    const p = e.target.closest('path[data-f]');
    if (!p) { tip.classList.remove('on'); return; }
    const box = host.getBoundingClientRect();
    // 提示是定位在 host 內容座標上的，捲動過的距離要加回來
    showTip(p.dataset.f, e.clientX - box.left + host.scrollLeft, e.clientY - box.top);
  });
  host.addEventListener('pointerleave', () => tip.classList.remove('on'));

  host.addEventListener('click', e => {
    const p = e.target.closest('path[data-f]');
    if (!p) return;
    const f = p.dataset.f;
    if (canHover || sel === f) { location.hash = '#/country/' + f; return; }
    $$('path.sel', host).forEach(x => x.classList.remove('sel'));
    p.classList.add('sel');
    sel = f;
    // 選取狀態下提示釘在該國的質心上（world.json 存的是投影後座標，換算成畫面像素）。
    // 比例要用 SVG 實際畫出來的寬度，不能用容器寬度——手機上 SVG 比容器寬
    const k = $('svg', host).getBoundingClientRect().width / world.w;
    showTip(f, world.c[f].p[0] * k, world.c[f].p[1] * k);
  });
}

function setMapMode(mode) {
  mapMode = mode;
  $$('.map-sw button').forEach(b => b.classList.toggle('on', b.dataset.map === mode));
  const bf = fileMap();
  // SVG 元素的 className 是 SVGAnimatedString 不是字串，只能用 setAttribute
  $$('#map path[data-f]').forEach(p => p.setAttribute('class', mapClass(bf[p.dataset.f])));
  $('#map-k0').textContent = mode === 'guide' ? '略述' : '少見';
  $('#map-k1').textContent = mode === 'guide' ? '詳盡' : '常見';
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

  // 這批也依洲分組。原本 122 張卡片平舖成一大片，排序只剩中文名筆劃，
  // 想找某個加勒比海小島得整片掃過去。洲別是人工補的（data/country_extra.json）。
  const thin = index.countries.filter(c => c.no_guide);
  const thinGroups = {};
  thin.forEach(c => (thinGroups[c.continent || '其他'] ||= []).push(c));
  Object.values(thinGroups).forEach(g => g.sort(byFreq));
  const thinKeys = [...new Set([...order.filter(k => thinGroups[k]), ...Object.keys(thinGroups)])];

  // 洲別章節帶羅馬數字編號，跟扉頁的 Plate I 是同一套製圖語彙
  const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

  $('#v-countries').innerHTML = `
    ${heroHtml(withGuide.length)}
    ${keys.map((k, i) => `
      <div class="rule"><i class="rn">${ROMAN[i] || i + 1}</i><h2>${CONTINENT_ZH[k] || k}</h2><span class="count">${groups[k].length}</span></div>
      <div class="grid">
        ${groups[k].map(c => `
          <a class="card" href="#/country/${c.file}">
            ${flagImg(c)}
            <div class="nm">${esc(cname(c))}</div>
          </a>`).join('')}
      </div>`).join('')}
    <div class="rule"><h2>僅有硬線索</h2><span class="count">${thin.length}</span></div>
    <p class="lead">這些國家沒有完整攻略，但仍可查行車方向、電話區碼、網域、貨幣等可直接鎖定答案的硬線索。</p>
    ${thinKeys.map(k => `
      <section class="sec">
        <h3>${CONTINENT_ZH[k] || k} <span class="count">${thinGroups[k].length}</span></h3>
        <div class="grid">
          ${thinGroups[k].map(c => `<a class="card thin" href="#/country/${c.file}">${flagImg(c)}<div class="nm">${esc(cname(c))}</div></a>`).join('')}
        </div>
      </section>`).join('')}`;

  initQuiz();
  initMap();
  $$('.stats b[data-n]').forEach(countUp);
  reveal();
  heroPlayed = true;
}

// ---------------------------------------------------------------- 線索一覽

// 從 build_data 給的候選裡挑代表縮圖：取常見度最高的那個國家。
// 候選是照國名字母序來的，直接取第一張會讓整頁縮圖清一色是波札那
// （字母序很前面又幾乎每類都有圖），而且「路標」會挑到珠雞警告標誌那種很不典型的。
// 沒有國家歸屬的條目（公路編號、公車站那幾類）排在最後，有國家的優先
function pickThumb(thumbs) {
  if (!thumbs || !thumbs.length) return '';
  let best = null, bestRank = Infinity;
  for (const [img, key] of thumbs) {
    const r = key ? (FREQ_RANK[key] ?? 900) : 950;
    if (r < bestRank) { bestRank = r; best = img; }
  }
  return best || thumbs[0][0];
}

function viewClues() {
  $('#v-clues').innerHTML = `
    <div class="plate-no"><b>Plate II</b><span>線索類型</span></div>
    <p class="lead">遊戲進行中最實用的入口：看到一根沒見過的電線桿、一種沒看過的路樁，
    從這裡挑對應類型，比對各國實例。</p>
    <div class="rule"><h2>線索類型</h2><span class="count">${index.clues.length}</span></div>
    <div class="grid grid-clue">
      ${index.clues.map(c => {
        const th = pickThumb(c.thumbs);
        return `
        <a class="card clue-card${th ? ' has-thumb' : ''}" href="#/clue/${c.key}">
          ${th ? `<img class="cth${/\.svg$/i.test(th) ? ' vec' : ''}" loading="lazy" src="${IMG}${esc(th)}" alt="">` : ''}
          <div class="cb">
            <div class="nm">${esc(c.zh)}</div>
            ${c.lead ? `<div class="cl">${esc(c.lead)}</div>` : ''}
          </div>
        </a>`;
      }).join('')}
    </div>`;
  reveal();
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

// 國旗配色（scripts/make_flag_colors.py 抽的）。258 頁的版型完全一樣，
// 翻到哪一國全靠標題那行字分辨；頁首加一條該國國旗的配色，
// 顏色是從資料長出來的不是硬套的裝飾，翻頁時一眼就知道換國家了。
let flagColors = null;

function bandHtml(file) {
  const e = flagColors?.[file];
  if (!e || e.band.length < 2) return '';
  // 等分成幾段，段數就是國旗的顏色數，不做漸層——國旗本來就是色塊不是漸層
  return `<div class="band">${e.band.map(col =>
    `<i style="background:${esc(col)}"></i>`).join('')}</div>`;
}

async function viewCountry(file) {
  const el = $('#v-country');
  el.innerHTML = '<p class="empty">載入中…</p>';
  // 配色檔 18KB，第一次進國家頁才載；載不到就不畫色帶，不影響其他內容
  if (flagColors === null) {
    try { flagColors = await load('flag_colors.json'); } catch { flagColors = {}; }
  }
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

  // 圖鑑編號：該國在索引裡的序號（字母序，固定不會跳動），零填充三位。
  // 用常見度名次會更有意義，但有 122 國不在那份清單上，會變成一堆沒編號的頁
  const meta = index.countries.find(x => x.file === file) || {};
  const no = String(index.countries.indexOf(meta) + 1).padStart(3, '0');

  el.innerHTML = `
    ${bandHtml(file)}
    <div class="page-head">
      <a class="back" href="#/">← 全部國家</a>
      <div class="plate-no"><b>No. ${no}</b><span>${esc(c.continent ? (CONTINENT_ZH[c.continent] || c.continent) : '國家圖鑑')}</span></div>
      <h1>${flagImg(meta)}${esc(cname(c))}</h1>
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
          <h3><a href="#/clue/${k}">${esc(clueName(k))}</a></h3>
          <div class="gal">${shots(list, () => '')}</div>
        </section>`).join('')}` : ''}

    ${!c.sections?.length && !Object.keys(gal).length && !factKeys.length
      ? '<p class="empty">這個國家目前只有基本資料</p>' : ''}`;

  reveal();
}

// ---------------------------------------------------------------- 易混淆對照

// 站上其他頁都是一國一頁，但實戰認錯幾乎都發生在特徵相近的鄰國之間：
// 認出西里爾字母只是第一步，俄烏白三選一才是真正的關卡。這頁把那幾國並排。
let confusions = null;

// 對照要看的硬資料。行車方向與標線顏色在鄰國之間常常就是決定性的差異，
// 而且這幾項每國都有，並排起來不會缺格
const VS_FACTS = ['driving_side', 'lines', 'phone_numbers', 'domains'];

async function viewVs() {
  const el = $('#v-vs');
  el.innerHTML = '<p class="empty">載入中…</p>';
  try {
    confusions = confusions || await load('confusions.json');
  } catch {
    el.innerHTML = '<p class="empty">讀不到對照資料</p>';
    return;
  }

  const groups = confusions.groups || [];
  // 一次把所有組要用到的國家檔抓齊。load() 有快取，同一國出現在兩組也只會抓一次
  const files = [...new Set(groups.flatMap(g => g.members.map(m => m.file)))];
  const data = {};
  await Promise.all(files.map(async f => {
    try { data[f] = await load(`countries/${f}.json`); } catch { data[f] = null; }
  }));

  const bf = fileMap();
  const clueName = k => (index.clues.find(x => x.key === k) || {}).zh || k;

  el.innerHTML = `
    <div class="plate-no"><b>Plate III</b><span>易混淆對照</span></div>
    <p class="lead">分辨不出來的通常不是兩個隨便的國家，而是特徵相近的鄰國。
    這裡把常被認錯的幾組並排，同一種線索的照片放在同一列比較，
    下面附上行車方向與道路標線這類可以直接定案的硬資料。</p>
    ${groups.map((g, gi) => {
      const members = g.members.filter(m => data[m.file]);
      if (!members.length) return '';
      // 只留組內真的有差異的欄位。原始資料對歐盟國家的網域多半只記了 .eu，
      // 三國並排都是 .eu，這一列不但幫不上忙還會讓人以為自己找到線索了。
      // 同理北歐三國都靠右行駛，那一列也不用佔版面
      const rows = VS_FACTS.filter(k => {
        const vals = members.map(m => JSON.stringify((data[m.file].facts || {})[k] ?? null));
        return vals.some(v => v !== 'null') && new Set(vals).size > 1;
      });
      return `
      <section class="sec vs-g">
        <div class="rule"><i class="rn">${gi + 1}</i><h2>${esc(g.title)}</h2><span class="count">${members.length} 國</span></div>
        <p class="lead">${esc(g.lead)}</p>
        <div class="vs">
          ${members.map(m => {
            const c = data[m.file];
            const meta = bf[m.file] || {};
            const list = ((c.gallery || {})[g.clue] || []).slice(0, 2);
            const facts = c.facts || {};
            return `
              <div class="vs-c">
                <a class="vs-h" href="#/country/${esc(m.file)}">
                  ${flagImg(meta)}<b>${esc(cname(c))}</b><i>攻略 →</i>
                </a>
                ${list.length ? `<div class="vs-shots">${shots(list, null)}</div>` : ''}
                <p class="vs-tell">${esc(m.tell)}</p>
                ${rows.length ? `<dl class="vs-facts">
                  ${rows.map(k => `
                    <dt>${FACT_LABEL[k]}</dt>
                    <dd>${facts[k] != null ? factValue(k, facts[k]) : '<span class="vs-na">無資料</span>'}</dd>`).join('')}
                </dl>` : ''}
              </div>`;
          }).join('')}
        </div>
        <p class="vs-note">上排照片比的是<a href="#/clue/${esc(g.clue)}">${esc(clueName(g.clue))}</a>。</p>
      </section>`;
    }).join('')}`;

  reveal();
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
      <div class="sub">${esc(c.en)}</div>
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
      <aside class="jump">
        <div class="jump-h">跳到國家<em>${countries.length}</em></div>
        <input class="jump-f" id="jf" type="search" placeholder="篩選國家" autocomplete="off">
        <div class="jump-list" id="jl">
          ${countries.map(k => {
            const f = index.countries.find(x => x.key === k)?.flag;
            return `
            <a data-jump="${cid(k)}" data-nm="${esc((zh[k] || byCountry[k].name).toLowerCase())} ${esc(k)}">
              ${f ? `<img class="jump-flag" src="${IMG}${esc(f)}" alt="" loading="lazy">` : '<span class="jump-flag"></span>'}
              ${esc(zh[k] || byCountry[k].name)}
            </a>`;
          }).join('')}
        </div>
      </aside>
      <div>
      ${countries.map((k, n) => {
        const b = byCountry[k];
        // 每一國做成圖鑑條目的標頭：編號、國旗、中文名、原名與洲別。
        // 原本只有一行光禿禿的國名，滑過 141 國每一段看起來都一樣，
        // 停下來時得往回找才知道自己在誰的段落裡。編號同時也是常見度排名。
        const ci = index.countries.find(x => x.key === k);
        return `
        <section class="sec" id="c-${cid(k)}">
          <header class="entry">
            <span class="entry-no">${String(n + 1).padStart(2, '0')}</span>
            ${ci?.flag ? `<img class="entry-flag" src="${IMG}${esc(ci.flag)}" alt="" loading="lazy">` : ''}
            <div class="entry-t">
              <h3><a href="#/country/${esc(k.replace(/ /g, '-'))}">${esc(zh[k] || b.name)}</a></h3>
              <div class="entry-sub">${esc(ci?.name || b.name)}${ci?.continent ? ` · ${CONTINENT_ZH[ci.continent] || ci.continent}` : ''}</div>
            </div>
          </header>
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
      </div>` : '<p class="empty">這個類型還沒有資料</p>'}`;

  // 111 國的清單用滑的還是慢，加個即時篩選。中英文都比對，打 japan 或 日本 都找得到
  const jf = $('#jf');
  const jl = $('#jl');
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
      if (!n && !none) jl.insertAdjacentHTML('beforeend', '<div class="jump-none">沒有符合的國家</div>');
      if (n && none) none.remove();
      // 移除再加回去才會重新播動畫，不然打第二個字時剩下的項目是硬跳出來的
      jl.classList.remove('filtered');
      if (t) { void jl.offsetWidth; jl.classList.add('filtered'); }
    });
  }

  watchSections();
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
    const nl = n.toLowerCase(), el = c.name.toLowerCase();
    if (nl.includes(t) || el.includes(t) || c.code.toLowerCase() === t) {
      // 帶上國旗：搜尋清單是全站最常用的入口，一排純文字得逐行讀，
      // 有旗子可以先用顏色粗篩（跟線索頁側欄同一個理由）
      hits.push({
        href: `#/country/${c.file}`, name: n, flag: c.flag,
        kind: c.no_guide ? '硬線索' : `${c.tips} 條`,
        // 開頭命中的排前面：打「瑞」要的是瑞典瑞士，不是格瑞那達與賴比瑞亞
        starts: nl.startsWith(t) || el.startsWith(t) ? 0 : 1,
        rank: FREQ_RANK[c.key] ?? 999,
      });
    }
    if (hits.length > 40) break;
  }
  // 國家先照「開頭命中」再照常見度排。線索類的結果一律接在國家後面，
  // 打國名的次數遠多於打線索類型名
  hits.sort((a, b) => (a.starts - b.starts) || (a.rank - b.rank));

  for (const c of index.clues) {
    if (c.zh.includes(t) || c.en.toLowerCase().includes(t)) {
      hits.push({ href: `#/clue/${c.key}`, name: c.zh, kind: '線索' });
    }
  }

  const seq = ++searchSeq;
  box.innerHTML = hits.length
    ? hits.slice(0, 12).map(h => `<a href="${h.href}">
        ${h.flag ? `<img class="flag" src="${IMG}${esc(h.flag)}" alt="" loading="lazy">` : '<span class="flag"></span>'}
        <b>${esc(h.name)}</b><span class="k">${esc(h.kind)}</span></a>`).join('')
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
  secCleanup?.();   // 離開線索頁就把捲動監聽拆掉，別留著算已經被換掉的節點

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
  } else if (seg === 'vs') {
    $('#v-vs').classList.add('on');
    $('nav a[data-nav=vs]').classList.add('on');
    viewVs();
  } else if (seg === 'quiz') {
    $('#v-quiz').classList.add('on');
    $('nav a[data-nav=quiz]').classList.add('on');
    viewQuizRun();
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

    // 地圖上色依據的切換。只改每塊地的 class，不重畫 SVG
    const mb = e.target.closest('[data-map]');
    if (mb) { setMapMode(mb.dataset.map); return; }

    // 練習模式。同樣用委派，每答一題整塊就重畫一次
    const rb = e.target.closest('[data-qz]');
    if (rb && run) {
      const act = rb.dataset.qz;
      if (act === 'ans' && run.picked === null) {
        run.picked = rb.dataset.key;
        const right = run.queue[run.i][1];
        const ok = run.picked === right;
        if (ok) run.score++;
        else run.wrong.push({ item: run.queue[run.i], picked: run.picked });
        noteAnswer(right, ok);
      } else if (act === 'next') {
        run.i++;
        run.picked = null;
        if (run.i < run.queue.length) run.opts = optionsFor(run.queue[run.i][1]);
        else finishRun();     // 整輪的統計在這裡結算，只會經過一次
      } else if (act === 'again') {
        startRun();
      } else if (act === 'reset') {
        clearStats();
        startRun();
      }
      renderRun();
      return;
    }

    // 側欄跳到某一國。不能用 href="#..." 錨點，這站是 hash 路由，改 hash 會被當成換頁
    const jp = e.target.closest('[data-jump]');
    if (jp) {
      // 用瞬間跳不用 smooth：跨越上萬像素的平滑捲動要等很久，而且 smooth 在
      // 開了減少動態效果的系統上本來就會被停用。被版首遮擋的問題交給
      // CSS 的 scroll-margin-top 處理，比在這裡硬減一個像素值可靠
      const sec = document.getElementById('c-' + jp.dataset.jump);
      if (sec) {
        sec.scrollIntoView();
        // 亮一下，否則瞬間跳完不知道自己落在哪。移除再加回去才會重播動畫
        sec.classList.remove('land');
        void sec.offsetWidth;
        sec.classList.add('land');
      }
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
