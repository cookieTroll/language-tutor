// Core: shared state, SSE event dispatch, session lifecycle, and generic UI helpers
// used across concerns. Module-specific handlers live in writing-ui.js/grammar-ui.js;
// purely cosmetic chrome lives in decor.js (loaded after this file — it wraps
// appendTutor, defined below, at parse time).

// ── State ────────────────────────────────────────────────────────────────────
let sid = null;
let phase = 'idle';           // idle | setup | loading | writing | evaluating | follow-up | done
                              // 'loading': a module header has been shown but its answer pad
                              // isn't interactive yet (e.g. grammar exercises still generating) —
                              // Submit/Ctrl+Enter must no-op, distinct from 'writing' which is
                              // shared across modules as "collecting a submittable answer".
let inSessionPhase = false;   // true once any module (writing/grammar) has started its interactive phase
let activeModule = null;      // 'writing' | 'grammar' | null — which panel is showing
let lastOutputText = '';
let timerStart = null;
let timerInterval = null;
let pendingTopic = sessionStorage.getItem('retryTopic');
let evalStep = 0;

// ── Session ──────────────────────────────────────────────────────────────────
async function startSession() {
  const userId = document.getElementById('user-id').value.trim() || 'student';
  document.getElementById('idle').style.display = 'none';
  document.getElementById('main').style.display = 'flex';
  showCmdSidebar('setup');

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

// ── Command hints sidebar ────────────────────────────────────────────────────
const CMD_HINTS = {
  setup: [
    { cmd: '/history', desc: 'Last 10 writing sessions' },
    { cmd: '/history &lt;n&gt;', desc: 'e.g. /history 5 — last n sessions' },
    { cmd: '/history &lt;n&gt;d', desc: 'e.g. /history 7d — last n days' },
    { cmd: '/progress', desc: 'Mastery dials + level trend, with option to level up' },
  ],
  writing: [
    { cmd: '/btw &lt;question&gt;', desc: 'Ask the tutor a question, typed in the answer box' },
  ],
  grammar: [
    { cmd: '/btw &lt;question&gt;', desc: 'Type on its own line inside your answer block' },
  ],
};

function showCmdSidebar(phaseKey) {
  const hints = CMD_HINTS[phaseKey];
  const sidebar = document.getElementById('cmd-sidebar');
  if (!hints) { sidebar.style.display = 'none'; return; }
  document.getElementById('cmd-list').innerHTML = hints.map(h =>
    `<div class="cmd-item"><code>${h.cmd}</code><div class="cmd-desc">${h.desc}</div></div>`
  ).join('');
  sidebar.style.display = 'block';
}

function hideCmdSidebar() {
  document.getElementById('cmd-sidebar').style.display = 'none';
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
  // Any event means the backend responded — whatever we were waiting on is over.
  hideSetupLoading();
  if (!text) return;
  lastOutputText = text;

  // Detect a fresh module-session header (writing or grammar). Fires on every
  // occurrence, not just once — a session chained via the next_actions accept
  // prompt starts a second header within the same SSE stream.
  const isWritingHeader = text.includes('WRITING EXERCISE');
  const isGrammarHeader = text.includes('GRAMMAR SESSION');

  if (isWritingHeader || isGrammarHeader) {
    if (inSessionPhase) resetForNewModuleSession();
    inSessionPhase = true;
    switchToSession();

    const topicMatch = text.match(/Topic:\s*(.+)/);
    const lvlMatch   = text.match(/Target Level:\s*(\w+)/);
    if (lvlMatch) updateChip('chip-level', lvlMatch[1].toUpperCase());

    if (isWritingHeader) {
      activeModule = 'writing';
      phase = 'writing'; // writing pad is interactive immediately — unlike grammar,
                          // there's no further generation step before it's usable
      const reqMatch = text.match(/Requirements:\s*(.+)/);
      document.getElementById('writing-pad').style.display = 'block';
      document.getElementById('grammar-pad').style.display = 'none';
      document.getElementById('word-count').style.display = '';
      document.getElementById('btw-inp').disabled = false;
      document.getElementById('btw-btn').disabled = false;
      document.getElementById('btw-inp').placeholder = 'Ask the tutor… (during writing)';
      if (topicMatch) {
        document.getElementById('topic-box').style.display = 'block';
        document.getElementById('topic-title').textContent = topicMatch[1].trim();
        document.getElementById('topic-req').textContent   = reqMatch ? reqMatch[1].trim() : '';
      }
      updateChip('chip-module', 'Writing');
      document.getElementById('writing-pad').focus();
      const draft = localStorage.getItem('draftText');
      if (draft) {
        document.getElementById('writing-pad').value = draft;
        updateWordCount();
      }
      // Writing uses the right column for tutor/btw — restore it in case a
      // prior grammar session in this chain hid it.
      document.getElementById('right-col').style.display = '';
      document.getElementById('col-resizer').style.display = '';
      document.getElementById('left-col').classList.remove('solo');
      showCmdSidebar('writing');
    } else {
      // Header + explanation arrive as one combined io.output() blob — pull the
      // explanation body out from between the separator and the closing rule.
      activeModule = 'grammar';
      const explMatch = text.match(/-{5,}[\r\n]+([\s\S]*)\n=+/);
      document.getElementById('writing-pad').style.display = 'none';
      document.getElementById('grammar-box').style.display = 'block';
      document.getElementById('grammar-resizer').style.display = 'block';
      document.getElementById('word-count').style.display = 'none';
      // /btw during grammar answer-collection must be typed inline in the block —
      // a separate Ask call here would collide with the single prompt_block() read.
      document.getElementById('btw-inp').disabled = true;
      document.getElementById('btw-btn').disabled = true;
      document.getElementById('btw-inp').placeholder = 'Type /btw questions directly in your answer block';
      if (topicMatch) document.getElementById('grammar-topic-title').textContent = topicMatch[1].trim();
      document.getElementById('grammar-explanation').textContent = explMatch ? explMatch[1].trim() : '';
      updateChip('chip-module', 'Grammar');
      // Exercises are still being generated at this point (phase stays 'loading' —
      // see handleExercisesReady in grammar-ui.js) — show a "preparing" indicator
      // and keep the answer pad/submit unusable until exercises_ready arrives, so
      // an early Submit click can't be read as a (blank) answer.
      document.getElementById('grammar-loading').style.display = 'flex';
      document.getElementById('grammar-pad').disabled = true;
      document.getElementById('submit-btn').disabled = true;
      // The right column (tutor/btw) is unused in grammar — reclaim the width
      // for the explanation/exercises panel instead of leaving it idle.
      document.getElementById('right-col').style.display = 'none';
      document.getElementById('col-resizer').style.display = 'none';
      document.getElementById('left-col').classList.add('solo');
      showCmdSidebar('grammar');
    }
    return; // don't render the raw ASCII header
  }

  // Detect language
  const langMatch = text.match(/(?:studying|EXERCISE.*?for|SESSION.*?for|)\s*(\bGERMAN\b|\bFRENCH\b|\bSPANISH\b|\bITALIAN\b|\bJAPANESE\b)/i);
  if (langMatch) updateChip('chip-lang', langMatch[1].toUpperCase());

  // Route text to the right panel
  if (!inSessionPhase) {
    appendSetup(text);
  } else {
    // Detect pipeline progress steps (writing evaluation only)
    const stepMatch = text.match(/^\[(\d+)\/6\]/);
    if (stepMatch) {
      const n = parseInt(stepMatch[1]);
      markEvalStep(n);
      appendTutor(text, 'progress');
    } else {
      appendTutor(text, 'tutor');
    }
  }

  if (text.includes('VOCABULARY')) updateChip('chip-module', 'Vocab');
}

function resetForNewModuleSession() {
  // A new module session is starting within the same SSE stream (chained via the
  // accept/decline next_actions prompt) — reset per-session UI, keep the stream alive.
  stopTimer();
  const divider = document.createElement('div');
  divider.className = 'tmsg section';
  divider.textContent = '── New session ──';
  document.getElementById('tutor-output').appendChild(divider);

  document.getElementById('eval-overlay').style.display = 'none';
  markEvalStep(0);
  document.getElementById('done-banner').style.display = 'none';
  document.getElementById('grammar-loading').style.display = 'none';

  document.getElementById('topic-box').style.display = 'none';
  document.getElementById('topic-title').textContent = '';
  document.getElementById('topic-req').textContent = '';
  document.getElementById('writing-pad').value = '';
  document.getElementById('writing-pad').disabled = false;
  document.getElementById('writing-pad').style.display = 'none';
  localStorage.removeItem('draftText');

  document.getElementById('grammar-box').style.display = 'none';
  document.getElementById('grammar-resizer').style.display = 'none';
  document.getElementById('grammar-topic-title').textContent = '';
  document.getElementById('grammar-explanation').textContent = '';
  document.getElementById('grammar-exercises').style.display = 'none';
  document.getElementById('grammar-exercises').innerHTML = '';
  document.getElementById('grammar-pad').value = '';
  document.getElementById('grammar-pad').placeholder = '';
  document.getElementById('grammar-pad').disabled = false;
  document.getElementById('grammar-pad').style.display = 'none';
  document.getElementById('grammar-results').style.display = 'none';
  document.getElementById('grammar-results').innerHTML = '';

  document.getElementById('submit-btn').disabled = false;
  activeModule = null;
}

function handlePrompt(text) {
  hideSetupLoading(); // the backend is asking for input, so whatever we were waiting on is done
  const trimmed = (text || '').trim();

  // Module-agnostic end-of-session chaining prompt (2a-vii bridge, either direction).
  const chainMatch = trimmed.match(/^Session complete\. Start (\w+) practice(?: on '([^']*)')? now\?/);
  if (chainMatch) {
    showChainPrompt(chainMatch[1], chainMatch[2] || '');
    return;
  }

  if (activeModule === 'grammar') {
    // The single block-answer prompt — handled by #grammar-pad, no separate input box.
    const pad = document.getElementById('grammar-pad');
    if (pad && !pad.placeholder) pad.placeholder = trimmed;
    pad.style.display = 'block';
    pad.disabled = false;
    pad.focus();
    return;
  }

  if (!inSessionPhase) {
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

function showChainPrompt(module, focus) {
  const wrap = document.createElement('div');
  wrap.className = 'invite-msg';
  const focusText = focus ? ` on '${escapeHtml(focus)}'` : '';
  wrap.innerHTML =
    `Session complete. Start <b>${escapeHtml(module)}</b> practice${focusText} now? ` +
    `<button class="btn-ask" id="chain-yes">Yes</button> ` +
    `<button class="btn-ask" id="chain-no">No</button>`;
  document.getElementById('tutor-output').appendChild(wrap);
  document.getElementById('chain-yes').onclick = () => {
    wrap.remove();
    // The chained run_session() still re-runs language/level confirmation (only
    // summarize/recommend/confirm are skipped, not setup) before the next module's
    // header appears — go back to the #setup panel so those prompts aren't swallowed
    // by the "no input box during a session" rule that (correctly) applies once a
    // module header actually starts.
    goBackToSetupForChaining();
    sendInput('y');
  };
  document.getElementById('chain-no').onclick  = () => { wrap.remove(); sendInput('n'); };
  const out = document.getElementById('tutor-output');
  out.scrollTop = out.scrollHeight;
}

function goBackToSetupForChaining() {
  resetForNewModuleSession();
  inSessionPhase = false;
  document.getElementById('session').style.display = 'none';
  document.getElementById('setup').style.display = 'flex';
  document.getElementById('setup-output').innerHTML = '';
  showCmdSidebar('setup');
}

function handleDone() {
  phase = 'done';
  stopTimer();
  document.getElementById('done-banner').style.display = 'block';
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('btw-btn').disabled   = true;
  document.getElementById('done-btn').style.display = 'none';
  localStorage.removeItem('draftText');
  hideCmdSidebar();
}

async function finishSession() {
  document.getElementById('done-btn').disabled  = true;
  document.getElementById('btw-btn').disabled   = true;
  document.getElementById('btw-inp').disabled   = true;
  await sendInput('');
}

function handleData(payload) {
  // progress_ready (unlike the other data events) fires during the setup phase,
  // right after submitSetup()'s showSetupLoading() — mirror handleOutput/handlePrompt
  // and clear it here too, since no output/prompt event necessarily follows first.
  hideSetupLoading();
  if (payload.event === 'evaluation_complete')      return handleEvaluationComplete(payload);
  if (payload.event === 'exercises_ready')          return handleExercisesReady(payload);
  if (payload.event === 'grammar_results_complete') return handleGrammarResultsComplete(payload);
  if (payload.event === 'progress_ready')           return handleProgressReady(payload);
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
  // Module-specific setup (pad focus/draft-restore/visibility, and — for writing
  // only — setting phase = 'writing') happens in handleOutput()'s header branch,
  // since it differs between writing and grammar. Grammar's pad isn't interactive
  // yet at this point (exercises are still generating), so phase stays 'loading'
  // until handleExercisesReady() flips it — see grammar-ui.js.
  document.getElementById('setup').style.display   = 'none';
  document.getElementById('session').style.display = 'flex';
  startTimer();
  phase = 'loading';
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
  showSetupLoading();
  await sendInput(text);
}

// ── Setup loading indicator ──────────────────────────────────────────────────
// Some setup steps (e.g. confirming the CEFR level) trigger an LLM call before
// the next prompt is shown, with nothing on screen in the meantime — this fills
// that gap. Hidden again as soon as any event arrives (handleOutput/handlePrompt).
function showSetupLoading() {
  document.getElementById('setup-loading').style.display = 'flex';
}
function hideSetupLoading() {
  document.getElementById('setup-loading').style.display = 'none';
}

function handleSubmitClick() {
  if (activeModule === 'grammar') submitGrammarAnswers();
  else submitWriting();
}

async function sendBtw() {
  const inp = document.getElementById('btw-inp');
  const q   = inp.value.trim();
  if (phase === 'follow-up' && !q) { finishSession(); return; }
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

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.activeElement === document.getElementById('user-id'))
    startSession();
  if (e.key === 'Enter' && document.activeElement === document.getElementById('setup-inp'))
    submitSetup();
  if (e.key === 'Enter' && document.activeElement === document.getElementById('btw-inp'))
    sendBtw();
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter'
      && (document.activeElement === document.getElementById('writing-pad')
          || document.activeElement === document.getElementById('grammar-pad')))
    handleSubmitClick();
});
