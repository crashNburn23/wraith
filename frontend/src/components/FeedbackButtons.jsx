import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { feedback as feedbackApi } from "../lib/api";

const STATIC_REASON_TAGS = [
  { key: "too_vague",      label: "too vague"      },
  { key: "not_actionable", label: "not actionable" },
];

function buildReasonTags(article) {
  const tags = [];
  if (article?.threat_category) {
    tags.push({ key: "wrong_category", label: `not my area: ${article.threat_category.toLowerCase()}` });
  }
  if (article?.sector_targets?.length) {
    tags.push({ key: "wrong_sector", label: "not my sector" });
  }
  return [...tags, ...STATIC_REASON_TAGS];
}

export default function FeedbackButtons({ articleId, article, initialRating = null, initialReasonTags = null }) {
  const qc = useQueryClient();
  const [rated, setRated] = useState(initialRating);
  const [reasonTags, setReasonTags] = useState(initialReasonTags || []);
  const [error, setError] = useState(null);
  const [savingTags, setSavingTags] = useState(false);

  useEffect(() => { setRated(initialRating); }, [initialRating]);
  useEffect(() => { setReasonTags(initialReasonTags || []); }, [initialReasonTags]);

  const rateMut = useMutation({
    mutationFn: ({ rating }) => feedbackApi.rate(articleId, rating),
    onSuccess: (_, { rating }) => {
      setError(null);
      setRated(rating);
      if (rating !== -1) setReasonTags([]);
      qc.invalidateQueries({ queryKey: ["bulletin-today"] });
      qc.invalidateQueries({ queryKey: ["feedback-signal"] });
    },
    onError: (e) => setError(e.response?.data?.detail || "Could not save rating"),
  });

  const toggleTag = async (key) => {
    if (savingTags) return;
    const previous = reasonTags;
    const next = reasonTags.includes(key)
      ? reasonTags.filter(t => t !== key)
      : [...reasonTags, key];
    setReasonTags(next);
    setError(null);
    setSavingTags(true);
    try {
      await feedbackApi.setReasons(articleId, next);
      qc.invalidateQueries({ queryKey: ["feedback-signal"] });
    } catch (e) {
      setReasonTags(previous);
      setError(e.response?.data?.detail || "Could not save reason tags");
    } finally {
      setSavingTags(false);
    }
  };

  const availableTags = buildReasonTags(article);

  const btn = (rating, emoji, hoverCls, activeCls) => (
    <button
      onClick={() => { if (rated !== rating) rateMut.mutate({ rating }); }}
      disabled={rateMut.isPending}
      className={`px-2 py-1 rounded text-sm transition-colors ${rated === rating ? activeCls : `text-slate-500 hover:${hoverCls}`}`}
      title={rating === 1 ? "Relevant" : "Not relevant"}
    >
      {emoji}
    </button>
  );

  return (
    <div>
      <div className="flex items-center gap-0.5">
        {btn(1,  "👍", "bg-emerald-900/40 text-emerald-400", "bg-emerald-900/50 text-emerald-300")}
        {btn(-1, "👎", "bg-red-900/40 text-red-400",        "bg-red-900/50 text-red-300")}
      </div>
      {rated === -1 && (
        <div className="mt-1.5 flex flex-wrap gap-1 items-center">
          <span className="text-[9px] text-slate-600 font-mono select-none">why?</span>
          {availableTags.map(tag => (
            <button
              key={tag.key}
              onClick={() => toggleTag(tag.key)}
              disabled={savingTags}
              className={`text-[9px] px-1.5 py-0.5 rounded font-mono transition-colors border ${
                reasonTags.includes(tag.key)
                  ? "bg-red-900/40 text-red-300 border-red-500/40"
                  : "bg-navy-800/60 text-slate-600 border-slate-700/40 hover:text-slate-400 hover:border-slate-600/60"
              }`}
            >
              {tag.label}
            </button>
          ))}
        </div>
      )}
      {error && <p className="mt-1 text-[10px] text-red-400 font-mono">{error}</p>}
    </div>
  );
}
