import { useState, useEffect, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { articles as articlesApi, enrich, feedback as feedbackApi } from "../lib/api";
import { Button, Spinner, Input, Textarea, SeverityBadge } from "../components/ui";
import { formatDate, categoryColor } from "../lib/utils";
import { useEntityModal } from "../components/EntityModalContext";
import HighlightedText, { buildHighlights } from "../components/HighlightedText";
import FeedbackButtons from "../components/FeedbackButtons";

// Muted accent palette for entity sections
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

function EditableRow({ value, onSave, onDelete, placeholder, onClickEntity }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(value || "");
  const [note, setNote] = useState("");

  if (!editing) {
    return (
      <div className="flex items-start gap-2 py-1.5 group">
        <span
          onClick={onClickEntity}
          className={`flex-1 text-sm text-slate-300 font-mono break-all ${onClickEntity ? "cursor-pointer hover:text-brand-300 hover:underline underline-offset-2" : ""}`}
        >
          {value}
        </span>
        <button onClick={() => setEditing(true)} className="opacity-0 group-hover:opacity-100 text-xs text-slate-600 hover:text-slate-300">✏</button>
        <button onClick={onDelete}              className="opacity-0 group-hover:opacity-100 text-xs text-slate-600 hover:text-red-400">✕</button>
      </div>
    );
  }

  return (
    <div className="bg-navy-900 rounded-lg p-2 space-y-2 my-1">
      <Input value={val} onChange={e => setVal(e.target.value)} placeholder={placeholder} className="w-full" />
      <Textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Note (optional)" rows={1} />
      <div className="flex gap-2">
        <Button size="sm" onClick={() => { onSave(val, note); setEditing(false); }}>Save</Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
      </div>
    </div>
  );
}

function EntitySection({ title, items, entityType, articleId }) {
  const qc = useQueryClient();
  const { open } = useEntityModal();

  const patch = useMutation({
    mutationFn: ({ id, body }) => enrich.patchEntity(entityType, id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["article", articleId] }),
  });

  if (!items || items.length === 0) {
    return (
      <div>
        <div className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest font-mono mb-1">{title}</div>
        <p className="text-xs text-slate-700 italic">None extracted</p>
      </div>
    );
  }

  return (
    <div>
      <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest font-mono mb-2">{title}</div>
      <div className="divide-y divide-navy-border">
        {items.map((item) => {
          const displayValue = item.value || item.technique_id || item.cve_id || item.actor_name || "—";
          const label = item.technique_name ? `${item.technique_id} · ${item.technique_name}` : displayValue;

          let clickHandler = null;
          if (entityType === "ioc")   clickHandler = () => open("ioc",   item.id,       item.value);
          if (entityType === "cve")   clickHandler = () => open("cve",   item.cve_id,   item.cve_id);
          if (entityType === "actor") clickHandler = () => open("actor", item.actor_id, item.actor_name);

          return (
            <EditableRow
              key={item.id}
              value={label}
              placeholder="Edit value"
              onClickEntity={clickHandler}
              onSave={(v, note) => patch.mutate({ id: item.id, body: { value: v, user_note: note || null } })}
              onDelete={() => patch.mutate({ id: item.id, body: { delete: true } })}
            />
          );
        })}
      </div>
    </div>
  );
}

export default function ArticleDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [rawOpen, setRawOpen] = useState(false);

  useEffect(() => { setRawOpen(false); }, [id]);

  const { data: article, isLoading, error } = useQuery({
    queryKey: ["article", id],
    queryFn: () => articlesApi.get(id),
  });

  const { data: feedbackData } = useQuery({
    queryKey: ["article-feedback", id],
    queryFn: () => feedbackApi.getForArticle(id),
  });

  const reEnrich = useMutation({
    mutationFn: () => enrich.runSingle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["article", id] }),
  });

  // Opening an article is an implicit positive signal — auto-acknowledge
  // unread articles so the feedback loop learns from what you actually read.
  useEffect(() => {
    let cancelled = false;
    feedbackApi.getReadStatus(id).then(({ status }) => {
      if (!cancelled && status === "unread") {
        feedbackApi.setReadStatus(id, "acknowledged").then(() => {
          qc.invalidateQueries({ queryKey: ["feedback-signal"] });
        });
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [id, qc]);

  // Keyboard: c/Esc=back, u=👍, n=👎 (d alias), m=dismiss+back (h alias), j/k=next/prev
  const goBack = useCallback(() => navigate("/"), [navigate]);

  useEffect(() => {
    const handler = (e) => {
      const t = e.target;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "c" || e.key === "Escape") { goBack(); return; }
      if (e.key === "u") { feedbackApi.rate(id, 1).then(() => qc.invalidateQueries({ queryKey: ["article-feedback", id] })); return; }
      if (e.key === "n" || e.key === "d") { feedbackApi.rate(id, -1).then(() => qc.invalidateQueries({ queryKey: ["article-feedback", id] })); return; }
      if (e.key === "m" || e.key === "h") {
        feedbackApi.setReadStatus(id, "dismissed").then(() => goBack());
        return;
      }
      if (e.key === "y") { navigator.clipboard?.writeText(article?.url || window.location.href); return; }
      if (e.key === "e") { setRawOpen(v => !v); return; }
      if (e.key === "j" || e.key === "k") {
        try {
          const navIds = JSON.parse(sessionStorage.getItem("bulletin-nav") || "[]");
          const idx = navIds.indexOf(id);
          if (idx === -1) return;
          const nextIdx = e.key === "j" ? idx + 1 : idx - 1;
          if (nextIdx >= 0 && nextIdx < navIds.length) navigate(`/articles/${navIds[nextIdx]}`);
        } catch {}
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [id, goBack, navigate, qc, article]);

  if (isLoading) return <div className="flex justify-center mt-20"><Spinner size="lg" /></div>;
  if (error || !article) return <div className="p-8 text-red-400 font-mono">Article not found.</div>;

  const entityCtx = {
    iocs: article.iocs,
    cve_mentions: article.cve_mentions,
    actors: article.article_actors?.map(a => ({ name: a.actor_name, ...a })),
    ttps: article.ttp_tags,
  };
  const highlights = buildHighlights(entityCtx, null);

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      {/* Back */}
      <div className="mb-4">
        <Link to="/" className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white font-mono tracking-wide transition-colors">
          ← Bulletin
        </Link>
      </div>

      {/* Meta badges */}
      <div className="flex flex-wrap items-start gap-2 mb-4">
        {article.threat_category && (
          <span className={`text-[10px] font-semibold px-2 py-1 rounded-md font-mono tracking-wide ${categoryColor(article.threat_category)}`}>
            {article.threat_category}
          </span>
        )}
        <SeverityBadge score={article.ai_severity_score} prefix="severity" title="AI-assigned severity score (0–100)" />
        <span className="text-[11px] text-slate-500 font-mono">{formatDate(article.published_at)}</span>
        <a href={article.url} target="_blank" rel="noopener noreferrer"
          className="text-[11px] font-mono ml-auto hover:underline underline-offset-2"
          style={{ color: NEON.brand.hex }}>
          source ↗
        </a>
      </div>

      {/* Title */}
      <h1 className="text-2xl font-bold text-white mb-3 leading-snug">{article.title}</h1>

      {/* Feedback */}
      <div className="mb-5">
        <FeedbackButtons
          articleId={id}
          article={article}
          initialRating={feedbackData?.rating ?? null}
          initialReasonTags={[]}
        />
      </div>

      {/* AI Summary */}
      {article.ai_summary && (
        <div className="p-4 mb-6 rounded-xl" style={neonCard(NEON.brand)}>
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 font-mono mb-2">AI Summary</div>
          <p className="text-slate-300 leading-relaxed text-sm">{article.ai_summary}</p>
        </div>
      )}

      {/* Entity grid */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* IOCs + CVEs — cyan */}
        <div className="p-4 rounded-xl space-y-4" style={neonCard(NEON.cyan)}>
          <EntitySection title="IOCs"  items={article.iocs}         entityType="ioc" articleId={id} />
          <EntitySection title="CVEs"  items={article.cve_mentions} entityType="cve" articleId={id} />
        </div>
        {/* TTPs + Actors — violet */}
        <div className="p-4 rounded-xl space-y-4" style={neonCard(NEON.violet)}>
          <EntitySection title="MITRE TTPs"    items={article.ttp_tags}      entityType="ttp"   articleId={id} />
          <EntitySection title="Threat Actors" items={article.article_actors} entityType="actor" articleId={id} />
        </div>
      </div>

      {/* Re-enrich */}
      <div className="flex items-center gap-3 mb-5">
        <Button size="sm" variant="secondary" onClick={() => reEnrich.mutate()} disabled={reEnrich.isPending}>
          {reEnrich.isPending ? <><Spinner size="sm" /> Re-enriching…</> : "Re-enrich"}
        </Button>
        {article.enrichment_status && (
          <span className="text-[11px] text-slate-600 font-mono">status: {article.enrichment_status}</span>
        )}
      </div>

      {/* Keyboard hint */}
      <p className="mb-5 text-[10px] font-mono text-slate-700">
        c close · j/k next/prev · u/n rate · m dismiss · e expand text · y copy url · ? help
      </p>

      {/* Scraped text — gated behind disclosure, [e] toggles */}
      {article.scraped_text && (
        <details
          className="group"
          open={rawOpen}
          onToggle={(e) => setRawOpen(e.currentTarget.open)}
        >
          <summary className="text-[11px] text-slate-600 hover:text-slate-400 font-mono cursor-pointer select-none list-none flex items-center gap-1.5 mb-2">
            <span className="transition-transform group-open:rotate-90 inline-block">▶</span>
            {rawOpen ? "Hide full article text [e]" : "Show full article text [e]"}
          </summary>
          <div className="p-4 rounded-xl mt-2" style={neonCard(NEON.brand)}>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 font-mono mb-3">Raw Source Text</div>
            <HighlightedText text={article.scraped_text} highlights={highlights} primaryValue={null} />
          </div>
        </details>
      )}
    </div>
  );
}
