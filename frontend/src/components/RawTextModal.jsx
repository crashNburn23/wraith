import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { articles as articlesApi } from "../lib/api";
import { Spinner } from "./ui";
import { buildHighlights, buildRanges, renderWithRanges } from "./HighlightedText";

const BRAND = { hex: "#5558D4", dim: "rgba(85,88,212,0.06)", border: "rgba(85,88,212,0.28)" };

const LEGEND_ITEMS = [
  { label: "IOC",   cls: "bg-rose-500/25 text-rose-200",        check: a => (a.iocs?.length || 0) > 0 },
  { label: "CVE",   cls: "bg-orange-500/30 text-orange-200",    check: a => (a.cve_mentions?.length || 0) > 0 },
  { label: "Actor", cls: "bg-violet-500/30 text-violet-200",    check: a => (a.article_actors?.length || 0) > 0 },
  { label: "TTP",   cls: "bg-emerald-500/25 text-emerald-200",  check: a => (a.ttp_tags?.length || 0) > 0 },
];

// Render text as prose paragraphs with inline entity highlights.
// Splits on blank lines, collapses whitespace within each paragraph.
function ParagraphText({ text, highlights }) {
  const paragraphs = text
    .split(/\n{2,}/)
    .map(p => p.replace(/[ \t]+/g, " ").replace(/\n/g, " ").trim())
    .filter(p => p.length > 0);

  if (paragraphs.length === 0) {
    return <p className="text-sm text-slate-600 italic font-mono">Empty text.</p>;
  }

  return (
    <div className="space-y-3">
      {paragraphs.map((para, i) => {
        const ranges = buildRanges(para, highlights);
        const parts = renderWithRanges(para, ranges);
        return (
          <p key={i} className="text-sm text-slate-300 leading-relaxed">
            {parts.map((part, j) =>
              part.style
                ? <mark key={j} className={`not-italic ${part.style}`}>{part.text}</mark>
                : <span key={j}>{part.text}</span>
            )}
          </p>
        );
      })}
    </div>
  );
}

export default function RawTextModal({ articleId, onClose }) {
  const { data: article, isLoading } = useQuery({
    queryKey: ["article", articleId],
    queryFn: () => articlesApi.get(articleId),
    enabled: !!articleId,
  });

  useEffect(() => {
    const h = (e) => {
      if (e.key === "Escape" || e.key === "e") { e.preventDefault(); onClose(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const entityCtx = article
    ? {
        iocs: article.iocs,
        cve_mentions: article.cve_mentions,
        actors: article.article_actors?.map(a => ({ name: a.actor_name, ...a })),
        ttps: article.ttp_tags,
      }
    : {};
  const highlights = buildHighlights(entityCtx, null);
  const visibleLegend = article ? LEGEND_ITEMS.filter(l => l.check(article)) : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm" />

      <div
        className="relative w-full max-w-3xl max-h-[90vh] flex flex-col bg-navy-800 rounded-2xl overflow-hidden"
        style={{ border: `1px solid ${BRAND.border}`, boxShadow: "0 25px 50px rgba(0,0,0,0.8)" }}
      >
        {/* Top accent line */}
        <div style={{ height: 2, background: `linear-gradient(90deg, ${BRAND.hex}, transparent)`, flexShrink: 0 }} />

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-navy-border flex-shrink-0">
          <span
            className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded font-mono flex-shrink-0"
            style={{ color: BRAND.hex, background: BRAND.dim, border: `1px solid ${BRAND.border}` }}
          >
            RAW TEXT
          </span>
          <h2 className="text-sm font-semibold text-slate-300 truncate flex-1 font-mono">
            {article?.title || (isLoading ? "Loading…" : "—")}
          </h2>
          <kbd className="text-[10px] font-mono text-slate-600 bg-navy-900 border border-navy-border rounded px-1.5 py-0.5 hidden sm:inline">esc</kbd>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 transition-colors p-1 rounded-lg hover:bg-navy-700"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && (
            <div className="flex justify-center py-10"><Spinner /></div>
          )}

          {!isLoading && !article?.scraped_text && (
            <p className="text-sm text-slate-600 italic font-mono py-4">
              No scraped text available for this article.
            </p>
          )}

          {!isLoading && article?.scraped_text && (
            <div className="space-y-4">
              {/* Legend */}
              {visibleLegend.length > 0 && (
                <div className="flex items-center gap-3 flex-wrap pb-2 border-b border-navy-border/50">
                  <span className="text-[10px] text-slate-600 font-mono">highlights:</span>
                  {visibleLegend.map(({ label, cls }) => (
                    <mark key={label} className={`not-italic text-[10px] font-mono px-1.5 py-0.5 rounded-sm ${cls}`}>
                      {label}
                    </mark>
                  ))}
                  <span className="text-[10px] text-slate-700 font-mono ml-auto">
                    {(article.scraped_text.length / 1000).toFixed(1)}k chars
                  </span>
                </div>
              )}

              <ParagraphText text={article.scraped_text} highlights={highlights} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
