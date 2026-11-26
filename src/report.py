"""Static HTML report with inline SVG charts (no PNG, no external assets).

9 charts (all values computed from the committed processed data):
1. Bump chart: Top 10 rank movement of the 14 slate titles over time.
2. Small multiples: per-title weekly trajectory sparklines (one SVG).
3. Forecast vs actual: connected scatter of the three models'
   one-step-ahead predictions vs actual last-week hours; points
   coloured by title, hover for title / week / actual / predicted.
4. Scenario totals: total hours by scenario (bars).
5. Peak-week load by scenario (bars).
6. Waterfall/bridge: how each scenario moves total slate hours away
   from the baseline (floating delta bars; scenarios are
   alternatives, not cumulative steps).
7. First-run shapes: median fraction of peak with every title's own
   decay curve behind it, plus three named titles.
8. Titles x weeks heatmap of hours viewed (log colour scale).
9. Slate composition as a treemap (area = share of total hours).

Interactivity is vanilla JS only, inline in the HTML; the report is
fully self-contained. Tooltip elements carry a data-tip attribute;
one small script handles them.
"""
from __future__ import annotations

import html
import math

import pandas as pd

COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]
# Tableau 20, for charts with many categories (bump chart, scatter).
PALETTE20 = ["#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c",
             "#98df8a", "#d62728", "#ff9896", "#9467bd", "#c5b0d5",
             "#8c564b", "#c49c94", "#e377c2", "#f7b6d2", "#7f7f7f",
             "#c7c7c7", "#bcbd22", "#dbdb8d", "#17becf", "#9edae5"]
W, H = 760, 320
PAD = {"l": 60, "r": 16, "t": 24, "b": 52}

SHORT_NAMES = {"KPop Demon Hunters": "KPop",
               "Plankton: The Movie": "Plankton",
               "The Wild Robot": "Wild Robot"}

TOOLTIP_JS = """
<script>
document.addEventListener('mouseover', function (e) {
  var t = e.target.closest ? e.target.closest('[data-tip]') : null;
  var tip = document.getElementById('tooltip');
  if (!t) { tip.style.display = 'none'; return; }
  tip.textContent = t.getAttribute('data-tip');
  tip.style.display = 'block';
  tip.style.left = (e.clientX + 12) + 'px';
  tip.style.top = (e.clientY + 12) + 'px';
});
document.addEventListener('mouseout', function (e) {
  var t = e.target.closest ? e.target.closest('[data-tip]') : null;
  if (t) { document.getElementById('tooltip').style.display = 'none'; }
});
document.addEventListener('click', function (e) {
  var l = e.target.closest ? e.target.closest('[data-toggle]') : null;
  if (!l) return;
  var el = document.getElementById(l.getAttribute('data-toggle'));
  if (!el) return;
  var hidden = el.style.display === 'none';
  el.style.display = hidden ? '' : 'none';
  l.style.opacity = hidden ? '1' : '0.35';
});
</script>
"""


def _fmt_millions(x: float) -> str:
    return f"{x / 1e6:,.1f}M"


def _fmt_billions(x: float) -> str:
    return f"{x / 1e9:.2f}B"


def _short(title: str) -> str:
    return SHORT_NAMES.get(title, title)


def _svg_open(title: str, width: int = W, height: int = H) -> list[str]:
    return [f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="{html.escape(title)}">',
            f'<text x="{width // 2}" y="16" text-anchor="middle" '
            f'font-size="13" font-weight="bold">{html.escape(title)}</text>']


def _axes(x_ticks, y_max: float, y_label: str, fmt):
    out = []
    iw, ih = W - PAD["l"] - PAD["r"], H - PAD["t"] - PAD["b"]
    # y gridlines (4)
    for i in range(5):
        y = PAD["t"] + ih - ih * i / 4
        val = y_max * i / 4
        out.append(f'<line x1="{PAD["l"]}" y1="{y:.1f}" x2="{W - PAD["r"]}" '
                   f'y2="{y:.1f}" stroke="#e0e0e0"/>')
        out.append(f'<text x="{PAD["l"] - 6}" y="{y + 4:.1f}" '
                   f'text-anchor="end" font-size="10" fill="#555">'
                   f'{fmt(val)}</text>')
    out.append(f'<text x="14" y="{PAD["t"] + ih // 2}" font-size="10" '
               f'fill="#555" transform="rotate(-90 14 {PAD["t"] + ih // 2})" '
               f'text-anchor="middle">{html.escape(y_label)}</text>')
    n = len(x_ticks)
    for j in range(0, n, max(1, n // 8)):
        x = PAD["l"] + iw * j / max(n - 1, 1)
        out.append(f'<text x="{x:.1f}" y="{PAD["t"] + ih + 14}" '
                   f'text-anchor="middle" font-size="10" fill="#555">'
                   f'{x_ticks[j]}</text>')
    return out, iw, ih


def line_chart(title: str, series: dict, x_labels, y_label: str, fmt) -> str:
    """series: {name: [values]} aligned to x_labels."""
    parts = _svg_open(title)
    y_max = max(max(v) for v in series.values()) * 1.08 or 1.0
    grid, iw, ih = _axes(x_labels, y_max, y_label, fmt)
    parts += grid
    n = len(x_labels)
    for k, (name, vals) in enumerate(series.items()):
        pts = " ".join(
            f"{PAD['l'] + iw * i / max(n - 1, 1):.1f},"
            f"{PAD['t'] + ih - ih * v / y_max:.1f}"
            for i, v in enumerate(vals))
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="{COLORS[k % len(COLORS)]}" stroke-width="2"/>')
    # legend (below the x tick labels)
    lx = PAD["l"]
    for k, name in enumerate(series):
        parts.append(f'<rect x="{lx}" y="{H - 14}" width="10" height="10" '
                     f'fill="{COLORS[k % len(COLORS)]}"/>')
        parts.append(f'<text x="{lx + 14}" y="{H - 5}" font-size="11">'
                     f'{html.escape(name)}</text>')
        lx += 14 + len(name) * 6.5 + 22
    parts.append("</svg>")
    return "\n".join(parts)


def bar_chart(title: str, labels, values, y_label: str, fmt) -> str:
    parts = _svg_open(title)
    y_max = max(values) * 1.15 or 1.0
    grid, iw, ih = _axes(labels, y_max, y_label, fmt)
    parts += grid
    bw = iw / len(labels) * 0.6
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = PAD["l"] + iw * (i + 0.5) / len(labels) - bw / 2
        y = PAD["t"] + ih - ih * v / y_max
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                     f'height="{PAD["t"] + ih - y:.1f}" '
                     f'fill="{COLORS[i % len(COLORS)]}"/>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" '
                     f'text-anchor="middle" font-size="11">{fmt(v)}</text>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{PAD["t"] + ih + 14}" '
                     f'text-anchor="middle" font-size="10" fill="#555">'
                     f'{html.escape(lab)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def bump_chart(title: str, weekly: pd.DataFrame) -> str:
    """Top 10 rank movement of each slate title over its first run.

    weekly: rows with week / show_title / weekly_rank /
    weekly_hours_viewed. X is calendar weeks; y is rank (1 at top).
    Each line is labelled at its last point."""
    df = weekly.sort_values(["show_title", "week"]).copy()
    weeks = pd.date_range(df["week"].min(), df["week"].max(), freq="7D")
    n = len(weeks)
    w_index = {pd.Timestamp(w): i for i, w in enumerate(weeks)}
    titles = sorted(df["show_title"].unique(),
                    key=lambda t: df[df["show_title"] == t]["week"].min())
    parts = _svg_open(title)
    iw, ih = W - PAD["l"] - PAD["r"], H - PAD["t"] - PAD["b"]
    # y gridlines: ranks 1..10, rank 1 at top
    for r in range(1, 11):
        y = PAD["t"] + ih * (r - 1) / 9
        parts.append(f'<line x1="{PAD["l"]}" y1="{y:.1f}" '
                     f'x2="{W - PAD["r"]}" y2="{y:.1f}" stroke="#e0e0e0"/>')
        parts.append(f'<text x="{PAD["l"] - 6}" y="{y + 4:.1f}" '
                     f'text-anchor="end" font-size="10" fill="#555">{r}'
                     f'</text>')
    parts.append(f'<text x="14" y="{PAD["t"] + ih // 2}" font-size="10" '
                 f'fill="#555" transform="rotate(-90 14 {PAD["t"] + ih // 2})" '
                 f'text-anchor="middle">Top 10 rank</text>')
    for j in range(0, n, max(1, n // 7)):
        x = PAD["l"] + iw * j / max(n - 1, 1)
        parts.append(f'<text x="{x:.1f}" y="{PAD["t"] + ih + 14}" '
                     f'text-anchor="middle" font-size="10" fill="#555">'
                     f'{weeks[j].strftime("%Y-%m-%d")}</text>')
    for k, t in enumerate(titles):
        g = df[df["show_title"] == t].sort_values("week")
        color = PALETTE20[k % len(PALETTE20)]
        pts = []
        for _, row in g.iterrows():
            i = w_index[pd.Timestamp(row["week"])]
            x = PAD["l"] + iw * i / max(n - 1, 1)
            y = PAD["t"] + ih * (int(row["weekly_rank"]) - 1) / 9
            pts.append((x, y, row))
        if len(pts) == 1:
            x, y, row = pts[0]
            tip = (f"{t}: {pd.Timestamp(row['week']).date()} — rank "
                   f"{int(row['weekly_rank'])}, "
                   f"{_fmt_millions(row['weekly_hours_viewed'])} hours")
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" '
                         f'fill="{color}" data-tip="{html.escape(tip)}"/>')
        else:
            joined = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
            parts.append(f'<polyline points="{joined}" fill="none" '
                         f'stroke="{color}" stroke-width="2"/>')
            for x, y, row in pts:
                tip = (f"{t}: {pd.Timestamp(row['week']).date()} — rank "
                       f"{int(row['weekly_rank'])}, "
                       f"{_fmt_millions(row['weekly_hours_viewed'])} hours")
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" '
                             f'fill="{color}" data-tip="{html.escape(tip)}"/>')
        lx, ly, _ = pts[-1]
        if lx > W - 90:
            parts.append(f'<text x="{lx - 6:.1f}" y="{ly + 3:.1f}" '
                         f'text-anchor="end" font-size="9" fill="{color}">'
                         f'{html.escape(_short(t))}</text>')
        else:
            parts.append(f'<text x="{lx + 6:.1f}" y="{ly + 3:.1f}" '
                         f'font-size="9" fill="{color}">'
                         f'{html.escape(_short(t))}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def small_multiples(title: str, slate: dict) -> str:
    """Per-title weekly trajectory sparklines in one SVG (2 columns).

    Each panel is scaled to its own peak so the shape stays visible;
    the peak value is labelled. slate: {title: [(week, hours), ...]}."""
    titles = sorted(slate, key=lambda t: slate[t][0][0])
    cols, rows = 2, (len(titles) + 1) // 2
    pw, ph, gap = 366, 50, 8
    total_w, total_h = 16 + cols * (pw + gap), 30 + rows * (ph + gap)
    parts = _svg_open(title, width=total_w, height=total_h)
    for idx, t in enumerate(titles):
        run = sorted(slate[t])
        hours = [h for _, h in run]
        peak = max(hours)
        col, row = idx % cols, idx // cols
        x0 = 8 + col * (pw + gap)
        y0 = 30 + row * (ph + gap)
        parts.append(f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" '
                     f'fill="none" stroke="#e0e0e0"/>')
        parts.append(f'<text x="{x0 + 6}" y="{y0 + 13}" font-size="10" '
                     f'font-weight="bold">{html.escape(_short(t))}</text>')
        parts.append(f'<text x="{x0 + pw - 6}" y="{y0 + 13}" '
                     f'text-anchor="end" font-size="9" fill="#555">'
                     f'peak {_fmt_millions(peak)}</text>')
        color = PALETTE20[idx % len(PALETTE20)]
        plot_y0, plot_h = y0 + 18, ph - 24
        if len(hours) == 1:
            parts.append(f'<circle cx="{x0 + 6}" cy="{y0 + 18}" '
                         f'r="3" fill="{color}"/>')
        else:
            pts = " ".join(
                f"{x0 + 6 + (pw - 12) * i / (len(hours) - 1):.1f},"
                f"{plot_y0 + plot_h - plot_h * v / peak:.1f}"
                for i, v in enumerate(hours))
            parts.append(f'<polyline points="{pts}" fill="none" '
                         f'stroke="{color}" stroke-width="1.5"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def connected_scatter(title: str, per_title: list) -> str:
    """Forecast vs actual, one-step-ahead last-week hours.

    Each title contributes three points (naive, shape, decay models)
    at the same actual value, connected in model order; points are
    coloured by title. per_title rows carry title, actual_last_week,
    naive_pred, shape_pred, decay_pred, last_week."""
    parts = _svg_open(title)
    xs = [r["actual_last_week"] for r in per_title]
    ys = [r[k] for r in per_title for k in
          ("naive_pred", "shape_pred", "decay_pred")]
    lim = max(max(xs), max(ys)) * 1.08 or 1.0
    iw, ih = W - PAD["l"] - PAD["r"], H - PAD["t"] - PAD["b"]

    def sx(v):
        return PAD["l"] + iw * v / lim

    def sy(v):
        return PAD["t"] + ih - ih * v / lim
    for i in range(5):
        val = lim * i / 4
        parts.append(f'<line x1="{PAD["l"]}" y1="{sy(val):.1f}" '
                     f'x2="{W - PAD["r"]}" y2="{sy(val):.1f}" '
                     f'stroke="#e0e0e0"/>')
        parts.append(f'<text x="{PAD["l"] - 6}" y="{sy(val) + 4:.1f}" '
                     f'text-anchor="end" font-size="10" fill="#555">'
                     f'{_fmt_millions(val)}</text>')
        parts.append(f'<line x1="{sx(val):.1f}" y1="{PAD["t"]}" '
                     f'x2="{sx(val):.1f}" y2="{PAD["t"] + ih}" '
                     f'stroke="#e0e0e0"/>')
        parts.append(f'<text x="{sx(val):.1f}" y="{PAD["t"] + ih + 14}" '
                     f'text-anchor="middle" font-size="10" fill="#555">'
                     f'{_fmt_millions(val)}</text>')
    parts.append(f'<text x="14" y="{PAD["t"] + ih // 2}" font-size="10" '
                 f'fill="#555" transform="rotate(-90 14 {PAD["t"] + ih // 2})" '
                 f'text-anchor="middle">predicted hours</text>')
    parts.append(f'<text x="{PAD["l"] + iw // 2}" y="{H - 22}" '
                 f'text-anchor="middle" font-size="10" fill="#555">'
                 f'actual last-week hours</text>')
    # y = x reference line
    parts.append(f'<line x1="{sx(0):.1f}" y1="{sy(0):.1f}" '
                 f'x2="{sx(lim):.1f}" y2="{sy(lim):.1f}" stroke="#999" '
                 f'stroke-dasharray="5,4"/>')
    models = [("naive_pred", "square"), ("shape_pred", "triangle"),
              ("decay_pred", "circle")]
    for k, r in enumerate(per_title):
        color = PALETTE20[k % len(PALETTE20)]
        pts = []
        for key, _shape in models:
            pts.append((sx(r["actual_last_week"]), sy(r[key])))
        joined = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<polyline points="{joined}" fill="none" '
                     f'stroke="{color}" stroke-width="1" opacity="0.6"/>')
        for (key, shape), (x, y) in zip(models, pts):
            tip = (f"{r['title']} — week {r['last_week']} — {key[:-5]}: "
                   f"actual {_fmt_millions(r['actual_last_week'])}, "
                   f"predicted {_fmt_millions(r[key])}")
            if shape == "circle":
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" '
                             f'fill="{color}" data-tip="{html.escape(tip)}"/>')
            elif shape == "square":
                parts.append(f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" '
                             f'width="8" height="8" fill="{color}" '
                             f'data-tip="{html.escape(tip)}"/>')
            else:
                parts.append(f'<polygon points="{x:.1f},{y - 5:.1f} '
                             f'{x - 5:.1f},{y + 4:.1f} {x + 5:.1f},{y + 4:.1f}" '
                             f'fill="{color}" data-tip="{html.escape(tip)}"/>')
    # shape legend
    lx = PAD["l"]
    for key, shape, lab in [("decay_pred", "circle", "decay"),
                            ("naive_pred", "square", "naive"),
                            ("shape_pred", "triangle", "shape")]:
        if shape == "circle":
            parts.append(f'<circle cx="{lx + 5}" cy="{H - 9}" r="4" '
                         f'fill="#555"/>')
        elif shape == "square":
            parts.append(f'<rect x="{lx}" y="{H - 14}" width="9" '
                         f'height="9" fill="#555"/>')
        else:
            parts.append(f'<polygon points="{lx + 5},{H - 14} {lx},{H - 5} '
                         f'{lx + 10},{H - 5}" fill="#555"/>')
        parts.append(f'<text x="{lx + 14}" y="{H - 5}" font-size="11">'
                     f'{lab}</text>')
        lx += 14 + len(lab) * 6.5 + 22
    parts.append("</svg>")
    return "\n".join(parts)


def waterfall_chart(title: str, scenarios: dict) -> str:
    """Bridge: how each scenario moves total slate hours vs baseline.

    The baseline bar is drawn from the axis floor; each scenario is a
    floating bar anchored at the baseline level, extending by its
    delta. Scenarios are alternatives, not cumulative steps, so no
    final total bar is drawn. The y axis is zoomed to the deltas and
    labelled in billions so the truncation is visible."""
    base = scenarios["baseline"]["summary"]["total_hours"]
    others = [(n, s["summary"]["total_hours"] - base,
               s["summary"]["total_hours"])
              for n, s in scenarios.items() if n != "baseline"]
    labels = ["Baseline"] + [n.replace("_", " ") for n, _, _ in others]
    deltas = [d for _, d, _ in others]
    totals = [t for _, _, t in others]
    lo = min(base + min(0.0, min(deltas)), base)
    hi = max(base + max(0.0, max(deltas)), base)
    pad = (hi - lo) * 0.12 or 1.0
    y_min, y_max = lo - pad, hi + pad
    parts = _svg_open(title)
    iw, ih = W - PAD["l"] - PAD["r"], H - PAD["t"] - PAD["b"]

    def sy(v):
        return PAD["t"] + ih - ih * (v - y_min) / (y_max - y_min)
    for i in range(5):
        val = y_min + (y_max - y_min) * i / 4
        parts.append(f'<line x1="{PAD["l"]}" y1="{sy(val):.1f}" '
                     f'x2="{W - PAD["r"]}" y2="{sy(val):.1f}" '
                     f'stroke="#e0e0e0"/>')
        parts.append(f'<text x="{PAD["l"] - 6}" y="{sy(val) + 4:.1f}" '
                     f'text-anchor="end" font-size="10" fill="#555">'
                     f'{_fmt_billions(val)}</text>')
    bw = iw / (len(labels)) * 0.55
    for i, lab in enumerate(labels):
        x = PAD["l"] + iw * (i + 0.5) / len(labels) - bw / 2
        if i == 0:
            y_top, y_bot = sy(base), sy(y_min)
            parts.append(f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bw:.1f}" '
                         f'height="{y_bot - y_top:.1f}" fill="{COLORS[0]}"/>')
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{y_top - 5:.1f}" '
                         f'text-anchor="middle" font-size="11">'
                         f'{_fmt_billions(base)}</text>')
        else:
            d, total = deltas[i - 1], totals[i - 1]
            top, bot = (sy(base + d), sy(base)) if d >= 0 else \
                (sy(base), sy(base + d))
            color = COLORS[2] if d > 0 else COLORS[1] if d < 0 else "#999"
            if d == 0:
                parts.append(f'<line x1="{x:.1f}" y1="{sy(base):.1f}" '
                             f'x2="{x + bw:.1f}" y2="{sy(base):.1f}" '
                             f'stroke="{color}" stroke-width="3"/>')
            else:
                parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" '
                             f'width="{bw:.1f}" height="{bot - top:.1f}" '
                             f'fill="{color}"/>')
            ly = top - 5 if d >= 0 else bot + 14
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{ly:.1f}" '
                         f'text-anchor="middle" font-size="11">'
                         f'{d / 1e6:+,.1f}M</text>')
            parts.append(f'<text x="{x + bw / 2:.1f}" '
                         f'y="{PAD["t"] + ih + 28}" text-anchor="middle" '
                         f'font-size="9" fill="#555">'
                         f'total {_fmt_billions(total)}</text>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{PAD["t"] + ih + 14}" '
                     f'text-anchor="middle" font-size="10" fill="#555">'
                     f'{html.escape(lab)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def shape_chart(title: str, shape_series: dict) -> str:
    """First-run shapes: every evaluation title's own decay curve in
    light grey behind the bold median shape, plus three named titles
    in colour. Values are weekly hours as a fraction of each title's
    own full-run peak."""
    median = shape_series["median_shape"]
    all_titles = shape_series.get("all_titles", {})
    named = shape_series.get("titles", {})
    xs = [f"wk {i}" for i in range(len(median))]
    parts = _svg_open(title)
    grid, iw, ih = _axes(xs, 1.08, "fraction of peak",
                         lambda v: f"{v:.1f}")
    parts += grid
    n = len(xs)

    def xy(i, v):
        return (PAD["l"] + iw * i / max(n - 1, 1),
                PAD["t"] + ih - ih * v / 1.08)
    for _t, fracs in all_titles.items():
        pts = " ".join(f"{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}"
                       for i, v in enumerate(fracs))
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="#cccccc" stroke-width="1"/>')
    med = [median[i] for i in sorted(median)]
    pts = " ".join(f"{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}"
                   for i, v in enumerate(med))
    parts.append(f'<polyline points="{pts}" fill="none" '
                 f'stroke="{COLORS[0]}" stroke-width="2.5"/>')
    legend = [("median shape", COLORS[0])]
    if all_titles:
        legend.append((f"individual titles ({len(all_titles)})", "#bbbbbb"))
    for k, (name, fracs) in enumerate(named.items()):
        color = COLORS[(k + 1) % len(COLORS)]
        pts = " ".join(f"{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}"
                       for i, v in enumerate(fracs))
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
        legend.append((_short(name), color))
    lx = PAD["l"]
    for name, color in legend:
        parts.append(f'<rect x="{lx}" y="{H - 14}" width="10" height="10" '
                     f'fill="{color}"/>')
        parts.append(f'<text x="{lx + 14}" y="{H - 5}" font-size="11">'
                     f'{html.escape(name)}</text>')
        lx += 14 + len(name) * 6.5 + 22
    parts.append("</svg>")
    return "\n".join(parts)


def _blue_ramp(t: float) -> str:
    """Light #deebf7 -> dark #08519c sequential blue ramp."""
    lo, hi = (222, 235, 247), (8, 81, 156)
    r = round(lo[0] + (hi[0] - lo[0]) * t)
    g = round(lo[1] + (hi[1] - lo[1]) * t)
    b = round(lo[2] + (hi[2] - lo[2]) * t)
    return f"rgb({r},{g},{b})"


def heatmap_chart(title: str, slate: dict) -> str:
    """Titles x weeks heatmap of hours viewed (first runs).

    Columns are every calendar week in the slate span; blank cells mean
    the title was not in the Top 10 that week. Colour is log-scaled."""
    titles = sorted(slate, key=lambda t: slate[t][0][0])
    all_weeks = sorted({w for run in slate.values() for w, _ in run})
    weeks = pd.date_range(all_weeks[0], all_weeks[-1], freq="7D")
    n = len(weeks)
    vals = {(t, w): h for t, run in slate.items() for w, h in run}
    all_h = [h for h in vals.values() if h > 0]
    log_min, log_max = math.log10(min(all_h)), math.log10(max(all_h))
    label_w = 215
    x0 = label_w
    cw = (W - PAD["r"] - x0) / n
    rh, y0 = 19, 38
    total_h = y0 + len(titles) * rh + 26
    parts = _svg_open(title, height=total_h)
    for j in range(0, n, 12):
        x = x0 + cw * j
        parts.append(f'<text x="{x:.1f}" y="30" font-size="9" fill="#555">'
                     f'{weeks[j].strftime("%Y-%m-%d")}</text>')
    for ri, t in enumerate(titles):
        y = y0 + ri * rh
        parts.append(f'<text x="{x0 - 6}" y="{y + rh / 2 + 3:.1f}" '
                     f'text-anchor="end" font-size="10">'
                     f'{html.escape(_short(t))}</text>')
        for j, w in enumerate(weeks):
            h = vals.get((t, pd.Timestamp(w)))
            x = x0 + cw * j
            if h is None:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{cw:.1f}" '
                             f'height="{rh - 1}" fill="#f0f0f0"/>')
            else:
                tt = (math.log10(h) - log_min) / (log_max - log_min)
                tip = (f"{t} — {pd.Timestamp(w).date()} — "
                       f"{_fmt_millions(h)} hours")
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{cw:.1f}" '
                             f'height="{rh - 1}" fill="{_blue_ramp(tt)}" '
                             f'data-tip="{html.escape(tip)}"/>')
    # colour legend
    ly = total_h - 12
    parts.append(f'<text x="{x0}" y="{ly + 3}" font-size="9" fill="#555">'
                 f'log scale: {_fmt_millions(min(all_h))}</text>')
    gx0, gw = x0 + 110, 200
    for i in range(40):
        parts.append(f'<rect x="{gx0 + gw * i / 40:.1f}" y="{ly - 7}" '
                     f'width="{gw / 40 + 0.5:.1f}" height="9" '
                     f'fill="{_blue_ramp(i / 39)}"/>')
    parts.append(f'<text x="{gx0 + gw + 6}" y="{ly + 3}" font-size="9" '
                 f'fill="#555">{_fmt_millions(max(all_h))}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _treemap_layout(items, x, y, w, h, horizontal=True):
    """Slice-and-dice treemap: split the group closest to half, recurse.
    items: [(label, value)] sorted desc. Returns [(label, value, x, y, w, h)]."""
    if len(items) == 1:
        return [(items[0][0], items[0][1], x, y, w, h)]
    total = sum(v for _, v in items)
    best_i, best_diff, acc = 1, None, 0.0
    for i in range(1, len(items)):
        acc += items[i - 1][1]
        diff = abs(acc - total / 2)
        if best_diff is None or diff < best_diff:
            best_diff, best_i = diff, i
    left, right = items[:best_i], items[best_i:]
    frac = sum(v for _, v in left) / total
    if horizontal:
        w1 = w * frac
        return (_treemap_layout(left, x, y, w1, h, not horizontal)
                + _treemap_layout(right, x + w1, y, w - w1, h,
                                  not horizontal))
    h1 = h * frac
    return (_treemap_layout(left, x, y, w, h1, not horizontal)
            + _treemap_layout(right, x, y + h1, w, h - h1, not horizontal))


def _text_on_fill(hex_color: str) -> str:
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#222222" if lum > 0.55 else "#ffffff"


def treemap_chart(title: str, per_title_hours: dict) -> str:
    """Slate composition as a treemap: rectangle area = share of the
    slate's total hours."""
    total = sum(per_title_hours.values())
    items = sorted(((t, v / total) for t, v in per_title_hours.items()),
                   key=lambda kv: -kv[1])
    height = 340
    rects = _treemap_layout(items, 8, 30, W - 16, height - 38,
                            horizontal=False)
    parts = _svg_open(title, height=height)
    for k, (t, share, x, y, w, h) in enumerate(rects):
        color = PALETTE20[k % len(PALETTE20)]
        tip = (f"{t} — {share * 100:.1f}% of slate "
               f"({_fmt_millions(share * total)} hours)")
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                     f'height="{h:.1f}" fill="{color}" stroke="#ffffff" '
                     f'stroke-width="1" data-tip="{html.escape(tip)}"/>')
        if w >= 64 and h >= 34:
            tc = _text_on_fill(color)
            parts.append(f'<text x="{x + 6:.1f}" y="{y + 16:.1f}" '
                         f'font-size="10" font-weight="bold" fill="{tc}">'
                         f'{html.escape(_short(t))}</text>')
            parts.append(f'<text x="{x + 6:.1f}" y="{y + 30:.1f}" '
                         f'font-size="10" fill="{tc}">'
                         f'{share * 100:.1f}%</text>')
        elif w >= 60 and h >= 16:
            tc = _text_on_fill(color)
            parts.append(f'<text x="{x + 6:.1f}" y="{y + h / 2 + 3:.1f}" '
                         f'font-size="9" fill="{tc}">'
                         f'{html.escape(_short(t))} {share * 100:.1f}%'
                         f'</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build_report(results: dict, weekly_by_scenario: dict,
                 shape_series: dict, scorecard: pd.DataFrame,
                 scenario_meta: dict, chart_data: dict | None = None) -> str:
    chart_data = chart_data or {}
    slate = chart_data.get("slate")
    slate_weekly = chart_data.get("slate_weekly_first")
    scen_names = list(weekly_by_scenario.keys())
    # Chart 2: bump chart of Top 10 ranks
    chart_bump = ""
    if slate_weekly is not None and len(slate_weekly):
        chart_bump = bump_chart("Top 10 rank by week — slate titles "
                                "(rank 1 at top; hover a point)",
                                slate_weekly)
    # Chart 3: small multiples of per-title trajectories
    chart_multiples = ""
    if slate:
        chart_multiples = small_multiples(
            "Weekly trajectory per title — first runs (each panel scaled "
            "to its own peak)", slate)
    # Chart 4: connected scatter, forecast vs actual
    chart_scatter = ""
    per_title = results.get("forecast", {}).get("per_title") or []
    if per_title:
        chart_scatter = connected_scatter(
            "Forecast vs actual — one-step-ahead last-week hours "
            "(each title's naive / shape / decay predictions connected; "
            "hover a point)", per_title)
    # Charts 5-6: scenario totals + peak-week load (bars, as before)
    totals = [results["scenarios"][n]["summary"]["total_hours"]
              for n in scen_names]
    peaks = [results["scenarios"][n]["summary"]["peak_week_hours"]
             for n in scen_names]
    chart_totals = bar_chart("Slate total hours by scenario", scen_names,
                             totals, "total hours",
                             lambda v: _fmt_millions(v))
    chart_peaks = bar_chart("Peak-week load by scenario", scen_names, peaks,
                            "hours in peak week", lambda v: _fmt_millions(v))
    # Chart 7: waterfall / bridge of scenario deltas vs baseline
    chart_waterfall = waterfall_chart(
        "Bridge: how each scenario moves slate total hours vs baseline "
        "(floating bars are alternatives, not cumulative steps)",
        results["scenarios"])
    # Chart 8: first-run shapes, individual curves behind the median
    chart_shape = shape_chart(
        "First-run shape: weekly hours as fraction of peak "
        "(grey: each title's own curve; blue: median)", shape_series)
    # Chart 9: titles x weeks heatmap
    chart_heatmap = ""
    if slate:
        chart_heatmap = heatmap_chart(
            "Weekly hours viewed by title and week (log colour scale; "
            "blank = not in the Top 10 that week)", slate)
    # Chart 10: slate composition treemap
    chart_treemap = ""
    per_title_hours = (results.get("scenarios", {}).get("baseline", {})
                       .get("per_title_hours"))
    if per_title_hours:
        chart_treemap = treemap_chart(
            "Slate composition — share of total hours by title "
            "(area = share)", per_title_hours)

    def table(df, cols, fmt_map=None):
        fmt_map = fmt_map or {}
        head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
        rows = []
        for _, r in df.iterrows():
            cells = []
            for c in cols:
                v = r[c]
                if c in fmt_map:
                    v = fmt_map[c](v)
                cells.append(f"<td>{html.escape(str(v))}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return ("<table border='1' cellpadding='5' cellspacing='0'>"
                f"<tr>{head}</tr>" + "".join(rows) + "</table>")

    sc = scorecard.copy()
    sc["peak_hours"] = sc["peak_hours"].map(lambda v: f"{v / 1e6:,.1f}M")
    sc["actual_first4w_hours"] = sc["actual_first4w_hours"].map(
        lambda v: f"{v / 1e6:,.1f}M")
    sc["forecast_first4w_hours"] = sc["forecast_first4w_hours"].map(
        lambda v: f"{v / 1e6:,.1f}M")
    sc["actual_vs_forecast"] = sc["actual_vs_forecast"].map(
        lambda v: f"{v:.2f}" if pd.notna(v) else "n/a")
    score_table = table(sc, ["title", "release_week", "run_weeks",
                             "peak_hours", "actual_first4w_hours",
                             "forecast_first4w_hours", "actual_vs_forecast",
                             "status"])

    scen_rows = []
    for n in scen_names:
        s = results["scenarios"][n]["summary"]
        scen_rows.append({
            "scenario": n,
            "total_hours": f"{s['total_hours'] / 1e9:.3f}B "
                           f"({s['total_hours_delta_pct']:+.2f}%)",
            "peak_week": s["peak_week"],
            "peak_week_hours": f"{s['peak_week_hours'] / 1e6:,.1f}M "
                               f"({s['peak_week_hours_delta_pct']:+.2f}%)",
            "what_changed": scenario_meta.get(n, ""),
        })
    scen_df = pd.DataFrame(scen_rows)
    scen_table = table(scen_df, ["scenario", "total_hours", "peak_week",
                                 "peak_week_hours", "what_changed"])

    f = results["forecast"]
    sections = []
    if chart_scatter:
        sections.append("<h2>Forecast vs actual</h2>\n" + chart_scatter)
    if chart_bump:
        sections.append("<h2>Rank movement</h2>\n" + chart_bump)
    if chart_multiples:
        sections.append("<h2>Title trajectories</h2>\n" + chart_multiples)
    if chart_heatmap:
        sections.append("<h2>Hours viewed heatmap</h2>\n" + chart_heatmap)
    sections.append("<h2>Scenario totals</h2>\n" + chart_totals + "\n"
                    + chart_peaks + "\n" + chart_waterfall + "\n" + scen_table)
    sections.append("<h2>First-run shapes</h2>\n" + chart_shape)
    if chart_treemap:
        sections.append("<h2>Slate composition</h2>\n" + chart_treemap)
    sections.append("<h2>Scorecard — first 4 weeks vs shape-model "
                    "forecast</h2>\n<p>Thresholds: &gt;1.20 ahead of plan; "
                    "0.80–1.20 on track; 0.60–0.80 at risk; &lt;0.60 below "
                    "plan; 1-week runs are insufficient data.</p>\n"
                    + score_table)
    body = "\n".join(sections)
    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Slate Scenario Planner — report</title>
<style>body{{font-family:Arial,sans-serif;max-width:900px;margin:auto;padding:20px}}
table{{border-collapse:collapse;font-size:13px}}th{{background:#eee}}
#tooltip{{position:fixed;display:none;background:rgba(20,20,20,.9);color:#fff;
padding:5px 8px;border-radius:4px;font-size:12px;pointer-events:none;
z-index:99;max-width:320px}}</style>
</head><body>
<div id="tooltip"></div>
<h1>Content-Slate Scenario Planner</h1>
<p>Personal project on public data. Slate: {results["slate"]["n_titles"]} new
animated films, first Top 10 runs starting {results["slate"]["first_week"]} to
{results["slate"]["last_week"]}. Data: Netflix Top 10 global weekly data
(official, top10.netflix.com) + IMDb public datasets. See README for sources,
definitions, and limitations. Charts are interactive where noted: hover
points for values.</p>
<h2>Forecast check (one-step-ahead, {f["n_titles"]} titles, first runs &ge; 4 weeks)</h2>
<p>Decay-curve model MAPE: <b>{f["mape_decay_pct"]:.1f}%</b>; naive (repeat last
week) MAPE: <b>{f["mape_naive_pct"]:.1f}%</b>; median-shape model MAPE:
<b>{f["mape_shape_pct"]:.1f}%</b>. Decay fell back to naive on
{f["n_decay_fallbacks"]} of {f["n_titles"]} titles (too few post-peak points
to fit). Pooled post-peak retention ratio: {f["pooled_retention_all"]:.3f}.</p>
{body}
<p><i>Limitations: Top 10 data covers only titles that reached the Top 10;
hours viewed are Netflix-reported weekly aggregates. The collision penalty
(5%) and the budget-shift effect (+/-10% of a run) are stated assumptions,
not measured causal effects. Forecasts are illustrative, not production
predictions.</i></p>
{TOOLTIP_JS}</body></html>"""
    return html_doc
