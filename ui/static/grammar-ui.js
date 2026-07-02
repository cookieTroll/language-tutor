// Grammar-module-specific handlers. Depends on shared state/helpers defined in
// app.js (phase, activeModule, escapeHtml, appendTutor, sendInput, etc.) — load after it.

function handleExercisesReady(payload) {
  const exercises = payload.exercises || [];
  const box = document.getElementById('grammar-exercises');
  box.innerHTML = '<ol>' + exercises.map(ex => `<li>${escapeHtml(ex.prompt)}</li>`).join('') + '</ol>';
  box.style.display = exercises.length ? 'block' : 'none';

  const pad = document.getElementById('grammar-pad');
  pad.style.display = 'block';
  pad.disabled = false;
  pad.value = '';
  pad.focus();
  phase = 'writing'; // shared "collecting a submittable answer" phase, reused across modules
}

function handleGrammarResultsComplete(payload) {
  // GrammarModule has no follow-up phase (unlike writing) — module.run() returns
  // right after grading, so no btw/done follow-up UI is offered here.
  const items = payload.items || [];
  const score = payload.score || 0;

  document.getElementById('grammar-pad').style.display = 'none';
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('btw-btn').disabled = true;

  const wrap = document.createElement('div');
  wrap.className = 'annotated-block';
  const rows = items.map((item, i) => {
    const cls = item.correct ? 'correct' : 'incorrect';
    const status = item.correct ? 'Correct' : 'Incorrect';
    let extra = '';
    if (!item.correct) {
      extra =
        `<div class="ex-answer">Correct answer: ${escapeHtml(item.correct_answer || '')}</div>` +
        `<div class="ex-feedback">${escapeHtml(item.feedback || '')}</div>`;
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
  document.getElementById('tutor-output').appendChild(wrap);

  if (score >= 0.999) fireConfetti();

  const out = document.getElementById('tutor-output');
  out.scrollTop = out.scrollHeight;
}

async function submitGrammarAnswers() {
  // GrammarModule calls io.prompt_block() exactly once — send the whole textarea
  // value (including any inline /btw lines) as a single sendInput() call, unlike
  // submitWriting()'s per-line loop for io.prompt()'s N round trips.
  if (phase !== 'writing' || activeModule !== 'grammar') return;
  const pad = document.getElementById('grammar-pad');

  phase = 'evaluating';
  pad.disabled = true;
  document.getElementById('submit-btn').disabled = true;
  appendTutor('Grading your answers…', 'progress');
  await sendInput(pad.value);
}
