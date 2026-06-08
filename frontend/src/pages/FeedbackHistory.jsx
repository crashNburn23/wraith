import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { settings as settingsApi, feedback as feedbackApi } from "../lib/api";
import { Button, Spinner } from "../components/ui";
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

// ─── Interest Profile ─────────────────────────────────────────────────────────

const PROFILE_DIMS = [
  {
    key: "sectors",
    label: "Sectors",
    description: "Industries you protect or monitor",
    placeholder: "e.g. healthcare",
    color: "bg-blue-900/30 text-blue-300 border-blue-500/20",
  },
  {
    key: "threat_actors",
    label: "Threat Actors",
    description: "Groups you actively track",
    placeholder: "e.g. Lazarus Group",
    color: "bg-violet-900/30 text-violet-300 border-violet-500/20",
  },
  {
    key: "categories",
    label: "Threat Categories",
    description: "Types of threats you care about",
    placeholder: "e.g. ransomware",
    color: "bg-orange-900/30 text-orange-300 border-orange-500/20",
  },
  {
    key: "keywords",
    label: "Keywords",
    description: "Matched against title and summary",
    placeholder: "e.g. VMware, Active Directory",
    color: "bg-emerald-900/30 text-emerald-300 border-emerald-500/20",
  },
];

function TagInput({ value = [], onChange, placeholder, color }) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const trimmed = draft.trim();
    if (!trimmed || value.includes(trimmed)) { setDraft(""); return; }
    onChange([...value, trimmed]);
    setDraft("");
  };

  const remove = (tag) => onChange(value.filter(t => t !== tag));

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {value.map(tag => (
          <span key={tag} className={`inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded border ${color}`}>
            {tag}
            <button onClick={() => remove(tag)} className="opacity-50 hover:opacity-100 leading-none">×</button>
          </span>
        ))}
        {value.length === 0 && <span className="text-xs text-slate-600 italic">None set</span>}
      </div>
      <div className="flex gap-2">
        <input
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          className="flex-1 bg-navy-800 border border-navy-border rounded px-2 py-1 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button onClick={add} disabled={!draft.trim()} className="text-xs px-2 py-1 rounded border border-navy-border text-slate-400 hover:text-slate-100 disabled:opacity-30">Add</button>
      </div>
    </div>
  );
}

function ProfileSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["user-profile"], queryFn: settingsApi.getProfile });
  const [profile, setProfile] = useState(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data && !dirty) setProfile(data);
  }, [data, dirty]);

  const saveMut = useMutation({
    mutationFn: (body) => settingsApi.updateProfile(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["user-profile"] }); setDirty(false); },
  });

  const update = (key, val) => { setProfile(p => ({ ...p, [key]: val })); setDirty(true); };

  if (isLoading || !profile) return (
    <div className="rounded-xl border border-navy-border bg-navy-900 p-8 mb-4 flex justify-center">
      <Spinner />
    </div>
  );

  const totalTags = Object.values(profile).flat().length;

  return (
    <div className="rounded-xl border border-navy-border bg-navy-900 p-4 mb-4" id="profile">
      <div className="flex items-start justify-between mb-1">
        <div>
          <h2 className="text-sm font-semibold text-white">Interest Profile</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Drives the Profile Match score component — no ratings needed
          </p>
        </div>
        {totalTags === 0 && (
          <span className="text-[10px] font-mono text-amber-400 border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 rounded">
            ○ EMPTY — profile match = 0
          </span>
        )}
      </div>

      <div className="mt-4 space-y-5">
        {PROFILE_DIMS.map(({ key, label, description, placeholder, color }) => (
          <div key={key}>
            <div className="flex items-baseline gap-2 mb-2">
              <span className="text-sm text-slate-300">{label}</span>
              <span className="text-xs text-slate-500">{description}</span>
            </div>
            <TagInput
              value={profile[key] || []}
              onChange={val => update(key, val)}
              placeholder={placeholder}
              color={color}
            />
          </div>
        ))}
      </div>

      <div className="mt-5 flex gap-2 items-center">
        <Button onClick={() => saveMut.mutate(profile)} disabled={!dirty || saveMut.isPending}>
          {saveMut.isPending ? <><Spinner size="sm" /> Saving…</> : "Save Profile"}
        </Button>
        {dirty && <span className="text-xs text-yellow-400">Unsaved changes</span>}
        {saveMut.isSuccess && !dirty && <span className="text-xs text-green-400">Saved — rebuild bulletin to apply</span>}
      </div>
    </div>
  );
}

// ─── Natural language feedback ────────────────────────────────────────────────

const PROFILE_LABELS = {
  sectors:       { label: "Sectors",       color: "text-orange-300 bg-orange-900/30 border-orange-500/20" },
  categories:    { label: "Categories",    color: "text-blue-300 bg-blue-900/30 border-blue-500/20"       },
  keywords:      { label: "Keywords",      color: "text-emerald-300 bg-emerald-900/30 border-emerald-500/20" },
  threat_actors: { label: "Threat Actors", color: "text-violet-300 bg-violet-900/30 border-violet-500/20" },
};

function NaturalLanguageInput() {
  const [text, setText] = useState("");
  const mut = useMutation({ mutationFn: () => feedbackApi.applyNote(text) });

  const anyAdded = mut.data && Object.values(mut.data.added).some(arr => arr.length > 0);

  return (
    <div className="rounded-xl border border-navy-border bg-navy-900 p-4 mb-4">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-white">Natural Language Feedback</h2>
        <p className="text-[11px] text-slate-500 mt-0.5">
          Describe what you care about in plain English — the system will extract and add preferences to your profile
        </p>
      </div>

      <textarea
        value={text}
        onChange={e => { setText(e.target.value); mut.reset(); }}
        placeholder="e.g. I'm most interested in ransomware targeting healthcare and critical infrastructure. I'd also like to see more on living-off-the-land techniques and APT28 activity…"
        rows={3}
        className="w-full bg-navy-800 border border-navy-border rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-500/50 resize-none font-sans leading-relaxed mb-2"
      />

      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0 mr-3">
          {mut.isError && (
            <p className="text-[11px] text-red-400 font-mono">
              {mut.error?.response?.data?.detail || "Something went wrong — try rephrasing."}
            </p>
          )}
          {mut.isSuccess && !anyAdded && (
            <p className="text-[11px] text-slate-500 font-mono">Nothing new — those preferences are already in your profile.</p>
          )}
        </div>
        <button
          onClick={() => mut.mutate()}
          disabled={mut.isPending || !text.trim()}
          className="flex-shrink-0 text-[11px] font-mono px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-40 disabled:cursor-not-allowed border-brand-500/30 text-brand-400 bg-brand-500/10 hover:bg-brand-500/20"
        >
          {mut.isPending ? <span className="flex items-center gap-1.5"><Spinner size="sm" />Applying…</span> : "Apply to profile"}
        </button>
      </div>

      {mut.isSuccess && anyAdded && (
        <div className="mt-3 pt-3 border-t border-navy-border">
          <p className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-2">Added to your profile</p>
          <div className="space-y-1.5">
            {Object.entries(PROFILE_LABELS).map(([key, meta]) => {
              const added = mut.data.added[key] || [];
              if (!added.length) return null;
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-600 font-mono w-24 flex-shrink-0">{meta.label}</span>
                  <div className="flex flex-wrap gap-1">
                    {added.map(v => (
                      <span key={v} className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${meta.color}`}>
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
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

      {/* Interest Profile (explicit config — drives scoring independently of ratings) */}
      <ProfileSection />

      {/* Natural language shortcut to populate profile */}
      <NaturalLanguageInput />

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
