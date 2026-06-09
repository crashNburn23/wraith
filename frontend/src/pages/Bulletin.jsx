import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { bulletin as bulletinApi, feedback as feedbackApi, settings as settingsApi } from "../lib/api";
import { Button, Spinner, EmptyState } from "../components/ui";
import { ScoreBreakdownPanel } from "../components/ScoreBreakdown";
import FeedbackButtons from "../components/FeedbackButtons";
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
        position: "absolute", top: 8, right: 8,
        width: 36, height: 36, borderRadius: "50%",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'JetBrains Mono','Fira Code',monospace",
        fontSize: 13, fontWeight: 800,
        color: c.hex,
        background: `radial-gradient(circle,${c.dim} 0%,#050c1a 100%)`,
        border: `1px solid ${c.border}`,
        boxShadow: `0 0 8px ${c.dim}, inset 0 0 6px rgba(0,0,0,0.6)`,
        cursor: "pointer", userSelect: "none", zIndex: 1,
      }}
    >
      {val}
    </button>
  );
}

// ─── Read status ──────────────────────────────────────────────────────────────

function ReadStatusCycle({ articleId, initialStatus = "unread" }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState(initialStatus);

  useEffect(() => { setStatus(initialStatus); }, [initialStatus]);

  const cycle  = { unread: "acknowledged", acknowledged: "dismissed", dismissed: "unread" };
  const labels = { unread: "○", acknowledged: "✓", dismissed: "—" };
  const colors = { unread: "text-slate-700", acknowledged: "text-emerald-500", dismissed: "text-slate-600" };
  const toggle = () => {
    const next = cycle[status];
    setStatus(next);
    feedbackApi.setReadStatus(articleId, next).then(() => {
      qc.invalidateQueries({ queryKey: ["feedback-signal"] });
    });
  };
  return (
    <button onClick={toggle} className={`text-sm leading-none ${colors[status]} hover:opacity-70 transition-opacity`} title={`Mark ${cycle[status]}`}>
      {labels[status]}
    </button>
  );
}

// ─── Bulletin card ────────────────────────────────────────────────────────────

function BulletinCard({ item, onHide, dimmed = false }) {
  const { article, score, rank, user_rating, user_reason_tags, read_status } = item;
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

      <div className="p-4" style={{ paddingRight: 52 }}>
        <div className="flex items-start gap-3">
          {/* Rank + read */}
          <div className="flex flex-col items-center gap-1 flex-shrink-0 w-7 pt-0.5">
            <span className="text-sm font-bold font-mono leading-none" style={{ color: c.hex, opacity: 0.35 }}>
              {rank}
            </span>
            <ReadStatusCycle articleId={article.id} initialStatus={read_status} />
          </div>

          <div className="flex-1 min-w-0">
            {/* Meta + thumbnail row */}
            <div className="flex items-start gap-2">
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
                <Link to={`/articles/${article.id}`} className="text-sm font-medium text-slate-200 hover:text-white leading-snug line-clamp-2 block">
                  {article.title}
                </Link>
              </div>

              {/* Thumbnail */}
              {article.og_image && (
                <a href={article.url} target="_blank" rel="noopener noreferrer" className="flex-shrink-0 mt-0.5">
                  <img
                    src={article.og_image}
                    alt=""
                    onError={e => { e.currentTarget.style.display = "none"; }}
                    style={{
                      width: 80, height: 52,
                      objectFit: "cover",
                      borderRadius: 6,
                      opacity: 0.82,
                      border: `1px solid ${c.border}`,
                    }}
                  />
                </a>
              )}
            </div>

            {/* Actions row */}
            <div className="flex items-center gap-3 mt-2">
              <FeedbackButtons articleId={article.id} article={article} initialRating={user_rating} initialReasonTags={user_reason_tags} />
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

// ─── Daily Brief Card ─────────────────────────────────────────────────────────

function DailyBriefCard({ brief, briefGeneratedAt, bulletinDate, onRegenerate, isRegenerating }) {
  const [expanded, setExpanded] = useState(true);

  const paragraphs = brief
    ? brief.split(/\n\n+/).map(p => p.trim()).filter(Boolean)
    : [];

  return (
    <div
      className="mb-6 rounded-xl overflow-hidden"
      style={{
        background: "linear-gradient(135deg, #090f1d 0%, #0b1120 100%)",
        border: "1px solid rgba(85,88,212,0.28)",
        borderLeft: "2px solid rgba(85,88,212,0.7)",
        boxShadow: "inset 2px 0 12px rgba(85,88,212,0.06), 0 1px 3px rgba(0,0,0,0.4)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: "1px solid rgba(85,88,212,0.15)" }}>
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-2.5 group"
        >
          <span
            className="text-[10px] font-mono font-bold uppercase tracking-widest px-1.5 py-0.5 rounded"
            style={{ background: "rgba(85,88,212,0.15)", color: "rgba(85,88,212,0.9)", border: "1px solid rgba(85,88,212,0.3)" }}
          >
            DAILY BRIEF
          </span>
          <span className="text-xs text-slate-400 font-mono group-hover:text-slate-200 transition-colors">
            {bulletinDate}
          </span>
          <span className="text-slate-700 text-[10px] transition-transform" style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}>▶</span>
        </button>
        <div className="flex items-center gap-3">
          {briefGeneratedAt && (
            <span className="text-[10px] text-slate-700 font-mono hidden sm:block">
              {new Date(briefGeneratedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={onRegenerate}
            disabled={isRegenerating}
            className="flex items-center gap-1.5 text-[11px] font-mono px-2.5 py-1 rounded border transition-colors disabled:opacity-40"
            style={{ borderColor: "rgba(85,88,212,0.3)", color: "rgba(85,88,212,0.7)" }}
            onMouseEnter={e => { if (!isRegenerating) { e.currentTarget.style.borderColor = "rgba(85,88,212,0.6)"; e.currentTarget.style.color = "rgba(85,88,212,1)"; }}}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(85,88,212,0.3)"; e.currentTarget.style.color = "rgba(85,88,212,0.7)"; }}
          >
            {isRegenerating ? <><Spinner size="sm" /> regenerating…</> : "↺ regenerate"}
          </button>
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div className="px-5 py-4">
          {isRegenerating && paragraphs.length === 0 ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm font-mono py-4">
              <Spinner size="sm" /> Generating brief…
            </div>
          ) : paragraphs.length > 0 ? (
            <div className="space-y-3">
              {paragraphs.map((p, i) => (
                <p
                  key={i}
                  className="text-sm leading-relaxed"
                  style={{ color: i === 0 ? "#c8d0e0" : "#8a95a8" }}
                >
                  {p}
                </p>
              ))}
            </div>
          ) : (
            <p className="text-slate-600 text-sm font-mono">No brief yet — build the bulletin to generate one.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Bulletin() {
  const qc = useQueryClient();
  const [hidden, setHidden] = useState(loadHidden);
  const [showHidden, setShowHidden] = useState(false);
  const [page, setPage] = useState(0);
  const autoBuilt = useRef(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["bulletin-today"],
    queryFn: bulletinApi.today,
    refetchInterval: 60_000,
  });

  const { data: fbSignal } = useQuery({
    queryKey: ["feedback-signal"],
    queryFn: settingsApi.feedbackSignal,
    staleTime: 60_000,
  });

  const buildMut = useMutation({
    mutationFn: bulletinApi.build,
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["bulletin-today"] }), 2000);
    },
  });

  const briefMut = useMutation({
    mutationFn: bulletinApi.generateBrief,
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["bulletin-today"] }), 4000);
    },
  });

  useEffect(() => {
    if (data && !data.items && !autoBuilt.current) {
      autoBuilt.current = true;
      buildMut.mutate();
    }
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const allItems    = data?.items || [];
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

      {/* Feedback cold-start notice */}
      {fbSignal?.status === "inactive" && (
        <div className="mb-4 px-3 py-2 rounded-lg border border-amber-500/20 bg-amber-500/5 flex items-center gap-2">
          <span className="text-amber-400/70 text-[10px] font-mono font-semibold uppercase tracking-widest flex-shrink-0">FEEDBACK LOOP</span>
          <span className="text-amber-300/60 text-[11px] font-mono">{fbSignal.active_reason}</span>
        </div>
      )}

      {/* Daily Brief */}
      {(data?.brief || allItems.length > 0) && (
        <DailyBriefCard
          brief={data?.brief}
          briefGeneratedAt={data?.brief_generated_at}
          bulletinDate={data?.bulletin_date}
          onRegenerate={() => briefMut.mutate()}
          isRegenerating={briefMut.isPending}
        />
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
          title={buildMut.isPending ? "Building bulletin…" : "No bulletin yet"}
          description={buildMut.isPending ? "Scoring and ranking enriched articles." : "Ingest some feeds and enrich articles, then build today's bulletin."}
          action={buildMut.isPending ? <Spinner size="lg" /> : <Button onClick={() => buildMut.mutate()}>Build Now</Button>}
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
