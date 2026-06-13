import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { bulletin } from "../lib/api";

function Bar({ value, color }) {
  const pct = Math.min(100, value * 100);
  return (
    <div className="flex-1 bg-navy-700 rounded-full h-1 overflow-hidden">
      <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function ComponentRow({ label, weighted, barColor, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => children && setOpen(!open)}
        className={`w-full flex items-center gap-3 py-1.5 text-left group ${children ? "cursor-pointer" : ""}`}
      >
        <span className="text-[11px] text-slate-400 w-36 truncate flex-shrink-0">{label}</span>
        <Bar value={weighted} color={barColor} />
        <span className="text-[11px] font-mono text-slate-300 w-10 text-right">{weighted.toFixed(3)}</span>
        {children && (
          <span className="text-slate-600 group-hover:text-slate-400 text-xs ml-1">{open ? "▲" : "▼"}</span>
        )}
      </button>
      {open && children && (
        <div className="ml-36 pl-4 border-l border-navy-border mb-2">{children}</div>
      )}
    </div>
  );
}

function FeedbackArticles({ articles }) {
  if (!articles || articles.length === 0) {
    return <p className="text-xs text-slate-500 py-1">No overlapping past-rated articles.</p>;
  }
  return (
    <div className="space-y-1.5 py-1">
      <p className="text-xs text-slate-500 mb-2">Articles that drove this signal:</p>
      {articles.map((a, i) => (
        <div key={i} className="text-xs bg-navy-700 rounded-lg px-2 py-1.5">
          <div className="flex items-start justify-between gap-2">
            <span className="text-slate-300 leading-snug">{a.title}</span>
            <span className={`flex-shrink-0 font-mono font-bold ${a.feedback_rating > 0 ? "text-emerald-400" : "text-red-400"}`}>
              {a.feedback_rating > 0 ? "+1" : "−1"}
            </span>
          </div>
          <div className="flex flex-wrap gap-1 mt-1">
            {a.overlap_reasons?.map((r, j) => (
              <span key={j} className="bg-navy-600 text-slate-400 rounded px-1.5 py-0.5 text-[10px]">{r}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function AxisGroup({ label, _color, hex, subtotal, children }) {
  return (
    <div className="rounded-lg overflow-hidden mb-2" style={{ border: `1px solid ${hex}22` }}>
      <div className="flex items-center justify-between px-3 py-1.5" style={{ background: `${hex}0D` }}>
        <span className="text-[10px] font-mono font-semibold uppercase tracking-widest" style={{ color: hex }}>
          {label}
        </span>
        <span className="text-[11px] font-mono font-bold" style={{ color: hex }}>
          {subtotal.toFixed(3)}
        </span>
      </div>
      <div className="px-3 py-1">
        {children}
      </div>
    </div>
  );
}

// Exported panel — used by BulletinCard
export function ScoreBreakdownPanel({ itemId, score }) {
  const s = score;
  const { data: full } = useQuery({
    queryKey: ["score-breakdown", itemId],
    queryFn: () => bulletin.scoreBreakdown(itemId),
    staleTime: 60_000,
  });

  const w = full?.weights ?? {
    ai_severity: 0.35, feedback_signal: 0.20, profile_match: 0.25, kev_bonus: 0.10, recency: 0.10,
  };

  const threatSubtotal  = (s.score_ai_severity || 0) + (s.score_kev_bonus || 0);
  const relevSubtotal   = (s.score_feedback_signal || 0) + (s.score_profile_match || 0) + (s.score_recency || 0);

  const fbArticles = s.feedback_signal_articles || full?.components?.feedback_signal?.contributing_articles;

  return (
    <div className="space-y-0">
      {/* Threat axis */}
      <AxisGroup label="Threat" hex="#C02040" subtotal={threatSubtotal}>
        <ComponentRow label={`AI Severity ×${w.ai_severity}`}  weighted={s.score_ai_severity || 0} barColor="bg-red-500" />
        <ComponentRow label={`KEV Bonus ×${w.kev_bonus}`}      weighted={s.score_kev_bonus || 0}   barColor="bg-orange-500" />
      </AxisGroup>

      {/* Relevance axis */}
      <AxisGroup label="Relevance" hex="#7722AA" subtotal={relevSubtotal}>
        <ComponentRow label={`Feedback ×${w.feedback_signal}`}   weighted={s.score_feedback_signal || 0} barColor="bg-violet-500">
          <FeedbackArticles articles={fbArticles} />
        </ComponentRow>
        <ComponentRow label={`Profile ×${w.profile_match}`}      weighted={s.score_profile_match || 0}   barColor="bg-fuchsia-500" />
        <ComponentRow label={`Recency ×${w.recency}`}            weighted={s.score_recency || 0}         barColor="bg-brand-500" />
      </AxisGroup>

      <div className="pt-1 flex items-center justify-between">
        <div className="text-[10px] text-slate-600 flex gap-3 font-mono">
          <span>sev {(s.raw_ai_severity * 100).toFixed(0)}/100</span>
          <span>fb {(s.raw_feedback_signal * 100).toFixed(0)}%</span>
          <span>profile {((s.raw_profile_match || 0) * 100).toFixed(0)}%</span>
          <span>rec {(s.raw_recency_factor * 100).toFixed(0)}%</span>
        </div>
        <a href="/settings#scoring" className="text-[10px] text-slate-600 hover:text-brand-400">edit weights →</a>
      </div>
    </div>
  );
}

// Self-contained trigger + panel (used in non-bulletin contexts)
export default function ScoreBreakdown({ itemId, score }) {
  const [showFull, setShowFull] = useState(false);
  const s = score;
  if (!s) return null;

  const val = (s.computed_score * 100).toFixed(0);
  const colorCls = s.computed_score >= 0.7 ? "text-red-400" : s.computed_score >= 0.5 ? "text-orange-400" : s.computed_score >= 0.3 ? "text-amber-400" : "text-slate-400";

  return (
    <div>
      <button onClick={() => setShowFull(v => !v)} className="flex items-center gap-1.5 group">
        <span className={`text-lg font-bold font-mono ${colorCls}`}>{val}</span>
        <span className="text-xs text-slate-600 group-hover:text-slate-400">{showFull ? "▲" : "▼"} score</span>
      </button>
      {showFull && (
        <div className="mt-2 bg-navy-900 border border-navy-border rounded-xl p-3">
          <ScoreBreakdownPanel itemId={itemId} score={score} />
        </div>
      )}
    </div>
  );
}
