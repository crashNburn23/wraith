import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { bulletin as bulletinApi, feedback as feedbackApi } from "../lib/api";
import { Button, Spinner, EmptyState } from "../components/ui";
import { ScoreBreakdownPanel } from "../components/ScoreBreakdown";
import { timeAgo, categoryColor, severityBg } from "../lib/utils";

const PAGE_SIZE = 25;

// ─── Cyberpunk color tiers (muted) ───────────────────────────────────────────

function cyberColor(computedScore) {
  if (computedScore >= 0.7) return {
    hex: "#C02040", dim: "rgba(192,32,64,0.06)",  border: "rgba(192,32,64,0.35)", label: "CRITICAL",
  };
  if (computedScore >= 0.5) return {
    hex: "#B85018", dim: "rgba(184,80,24,0.06)",  border: "rgba(184,80,24,0.35)", label: "HIGH",
  };
  if (computedScore >= 0.3) return {
    hex: "#7722AA", dim: "rgba(119,34,170,0.06)", border: "rgba(119,34,170,0.30)", label: "MEDIUM",
  };
  return {
    hex: "#0088A8", dim: "rgba(0,136,168,0.05)",  border: "rgba(0,136,168,0.28)", label: "LOW",
  };
}

// ─── Hidden articles (localStorage) ──────────────────────────────────────────

function loadHidden() {
  try { return new Set(JSON.parse(localStorage.getItem("cti-hidden-articles") || "[]")); }
  catch { return new Set(); }
}

function saveHidden(set) {
  localStorage.setItem("cti-hidden-articles", JSON.stringify([...set]));
}

// ─── Score badge ──────────────────────────────────────────────────────────────

function CyberScoreBadge({ score, expanded, onToggle }) {
  const val = Math.round(score.computed_score * 100);
  const c = cyberColor(score.computed_score);
  return (
    <button
      onClick={onToggle}
      title="Click to expand score breakdown"
      style={{
        position: "absolute", top: 0, right: 0, width: 72,
        display: "flex", flexDirection: "column", alignItems: "center",
        padding: "10px 8px 11px",
        fontFamily: "'JetBrains Mono','Fira Code',monospace",
        color: c.hex,
        background: `linear-gradient(160deg,#03060d 0%,${c.dim} 100%)`,
        borderLeft: `1px solid ${c.border}`, borderBottom: `1px solid ${c.border}`,
        clipPath: "polygon(18px 0%,100% 0%,100% 100%,0% 100%,0% 18px)",
        boxShadow: "inset 0 0 18px rgba(0,0,0,0.8)",
        cursor: "pointer", userSelect: "none", zIndex: 1,
      }}
    >
      <span style={{ fontSize: 8, letterSpacing: "0.22em", opacity: 0.55, marginBottom: 3 }}>REC</span>
      <span style={{ fontSize: 26, fontWeight: 800, lineHeight: 1 }}>{val}</span>
      <span style={{ fontSize: 8, opacity: 0.35, marginTop: 2 }}>/100</span>
      <span style={{ fontSize: 7, letterSpacing: "0.18em", opacity: 0.6, marginTop: 4 }}>{c.label}</span>
      <span style={{ fontSize: 8, opacity: expanded ? 0.8 : 0.35, marginTop: 3 }}>{expanded ? "▲" : "▼"}</span>
    </button>
  );
}

// ─── Feedback buttons ─────────────────────────────────────────────────────────

function FeedbackButtons({ articleId }) {
  const qc = useQueryClient();
  const [rated, setRated] = useState(null);
  const mut = useMutation({
    mutationFn: ({ rating }) => feedbackApi.rate(articleId, rating),
    onSuccess: (_, { rating }) => {
      setRated(rating);
      qc.invalidateQueries({ queryKey: ["bulletin-today"] });
    },
  });
  const btn = (rating, emoji, hoverCls, activeCls) => (
    <button
      onClick={() => { if (rated !== rating) mut.mutate({ rating }); }}
      disabled={mut.isPending}
      className={`px-2 py-1 rounded text-sm transition-colors ${rated === rating ? activeCls : `text-slate-500 hover:${hoverCls}`}`}
      title={rating === 1 ? "Relevant" : "Not relevant"}
    >
      {emoji}
    </button>
  );
  return (
    <div className="flex items-center gap-0.5">
      {btn(1,  "👍", "bg-emerald-900/40 text-emerald-400", "bg-emerald-900/50 text-emerald-300")}
      {btn(-1, "👎", "bg-red-900/40 text-red-400",        "bg-red-900/50 text-red-300")}
    </div>
  );
}

// ─── Read status ──────────────────────────────────────────────────────────────

function ReadStatusCycle({ articleId }) {
  const [status, setStatus] = useState("unread");
  const cycle  = { unread: "acknowledged", acknowledged: "dismissed", dismissed: "unread" };
  const labels = { unread: "○", acknowledged: "✓", dismissed: "—" };
  const colors = { unread: "text-slate-700", acknowledged: "text-emerald-500", dismissed: "text-slate-600" };
  const toggle = () => {
    const next = cycle[status];
    setStatus(next);
    feedbackApi.setReadStatus(articleId, next);
  };
  return (
    <button onClick={toggle} className={`text-sm leading-none ${colors[status]} hover:opacity-70 transition-opacity`} title={`Mark ${cycle[status]}`}>
      {labels[status]}
    </button>
  );
}

// ─── Bulletin card ────────────────────────────────────────────────────────────

function BulletinCard({ item, onHide, dimmed = false }) {
  const { article, score, rank } = item;
  const [expanded, setExpanded] = useState(false);
  const c = cyberColor(score.computed_score);

  return (
    <div
      className="relative overflow-hidden rounded-xl group/card"
      style={{
        background: "#0D1628",
        border: `1px solid ${c.border}`,
        borderLeft: `2px solid ${c.hex}`,
        boxShadow: `inset 2px 0 8px ${c.dim}`,
        transition: "box-shadow 0.2s ease, opacity 0.15s ease",
        opacity: dimmed ? 0.35 : 1,
      }}
    >
      <CyberScoreBadge score={score} expanded={expanded} onToggle={() => setExpanded(v => !v)} />

      <div className="p-4" style={{ paddingRight: 84 }}>
        <div className="flex items-start gap-3">
          {/* Rank + read */}
          <div className="flex flex-col items-center gap-1 flex-shrink-0 w-7 pt-0.5">
            <span className="text-sm font-bold font-mono leading-none" style={{ color: c.hex, opacity: 0.35 }}>
              {rank}
            </span>
            <ReadStatusCycle articleId={article.id} />
          </div>

          <div className="flex-1 min-w-0">
            {/* Meta */}
            <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
              {article.threat_category && (
                <span className={`text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded ${categoryColor(article.threat_category)}`}>
                  {article.threat_category}
                </span>
              )}
              {article.ai_severity_score != null && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${severityBg(article.ai_severity_score)}`}>
                  sev {article.ai_severity_score.toFixed(0)}
                </span>
              )}
              <span className="text-[11px] text-slate-600">{timeAgo(article.published_at)}</span>
            </div>

            {/* Title */}
            <Link to={`/articles/${article.id}`} className="text-sm font-medium text-slate-200 hover:text-white leading-snug line-clamp-2 block mb-2">
              {article.title}
            </Link>

            {/* Actions row */}
            <div className="flex items-center gap-3">
              <FeedbackButtons articleId={article.id} />
              <a href={article.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-slate-600 hover:text-brand-400">
                source ↗
              </a>
              {/* Hide/unhide button */}
              <button
                onClick={() => onHide(article.id)}
                className={`ml-auto text-[10px] font-mono transition-opacity ${
                  dimmed
                    ? "text-brand-500 opacity-100 hover:text-brand-300"
                    : "text-slate-700 opacity-0 group-hover/card:opacity-100 hover:text-slate-400"
                }`}
                title={dimmed ? "Unhide" : "Hide from bulletin"}
              >
                {dimmed ? "[UNHIDE]" : "[HIDE]"}
              </button>
            </div>
          </div>
        </div>

        {/* Score breakdown */}
        {expanded && (
          <div className="mt-3 pt-3" style={{ borderTop: `1px solid ${c.border}` }}>
            <ScoreBreakdownPanel itemId={item.id} score={score} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Bulletin() {
  const qc = useQueryClient();
  const [hidden, setHidden] = useState(loadHidden);
  const [showHidden, setShowHidden] = useState(false);
  const [page, setPage] = useState(0);
  const [focusPrompt, setFocusPrompt] = useState("");
  const [rerankResult, setRerankResult] = useState(null); // { items, prompt }
  const focusRef = useRef(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["bulletin-today"],
    queryFn: bulletinApi.today,
    refetchInterval: 60_000,
  });

  const buildMut = useMutation({
    mutationFn: bulletinApi.build,
    onSuccess: () => {
      setRerankResult(null);
      setTimeout(() => qc.invalidateQueries({ queryKey: ["bulletin-today"] }), 2000);
    },
  });

  const rerankMut = useMutation({
    mutationFn: ({ date, prompt }) => bulletinApi.rerank(date, prompt),
    onSuccess: (result) => { setRerankResult(result); setPage(0); },
  });

  const hideArticle = useCallback((articleId) => {
    setHidden(prev => {
      const next = new Set(prev);
      if (next.has(articleId)) {
        next.delete(articleId);   // toggle: clicking [UNHIDE] removes it
      } else {
        next.add(articleId);
      }
      saveHidden(next);
      return next;
    });
  }, []);

  const unhideAll = useCallback(() => {
    setHidden(new Set());
    saveHidden(new Set());
    setShowHidden(false);
    setPage(0);
  }, []);

  useEffect(() => { setPage(0); }, [showHidden]);

  if (isLoading) return <div className="flex justify-center mt-20"><Spinner size="lg" /></div>;
  if (error)     return <div className="p-8 text-red-400">Error loading bulletin.</div>;

  const allItems    = rerankResult?.items || data?.items || [];
  const hiddenCount = allItems.filter(item => hidden.has(item.article.id)).length;
  const visibleItems = showHidden
    ? allItems
    : allItems.filter(item => !hidden.has(item.article.id));
  const totalPages  = Math.ceil(visibleItems.length / PAGE_SIZE);
  const pagedItems  = visibleItems.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Daily Bulletin</h1>
          {data?.bulletin_date && (
            <p className="text-xs text-slate-500 font-mono mt-0.5">{data.bulletin_date}</p>
          )}
        </div>
        <Button onClick={() => buildMut.mutate()} disabled={buildMut.isPending} size="sm">
          {buildMut.isPending ? <><Spinner size="sm" /> Building…</> : "Build Bulletin"}
        </Button>
      </div>

      {/* Re-rank focus bar */}
      {data && allItems.length > 0 && (
        <div className="mb-4">
          {rerankResult ? (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-mono"
              style={{ background: "rgba(119,34,170,0.08)", border: "1px solid rgba(119,34,170,0.3)" }}>
              <span style={{ color: "#9B5DC8" }}>◈ FOCUS</span>
              <span className="text-slate-300 flex-1 truncate">"{rerankResult.prompt}"</span>
              <button
                onClick={() => { setRerankResult(null); setFocusPrompt(""); setPage(0); }}
                className="text-slate-500 hover:text-slate-200 transition-colors ml-2 flex-shrink-0"
              >
                [clear]
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                ref={focusRef}
                value={focusPrompt}
                onChange={e => setFocusPrompt(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && focusPrompt.trim() && !rerankMut.isPending)
                    rerankMut.mutate({ date: data.bulletin_date, prompt: focusPrompt.trim() });
                }}
                placeholder="Re-rank by focus… e.g. 'ransomware hitting healthcare'"
                className="flex-1 bg-navy-800 border border-navy-border rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-violet-600 focus:border-violet-600 font-mono"
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  if (focusPrompt.trim())
                    rerankMut.mutate({ date: data.bulletin_date, prompt: focusPrompt.trim() });
                }}
                disabled={!focusPrompt.trim() || rerankMut.isPending}
              >
                {rerankMut.isPending ? <><Spinner size="sm" /> Thinking…</> : "Re-rank"}
              </Button>
            </div>
          )}
          {rerankMut.isError && (
            <p className="text-red-400 text-xs mt-1 font-mono">
              {rerankMut.error?.response?.data?.detail || "Re-rank failed"}
            </p>
          )}
        </div>
      )}

      {/* Filter bar — only when there are hidden items or many items */}
      {allItems.length > 0 && (
        <div className="flex items-center gap-3 mb-4 text-xs font-mono">
          <span className="text-slate-600">
            {visibleItems.length}/{allItems.length} shown
          </span>
          {hiddenCount > 0 && (
            <>
              <button
                onClick={() => setShowHidden(v => !v)}
                className="text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showHidden ? `[HIDE FILTERED]` : `[SHOW ${hiddenCount} HIDDEN]`}
              </button>
              <button
                onClick={unhideAll}
                className="text-slate-600 hover:text-slate-400 transition-colors"
              >
                [UNHIDE ALL]
              </button>
            </>
          )}
        </div>
      )}

      {/* Cards */}
      {allItems.length === 0 ? (
        <EmptyState
          title="No bulletin yet"
          description="Ingest some feeds and enrich articles, then build today's bulletin."
          action={<Button onClick={() => buildMut.mutate()}>Build Now</Button>}
        />
      ) : visibleItems.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-500 font-mono text-sm mb-3">All articles hidden.</p>
          <button onClick={unhideAll} className="text-brand-400 hover:text-brand-300 font-mono text-xs">
            [UNHIDE ALL]
          </button>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {pagedItems.map(item => (
              <BulletinCard
                key={item.id}
                item={item}
                onHide={hideArticle}
                dimmed={showHidden && hidden.has(item.article.id)}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-6 font-mono text-xs">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-2 py-1 text-slate-500 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                ← prev
              </button>
              <span className="text-slate-500">
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page === totalPages - 1}
                className="px-2 py-1 text-slate-500 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
