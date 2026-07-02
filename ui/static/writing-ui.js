// Writing-module-specific handlers. Depends on shared state/helpers defined in
// app.js (phase, sid, escapeHtml, appendTutor, sendInput, etc.) — load after it.

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

function handleEvaluationComplete(payload) {
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
