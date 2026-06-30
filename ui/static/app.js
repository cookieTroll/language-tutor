// ── State ────────────────────────────────────────────────────────────────────
let sid = null;
let phase = 'idle';           // idle | setup | writing | evaluating | done
let inWritingPhase = false;
let lastOutputText = '';
let timerStart = null;
let timerInterval = null;
let pendingTopic = sessionStorage.getItem('retryTopic');
let evalStep = 0;
const THEMES = ['ruled', 'dots', 'diamonds', 'words', 'cat'];
let themeIdx = Math.floor(Math.random() * THEMES.length);

// ── Theme ────────────────────────────────────────────────────────────────────
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

// ── Session ──────────────────────────────────────────────────────────────────
async function startSession() {
  const userId = document.getElementById('user-id').value.trim() || 'student';
  document.getElementById('idle').style.display = 'none';
  document.getElementById('main').style.display = 'flex';

  const res  = await fetch('/api/start', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({user_id: userId}),
  });
  const data = await res.json();
  sid = data.session_id;

  const es = new EventSource('/api/stream/' + sid);
  es.onmessage = e => handleEvent(JSON.parse(e.data));
  es.onerror   = () => appendTutor('Connection lost.', 'system');
}

function confirmLeave() {
  return phase === 'idle' || phase === 'done' || confirm('Leave current session?');
}

// ── Event handling ────────────────────────────────────────────────────────────
function handleEvent(ev) {
  if (ev.type === 'heartbeat') return;
  if (ev.type === 'output')   handleOutput(ev.text || '');
  if (ev.type === 'prompt')   handlePrompt(ev.text || '');
  if (ev.type === 'data')     handleData(ev.payload || {});
  if (ev.type === 'done')     handleDone();
}

function handleOutput(text) {
  if (!text) return;
  lastOutputText = text;

  // Detect exercise header → switch to writing layout
  if (text.includes('WRITING EXERCISE') && !inWritingPhase) {
    inWritingPhase = true;
    switchToSession();
    // Parse topic / requirements / level
    const topicMatch = text.match(/Topic:\s*(.+)/);
    const reqMatch   = text.match(/Requirements:\s*(.+)/);
    const lvlMatch   = text.match(/Target Level:\s*(\w+)/);
    if (topicMatch) {
      document.getElementById('topic-box').style.display = 'block';
      document.getElementById('topic-title').textContent = topicMatch[1].trim();
      document.getElementById('topic-req').textContent   = reqMatch ? reqMatch[1].trim() : '';
    }
    if (lvlMatch) updateChip('chip-level', lvlMatch[1].toUpperCase());
    return; // don't render the raw ASCII header
  }

  // Detect language
  const langMatch = text.match(/(?:studying|WRITING EXERCISE.*?for|)\s*(\bGERMAN\b|\bFRENCH\b|\bSPANISH\b|\bITALIAN\b|\bJAPANESE\b)/i);
  if (langMatch) updateChip('chip-lang', langMatch[1].toUpperCase());

  // Route text to the right panel
  if (!inWritingPhase) {
    appendSetup(text);
  } else {
    // Detect pipeline progress steps
    const stepMatch = text.match(/^\[(\d+)\/6\]/);
    if (stepMatch) {
      const n = parseInt(stepMatch[1]);
      markEvalStep(n);
      appendTutor(text, 'progress');
    } else {
      appendTutor(text, 'tutor');
    }
  }

  // Update module chip from output
  if (text.includes('WRITING EXERCISE')) updateChip('chip-module', 'Writing');
  if (text.includes('GRAMMAR'))          updateChip('chip-module', 'Grammar');
  if (text.includes('VOCABULARY'))       updateChip('chip-module', 'Vocab');
}

function handlePrompt(text) {
  if (!inWritingPhase) {
    // Setup prompts
    if (pendingTopic && lastOutputText.includes('suggestion')) {
      sendInput(pendingTopic);
      sessionStorage.removeItem('retryTopic');
      pendingTopic = null;
      return;
    }
    if (text && text !== '>') appendSetup(text);
    showSetupInput(text);
  }
  // Writing prompts (">") are handled by the textarea — no input box shown
}

function handleDone() {
  phase = 'done';
  stopTimer();
  document.getElementById('done-banner').style.display = 'block';
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('btw-btn').disabled   = true;
  localStorage.removeItem('draftText');
}

function handleData(payload) {
  if (payload.event !== 'evaluation_complete') return;

  // Hide eval overlay now that evaluation output is fully rendered
  document.getElementById('eval-overlay').style.display = 'none';

  const { user_text, corrected_text, mistakes } = payload;
  if (!user_text) return;

  // Annotated original (only if there are mistakes to highlight)
  if (mistakes && mistakes.length > 0) {
    const annotatedHtml = annotateText(user_text, mistakes);
    const orig = document.createElement('div');
    orig.className = 'annotated-block';
    orig.innerHTML =
      `<div class="ann-label">Your text <span class="ann-count">${mistakes.length} issue${mistakes.length === 1 ? '' : 's'}</span></div>` +
      `<div>${annotatedHtml}</div>`;
    document.getElementById('tutor-output').appendChild(orig);

    if (corrected_text && corrected_text !== user_text) {
      const corr = document.createElement('div');
      corr.className = 'annotated-block corr';
      corr.innerHTML =
        `<div class="ann-label">Corrected</div>` +
        `<div>${escapeHtml(corrected_text)}</div>`;
      document.getElementById('tutor-output').appendChild(corr);
    }
  }

  // Invitation to ask follow-up questions
  const inv = document.createElement('div');
  inv.className = 'invite-msg';
  inv.textContent = 'Unsure why something was flagged? Ask me below ↓';
  document.getElementById('tutor-output').appendChild(inv);

  // Enter follow-up phase so sendBtw() doesn't gate out
  phase = 'follow-up';

  // Focus the btw input for follow-up
  const btwInp = document.getElementById('btw-inp');
  btwInp.placeholder = 'Ask about a mistake…';
  document.getElementById('btw-btn').disabled = false;
  setTimeout(() => btwInp.focus(), 150);

  const out = document.getElementById('tutor-output');
  out.scrollTop = out.scrollHeight;
}

function annotateText(text, mistakes) {
  const ranges = [];
  for (const m of mistakes) {
    const frag = m.fragment;
    if (!frag || !frag.trim()) continue;
    const idx = text.indexOf(frag);
    if (idx === -1) continue;
    if (ranges.some(r => idx < r.end && idx + frag.length > r.start)) continue;
    ranges.push({
      start: idx, end: idx + frag.length,
      tag: m.error_tag || '', correction: m.correction || '',
    });
  }
  ranges.sort((a, b) => a.start - b.start);

  let html = '', pos = 0;
  for (const r of ranges) {
    if (r.start > pos) html += escapeHtml(text.slice(pos, r.start));
    const tip = r.correction ? `${r.tag} → ${r.correction}` : r.tag;
    html += `<mark class="mistake-hl" title="${escapeHtml(tip)}">${escapeHtml(text.slice(r.start, r.end))}</mark>`;
    pos = r.end;
  }
  if (pos < text.length) html += escapeHtml(text.slice(pos));
  return html || escapeHtml(text);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function appendSetup(text) {
  const div = document.createElement('div');
  div.className = 'setup-msg';
  div.textContent = text;
  document.getElementById('setup-output').appendChild(div);
  const el = document.getElementById('setup-output');
  el.scrollTop = el.scrollHeight;
}

function appendTutor(text, cls = 'tutor') {
  if (!text && cls === 'tutor') return;
  const div = document.createElement('div');
  div.className = 'tmsg ' + cls;
  div.textContent = text;
  document.getElementById('tutor-output').appendChild(div);
  const el = document.getElementById('tutor-output');
  el.scrollTop = el.scrollHeight;
}

function showSetupInput(placeholder) {
  const row = document.getElementById('setup-input-row');
  row.style.display = 'flex';
  const inp = document.getElementById('setup-inp');
  inp.value = '';
  inp.placeholder = placeholder && placeholder !== '>' ? placeholder.trim() : '';
  inp.focus();
}

function switchToSession() {
  document.getElementById('setup').style.display   = 'none';
  document.getElementById('session').style.display = 'flex';
  document.getElementById('writing-pad').focus();
  startTimer();
  phase = 'writing';

  // Restore draft
  const draft = localStorage.getItem('draftText');
  if (draft) {
    document.getElementById('writing-pad').value = draft;
    updateWordCount();
  }
}

function updateChip(id, text) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.classList.add('active');
}

// ── Timer ─────────────────────────────────────────────────────────────────────
function startTimer() {
  timerStart = Date.now();
  timerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - timerStart) / 1000);
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    document.getElementById('timer').textContent = '⏱ ' + m + ':' + sec;
  }, 1000);
}
function stopTimer() { clearInterval(timerInterval); }

// ── Inputs ────────────────────────────────────────────────────────────────────
async function submitSetup() {
  const inp  = document.getElementById('setup-inp');
  const text = inp.value;
  document.getElementById('setup-input-row').style.display = 'none';
  appendSetup('> ' + text);
  await sendInput(text);
}

async function submitWriting() {
  if (phase !== 'writing') return;
  const pad   = document.getElementById('writing-pad');
  const text  = pad.value.trim();
  if (!text) return;

  phase = 'evaluating';
  pad.disabled = true;
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('eval-overlay').style.display = 'flex';
  localStorage.removeItem('draftText');

  const lines = text.split('\n');
  for (const line of [...lines, '']) {
    await fetch('/api/input/' + sid, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({text: line}),
    });
  }
}

async function sendBtw() {
  const inp = document.getElementById('btw-inp');
  const q   = inp.value.trim();
  if (!q || (phase !== 'writing' && phase !== 'follow-up')) return;
  inp.value = '';
  if (phase === 'follow-up') {
    appendTutor(q, 'btw-q');
    await sendInput(q);              // server expects plain question in follow-up phase
  } else {
    appendTutor('/btw ' + q, 'btw-q');
    await sendInput('/btw ' + q);
  }
}

async function sendInput(text) {
  await fetch('/api/input/' + sid, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({text}),
  });
}

// ── Eval progress ─────────────────────────────────────────────────────────────
function markEvalStep(n) {
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById('p' + i);
    if (!el) continue;
    el.classList.remove('active', 'done');
    if (i < n)  el.classList.add('done');
    if (i === n) el.classList.add('active');
  }
}

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

// ── Word count + auto-save ────────────────────────────────────────────────────
function updateWordCount() {
  const text  = document.getElementById('writing-pad').value.trim();
  const count = text ? text.split(/\s+/).length : 0;
  document.getElementById('word-count').textContent = count + ' word' + (count === 1 ? '' : 's');
}
document.getElementById('writing-pad').addEventListener('input', () => {
  updateWordCount();
  localStorage.setItem('draftText', document.getElementById('writing-pad').value);
});

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.activeElement === document.getElementById('user-id'))
    startSession();
  if (e.key === 'Enter' && document.activeElement === document.getElementById('setup-inp'))
    submitSetup();
  if (e.key === 'Enter' && document.activeElement === document.getElementById('btw-inp'))
    sendBtw();
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter'
      && document.activeElement === document.getElementById('writing-pad'))
    submitWriting();
});

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
