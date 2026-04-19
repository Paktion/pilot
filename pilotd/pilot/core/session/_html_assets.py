"""
Static CSS, JavaScript, and HTML shell strings used by
:mod:`pilot.core.session.exporter` to build self-contained HTML session
reports.

Kept in a separate module purely to hold the template data outside the
rendering logic — no runtime behaviour lives here.
"""

from __future__ import annotations


CSS: str = """\
:root {
    --bg: #0f0f1a;
    --surface: #1a1a2e;
    --surface-2: #24243e;
    --border: #2d2d4a;
    --text: #e2e2f0;
    --text-dim: #8888a8;
    --accent: #6c63ff;
    --green: #4ade80;
    --red: #f87171;
    --yellow: #facc15;
    --blue: #60a5fa;
    --purple: #c084fc;
    --cyan: #22d3ee;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display',
                 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.6; min-height: 100vh;
}
.container { max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }
.header { text-align: center; margin-bottom: 2.5rem; }
.header .logo {
    font-size: 1.1rem; letter-spacing: 0.15em; text-transform: uppercase;
    color: var(--accent); font-weight: 700; margin-bottom: 0.25rem;
}
.header h1 { font-size: 1.6rem; font-weight: 600; margin-bottom: 0.5rem; }
.header .meta { color: var(--text-dim); font-size: 0.85rem; }
.header .meta span { margin: 0 0.5rem; }
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 1rem; margin-bottom: 2rem;
}
.stat-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.2rem 1rem; text-align: center;
}
.stat-card .stat-value {
    font-size: 1.5rem; font-weight: 700; margin-bottom: 0.15rem;
}
.stat-card .stat-label {
    font-size: 0.75rem; color: var(--text-dim);
    text-transform: uppercase; letter-spacing: 0.08em;
}
.summary-panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem;
}
.summary-panel h2 {
    font-size: 1rem; color: var(--accent); margin-bottom: 0.5rem;
}
.summary-panel p { color: var(--text-dim); }
.carousel-nav {
    display: flex; align-items: center; justify-content: center;
    gap: 0.75rem; margin-bottom: 1.5rem;
}
.carousel-nav button {
    background: var(--surface-2); border: 1px solid var(--border);
    color: var(--text); border-radius: 8px; padding: 0.5rem 1.2rem;
    cursor: pointer; font-size: 0.85rem;
    transition: background 0.2s, border-color 0.2s;
}
.carousel-nav button:hover {
    background: var(--accent); border-color: var(--accent);
}
.carousel-nav button:disabled { opacity: 0.35; cursor: not-allowed; }
.carousel-nav .page-info {
    color: var(--text-dim); font-size: 0.85rem;
    min-width: 6rem; text-align: center;
}
.step-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; margin-bottom: 1.5rem;
    overflow: hidden; display: none;
}
.step-card.active { display: block; }
.step-header {
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0.9rem 1.2rem; background: var(--surface-2);
    border-bottom: 1px solid var(--border); flex-wrap: wrap;
}
.step-number { font-weight: 700; font-size: 0.95rem; }
.badge {
    display: inline-block; padding: 0.15rem 0.6rem;
    border-radius: 999px; font-size: 0.7rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.badge.tap     { background: rgba(74, 222, 128, 0.15); color: var(--green); }
.badge.swipe   { background: rgba(250, 204, 21, 0.15); color: var(--yellow); }
.badge.type    { background: rgba(192, 132, 252, 0.15); color: var(--purple); }
.badge.scroll  { background: rgba(250, 204, 21, 0.15); color: var(--yellow); }
.badge.key     { background: rgba(96, 165, 250, 0.15); color: var(--blue); }
.badge.wait    { background: rgba(136, 136, 168, 0.15); color: var(--text-dim); }
.badge.done    { background: rgba(34, 211, 238, 0.15); color: var(--cyan); }
.badge.home    { background: rgba(96, 165, 250, 0.15); color: var(--blue); }
.badge.back    { background: rgba(96, 165, 250, 0.15); color: var(--blue); }
.badge.other   { background: rgba(136, 136, 168, 0.15); color: var(--text-dim); }
.badge.success { background: rgba(74, 222, 128, 0.15); color: var(--green); }
.badge.failure { background: rgba(248, 113, 113, 0.15); color: var(--red); }
.confidence { font-size: 0.75rem; font-weight: 600; }
.confidence.high   { color: var(--green); }
.confidence.medium { color: var(--yellow); }
.confidence.low    { color: var(--red); }
.timestamp { margin-left: auto; font-size: 0.75rem; color: var(--text-dim); }
.step-body {
    display: grid;
    grid-template-columns: minmax(200px, 320px) 1fr;
    gap: 1.2rem; padding: 1.2rem;
}
@media (max-width: 700px) { .step-body { grid-template-columns: 1fr; } }
.screenshot-col img {
    width: 100%; border-radius: 10px; border: 1px solid var(--border);
}
.no-screenshot {
    width: 100%; aspect-ratio: 9/16; background: var(--surface-2);
    border-radius: 10px; display: flex; align-items: center;
    justify-content: center; color: var(--text-dim); font-size: 0.85rem;
}
.thought-bubble {
    background: var(--surface-2); border-radius: 12px;
    padding: 1rem 1.2rem; margin-bottom: 1rem;
    border-left: 3px solid var(--accent);
}
.thought-label, .action-label {
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--accent); font-weight: 600; margin-bottom: 0.4rem;
}
.thought-bubble p {
    color: var(--text); font-size: 0.9rem; white-space: pre-wrap;
}
.action-block {
    background: var(--surface-2); border-radius: 12px;
    padding: 1rem 1.2rem;
}
.action-block pre {
    background: var(--bg); border-radius: 8px; padding: 0.75rem;
    overflow-x: auto; font-size: 0.8rem; color: var(--cyan);
}
.action-block code {
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
}
.error-msg {
    background: rgba(248, 113, 113, 0.1);
    border: 1px solid rgba(248, 113, 113, 0.3);
    border-radius: 8px; padding: 0.75rem 1rem; margin-top: 0.75rem;
    color: var(--red); font-size: 0.85rem;
}
.footer {
    text-align: center; padding: 2rem 0 1rem;
    color: var(--text-dim); font-size: 0.75rem;
}
.footer a { color: var(--accent); text-decoration: none; }
.timeline {
    display: flex; gap: 0.35rem; justify-content: center;
    margin-bottom: 1.5rem; flex-wrap: wrap;
}
.timeline .dot {
    width: 10px; height: 10px; border-radius: 50%;
    cursor: pointer; transition: transform 0.15s;
    border: 2px solid transparent;
}
.timeline .dot:hover { transform: scale(1.4); }
.timeline .dot.active {
    border-color: var(--text); transform: scale(1.3);
}
.timeline .dot.ok   { background: var(--green); }
.timeline .dot.fail { background: var(--red); }
"""


JS: str = """\
(function() {
    const cards = document.querySelectorAll('.step-card');
    const total = cards.length;
    let current = 0;

    const timeline = document.getElementById('timeline');
    cards.forEach((card, i) => {
        const dot = document.createElement('span');
        dot.className = 'dot ' + (card.querySelector('.badge.success') ? 'ok' : 'fail');
        dot.title = 'Step ' + (i + 1);
        dot.addEventListener('click', () => goTo(i));
        timeline.appendChild(dot);
    });

    function goTo(idx) {
        if (idx < 0 || idx >= total) return;
        cards[current].classList.remove('active');
        current = idx;
        cards[current].classList.add('active');
        updateUI();
    }
    function updateUI() {
        document.getElementById('page-info').textContent = (current + 1) + ' / ' + total;
        document.getElementById('btn-prev').disabled = current === 0;
        document.getElementById('btn-next').disabled = current === total - 1;
        const dots = timeline.querySelectorAll('.dot');
        dots.forEach((d, i) => d.classList.toggle('active', i === current));
    }
    window.navigate = function(dir) { goTo(current + dir); };
    document.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowLeft')  goTo(current - 1);
        if (e.key === 'ArrowRight') goTo(current + 1);
    });
    if (total > 0) { cards[0].classList.add('active'); updateUI(); }
})();
"""


HTML_SHELL: str = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Pilot Session — {title}</title>
<style>
{css}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="logo">Pilot</div>
        <h1>{task}</h1>
        <div class="meta">
            <span>Session <code>{session_id}</code></span>
            <span>|</span>
            <span>{created_at}</span>
            <span>|</span>
            <span>Model: {model}</span>
        </div>
    </div>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value" style="color: {status_color}">{status_label}</div>
            <div class="stat-label">Status</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{steps}</div>
            <div class="stat-label">Steps</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{duration_str}</div>
            <div class="stat-label">Duration</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{avg_confidence_pct}%</div>
            <div class="stat-label">Avg Confidence</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{success_rate_pct}%</div>
            <div class="stat-label">Step Success</div>
        </div>
    </div>
    <div class="summary-panel">
        <h2>Summary</h2>
        <p>{summary_text}</p>
    </div>
    <div class="timeline" id="timeline"></div>
    <div class="carousel-nav">
        <button id="btn-prev" onclick="navigate(-1)">Prev</button>
        <span class="page-info" id="page-info">1 / {steps}</span>
        <button id="btn-next" onclick="navigate(1)">Next</button>
    </div>
    <div id="steps-container">
{steps_html}
    </div>
    <div class="footer">
        Generated by <strong>Pilot</strong>
    </div>
</div>
<script>
{js}
</script>
</body>
</html>
"""
