import { useQuery, useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { settings as settingsApi, feedback as feedbackApi } from "../lib/api";
import { Spinner } from "../components/ui";
import { timeAgo } from "../lib/utils";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function SignalBadge({ source, rating }) {
  if (source === "dismissed") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-mono text-slate-500 bg-navy-800 border border-slate-600/30 px-1.5 py-0.5 rounded" title="Dismissed — counts as implicit −1">
        — dismissed
      </span>
    );
  }
  if (rating > 0) {
    return (
      <span className="inline-flex items-center text-[10px] font-bold font-mono text-emerald-400 bg-emerald-900/30 px-1.5 py-0.5 rounded">
        👍 relevant
      </span>
    );
  }
  return (
    <span className="inline-flex items-center text-[10px] font-bold font-mono text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">
      👎 not relevant
    </span>
  );
}

function FeatureTags({ features }) {
  if (!features) return null;
  const tags = [];
  if (features.threat_category) {
    tags.push(
      <span key="cat" className="text-[10px] font-mono bg-blue-900/30 text-blue-300 border border-blue-500/20 px-1.5 py-0.5 rounded">
        {features.threat_category}
      </span>
    );
  }
  (features.ttps || []).forEach(t => tags.push(
    <span key={`ttp-${t}`} className="text-[10px] font-mono bg-emerald-900/30 text-emerald-300 border border-emerald-500/20 px-1.5 py-0.5 rounded">{t}</span>
  ));
  (features.actors || []).forEach(a => tags.push(
    <span key={`act-${a}`} className="text-[10px] font-mono bg-violet-900/30 text-violet-300 border border-violet-500/20 px-1.5 py-0.5 rounded">{a}</span>
  ));
  (features.sectors || []).forEach(s => tags.push(
    <span key={`sec-${s}`} className="text-[10px] font-mono bg-orange-900/30 text-orange-300 border border-orange-500/20 px-1.5 py-0.5 rounded">{s}</span>
  ));
  if (tags.length === 0) {
    return <span className="text-[10px] text-slate-600 italic">no enriched features</span>;
  }
  return <div className="flex flex-wrap gap-1 mt-1">{tags}</div>;
}

// ─── Preference summary ───────────────────────────────────────────────────────

function PreferenceSummary({ hasData }) {
  const mut = useMutation({ mutationFn: feedbackApi.summarize });

  return (
    <div className="rounded-xl border border-navy-border bg-navy-900 p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Preference Summary</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">LLM-generated insight from your rating history</p>
        </div>
        <button
          onClick={() => mut.mutate()}
          disabled={mut.isPending || !hasData}
          className="text-[11px] font-mono px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-40 disabled:cursor-not-allowed border-brand-500/30 text-brand-400 bg-brand-500/10 hover:bg-brand-500/20"
        >
          {mut.isPending ? <span className="flex items-center gap-1.5"><Spinner size="sm" /> Generating…</span> : "Generate"}
        </button>
      </div>

      {!hasData && (
        <p className="text-[11px] text-slate-600 italic">
          Rate some articles on the <Link to="/" className="text-brand-400 hover:text-brand-300">bulletin</Link> first to generate a summary.
        </p>
      )}

      {mut.isError && (
        <p className="text-[11px] text-red-400 font-mono">
          {mut.error?.response?.data?.detail || "LLM unavailable — make sure Ollama is running."}
        </p>
      )}

      {mut.isSuccess && mut.data?.summary && (
        <p className="text-sm text-slate-300 leading-relaxed">
          {mut.data.summary}
        </p>
      )}

      {!mut.isPending && !mut.isError && !mut.isSuccess && hasData && (
        <p className="text-[11px] text-slate-600 italic">
          Click Generate to get an AI-written summary of your interests.
        </p>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function FeedbackHistory() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["feedback-signal"],
    queryFn: settingsApi.feedbackSignal,
    staleTime: 30_000,
  });

  if (isLoading) {
    return <div className="flex justify-center mt-20"><Spinner size="lg" /></div>;
  }
  if (error) {
    return <div className="p-8 text-red-400">Error loading feedback history.</div>;
  }

  const { status, active_reason, rated_articles = [], config } = data || {};
  const isActive = status === "active";

  const explicit = rated_articles.filter(a => a.source === "explicit");
  const dismissed = rated_articles.filter(a => a.source === "dismissed");
  const thumbsUp = explicit.filter(a => a.rating > 0).length;
  const thumbsDown = explicit.filter(a => a.rating < 0).length;
  const hasData = rated_articles.length > 0;

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Feedback Loop</h1>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">How your ratings shape the bulletin</p>
        </div>
      </div>

      {/* Status banner */}
      <div className={`rounded-xl border px-4 py-3 mb-5 flex items-center gap-3 ${
        isActive
          ? "border-emerald-500/25 bg-emerald-500/5"
          : "border-amber-500/20 bg-amber-500/5"
      }`}>
        <span className={`text-[10px] font-mono font-semibold uppercase tracking-widest flex-shrink-0 ${
          isActive ? "text-emerald-400" : "text-amber-400/80"
        }`}>
          {isActive ? "● ACTIVE" : "○ INACTIVE"}
        </span>
        <span className={`text-[11px] font-mono ${isActive ? "text-emerald-300/70" : "text-amber-300/60"}`}>
          {active_reason}
        </span>
      </div>

      {/* Stats row */}
      {config && (
        <div className="grid grid-cols-2 gap-3 mb-5 sm:grid-cols-4">
          {[
            ["Signals",    rated_articles.length],
            ["👍 Liked",   thumbsUp],
            ["👎 Skipped", thumbsDown + dismissed.length],
            ["Lookback",   `${config.lookback_days}d`],
          ].map(([label, val]) => (
            <div key={label} className="rounded-lg border border-navy-border bg-navy-900 px-3 py-2">
              <div className="text-[10px] text-slate-600 font-mono uppercase tracking-wide">{label}</div>
              <div className="text-lg font-bold text-white font-mono">{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Preference summary (LLM insight from rating history) */}
      <PreferenceSummary hasData={hasData} />

      {/* Signal list */}
      {rated_articles.length === 0 ? (
        <div className="rounded-xl border border-navy-border bg-navy-900 px-6 py-10 text-center">
          <p className="text-slate-400 text-sm mb-1">No feedback yet</p>
          <p className="text-slate-600 text-xs">
            Rate articles on the <Link to="/" className="text-brand-400 hover:text-brand-300">bulletin</Link> using 👍 / 👎, or dismiss items with —
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-navy-border bg-navy-900 overflow-hidden">
          <div className="px-4 py-2 border-b border-navy-border">
            <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">
              Signals in window ({rated_articles.length})
            </span>
          </div>
          {rated_articles.map((a, i) => (
            <div
              key={a.article_id}
              className={`px-4 py-3 ${i < rated_articles.length - 1 ? "border-b border-navy-border" : ""}`}
            >
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 pt-0.5">
                  <SignalBadge source={a.source} rating={a.rating} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-300 leading-snug line-clamp-2">{a.title}</p>
                  <FeatureTags features={a.features} />
                  {a.reason_tags?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {a.reason_tags.map(tag => (
                        <span key={tag} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-red-900/30 text-red-400/70 border border-red-500/20">
                          {tag.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <span className="text-[10px] text-slate-600 font-mono flex-shrink-0 pt-0.5">
                  {a.rated_at ? timeAgo(a.rated_at) : ""}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="mt-4 text-[11px] text-slate-600 font-mono">
        Decay half-life: {config?.decay_half_life_days}d · Weight in score: ×{config?.weight_in_score} ·{" "}
        <Link to="/settings#scoring" className="text-brand-400/70 hover:text-brand-400">configure →</Link>
      </p>
    </div>
  );
}
