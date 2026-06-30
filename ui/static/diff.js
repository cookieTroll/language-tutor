// ── Diff ──────────────────────────────────────────────────────────────────────
function tokenise(text) { return text.match(/\S+|\s+/g) || []; }

function lcs(a, b) {
  const m = a.length, n = b.length;
  const dp = Array.from({length: m+1}, () => new Uint16Array(n+1));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1]+1 : Math.max(dp[i-1][j], dp[i][j-1]);
  const ops = [];
  let i = m, j = n;
  while (i || j) {
    if (i && j && a[i-1] === b[j-1]) { ops.push({t:'=', v:a[i-1]}); i--; j--; }
    else if (j && (!i || dp[i][j-1] >= dp[i-1][j])) { ops.push({t:'+', v:b[j-1]}); j--; }
    else { ops.push({t:'-', v:a[i-1]}); i--; }
  }
  return ops.reverse();
}

function renderDiff(origText, corrText) {
  const ops  = lcs(tokenise(origText), tokenise(corrText));
  const wrap = document.getElementById('diff-view');
  if (!wrap) return;
  wrap.innerHTML = '';
  ops.forEach(op => {
    if (op.t === '=') {
      wrap.appendChild(document.createTextNode(op.v));
    } else if (op.t === '-') {
      const s = document.createElement('span');
      s.className = 'del'; s.textContent = op.v; wrap.appendChild(s);
    } else {
      const s = document.createElement('span');
      s.className = 'ins'; s.textContent = op.v; wrap.appendChild(s);
    }
  });
}

// origText / corrText injected by inline <script> above this file
if (typeof origText !== 'undefined' && typeof corrText !== 'undefined'
    && origText && corrText && origText !== corrText) {
  renderDiff(origText, corrText);
}

// ── Copy ──────────────────────────────────────────────────────────────────────
function copyText(id) {
  const text = document.getElementById(id).textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  });
}

// ── Practice again ────────────────────────────────────────────────────────────
function setPracticeTopic(topic) {
  if (topic) sessionStorage.setItem('retryTopic', topic);
}
