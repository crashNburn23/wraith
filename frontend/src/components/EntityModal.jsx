import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { entities as entitiesApi, settings as settingsApi } from "../lib/api";
import { Spinner } from "./ui";
import HighlightedText, { buildHighlights } from "./HighlightedText";
import { formatDate } from "../lib/utils";

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

function useFocusTrap(ref) {
  useEffect(() => {
    const prev = document.activeElement;
    // Focus the first focusable element inside the modal
    const first = ref.current?.querySelectorAll(FOCUSABLE)?.[0];
    first?.focus();

    const trap = (e) => {
      if (e.key !== "Tab") return;
      const els = [...(ref.current?.querySelectorAll(FOCUSABLE) || [])];
      if (!els.length) return;
      const idx = els.indexOf(document.activeElement);
      if (e.shiftKey) {
        if (idx <= 0) { e.preventDefault(); els[els.length - 1].focus(); }
      } else {
        if (idx === els.length - 1) { e.preventDefault(); els[0].focus(); }
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      prev?.focus();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}

// ─── Per-entity-type muted accent palette ─────────────────────────────────────

const TYPE_NEON = {
  cve:   { hex: "#B85018", dim: "rgba(184,80,24,0.06)",  border: "rgba(184,80,24,0.32)"  },
  ioc:   { hex: "#0088A8", dim: "rgba(0,136,168,0.05)",  border: "rgba(0,136,168,0.28)"  },
  actor: { hex: "#7722AA", dim: "rgba(119,34,170,0.06)", border: "rgba(119,34,170,0.28)" },
};

const TYPE_META = {
  cve:   { label: "CVE" },
  ioc:   { label: "Indicator" },
  actor: { label: "Threat Actor" },
};

// ─── Shared sub-components ────────────────────────────────────────────────────

function Stat({ label, value, className = "text-slate-200", neon }) {
  return (
    <div
      className="rounded-xl p-3"
      style={{
        background: "#09101E",
        border: `1px solid ${neon?.border || "rgba(28,46,72,1)"}`,
        borderLeft: neon ? `2px solid ${neon.hex}` : undefined,
        boxShadow: neon ? `inset 2px 0 8px ${neon.dim}` : undefined,
      }}
    >
      <div className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest mb-1 font-mono">{label}</div>
      <div className={`text-sm font-bold font-mono ${className}`}>{value}</div>
    </div>
  );
}

function SectionHeader({ count, label, neon }) {
  return (
    <div className="flex items-center gap-2 pt-1">
      <span className="text-[10px] font-semibold uppercase tracking-widest font-mono" style={{ color: neon?.hex || "#64748B" }}>
        {label}
      </span>
      {count != null && (
        <span className="text-[10px] bg-navy-700 border border-navy-border text-slate-500 px-1.5 py-0.5 rounded font-mono">{count}</span>
      )}
      <div className="flex-1 h-px" style={{ background: neon ? `linear-gradient(90deg, ${neon.border}, transparent)` : "rgba(28,46,72,1)" }} />
    </div>
  );
}

function Empty({ text }) {
  return <p className="text-sm text-slate-600 italic py-2 font-mono">{text}</p>;
}

// Pin an actor/CVE to the watchlist — matching articles get a relevance boost
function WatchButton({ itemType, value, neon }) {
  const qc = useQueryClient();
  const { data: watchlist } = useQuery({ queryKey: ["watchlist"], queryFn: settingsApi.getWatchlist });
  const existing = (watchlist || []).find(
    w => w.item_type === itemType && w.value.toLowerCase() === (value || "").toLowerCase()
  );

  const addMut = useMutation({
    mutationFn: () => settingsApi.addWatchlist(itemType, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const delMut = useMutation({
    mutationFn: () => settingsApi.removeWatchlist(existing.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  if (!value) return null;
  return (
    <button
      onClick={() => (existing ? delMut.mutate() : addMut.mutate())}
      disabled={addMut.isPending || delMut.isPending}
      className="text-[10px] font-mono px-2 py-1 rounded border transition-colors flex-shrink-0"
      style={{
        color: existing ? neon.hex : "rgba(148,163,184,0.7)",
        borderColor: existing ? neon.border : "rgba(148,163,184,0.25)",
        background: existing ? neon.dim : "transparent",
      }}
      title={existing ? "Remove from watchlist" : "Watch — boost matching articles in the bulletin"}
    >
      {existing ? "★ watching" : "☆ watch"}
    </button>
  );
}

// ─── Article context card ─────────────────────────────────────────────────────

function ArticleCtxCard({ article, primaryValue, defaultOpen = false, neon }) {
  const [open, setOpen] = useState(defaultOpen);
  const highlights = buildHighlights(article.entities, primaryValue);

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: "#09101E",
        border: `1px solid ${neon?.border || "rgba(28,46,72,1)"}`,
        borderLeft: neon ? `2px solid ${neon.hex}` : undefined,
        boxShadow: neon ? `inset 2px 0 6px ${neon.dim}` : undefined,
      }}
    >
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-start gap-3 p-4 text-left transition-colors"
        style={{ background: open ? "rgba(255,255,255,0.02)" : "transparent" }}
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap gap-1.5 mb-1">
            {article.published_at && (
              <span className="text-[10px] text-slate-500 font-mono">{formatDate(article.published_at)}</span>
            )}
            {article.enrichment_status === "enriched" && (
              <span className="text-[10px] text-emerald-500 font-mono">enriched</span>
            )}
          </div>
          <p className="text-sm font-medium text-slate-200 leading-snug line-clamp-2">{article.title}</p>
          {article.ai_summary && !open && (
            <p className="text-xs text-slate-500 mt-1 line-clamp-2">{article.ai_summary}</p>
          )}
        </div>
        <span className="text-slate-600 text-xs mt-1 flex-shrink-0">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-navy-border px-4 pb-4 pt-3 space-y-3">
          <EntityChips entities={article.entities} primaryValue={primaryValue} neon={neon} />
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold uppercase tracking-widest font-mono text-slate-600">Scraped Text</span>
              <Link to={`/articles/${article.id}`} className="text-[10px] font-mono hover:underline" style={{ color: neon?.hex || "#818CF8" }}>
                open article →
              </Link>
            </div>
            <div className="bg-navy-950 border border-navy-border rounded-lg p-3 max-h-72 overflow-y-auto">
              <HighlightedText text={article.scraped_text} highlights={highlights} primaryValue={primaryValue} />
            </div>
          </div>
          <HighlightLegend entities={article.entities} />
        </div>
      )}
    </div>
  );
}

function EntityChips({ entities, primaryValue, neon }) {
  if (!entities) return null;
  const all = [
    ...((entities.iocs || []).map(i => ({ label: i.value, sub: i.ioc_type, color: "blue", excerpt: i.source_excerpt }))),
    ...((entities.cve_mentions || []).map(c => ({ label: c.cve_id, sub: "CVE", color: "orange", excerpt: c.source_excerpt }))),
    ...((entities.actors || []).map(a => ({ label: a.name, sub: "actor", color: "purple", excerpt: a.source_excerpt }))),
    ...((entities.ttps || []).map(t => ({ label: t.technique_id, sub: t.tactic || "TTP", color: "green", excerpt: t.source_excerpt }))),
  ];
  if (all.length === 0) return null;

  const COLOR = {
    blue:   "bg-blue-500/15 text-blue-300 border-blue-500/25",
    orange: "bg-orange-500/15 text-orange-300 border-orange-500/25",
    purple: "bg-violet-500/15 text-violet-300 border-violet-500/25",
    green:  "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  };

  return (
    <div className="flex flex-wrap gap-1.5">
      {all.map((e, i) => (
        <span
          key={i}
          title={e.excerpt || undefined}
          className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border ${COLOR[e.color] || COLOR.blue} ${e.label === primaryValue ? "ring-1 ring-offset-0" : ""}`}
          style={e.label === primaryValue && neon ? { ringColor: neon.hex } : undefined}
        >
          <span className="text-[9px] opacity-60">{e.sub}</span>
          {e.label}
          {e.excerpt && <span className="text-[9px] opacity-40 ml-0.5">❝</span>}
        </span>
      ))}
    </div>
  );
}

function HighlightLegend({ entities }) {
  const has = {
    ioc: (entities?.iocs?.length || 0) > 0,
    cve: (entities?.cve_mentions?.length || 0) > 0,
    actor: (entities?.actors?.length || 0) > 0,
    ttp: (entities?.ttps?.length || 0) > 0,
  };
  const items = [
    has.ioc   && { label: "IOC",   cls: "bg-rose-500/25 text-rose-300"      },
    has.cve   && { label: "CVE",   cls: "bg-orange-500/30 text-orange-300"  },
    has.actor && { label: "Actor", cls: "bg-violet-500/30 text-violet-300"  },
    has.ttp   && { label: "TTP",   cls: "bg-emerald-500/25 text-emerald-300" },
  ].filter(Boolean);
  if (items.length === 0) return null;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <span className="text-[10px] text-slate-600 font-mono">highlights:</span>
      <span className="inline-flex items-center gap-1 text-[10px]">
        <mark className="bg-yellow-400/40 text-yellow-200 px-1 rounded-sm not-italic font-mono">primary</mark>
      </span>
      {items.map(({ label, cls }) => (
        <span key={label} className="inline-flex items-center gap-1 text-[10px]">
          <mark className={`${cls} px-1 rounded-sm not-italic font-mono`}>{label}</mark>
        </span>
      ))}
    </div>
  );
}

// ─── CVE content ──────────────────────────────────────────────────────────────

function CVEContent({ cveId }) {
  const neon = TYPE_NEON.cve;
  const { data, isLoading } = useQuery({
    queryKey: ["entity-cve", cveId],
    queryFn: () => entitiesApi.cve(cveId),
  });

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>;

  const rec = data?.record;
  const cvssColor = rec?.cvss_score >= 9 ? "text-red-400" : rec?.cvss_score >= 7 ? "text-orange-400" : "text-slate-300";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="CVSS"      value={rec?.cvss_score != null ? rec.cvss_score.toFixed(1) : "—"} className={cvssColor} neon={neon} />
        <Stat label="EPSS"      value={rec?.epss_score != null ? `${(rec.epss_score * 100).toFixed(2)}%` : "—"} neon={neon} />
        <Stat label="EPSS %ile" value={rec?.epss_percentile != null ? `${(rec.epss_percentile * 100).toFixed(0)}th` : "—"} neon={neon} />
        <Stat label="KEV"       value={rec?.in_kev ? `Due ${rec.kev_due_date || "—"}` : "Not in KEV"} className={rec?.in_kev ? "text-red-400" : "text-slate-500"} neon={neon} />
      </div>

      {rec?.ai_summary && (
        <div className="rounded-xl p-4" style={{ background: "#09101E", border: `1px solid ${neon.border}`, borderLeft: `2px solid ${neon.hex}` }}>
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 font-mono mb-2">Plain English</div>
          <p className="text-sm text-slate-200 leading-relaxed">{rec.ai_summary}</p>
        </div>
      )}
      {rec?.nvd_description && (
        <div className="rounded-xl p-4" style={{ background: "#09101E", border: `1px solid ${neon.border}` }}>
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 font-mono mb-2">NVD Description</div>
          <p className="text-sm text-slate-300 leading-relaxed">{rec.nvd_description}</p>
        </div>
      )}

      <SectionHeader count={data?.articles?.length} label="Articles mentioning this CVE" neon={neon} />
      {data?.articles?.length === 0 && <Empty text="No articles found in your intel database." />}
      {(data?.articles || []).map((a, i) => (
        <ArticleCtxCard key={a.id} article={a} primaryValue={cveId} defaultOpen={i === 0} neon={neon} />
      ))}
    </div>
  );
}

// ─── IOC content ──────────────────────────────────────────────────────────────

function IOCContent({ iocId }) {
  const neon = TYPE_NEON.ioc;
  const { data, isLoading } = useQuery({
    queryKey: ["entity-ioc", iocId],
    queryFn: () => entitiesApi.ioc(iocId),
  });

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>;

  const ioc = data?.ioc;
  const primaryValue = ioc?.value;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Type"              value={ioc?.ioc_type?.toUpperCase() || "—"} neon={neon} />
        <Stat label="Other occurrences" value={data?.other_articles?.length || 0}   neon={neon} />
      </div>
      {ioc?.user_note && (
        <div className="text-sm text-slate-400 rounded-xl p-3" style={{ background: "#09101E", border: `1px solid ${neon.border}` }}>
          <span className="text-slate-600 text-xs font-mono">note: </span>{ioc.user_note}
        </div>
      )}

      {data?.article && (
        <>
          <SectionHeader count={1} label="Source article" neon={neon} />
          <ArticleCtxCard article={data.article} primaryValue={primaryValue} defaultOpen neon={neon} />
        </>
      )}

      {data?.other_articles?.length > 0 && (
        <>
          <SectionHeader count={data.other_articles.length} label="Other articles with this value" neon={neon} />
          {data.other_articles.map(a => (
            <ArticleCtxCard key={a.id} article={a} primaryValue={primaryValue} neon={neon} />
          ))}
        </>
      )}
    </div>
  );
}

// ─── Actor content ────────────────────────────────────────────────────────────

function ActorContent({ actorId }) {
  const neon = TYPE_NEON.actor;
  const { data, isLoading } = useQuery({
    queryKey: ["entity-actor", actorId],
    queryFn: () => entitiesApi.actor(actorId),
  });

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>;

  const actor = data?.actor;
  const primaryValue = actor?.name;

  return (
    <div className="space-y-4">
      {actor?.aliases?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {actor.aliases.map(a => (
            <span key={a} className="text-xs font-mono px-2 py-0.5 rounded-md" style={{ background: neon.dim, border: `1px solid ${neon.border}`, color: "#CC00FF" }}>
              {a}
            </span>
          ))}
        </div>
      )}
      <SectionHeader count={data?.articles?.length} label="Articles mentioning this actor" neon={neon} />
      {data?.articles?.length === 0 && <Empty text="No articles found in your intel database." />}
      {(data?.articles || []).map((a, i) => (
        <ArticleCtxCard key={a.id} article={a} primaryValue={primaryValue} defaultOpen={i === 0} neon={neon} />
      ))}
    </div>
  );
}

// ─── Modal shell ──────────────────────────────────────────────────────────────

export default function EntityModal({ type, id, label, onClose }) {
  const modalRef = useRef(null);
  useFocusTrap(modalRef);

  useEffect(() => {
    const h = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const neon = TYPE_NEON[type] || TYPE_NEON.ioc;
  const meta = TYPE_META[type] || { label: type };
  const titleId = "entity-modal-title";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm" />

      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-2xl max-h-[88vh] flex flex-col bg-navy-800 rounded-2xl overflow-hidden"
        style={{
          border: `1px solid ${neon.border}`,
          boxShadow: "0 25px 50px rgba(0,0,0,0.8)",
        }}
      >
        {/* Neon top accent line */}
        <div style={{ height: 2, background: `linear-gradient(90deg, ${neon.hex} 0%, ${neon.border} 60%, transparent 100%)`, flexShrink: 0 }} />

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-navy-border flex-shrink-0">
          <span
            className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded font-mono"
            style={{
              color: neon.hex,
              background: neon.dim,
              border: `1px solid ${neon.border}`,
            }}
          >
            {meta.label}
          </span>
          <h2 id={titleId} className="text-sm font-semibold text-white font-mono truncate flex-1">{label}</h2>
          {(type === "actor" || type === "cve") && (
            <WatchButton itemType={type} value={label} neon={neon} />
          )}
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-slate-500 hover:text-slate-200 transition-colors p-1 rounded-lg hover:bg-navy-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
            style={{ "--tw-outline-color": neon.hex }}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {type === "cve"   && <CVEContent   cveId={id}   />}
          {type === "ioc"   && <IOCContent   iocId={id}   />}
          {type === "actor" && <ActorContent actorId={id} />}
        </div>
      </div>
    </div>
  );
}
