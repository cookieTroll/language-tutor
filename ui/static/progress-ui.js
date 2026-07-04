// Layer 2c — /progress command rendering. Fires during the setup phase (like
// /history), so it renders into #setup-output rather than the session panels.

function handleProgressReady(payload) {
  const level = (payload.current_level || '').toUpperCase();
  const modules = payload.modules || [];
  const trend = payload.trend || [];

  const wrap = document.createElement('div');
  wrap.className = 'progress-block';

  const title = document.createElement('div');
  title.className = 'progress-title';
  title.textContent = `Level & Progress (${level})`;
  wrap.appendChild(title);

  const dialRow = document.createElement('div');
  dialRow.className = 'dial-row';
  modules.forEach(m => dialRow.appendChild(renderMasteryDial(m)));
  wrap.appendChild(dialRow);

  if (trend.length) {
    const spark = document.createElement('div');
    spark.className = 'progress-trend';
    spark.textContent = 'Recent text-level trend: ' +
      trend.slice(-5).map(t => (t.level || '').toUpperCase()).join(' → ');
    wrap.appendChild(spark);
  }

  document.getElementById('setup-output').appendChild(wrap);
  const el = document.getElementById('setup-output');
  el.scrollTop = el.scrollHeight;
}

function renderMasteryDial(m) {
  const box = document.createElement('div');
  box.className = 'dial-wrap';

  const pct = Math.round((m.mastery_ratio || 0) * 100);
  const dial = document.createElement('div');
  dial.className = 'dial';
  dial.style.setProperty('--pct', pct);
  dial.innerHTML = `<span class="dial-pct">${pct}%</span>`;
  box.appendChild(dial);

  const label = document.createElement('div');
  label.className = 'dial-label';
  label.textContent = m.module.charAt(0).toUpperCase() + m.module.slice(1);
  box.appendChild(label);

  const stats = document.createElement('div');
  stats.className = 'dial-stats';
  if (m.module === 'grammar') {
    stats.textContent = `${m.topics_mastered || 0}/${m.topics_total || 0} topics mastered`;
  } else if (m.module === 'writing') {
    stats.textContent =
      `${m.texts_written || 0} texts · ${m.total_words || 0} words ` +
      `(${m.words_at_current_level || 0} at this level)`;
  }
  box.appendChild(stats);

  const tags = document.createElement('div');
  tags.className = 'dial-tags';
  (m.strong_tags || []).forEach(t => tags.appendChild(makeProgressTagChip(t, 'strong')));
  (m.weak_tags || []).forEach(t => tags.appendChild(makeProgressTagChip(t, 'weak')));
  box.appendChild(tags);

  return box;
}

function makeProgressTagChip(text, kind) {
  const span = document.createElement('span');
  span.className = 'tag-chip ' + kind;
  span.textContent = text;
  return span;
}
