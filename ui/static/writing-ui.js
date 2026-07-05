// Writing-module-specific handlers. Depends on shared state/helpers defined in
// app.js (phase, sid, escapeHtml, appendTutor, sendInput, etc.) — load after it.

async function submitWriting() {
  if (phase !== 'writing') return;
  const pad   = document.getElementById('writing-pad');
  const text  = pad.value.trim();
  if (!text) return;

  stopTimer(); // timer tracks time spent writing, not the evaluation/follow-up that follows
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

function handleEvaluationComplete(payload) {
  // Hide eval overlay now that evaluation output is fully rendered
  document.getElementById('eval-overlay').style.display = 'none';

  const { user_text, corrected_text, mistakes, explained_mistakes, session_summary, tips, text_level_estimate } = payload;
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
  }

  // Itemized mistake breakdown (severity-grouped, with corrections and
  // explanations) — the inline highlighting above only carries a hover
  // tooltip, easy to miss. This mirrors what the CLI and the post-session
  // review page already show but the live UI never rendered.
  if (explained_mistakes && explained_mistakes.length > 0) {
    const order = ['critical', 'expected', 'minor', ''];
    const labels = { critical: 'Critical', expected: 'Expected at this level', minor: 'Minor / stylistic', '': 'Mistakes' };
    const groups = {};
    for (const m of explained_mistakes) {
      const sev = m.severity || '';
      (groups[sev] = groups[sev] || []).push(m);
    }
    const block = document.createElement('div');
    block.className = 'annotated-block';
    let html = `<div class="ann-label">Mistakes <span class="ann-count">${explained_mistakes.length}</span></div>`;
    let counter = 0;
    for (const sev of order) {
      if (!groups[sev] || !groups[sev].length) continue;
      html += `<div class="mistake-group-heading">${escapeHtml(labels[sev])}</div>`;
      for (const m of groups[sev]) {
        counter++;
        html +=
          `<div class="mistake-item">` +
          `<div>${counter}. [${escapeHtml(m.error_tag || '')}] "${escapeHtml(m.fragment || '')}" &rarr; ${escapeHtml(m.correction || '')}</div>` +
          `<div class="mistake-expl">${escapeHtml(m.explanation || '')}</div>` +
          `</div>`;
      }
    }
    block.innerHTML = html;
    document.getElementById('tutor-output').appendChild(block);
  }

  if (corrected_text && corrected_text !== user_text) {
    const corr = document.createElement('div');
    corr.className = 'annotated-block corr';
    corr.innerHTML =
      `<div class="ann-label">Corrected</div>` +
      `<div>${escapeHtml(corrected_text)}</div>`;
    document.getElementById('tutor-output').appendChild(corr);
  }

  // Session summary + tips + estimated level — sent by the backend on every
  // evaluation (see shared/io.py's render_evaluation) but previously dropped
  // here since this handler never read them off the payload.
  if (session_summary) {
    const summary = document.createElement('div');
    summary.className = 'annotated-block';
    summary.innerHTML =
      `<div class="ann-label">Summary</div>` +
      `<div>${escapeHtml(session_summary)}</div>`;
    document.getElementById('tutor-output').appendChild(summary);
  }

  if (tips && tips.length > 0) {
    const tipsBlock = document.createElement('div');
    tipsBlock.className = 'annotated-block';
    tipsBlock.innerHTML =
      `<div class="ann-label">Tips</div>` +
      `<ul class="tips-list">${tips.map(t => `<li>${escapeHtml(t)}</li>`).join('')}</ul>`;
    document.getElementById('tutor-output').appendChild(tipsBlock);
  }

  if (text_level_estimate) {
    const levelBlock = document.createElement('div');
    levelBlock.className = 'annotated-block';
    levelBlock.innerHTML =
      `<div class="ann-label">Text level</div>` +
      `<div>Estimated: ${escapeHtml(text_level_estimate.toUpperCase())}</div>`;
    document.getElementById('tutor-output').appendChild(levelBlock);
  }

  // Invitation to ask follow-up questions
  const inv = document.createElement('div');
  inv.className = 'invite-msg';
  inv.textContent = 'Unsure why something was flagged? Ask me below ↓';
  document.getElementById('tutor-output').appendChild(inv);

  // Enter follow-up phase so sendBtw() doesn't gate out
  phase = 'follow-up';

  // Focus the btw input for follow-up; show Done button
  const btwInp = document.getElementById('btw-inp');
  btwInp.placeholder = 'Ask about a mistake… (Enter to finish)';
  document.getElementById('btw-btn').disabled = false;
  document.getElementById('done-btn').style.display = '';
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
