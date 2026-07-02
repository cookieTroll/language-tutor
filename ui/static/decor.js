// Purely cosmetic/preference chrome — background themes, confetti, font size,
// column resizer. No session state, no coupling to app.js/writing-ui.js/grammar-ui.js
// except the confetti hook below, which reads appendTutor (defined in app.js) at
// parse time — this file must load after app.js.

// ── Theme ────────────────────────────────────────────────────────────────────
const THEMES = ['ruled', 'dots', 'diamonds', 'words', 'cat'];
let themeIdx = Math.floor(Math.random() * THEMES.length);

function applyTheme(name) {
  THEMES.forEach(t => document.body.classList.remove('theme-' + t));
  document.body.classList.add('theme-' + name);
  clearBgParticles();
  if (name === 'words') spawnWords();
  if (name === 'cat')   { spawnCat(); spawnMice(); }
}

function cycleTheme() {
  themeIdx = (themeIdx + 1) % THEMES.length;
  applyTheme(THEMES[themeIdx]);
}

function clearBgParticles() {
  document.querySelectorAll('.word-particle, .cat-walk, .mouse-peek').forEach(el => el.remove());
}

const GERMAN_WORDS = [
  'sprechen','lernen','schreiben','lesen','verstehen','üben','Grammatik',
  'Wörter','Deutsch','Artikel','Verb','Nomen','Adjektiv','Satz','Übung',
  'der','die','das','haben','sein','werden','gehen','kommen','machen',
  'sagen','geben','wissen','denken','fragen','antworten','schön','gut',
];

function spawnWords() {
  for (let i = 0; i < 22; i++) {
    const span = document.createElement('span');
    span.className = 'word-particle';
    span.textContent = GERMAN_WORDS[Math.floor(Math.random() * GERMAN_WORDS.length)];
    span.style.left     = (Math.random() * 98) + 'vw';
    span.style.bottom   = '-40px';
    span.style.fontSize = (0.75 + Math.random() * 0.7) + 'rem';
    span.style.animationDuration = (18 + Math.random() * 22) + 's';
    span.style.animationDelay   = -(Math.random() * 35) + 's';
    document.body.appendChild(span);
  }
}

function spawnCat() {
  const wrap = document.createElement('div');
  wrap.className = 'cat-walk';
  wrap.innerHTML = `
  <svg width="120" height="100" viewBox="0 0 120 100"
       fill="none" stroke="rgba(248,113,113,0.85)"
       stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <!-- body -->
    <ellipse cx="60" cy="68" rx="28" ry="20"/>
    <!-- head -->
    <circle cx="60" cy="32" r="18"/>
    <!-- ears -->
    <g class="cat-ear-l"><path d="M44 20 L36 4 L54 17"/></g>
    <g class="cat-ear-r"><path d="M76 20 L84 4 L66 17"/></g>
    <!-- eyes -->
    <ellipse cx="52" cy="30" rx="4" ry="4.5"/>
    <ellipse cx="68" cy="30" rx="4" ry="4.5"/>
    <!-- pupils -->
    <ellipse cx="52" cy="30" rx="2" ry="3.5" fill="rgba(248,113,113,0.4)" stroke="none"/>
    <ellipse cx="68" cy="30" rx="2" ry="3.5" fill="rgba(248,113,113,0.4)" stroke="none"/>
    <!-- nose -->
    <path d="M57 38 L60 41 L63 38"/>
    <!-- whiskers left -->
    <line x1="22" y1="36" x2="50" y2="38"/>
    <line x1="22" y1="40" x2="50" y2="40"/>
    <!-- whiskers right -->
    <line x1="70" y1="38" x2="98" y2="36"/>
    <line x1="70" y1="40" x2="98" y2="40"/>
    <!-- tail -->
    <g class="cat-tail" style="transform-origin:88px 72px">
      <path d="M88 72 Q108 56 100 38 Q96 28 104 22"/>
    </g>
    <!-- front legs -->
    <line x1="46" y1="84" x2="42" y2="98"/>
    <line x1="56" y1="86" x2="53" y2="100"/>
    <!-- back legs -->
    <line x1="64" y1="86" x2="67" y2="100"/>
    <line x1="74" y1="84" x2="78" y2="98"/>
  </svg>`;
  document.body.appendChild(wrap);
}

function spawnMice() {
  // Mouse SVG facing right (used for left-edge peeker; mirrored via scaleX for right-edge)
  const mouseSVG = `
  <svg width="100" height="80" viewBox="0 0 100 80"
       fill="none" stroke="rgba(248,113,113,0.9)"
       stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <!-- tail curling back left (disappears off screen edge) -->
    <path d="M14 54 Q4 62 0 56 Q-4 48 2 44"/>
    <!-- body -->
    <ellipse cx="34" cy="52" rx="20" ry="14"/>
    <!-- neck -->
    <line x1="50" y1="44" x2="56" y2="38"/>
    <!-- head -->
    <circle cx="68" cy="30" r="18"/>
    <!-- left ear (far) -->
    <ellipse cx="56" cy="10" rx="7" ry="11" transform="rotate(-15 56 10)"/>
    <!-- right ear (near) -->
    <ellipse cx="74" cy="8" rx="7" ry="11" transform="rotate(10 74 8)"/>
    <!-- inner ears (faint fill) -->
    <ellipse cx="56" cy="11" rx="4" ry="7" transform="rotate(-15 56 11)"
             fill="rgba(248,113,113,0.15)" stroke="none"/>
    <ellipse cx="74" cy="9" rx="4" ry="7" transform="rotate(10 74 9)"
             fill="rgba(248,113,113,0.15)" stroke="none"/>
    <!-- eye -->
    <circle cx="76" cy="27" r="3.5"/>
    <circle cx="77" cy="26" r="1.8" fill="rgba(248,113,113,0.5)" stroke="none"/>
    <!-- shine dot -->
    <circle cx="75" cy="25" r="0.8" fill="rgba(248,113,113,0.9)" stroke="none"/>
    <!-- nose -->
    <ellipse cx="86" cy="34" rx="3" ry="2.2"/>
    <!-- mouth -->
    <path d="M86 36 Q83 40 80 39"/>
    <path d="M86 36 Q89 40 92 39"/>
    <!-- whiskers right (towards screen interior) -->
    <line x1="88" y1="32" x2="100" y2="28"/>
    <line x1="88" y1="34" x2="100" y2="34"/>
    <line x1="88" y1="36" x2="100" y2="40"/>
    <!-- whiskers left (towards edge, shorter) -->
    <line x1="86" y1="32" x2="76" y2="28"/>
    <line x1="86" y1="34" x2="76" y2="34"/>
  </svg>`;

  const configs = [
    { side: 'left',  top: '18%', dur: '11s', delay: '0s'    },
    { side: 'right', top: '42%', dur: '14s', delay: '4.5s'  },
    { side: 'left',  top: '65%', dur: '9s',  delay: '7.5s'  },
  ];

  configs.forEach(({ side, top, dur, delay }) => {
    const wrap = document.createElement('div');
    wrap.className = `mouse-peek from-${side}`;
    wrap.style.top = top;
    wrap.style.setProperty('--dur', dur);
    wrap.style.setProperty('--delay', delay);
    // Mirror the SVG for right-edge mice so they face left (into the screen)
    const svgContent = side === 'right'
      ? mouseSVG.replace('<svg ', '<svg style="transform:scaleX(-1);display:block" ')
      : mouseSVG;
    // Wrap SVG in sniff-wrap so vertical bob animation doesn't fight the horizontal peek
    wrap.innerHTML = `<div class="mouse-sniff-wrap">${svgContent}</div>`;
    document.body.appendChild(wrap);
  });

  // Cat proximity watcher: fade mice out when cat approaches their side
  setInterval(() => {
    const cat = document.querySelector('.cat-walk');
    if (!cat) return;
    const rect = cat.getBoundingClientRect();
    const W    = window.innerWidth;
    const nearLeft  = rect.left  < 320;
    const nearRight = rect.right > W - 320;

    document.querySelectorAll('.mouse-peek.from-left').forEach(m => {
      if (nearLeft)  { m.style.animationPlayState = 'paused'; m.style.opacity = '0'; }
      else           { m.style.animationPlayState = '';        m.style.opacity = ''; }
    });
    document.querySelectorAll('.mouse-peek.from-right').forEach(m => {
      if (nearRight) { m.style.animationPlayState = 'paused'; m.style.opacity = '0'; }
      else           { m.style.animationPlayState = '';        m.style.opacity = ''; }
    });
  }, 300);
}

// Apply initial theme
applyTheme(THEMES[themeIdx]);

// ── Font size slider (scales all rem-based text via root font-size) ───────────
(function () {
  const slider = document.getElementById('font-slider');
  const root   = document.documentElement;
  const saved  = localStorage.getItem('rootFontSize');
  if (saved) { slider.value = saved; root.style.fontSize = saved + 'px'; }
  slider.addEventListener('input', () => {
    root.style.fontSize = slider.value + 'px';
    localStorage.setItem('rootFontSize', slider.value);
  });
})();

// ── Column resizer ────────────────────────────────────────────────────────────
(function () {
  const resizer = document.getElementById('col-resizer');
  const left    = document.getElementById('left-col');
  const right   = document.getElementById('right-col');
  let dragging = false, startX = 0, startLeftW = 0, totalW = 0;

  const saved = localStorage.getItem('colSplit');
  if (saved) {
    const pct = parseFloat(saved);
    left.style.flex  = 'none';
    right.style.flex = 'none';
    left.style.width  = pct + '%';
    right.style.width = (100 - pct) + '%';
  }

  resizer.addEventListener('mousedown', e => {
    dragging   = true;
    startX     = e.clientX;
    startLeftW = left.getBoundingClientRect().width;
    totalW     = left.getBoundingClientRect().width + right.getBoundingClientRect().width;
    resizer.classList.add('dragging');
    document.body.style.cursor    = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const newW = Math.min(Math.max(startLeftW + e.clientX - startX, totalW * 0.2), totalW * 0.8);
    const pct  = (newW / totalW) * 100;
    left.style.flex  = 'none';
    right.style.flex = 'none';
    left.style.width  = pct + '%';
    right.style.width = (100 - pct) + '%';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove('dragging');
    document.body.style.cursor    = '';
    document.body.style.userSelect = '';
    const tot = left.offsetWidth + right.offsetWidth;
    if (tot > 0) localStorage.setItem('colSplit', (left.offsetWidth / tot * 100).toFixed(1));
  });
})();

// ── Confetti ──────────────────────────────────────────────────────────────────
function fireConfetti() {
  const colors = ['#f87171','#34d399','#60a5fa','#fbbf24','#a78bfa'];
  for (let i = 0; i < 60; i++) {
    const el = document.createElement('div');
    el.className = 'confetti-piece';
    el.style.left            = (Math.random() * 100) + 'vw';
    el.style.top             = '-10px';
    el.style.background      = colors[Math.floor(Math.random() * colors.length)];
    el.style.animationDuration = (1.5 + Math.random() * 2) + 's';
    el.style.animationDelay  = (Math.random() * 0.8) + 's';
    el.style.width  = (6 + Math.random() * 8) + 'px';
    el.style.height = (6 + Math.random() * 8) + 'px';
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }
}

// Trigger confetti when evaluation completes with zero mistakes
(function () {
  const orig = appendTutor;
  window.appendTutor = function(text, cls) {
    orig(text, cls);
    if (text && text.includes('No mistakes were identified')) fireConfetti();
  };
})();
