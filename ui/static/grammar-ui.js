// Grammar-module-specific handlers. Depends on shared state/helpers defined in
// app.js (phase, activeModule, escapeHtml, appendTutor, sendInput, etc.) — load after it.
// Also depends on diff.js's tokenise()/lcs() (word-level LCS diff), loaded before this file.

// Word-level diff between a wrong free-text answer and the reference answer —
// only meaningful for llm-graded types (whole-sentence answers); exact-match
// types (fill-in-the-blank etc.) are single tokens where a diff adds nothing
// over the plain "Your answer / Correct answer" pair.
function diffToHtml(origText, corrText) {
  if (typeof lcs !== 'function' || typeof tokenise !== 'function') return '';
  const ops = lcs(tokenise(origText), tokenise(corrText));
  return ops.map(op => {
    if (op.t === '=') return escapeHtml(op.v);
    if (op.t === '-') return `<span class="del">${escapeHtml(op.v)}</span>`;
    return `<span class="ins">${escapeHtml(op.v)}</span>`;
  }).join('');
}

function handleExercisesReady(payload) {
  const groups = payload.groups || [];
  const box = document.getElementById('grammar-exercises');
  let counter = 0;
  box.innerHTML = groups.map(group => {
    const heading = group.instruction
      ? `<div class="ex-group-heading">${escapeHtml(group.instruction)}</div>` : '';
    const items = group.exercises.map(ex => {
      counter++;
      return `<li>${escapeHtml(ex.prompt)}</li>`;
    }).join('');
    return `${heading}<ol start="${counter - group.exercises.length + 1}">${items}</ol>`;
  }).join('');
  box.style.display = groups.length ? 'block' : 'none';

  document.getElementById('grammar-loading').style.display = 'none';
  document.getElementById('submit-btn').disabled = false;

  const pad = document.getElementById('grammar-pad');
  pad.style.display = 'block';
  pad.disabled = false;
  pad.value = '';
  pad.focus();
  phase = 'writing'; // shared "collecting a submittable answer" phase, reused across modules —
                      // only set once exercises actually exist, so an early Submit/Ctrl+Enter
                      // can't be read as a (blank) answer before the pad is ready.
}

function handleGrammarResultsComplete(payload) {
  // A "do another round on this topic?" prompt follows this event (see
  // showGrammarAgainPrompt in this file / handlePrompt in app.js) — so unlike a
  // one-shot module, the explanation stays visible as reference material instead
  // of being hidden as "stale".
  const items = payload.items || [];
  const score = payload.score || 0;

  document.getElementById('grammar-pad').style.display = 'none';
  document.getElementById('submit-btn').disabled = true;

  // Exercise list is redundant with the itemized results below — hide it to
  // give #grammar-results (and the footer/done-banner below it) room in
  // #left-col, which has overflow:hidden and no scrollbar of its own.
  document.getElementById('grammar-exercises').style.display = 'none';

  const wrap = document.createElement('div');
  wrap.className = 'annotated-block';
  const rows = items.map((item, i) => {
    const cls = item.correct ? 'correct' : 'incorrect';
    const status = item.correct ? 'Correct' : 'Incorrect';
    let extra = '';
    if (!item.correct) {
      const diffWorthy = item.grading === 'llm' && item.user_answer && item.correct_answer;
      const diffLine = diffWorthy
        ? `<div class="ex-diff">${diffToHtml(item.user_answer, item.correct_answer)}</div>`
        : '';
      extra =
        diffLine +
        `<div class="ex-answer">Correct answer: ${escapeHtml(item.correct_answer || '')}</div>` +
        `<div class="ex-feedback">${escapeHtml(item.feedback || '')}</div>`;
    } else if (item.feedback) {
      // Correct but with a non-penalizing note (e.g. a flagged typo).
      extra = `<div class="ex-feedback">${escapeHtml(item.feedback)}</div>`;
    }
    return (
      `<div class="exercise-item ${cls}">` +
      `<div>${i + 1}. [${status}] ${escapeHtml(item.prompt)}</div>` +
      `<div class="ex-answer">Your answer: ${escapeHtml(item.user_answer || '')}</div>` +
      extra +
      `</div>`
    );
  }).join('');
  wrap.innerHTML =
    `<div class="ann-label">Results <span class="ann-count">${Math.round(score * 100)}%</span></div>` +
    rows;

  // Rendered in the left column, not #tutor-output — #right-col is hidden for
  // the whole grammar session (see handleOutput's grammar branch in app.js).
  const out = document.getElementById('grammar-results');
  out.style.display = 'block';
  out.appendChild(wrap);

  document.getElementById('grammar-grading').style.display = 'none';

  if (score >= 0.999) fireConfetti();

  out.scrollTop = out.scrollHeight;
}

async function submitGrammarAnswers() {
  // GrammarModule calls io.prompt_block() exactly once — send the whole textarea
  // value as a single sendInput() call, unlike submitWriting()'s per-line loop
  // for io.prompt()'s N round trips.
  if (phase !== 'writing' || activeModule !== 'grammar') return;
  const pad = document.getElementById('grammar-pad');

  phase = 'evaluating';
  pad.disabled = true;
  document.getElementById('submit-btn').disabled = true;
  // #tutor-output (appendTutor's target) is hidden for grammar sessions — show
  // the grading state in the left column instead, same pattern as grammar-loading.
  document.getElementById('grammar-grading').style.display = 'flex';
  await sendInput(pad.value);
}

// ── Intra-session continuation ("another exercise?") ──────────────────────────
function showGrammarAgainPrompt(topic) {
  const wrap = document.createElement('div');
  wrap.className = 'invite-msg';
  wrap.innerHTML =
    `Try another exercise on <b>${escapeHtml(topic)}</b>? ` +
    `<button class="btn-ask" id="grammar-again-yes">Yes</button> ` +
    `<button class="btn-ask" id="grammar-again-no">No</button>`;
  const out = document.getElementById('grammar-results');
  out.appendChild(wrap);
  out.scrollTop = out.scrollHeight;

  document.getElementById('grammar-again-yes').onclick = () => {
    wrap.remove();
    resetGrammarForNextRound();
    sendInput('y');
  };
  document.getElementById('grammar-again-no').onclick = () => {
    wrap.remove();
    sendInput('n');
  };
}

function resetGrammarForNextRound() {
  // Backend is about to generate a fresh batch of exercises on the same topic —
  // clear the previous round's exercises/results and re-show the "preparing"
  // state, mirroring the very first round (see handleOutput's grammar branch
  // in app.js). The explanation panel is left as-is — it stays visible for
  // reference across every round.
  document.getElementById('grammar-results').innerHTML = '';
  document.getElementById('grammar-results').style.display = 'none';
  document.getElementById('grammar-exercises').innerHTML = '';
  document.getElementById('grammar-exercises').style.display = 'none';
  document.getElementById('grammar-pad').value = '';
  document.getElementById('grammar-pad').disabled = true;
  document.getElementById('grammar-pad').style.display = 'none';
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('grammar-loading').style.display = 'flex';
  phase = 'loading';
}
