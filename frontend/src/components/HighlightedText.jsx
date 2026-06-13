import { useState } from "react";

// Color class per entity type
const TYPE_STYLE = {
  primary: "bg-yellow-400/40 text-yellow-100 ring-1 ring-yellow-400/60 rounded-sm px-0.5",
  ioc_ip:     "bg-rose-500/25 text-rose-200 rounded-sm px-0.5",
  ioc_domain: "bg-pink-500/25 text-pink-200 rounded-sm px-0.5",
  ioc_hash:   "bg-amber-500/25 text-amber-200 rounded-sm px-0.5",
  ioc_url:    "bg-amber-500/20 text-amber-200 rounded-sm px-0.5",
  ioc_email:  "bg-orange-500/25 text-orange-200 rounded-sm px-0.5",
  cve:        "bg-orange-500/30 text-orange-200 rounded-sm px-0.5",
  actor:      "bg-violet-500/30 text-violet-200 rounded-sm px-0.5",
  ttp:        "bg-emerald-500/25 text-emerald-200 rounded-sm px-0.5",
};

function iocStyle(iocType) {
  return TYPE_STYLE[`ioc_${iocType}`] || TYPE_STYLE.ioc_ip;
}

export function buildRanges(text, highlights) {
  const lower = text.toLowerCase();
  const ranges = [];

  for (const h of highlights) {
    if (!h.value || h.value.length < 2) continue;
    const vl = h.value.toLowerCase();
    let pos = 0;
    while (pos < lower.length) {
      const idx = lower.indexOf(vl, pos);
      if (idx === -1) break;
      ranges.push({ start: idx, end: idx + h.value.length, style: h.style, isPrimary: h.isPrimary });
      pos = idx + 1;
    }
  }

  // Sort: primary first within same start, then by position
  ranges.sort((a, b) => a.start - b.start || (b.isPrimary ? 1 : -1));

  // Remove overlapping — keep whichever started first (primary wins at same start)
  const merged = [];
  let lastEnd = 0;
  for (const r of ranges) {
    if (r.start >= lastEnd) {
      merged.push(r);
      lastEnd = r.end;
    }
  }
  return merged;
}

export function renderWithRanges(text, ranges) {
  const parts = [];
  let cursor = 0;
  for (const r of ranges) {
    if (r.start > cursor) parts.push({ text: text.slice(cursor, r.start), style: null });
    parts.push({ text: text.slice(r.start, r.end), style: r.style });
    cursor = r.end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), style: null });
  return parts;
}

// Build highlight descriptors from article entity lists + a primary value
export function buildHighlights(entities, primaryValue, _primaryStyle = "primary") {
  const hl = [];

  if (primaryValue) {
    hl.push({ value: primaryValue, style: TYPE_STYLE.primary, isPrimary: true });
  }

  for (const ioc of entities?.iocs || []) {
    if (ioc.value !== primaryValue)
      hl.push({ value: ioc.value, style: iocStyle(ioc.ioc_type), isPrimary: false });
  }
  for (const cve of entities?.cve_mentions || []) {
    if (cve.cve_id !== primaryValue)
      hl.push({ value: cve.cve_id, style: TYPE_STYLE.cve, isPrimary: false });
  }
  for (const actor of entities?.actors || []) {
    if (actor.name !== primaryValue)
      hl.push({ value: actor.name, style: TYPE_STYLE.actor, isPrimary: false });
  }
  for (const ttp of entities?.ttps || []) {
    if (ttp.technique_id !== primaryValue)
      hl.push({ value: ttp.technique_id, style: TYPE_STYLE.ttp, isPrimary: false });
  }
  return hl;
}

const EXCERPT_RADIUS = 450;

export default function HighlightedText({ text, highlights, primaryValue, className = "" }) {
  const [showFull, setShowFull] = useState(false);

  if (!text) return <p className="text-slate-600 text-xs italic">No scraped text available.</p>;

  let display = text;
  let prefixEllipsis = false;
  let suffixEllipsis = false;

  if (!showFull) {
    const needle = primaryValue?.toLowerCase();
    const idx = needle ? text.toLowerCase().indexOf(needle) : -1;

    if (text.length > EXCERPT_RADIUS * 2) {
      const center = idx !== -1 ? idx : 0;
      const start = Math.max(0, center - EXCERPT_RADIUS);
      const end = Math.min(text.length, center + EXCERPT_RADIUS);
      display = text.slice(start, end);
      prefixEllipsis = start > 0;
      suffixEllipsis = end < text.length;
    }
  }

  const ranges = buildRanges(display, highlights);
  const parts = renderWithRanges(display, ranges);

  return (
    <div className={className}>
      <pre className="text-xs text-slate-400 whitespace-pre-wrap leading-relaxed font-mono break-words">
        {prefixEllipsis && <span className="text-slate-600">…</span>}
        {parts.map((p, i) =>
          p.style
            ? <mark key={i} className={`not-italic ${p.style}`}>{p.text}</mark>
            : <span key={i}>{p.text}</span>
        )}
        {suffixEllipsis && <span className="text-slate-600">…</span>}
      </pre>

      {(text.length > EXCERPT_RADIUS * 2) && (
        <button
          onClick={() => setShowFull(v => !v)}
          className="mt-2 text-xs text-brand-400 hover:text-brand-300"
        >
          {showFull ? "Show excerpt" : `Show full text (${(text.length / 1000).toFixed(1)}k chars)`}
        </button>
      )}
    </div>
  );
}
