import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { feedback as feedbackApi } from "../lib/api";
import { categoryColor } from "../lib/utils";
import { isTypingTarget } from "../lib/shortcuts";

// Full-screen one-article-at-a-time triage flow. Single-key actions, every
// action auto-advances — the fastest way to feed the learning loop.
export default function TriageMode({ items, onClose }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [idx, setIdx] = useState(0);
  const [stats, setStats] = useState({ liked: 0, disliked: 0, dismissed: 0, skipped: 0 });
  const done = idx >= items.length;
  const item = items[idx];

  const advance = useCallback((statKey) => {
    if (statKey) setStats(s => ({ ...s, [statKey]: s[statKey] + 1 }));
    setIdx(i => i + 1);
  }, []);

  const act = useCallback((action) => {
    if (!item) return;
    const id = item.article.id;
    if (action === "like")    { feedbackApi.rate(id, 1);  advance("liked"); }
    if (action === "dislike") { feedbackApi.rate(id, -1); advance("disliked"); }
    if (action === "dismiss") { feedbackApi.setReadStatus(id, "dismissed"); advance("dismissed"); }
    if (action === "skip")    { advance("skipped"); }
  }, [item, advance]);

  useEffect(() => {
    const handler = (e) => {
      if (isTypingTarget(e)) return;
      if (e.key === "Escape" || e.key === "q" || e.key === "t") { e.preventDefault(); finish(); return; }
      if (done) { if (e.key === "Enter") finish(); return; }
      if (e.key === "u") { e.preventDefault(); act("like"); }
      if (e.key === "n") { e.preventDefault(); act("dislike"); }
      if (e.key === "m") { e.preventDefault(); act("dismiss"); }
      if (e.key === "j") { e.preventDefault(); act("skip"); }
      if (e.key === "o" || e.key === "Enter") {
        e.preventDefault();
        if (item) navigate(`/articles/${item.article.id}`);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [act, done, item]);

  const finish = () => {
    qc.invalidateQueries({ queryKey: ["bulletin-today"] });
    qc.invalidateQueries({ queryKey: ["feedback-signal"] });
    onClose();
  };

  const Key = ({ k }) => (
    <kbd className="text-[10px] font-mono text-slate-200 bg-navy-900 border border-navy-border rounded px-1.5 py-0.5">{k}</kbd>
  );

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-navy-950">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-navy-border flex-shrink-0">
        <span className="text-[10px] font-mono font-bold uppercase tracking-widest px-1.5 py-0.5 rounded"
          style={{ background: "rgba(85,88,212,0.15)", color: "rgba(85,88,212,0.9)", border: "1px solid rgba(85,88,212,0.3)" }}>
          TRIAGE MODE
        </span>
        <span className="text-xs font-mono text-slate-500 tabular-nums">
          {done ? `${items.length} / ${items.length}` : `${idx + 1} / ${items.length}`}
        </span>
        <button onClick={finish} className="text-[11px] font-mono text-slate-600 hover:text-slate-300 transition-colors">
          [esc] exit
        </button>
      </div>

      {/* Progress bar */}
      <div className="h-0.5 bg-navy-800 flex-shrink-0">
        <div className="h-full bg-brand-500 transition-all duration-200"
          style={{ width: `${(Math.min(idx, items.length) / Math.max(items.length, 1)) * 100}%` }} />
      </div>

      {/* Body */}
      <div className="flex-1 flex items-center justify-center p-8 overflow-y-auto">
        {done ? (
          <div className="text-center max-w-sm">
            <div className="text-3xl mb-4">✓</div>
            <h2 className="text-lg font-bold text-white mb-4">Triage complete</h2>
            <div className="grid grid-cols-2 gap-2 mb-6 text-left">
              {[
                ["👍 Liked", stats.liked, "text-emerald-400"],
                ["👎 Disliked", stats.disliked, "text-red-400"],
                ["Dismissed", stats.dismissed, "text-slate-400"],
                ["Skipped", stats.skipped, "text-slate-500"],
              ].map(([label, val, cls]) => (
                <div key={label} className="bg-navy-900 border border-navy-border rounded-lg px-3 py-2">
                  <div className="text-[10px] text-slate-600 font-mono">{label}</div>
                  <div className={`text-xl font-bold font-mono ${cls}`}>{val}</div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-slate-500 font-mono mb-4">
              Every rating sharpens tomorrow's ranking.
            </p>
            <button onClick={finish}
              className="text-xs font-mono px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white transition-colors">
              Back to bulletin [Enter]
            </button>
          </div>
        ) : (
          <div className="max-w-xl w-full">
            <div className="flex items-center gap-2 mb-3">
              {item.article.threat_category && (
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded font-mono ${categoryColor(item.article.threat_category)}`}>
                  {item.article.threat_category}
                </span>
              )}
              <span className="text-[10px] font-mono text-slate-500">
                score {Math.round(item.score.computed_score * 100)}
              </span>
              {item.article.ai_severity_score != null && (
                <span className="text-[10px] font-mono text-slate-600">sev {Math.round(item.article.ai_severity_score)}</span>
              )}
            </div>
            <h2 className="text-xl font-bold text-white leading-snug mb-6">{item.article.title}</h2>
          </div>
        )}
      </div>

      {/* Action bar */}
      {!done && (
        <div className="flex items-center justify-center gap-5 px-6 py-4 border-t border-navy-border flex-shrink-0 flex-wrap">
          <span className="flex items-center gap-1.5 text-[11px] text-slate-400"><Key k="u" /> 👍 like</span>
          <span className="flex items-center gap-1.5 text-[11px] text-slate-400"><Key k="n" /> 👎 nope</span>
          <span className="flex items-center gap-1.5 text-[11px] text-slate-400"><Key k="m" /> dismiss</span>
          <span className="flex items-center gap-1.5 text-[11px] text-slate-400"><Key k="j" /> skip</span>
          <span className="flex items-center gap-1.5 text-[11px] text-slate-400"><Key k="o" /> open</span>
        </div>
      )}
    </div>
  );
}
