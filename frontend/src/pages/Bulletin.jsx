import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  bulletin as bulletinApi,
  feedback as feedbackApi,
  settings as settingsApi,
  articles as articlesApi,
  ingest as ingestApi,
} from "../lib/api";
import { Button, Spinner, EmptyState, SeverityBadge } from "../components/ui";
import { ScoreBreakdownPanel } from "../components/ScoreBreakdown";
import FeedbackButtons from "../components/FeedbackButtons";
import TriageMode from "../components/TriageMode";
import { timeAgo, formatDate, categoryColor } from "../lib/utils";
import { isTypingTarget } from "../lib/shortcuts";

const PAGE_SIZE = 25;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function cyberColor(computedScore) {
  if (computedScore >= 0.7) return { hex: "#C02040", dim: "rgba(192,32,64,0.06)",  border: "rgba(192,32,64,0.35)"  };
  if (computedScore >= 0.5) return { hex: "#B85018", dim: "rgba(184,80,24,0.06)",  border: "rgba(184,80,24,0.35)"  };
  if (computedScore >= 0.3) return { hex: "#7722AA", dim: "rgba(119,34,170,0.06)", border: "rgba(119,34,170,0.30)" };
  return                           { hex: "#0088A8", dim: "rgba(0,136,168,0.05)",  border: "rgba(0,136,168,0.28)"  };
}

const NEON = {
  brand:  { hex: "#5558D4", dim: "rgba(85,88,212,0.05)",  border: "rgba(85,88,212,0.25)"  },
  cyan:   { hex: "#0088A8", dim: "rgba(0,136,168,0.05)",  border: "rgba(0,136,168,0.24)"  },
  violet: { hex: "#7722AA", dim: "rgba(119,34,170,0.05)", border: "rgba(119,34,170,0.24)" },
};

function neonCard(n) {
  return {
    background: "#0D1628",
    border: `1px solid ${n.border}`,
    borderLeft: `2px solid ${n.hex}`,
    boxShadow: `inset 2px 0 6px ${n.dim}`,
  };
}

// "Why am I seeing this" — top contributor to the ranking score
const WHY_LABELS = {
  score_ai_severity:     { label: "sev",  title: "Top driver: AI severity" },
  score_kev_bonus:       { label: "KEV",  title: "Top driver: CISA KEV CVE" },
  score_feedback_signal: { label: "fdbk", title: "Top driver: similar to articles you rated" },
  score_profile_match:   { label: "prof", title: "Top driver: matches your interest profile / watchlist" },
  score_recency:         { label: "new",  title: "Top driver: recently published" },
};

function topScoreDriver(score) {
  let best = null;
  for (const key of Object.keys(WHY_LABELS)) {
    let v = score[key] || 0;
    // The feedback signal normalizes to 0.5 = neutral, so a weak/no-data
    // signal still carries weight. Only credit it as the "why" when it's
    // meaningfully positive — otherwise new articles get a misleading fdbk chip.
    if (key === "score_feedback_signal" && (score.raw_feedback_signal || 0) < 0.55) v = 0;
    if (v > 0 && (!best || v > (best.v || 0))) best = { key, v };
  }
  return best ? WHY_LABELS[best.key] : null;
}

// ─── Read status cycle ────────────────────────────────────────────────────────

function ReadStatusCycle({ articleId, status, onChange }) {
  const cycle  = { unread: "acknowledged", acknowledged: "dismissed", dismissed: "unread" };
  const labels = { unread: "○", acknowledged: "✓", dismissed: "—" };
  const colors = { unread: "text-slate-700", acknowledged: "text-emerald-500", dismissed: "text-slate-600" };

  const toggle = (e) => {
    e.stopPropagation();
    onChange(articleId, cycle[status] || "unread");
  };

  return (
    <button
      onClick={toggle}
      className={`text-sm leading-none flex-shrink-0 ${colors[status] || colors.unread} hover:opacity-70 transition-opacity`}
      title={`Mark ${cycle[status] || "unread"} [i]`}
    >
      {labels[status] || "○"}
    </button>
  );
}

// ─── Left panel: compact list row ────────────────────────────────────────────

function BulletinListRow({ item, status, selected, dimmed, onSelect, onStatusChange }) {
  const { article, score, rank } = item;
  const c = cyberColor(score.computed_score);
  const val = Math.round(score.computed_score * 100);
  const why = topScoreDriver(score);

  return (
    <div
      onClick={onSelect}
      style={{
        borderLeft: `2px solid ${selected ? "#5558D4" : "transparent"}`,
        background: selected ? "rgba(85,88,212,0.08)" : "transparent",
        opacity: dimmed ? 0.4 : 1,
        borderBottom: "1px solid rgba(255,255,255,0.035)",
      }}
      className="flex items-start gap-2.5 px-3 py-2.5 cursor-pointer hover:bg-white/[0.025] transition-colors"
    >
      {/* Score tier — color only, no numbers; exact score lives in the reading pane */}
      <span
        className="w-[3px] self-stretch rounded-full flex-shrink-0"
        style={{ background: c.hex, opacity: 0.75, minHeight: 28 }}
        title={`Rank ${rank} · ranking score ${val}/100`}
      />

      {/* Read status */}
      <ReadStatusCycle articleId={article.id} status={status} onChange={onStatusChange} />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1 mb-0.5">
          {article.threat_category && (
            <span className={`text-[9px] uppercase tracking-wide font-semibold px-1 rounded leading-tight ${categoryColor(article.threat_category)}`}>
              {article.threat_category}
            </span>
          )}
          {why && (
            <span
              className="text-[8px] font-mono px-1 rounded leading-tight"
              style={{ color: c.hex, border: `1px solid ${c.border}`, opacity: 0.8 }}
              title={why.title}
            >
              {why.label}
            </span>
          )}
          <span className="text-[9px] text-slate-600 ml-auto font-mono flex-shrink-0">{timeAgo(article.published_at)}</span>
        </div>
        <p className={`text-xs leading-snug line-clamp-2 ${selected ? "text-white font-medium" : "text-slate-300"}`}>
          {article.title}
        </p>
      </div>
    </div>
  );
}

// ─── Reading pane: top navigation bar ────────────────────────────────────────

function ReadingNav({ selectedIdx, total, onPrev, onNext, onDeselect, articleId }) {
  const navigate = useNavigate();

  if (selectedIdx === null) {
    return (
      <div
        className="flex items-center px-5 border-b border-navy-border flex-shrink-0"
        style={{ background: "#070d1b", height: 41 }}
      >
        <span
          className="text-[10px] font-mono font-bold uppercase tracking-widest px-1.5 py-0.5 rounded"
          style={{ background: "rgba(85,88,212,0.15)", color: "rgba(85,88,212,0.9)", border: "1px solid rgba(85,88,212,0.3)" }}
        >
          DAILY BRIEF
        </span>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-1 px-4 border-b border-navy-border flex-shrink-0"
      style={{ background: "#070d1b", height: 41 }}
    >
      <button
        onClick={onPrev}
        disabled={selectedIdx === 0}
        className="px-2 py-1 text-[11px] font-mono text-slate-500 hover:text-slate-200 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
      >
        ← prev
      </button>
      <span className="text-[10px] font-mono text-slate-600 px-1 tabular-nums">{selectedIdx + 1} / {total}</span>
      <button
        onClick={onNext}
        disabled={selectedIdx === total - 1}
        className="px-2 py-1 text-[11px] font-mono text-slate-500 hover:text-slate-200 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
      >
        next →
      </button>

      <div className="w-px h-3 bg-navy-border mx-2" />

      <button
        onClick={onDeselect}
        className="text-[10px] font-mono text-slate-600 hover:text-slate-300 px-1 transition-colors"
        title="Back to brief [h]"
      >
        ← brief
      </button>

      <div className="flex-1" />

      <button
        onClick={() => navigate(`/articles/${articleId}`)}
        className="text-[10px] font-mono text-brand-400/60 hover:text-brand-300 transition-colors"
        title="Open full article page [o]"
      >
        full page [o] ↗
      </button>
    </div>
  );
}

// ─── Reading pane: daily brief ────────────────────────────────────────────────

function BriefPane({ brief, briefSources, briefGeneratedAt, bulletinDate, newCount, onRegenerate, isRegenerating }) {
  let sources = briefSources || [];
  let briefText = brief || "";
  const sourcesMatch = briefText.match(/\n\nSOURCES:(.+)$/s);
  if (sourcesMatch) {
    briefText = briefText.slice(0, sourcesMatch.index);
    if (!sources.length) {
      sources = sourcesMatch[1].split("||").map(s => {
        const [id, ...titleParts] = s.split("::");
        return { id: id.trim(), title: titleParts.join("::").trim() };
      }).filter(s => s.id && s.title);
    }
  }
  const paragraphs = briefText ? briefText.split(/\n\n+/).map(p => p.trim()).filter(Boolean) : [];

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-2">
            <div className="text-xs text-slate-500 font-mono">{bulletinDate}</div>
            {newCount > 0 && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                {newCount} new since yesterday
              </span>
            )}
          </div>
          {briefGeneratedAt && (
            <div className="text-[10px] text-slate-700 font-mono mt-0.5">
              generated {new Date(briefGeneratedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </div>
          )}
        </div>
        <button
          onClick={onRegenerate}
          disabled={isRegenerating}
          className="flex items-center gap-1.5 text-[11px] font-mono px-2.5 py-1 rounded border transition-colors disabled:opacity-40 flex-shrink-0"
          style={{ borderColor: "rgba(85,88,212,0.3)", color: "rgba(85,88,212,0.7)" }}
          onMouseEnter={e => { if (!isRegenerating) { e.currentTarget.style.borderColor = "rgba(85,88,212,0.6)"; e.currentTarget.style.color = "rgba(85,88,212,1)"; } }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(85,88,212,0.3)"; e.currentTarget.style.color = "rgba(85,88,212,0.7)"; }}
        >
          {isRegenerating ? <><Spinner size="sm" /> regenerating…</> : "↺ regenerate"}
        </button>
      </div>

      {isRegenerating && paragraphs.length === 0 ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm font-mono py-8">
          <Spinner size="sm" /> Generating brief…
        </div>
      ) : paragraphs.length > 0 ? (
        <div className="space-y-4">
          {paragraphs.map((p, i) => (
            <p key={i} className="text-sm leading-relaxed" style={{ color: i === 0 ? "#c8d0e0" : "#8a95a8" }}>
              {p}
            </p>
          ))}
          {sources.length > 0 && (
            <div className="pt-4 mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5" style={{ borderTop: "1px solid rgba(85,88,212,0.15)" }}>
              <span className="text-[10px] font-mono font-semibold uppercase tracking-widest text-slate-600">Sources</span>
              {sources.map((s, i) => (
                <Link key={s.id} to={`/articles/${s.id}`} className="text-[11px] font-mono text-brand-400/70 hover:text-brand-300 hover:underline underline-offset-2 transition-colors">
                  [{i + 1}] {s.title}
                </Link>
              ))}
            </div>
          )}
        </div>
      ) : (
        <p className="text-slate-600 text-sm font-mono">No brief yet — build the bulletin to generate one.</p>
      )}
    </div>
  );
}

// ─── Reading pane: entity list (read-only) ────────────────────────────────────

function EntityList({ title, items, render }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest font-mono mb-2">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item, i) => (
          <span key={i} className="text-xs font-mono text-slate-300 px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
            {render(item)}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Reading pane: article view ───────────────────────────────────────────────

function ArticlePane({ item, status, onHide, onStatusChange }) {
  const { article: bulletinArticle, score, id: itemId, user_rating, user_reason_tags } = item;
  const [scoreExpanded, setScoreExpanded] = useState(false);
  const c = cyberColor(score.computed_score);
  const val = Math.round(score.computed_score * 100);

  const { data: article, isLoading } = useQuery({
    queryKey: ["article", bulletinArticle.id],
    queryFn: () => articlesApi.get(bulletinArticle.id),
  });

  const { data: feedbackData } = useQuery({
    queryKey: ["article-feedback", bulletinArticle.id],
    queryFn: () => feedbackApi.getForArticle(bulletinArticle.id),
  });

  const hasEntities = article && (
    article.iocs?.length > 0 ||
    article.cve_mentions?.length > 0 ||
    article.ttp_tags?.length > 0 ||
    article.article_actors?.length > 0
  );

  return (
    <div className="p-6 max-w-3xl">
      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {(article?.threat_category ?? bulletinArticle.threat_category) && (
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded font-mono tracking-wide ${categoryColor(article?.threat_category ?? bulletinArticle.threat_category)}`}>
            {article?.threat_category ?? bulletinArticle.threat_category}
          </span>
        )}
        <SeverityBadge score={article?.ai_severity_score ?? bulletinArticle.ai_severity_score} />
        <button
          onClick={() => setScoreExpanded(v => !v)}
          className="text-[10px] font-mono font-bold px-2 py-0.5 rounded transition-opacity hover:opacity-80"
          style={{ color: c.hex, background: c.dim, border: `1px solid ${c.border}` }}
          title="Ranking score — click for breakdown"
        >
          score {val}
        </button>
        <span className="text-[11px] text-slate-500 font-mono ml-auto">{formatDate(bulletinArticle.published_at)}</span>
        <a
          href={bulletinArticle.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] font-mono text-brand-400/70 hover:text-brand-300 transition-colors"
        >
          source ↗
        </a>
      </div>

      {/* Title */}
      <h1 className="text-xl font-bold text-white mb-4 leading-snug">{bulletinArticle.title}</h1>

      {isLoading && (
        <div className="flex items-center gap-2 text-slate-600 text-sm font-mono mb-4">
          <Spinner size="sm" /> Loading…
        </div>
      )}

      {/* og_image */}
      {article?.og_image && (
        <a href={bulletinArticle.url} target="_blank" rel="noopener noreferrer" className="block mb-5">
          <img
            src={article.og_image}
            alt=""
            onError={e => { e.currentTarget.style.display = "none"; }}
            style={{
              width: "100%", maxHeight: 220,
              objectFit: "cover",
              borderRadius: 8,
              opacity: 0.85,
              border: `1px solid ${c.border}`,
            }}
          />
        </a>
      )}

      {/* AI Summary */}
      {article?.ai_summary && (
        <div className="p-4 mb-5 rounded-xl" style={neonCard(NEON.brand)}>
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 font-mono mb-2">AI Summary</div>
          <p className="text-slate-300 leading-relaxed text-sm">{article.ai_summary}</p>
        </div>
      )}

      {/* Entities */}
      {hasEntities && (
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="p-3 rounded-xl space-y-3" style={neonCard(NEON.cyan)}>
            <EntityList title="IOCs" items={article.iocs} render={i => i.value} />
            <EntityList title="CVEs" items={article.cve_mentions} render={i => i.cve_id} />
          </div>
          <div className="p-3 rounded-xl space-y-3" style={neonCard(NEON.violet)}>
            <EntityList
              title="MITRE TTPs"
              items={article.ttp_tags}
              render={i => i.technique_id ? `${i.technique_id}${i.technique_name ? " · " + i.technique_name : ""}` : (i.value || "—")}
            />
            <EntityList title="Threat Actors" items={article.article_actors} render={i => i.actor_name} />
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-4 flex-wrap mb-5">
        <FeedbackButtons
          articleId={bulletinArticle.id}
          article={article ?? bulletinArticle}
          initialRating={feedbackData?.rating ?? user_rating ?? null}
          initialReasonTags={feedbackData?.reason_tags ?? user_reason_tags ?? []}
        />
        <ReadStatusCycle articleId={bulletinArticle.id} status={status} onChange={onStatusChange} />
        <button
          onClick={() => onHide(bulletinArticle.id)}
          className="ml-auto text-[10px] font-mono text-slate-600 hover:text-slate-400 transition-colors"
          title="Dismiss [m]"
        >
          [DISMISS]
        </button>
        <Link
          to={`/articles/${bulletinArticle.id}`}
          className="text-[10px] font-mono text-brand-400/50 hover:text-brand-300 transition-colors"
        >
          full page →
        </Link>
      </div>

      {/* Score breakdown */}
      {scoreExpanded && (
        <div className="p-4 rounded-xl" style={neonCard(NEON.brand)}>
          <ScoreBreakdownPanel itemId={itemId} score={score} />
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

function loadSplit() {
  const v = parseInt(localStorage.getItem("bulletin-split") || "33", 10);
  return isNaN(v) ? 33 : Math.min(60, Math.max(20, v));
}

export default function Bulletin() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  // Optimistic read-status overrides on top of server state (DB is the source of truth)
  const [statusOverrides, setStatusOverrides] = useState({});
  const [showHidden, setShowHidden] = useState(false);
  const [page, setPage] = useState(0);
  const [selectedIdx, setSelectedIdx] = useState(null); // null = show brief
  const [triageOpen, setTriageOpen] = useState(false);
  const [splitPct, setSplitPct] = useState(loadSplit);
  const autoBuilt = useRef(false);
  const [waitingForBrief, setWaitingForBrief] = useState(false);
  const prevBriefGenAt = useRef(null);
  const listRef = useRef(null);
  const readingRef = useRef(null);
  const rowRefs = useRef({});
  const dragging = useRef(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["bulletin-today"],
    queryFn: bulletinApi.today,
    refetchInterval: waitingForBrief ? 3_000 : 60_000,
  });

  // When the bulletin is empty, fetch pipeline status to drive onboarding
  const { data: pipelineStatus } = useQuery({
    queryKey: ["ingest-status"],
    queryFn: ingestApi.status,
    enabled: !!data && (!data.items || data.items.length === 0),
  });

  useEffect(() => {
    if (waitingForBrief && data?.brief_generated_at && data.brief_generated_at !== prevBriefGenAt.current) {
      setWaitingForBrief(false);
    }
  }, [data?.brief_generated_at, waitingForBrief]);

  // Server refetch makes overrides redundant — drop ones the server now agrees with
  useEffect(() => {
    if (!data?.items) return;
    setStatusOverrides(prev => {
      const next = { ...prev };
      let changed = false;
      for (const item of data.items) {
        if (next[item.article.id] !== undefined && next[item.article.id] === item.read_status) {
          delete next[item.article.id];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [data]);

  const { data: fbSignal } = useQuery({
    queryKey: ["feedback-signal"],
    queryFn: settingsApi.feedbackSignal,
    staleTime: 60_000,
  });

  const buildMut = useMutation({
    mutationFn: () => bulletinApi.build(),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["bulletin-today"] }), 2000);
    },
  });

  const briefMut = useMutation({
    mutationFn: bulletinApi.generateBrief,
    onSuccess: () => {
      prevBriefGenAt.current = data?.brief_generated_at ?? null;
      setWaitingForBrief(true);
    },
  });

  useEffect(() => {
    if (data && !data.items && !autoBuilt.current) {
      autoBuilt.current = true;
      buildMut.mutate();
    }
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  const effectiveStatus = useCallback(
    (item) => statusOverrides[item.article.id] ?? item.read_status ?? "unread",
    [statusOverrides],
  );

  const setStatus = useCallback((articleId, status) => {
    setStatusOverrides(prev => ({ ...prev, [articleId]: status }));
    feedbackApi.setReadStatus(articleId, status).then(() => {
      qc.invalidateQueries({ queryKey: ["feedback-signal"] });
    });
  }, [qc]);

  const dismissArticle = useCallback((articleId) => {
    setStatus(articleId, "dismissed");
  }, [setStatus]);

  const undismissAll = useCallback(() => {
    const dismissed = (data?.items || []).filter(i => effectiveStatus(i) === "dismissed");
    dismissed.forEach(i => {
      setStatusOverrides(prev => ({ ...prev, [i.article.id]: "unread" }));
      feedbackApi.setReadStatus(i.article.id, "unread");
    });
    setShowHidden(false);
    setPage(0);
    setSelectedIdx(null);
    setTimeout(() => qc.invalidateQueries({ queryKey: ["bulletin-today"] }), 500);
  }, [data, effectiveStatus, qc]);

  useEffect(() => { setPage(0); setSelectedIdx(null); }, [showHidden]);

  useEffect(() => {
    const items = data?.items;
    if (items?.length > 0) {
      sessionStorage.setItem("bulletin-nav", JSON.stringify(items.map(i => i.article.id)));
    }
  }, [data]);

  // Auto-scroll focused row into view
  useEffect(() => {
    if (selectedIdx !== null) {
      rowRefs.current[selectedIdx]?.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIdx]);

  // Resizable split
  useEffect(() => {
    const move = (e) => {
      if (!dragging.current) return;
      const pct = Math.min(60, Math.max(20, (e.clientX / window.innerWidth) * 100));
      setSplitPct(pct);
    };
    const up = () => {
      if (dragging.current) {
        dragging.current = false;
        setSplitPct(p => { localStorage.setItem("bulletin-split", String(Math.round(p))); return p; });
        document.body.style.userSelect = "";
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, []);

  // ─── Keyboard: one-handed right-cluster scheme ──────────────────────────────
  // j/k nav · h brief · o/Enter open · m dismiss · u 👍 · n 👎 · i cycle status
  // ,/. pages · 1-9 jump · Space scroll · y copy URL · t triage
  useEffect(() => {
    const handler = (e) => {
      if (isTypingTarget(e) || triageOpen) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const allData = data?.items || [];
      const visible = showHidden ? allData : allData.filter(i => effectiveStatus(i) !== "dismissed");
      const items = visible.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
      const totalPages = Math.ceil(visible.length / PAGE_SIZE);
      const sel = selectedIdx !== null ? items[selectedIdx] : null;

      switch (e.key) {
        case "j":
          e.preventDefault();
          if (items.length) setSelectedIdx(i => (i === null ? 0 : Math.min(i + 1, items.length - 1)));
          break;
        case "k":
          e.preventDefault();
          setSelectedIdx(i => (i === null || i === 0 ? null : i - 1));
          break;
        case "h":
        case "b":
        case "Escape":
          setSelectedIdx(null);
          break;
        case "o":
        case "Enter":
          if (sel) navigate(`/articles/${sel.article.id}`);
          break;
        case "m":
          if (sel) {
            e.preventDefault();
            dismissArticle(sel.article.id);
            // list shrinks (unless showing hidden) — same index is the next item
            setSelectedIdx(i => {
              const newLen = showHidden ? items.length : items.length - 1;
              if (newLen <= 0) return null;
              const next = showHidden ? Math.min(i + 1, newLen - 1) : Math.min(i, newLen - 1);
              return next;
            });
          }
          break;
        case "u":
          if (sel) {
            e.preventDefault();
            feedbackApi.rate(sel.article.id, 1).then(() => qc.invalidateQueries({ queryKey: ["bulletin-today"] }));
            setSelectedIdx(i => Math.min(i + 1, items.length - 1));
          }
          break;
        case "n":
        case "d": // legacy alias
          if (sel) {
            e.preventDefault();
            feedbackApi.rate(sel.article.id, -1).then(() => qc.invalidateQueries({ queryKey: ["bulletin-today"] }));
            setSelectedIdx(i => Math.min(i + 1, items.length - 1));
          }
          break;
        case "i":
          if (sel) {
            e.preventDefault();
            const cycle = { unread: "acknowledged", acknowledged: "dismissed", dismissed: "unread" };
            setStatus(sel.article.id, cycle[effectiveStatus(sel)] || "unread");
          }
          break;
        case ",":
          if (page > 0) { setPage(p => p - 1); setSelectedIdx(null); }
          break;
        case ".":
          if (page < totalPages - 1) { setPage(p => p + 1); setSelectedIdx(null); }
          break;
        case "y":
          if (sel) { navigator.clipboard?.writeText(sel.article.url); }
          break;
        case "t":
          e.preventDefault();
          setTriageOpen(true);
          break;
        case " ": {
          const pane = readingRef.current;
          if (pane) {
            e.preventDefault();
            pane.scrollBy({ top: (e.shiftKey ? -1 : 1) * pane.clientHeight * 0.8, behavior: "smooth" });
          }
          break;
        }
        default:
          if (/^[1-9]$/.test(e.key)) {
            const n = parseInt(e.key, 10) - 1;
            if (n < items.length) { e.preventDefault(); setSelectedIdx(n); }
          }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [data, statusOverrides, showHidden, page, selectedIdx, dismissArticle, effectiveStatus, setStatus, navigate, qc, triageOpen]);

  if (isLoading) return <div className="flex justify-center mt-20"><Spinner size="lg" /></div>;
  if (error)     return <div className="p-8 text-red-400 font-mono">Error loading bulletin.</div>;

  const allItems     = data?.items || [];
  const hiddenCount  = allItems.filter(item => effectiveStatus(item) === "dismissed").length;
  const visibleItems = showHidden ? allItems : allItems.filter(item => effectiveStatus(item) !== "dismissed");
  const totalPages   = Math.ceil(visibleItems.length / PAGE_SIZE);
  const pagedItems   = visibleItems.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const selectedItem = selectedIdx !== null ? (pagedItems[selectedIdx] ?? null) : null;
  const triageItems  = visibleItems.filter(i => !i.user_rating);

  const noArticlesYet = (pipelineStatus?.articles?.total ?? null) === 0;

  return (
    <div className="flex h-full overflow-hidden">
      {triageOpen && triageItems.length > 0 && (
        <TriageMode items={triageItems} onClose={() => setTriageOpen(false)} />
      )}

      {/* ── Left: bulletin list ─────────────────────────────────────────────── */}
      <div className="flex flex-col border-r border-navy-border flex-shrink-0" style={{ width: `${splitPct}%` }}>
        {/* Header */}
        <div className="flex-shrink-0 px-4 py-3 border-b border-navy-border" style={{ background: "#070d1b" }}>
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-white tracking-tight leading-tight">Daily Bulletin</h1>
              <div className="flex items-center gap-2 mt-0.5">
                {data?.bulletin_date && (
                  <p className="text-[10px] text-slate-500 font-mono">{data.bulletin_date}</p>
                )}
                {data?.new_count > 0 && (
                  <span className="text-[9px] font-mono text-emerald-400/80">+{data.new_count} new</span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {triageItems.length > 0 && (
                <Button size="sm" variant="secondary" onClick={() => setTriageOpen(true)} title="Triage mode [t]">
                  Triage {triageItems.length}
                </Button>
              )}
              <Button
                onClick={() => {
                  if (allItems.length > 0 && !window.confirm("Rebuild today's bulletin? This will rescore and re-rank all articles.")) return;
                  buildMut.mutate();
                }}
                disabled={buildMut.isPending}
                size="sm"
                variant={allItems.length === 0 ? "primary" : "secondary"}
              >
                {buildMut.isPending ? <><Spinner size="sm" /> Building…</> : allItems.length > 0 ? "Rebuild" : "Build"}
              </Button>
            </div>
          </div>

          {/* Feedback cold-start notice */}
          {fbSignal?.status === "inactive" && (
            <div className="mb-2 px-2 py-1 rounded border border-amber-500/20 bg-amber-500/5 flex items-center gap-1.5">
              <span className="text-amber-400/70 text-[9px] font-mono font-semibold uppercase tracking-widest flex-shrink-0">FEEDBACK</span>
              <span className="text-amber-300/60 text-[10px] font-mono truncate">{fbSignal.active_reason}</span>
            </div>
          )}

          {/* Filter bar */}
          {allItems.length > 0 && (
            <div className="flex items-center gap-2 text-[10px] font-mono flex-wrap">
              <span className="text-slate-600">{visibleItems.length}/{allItems.length} shown</span>
              {hiddenCount > 0 && (
                <>
                  <button onClick={() => setShowHidden(v => !v)} className="text-slate-500 hover:text-slate-300 transition-colors">
                    {showHidden ? "[HIDE DISMISSED]" : `[+${hiddenCount} DISMISSED]`}
                  </button>
                  {showHidden && (
                    <button onClick={undismissAll} className="text-slate-600 hover:text-slate-400 transition-colors">
                      [UNDISMISS ALL]
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Scrollable list */}
        <div ref={listRef} className="flex-1 overflow-y-auto">
          {allItems.length === 0 ? (
            <div className="p-4">
              {noArticlesYet ? (
                <EmptyState
                  title="Welcome to Wraith"
                  description="No articles yet. Get your first bulletin in three steps: 1) Settings → Ingest to pull your RSS feeds, 2) Enrich to extract intel with the LLM, 3) Build the bulletin."
                  action={<Button onClick={() => navigate("/settings")}>Open Settings</Button>}
                />
              ) : (
                <EmptyState
                  title={buildMut.isPending ? "Building bulletin…" : "No bulletin yet"}
                  description={buildMut.isPending ? "Scoring and ranking articles." : "Build the bulletin to get started."}
                  action={buildMut.isPending ? <Spinner size="lg" /> : <Button onClick={() => buildMut.mutate()}>Build Now</Button>}
                />
              )}
            </div>
          ) : visibleItems.length === 0 ? (
            <div className="p-4 text-center">
              <p className="text-slate-500 font-mono text-xs mb-2">All articles hidden.</p>
              <button onClick={undismissAll} className="text-brand-400 hover:text-brand-300 font-mono text-[10px]">[UNDISMISS ALL]</button>
            </div>
          ) : (
            pagedItems.map((item, idx) => (
              <div key={item.id} ref={el => { rowRefs.current[idx] = el; }}>
                <BulletinListRow
                  item={item}
                  status={effectiveStatus(item)}
                  selected={selectedIdx === idx}
                  dimmed={showHidden && effectiveStatus(item) === "dismissed"}
                  onSelect={() => setSelectedIdx(idx)}
                  onStatusChange={setStatus}
                />
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex-shrink-0 border-t border-navy-border" style={{ background: "#070d1b" }}>
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 px-4 py-1.5 font-mono text-[10px] border-b border-navy-border">
              <button
                onClick={() => { setPage(p => Math.max(0, p - 1)); setSelectedIdx(null); }}
                disabled={page === 0}
                className="text-slate-500 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                ← prev
              </button>
              <span className="text-slate-600">{page + 1} / {totalPages}</span>
              <button
                onClick={() => { setPage(p => Math.min(totalPages - 1, p + 1)); setSelectedIdx(null); }}
                disabled={page === totalPages - 1}
                className="text-slate-500 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                next →
              </button>
            </div>
          )}
          <p className="px-4 py-2 text-[9px] font-mono text-slate-700 text-center">
            j/k nav · o open · m dismiss · u/n rate · i status · t triage · ? help
          </p>
        </div>
      </div>

      {/* Drag handle */}
      <div
        onPointerDown={() => { dragging.current = true; document.body.style.userSelect = "none"; }}
        className="w-1 flex-shrink-0 cursor-col-resize hover:bg-brand-600/40 transition-colors"
        style={{ marginLeft: -2, zIndex: 10 }}
        title="Drag to resize"
      />

      {/* ── Right: reading pane ─────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <ReadingNav
          selectedIdx={selectedIdx}
          total={pagedItems.length}
          onPrev={() => setSelectedIdx(i => Math.max(0, i - 1))}
          onNext={() => setSelectedIdx(i => Math.min(pagedItems.length - 1, i + 1))}
          onDeselect={() => setSelectedIdx(null)}
          articleId={selectedItem?.article.id}
        />
        <div ref={readingRef} className="flex-1 overflow-y-auto">
          {selectedItem ? (
            <ArticlePane
              key={selectedItem.article.id}
              item={selectedItem}
              status={effectiveStatus(selectedItem)}
              onHide={dismissArticle}
              onStatusChange={setStatus}
            />
          ) : (
            <BriefPane
              brief={data?.brief}
              briefSources={data?.brief_sources}
              briefGeneratedAt={data?.brief_generated_at}
              bulletinDate={data?.bulletin_date}
              newCount={data?.new_count || 0}
              onRegenerate={() => briefMut.mutate()}
              isRegenerating={briefMut.isPending || waitingForBrief}
            />
          )}
        </div>
      </div>
    </div>
  );
}
