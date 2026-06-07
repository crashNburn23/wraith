import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { sources as sourcesApi, ingest, enrich, bulletin as bulletinApi, settings as settingsApi, cve } from "../lib/api";
import { Button, Input, Card, Spinner, Divider } from "../components/ui";

// ─── Ingest Tracker ──────────────────────────────────────────────────────────

function IngestTracker() {
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["ingest-status"],
    queryFn: ingest.status,
    refetchInterval: (query) => {
      const run = query.state.data?.current_run;
      return run?.status === "running" ? 3000 : 15000;
    },
  });

  const runMut = useMutation({
    mutationFn: ingest.run,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ingest-status"] }),
  });

  const run = data?.current_run;
  const articles = data?.articles;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-300">Ingest</h3>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending || run?.status === "running"}
        >
          {run?.status === "running" ? <><Spinner size="sm" /> Running…</> : "Run Now"}
        </Button>
      </div>

      {/* Article counts */}
      {articles && (
        <div className="flex gap-3 text-xs mb-3 flex-wrap">
          <span className="text-slate-400">Total: <span className="text-white font-mono">{articles.total}</span></span>
          <span className="text-yellow-400">Pending: <span className="font-mono">{articles.pending}</span></span>
          <span className="text-green-400">Enriched: <span className="font-mono">{articles.enriched}</span></span>
          <span className="text-slate-500">No text: <span className="font-mono">{articles.no_text}</span></span>
          {articles.error > 0 && <span className="text-red-400">Errors: <span className="font-mono">{articles.error}</span></span>}
        </div>
      )}

      {/* Last / current run */}
      {run && (
        <div className="bg-navy-900/80 rounded p-3 text-xs">
          <div className="flex items-center gap-2 mb-2">
            <RunStatusBadge status={run.status} />
            <span className="text-slate-500">{run.elapsed_seconds}s elapsed</span>
            <span className="text-slate-600 ml-auto">{new Date(run.started_at).toLocaleTimeString()}</span>
          </div>
          {run.source_results?.length > 0 && (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {run.source_results.map((s, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${s.status === "ok" ? "bg-green-500" : "bg-red-500"}`} />
                  <span className="text-slate-300 truncate flex-1">{s.name}</span>
                  {s.status === "ok" ? (
                    <span className="text-slate-500 flex-shrink-0">
                      +{s.new_articles} new · {s.duplicates} dup
                    </span>
                  ) : (
                    <span className="text-red-400 truncate max-w-xs" title={s.error}>{s.error}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Enrich Tracker ──────────────────────────────────────────────────────────

function EnrichTracker() {
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["enrich-status"],
    queryFn: enrich.status,
    refetchInterval: (query) => {
      const run = query.state.data?.current_run;
      return run?.status === "running" ? 2000 : 10000;
    },
  });

  const runMut = useMutation({
    mutationFn: enrich.run,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrich-status"] }),
    onError: (e) => alert(e.response?.data?.detail || "Failed to start enrichment"),
  });
  const pauseMut = useMutation({
    mutationFn: enrich.pause,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrich-status"] }),
  });
  const resumeMut = useMutation({
    mutationFn: enrich.resume,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrich-status"] }),
  });

  const run = data?.current_run;
  const isRunning = run?.status === "running";
  const isPaused = run?.status === "paused" || data?.paused;
  const pct = run?.total > 0 ? Math.round((run.processed / run.total) * 100) : 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-300">Enrich</h3>
        <div className="flex gap-1.5">
          {isRunning ? (
            <Button size="sm" variant="danger" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
              Pause
            </Button>
          ) : isPaused ? (
            <Button size="sm" variant="success" onClick={() => resumeMut.mutate()} disabled={resumeMut.isPending}>
              Resume
            </Button>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => runMut.mutate()} disabled={runMut.isPending}>
              Run Now
            </Button>
          )}
        </div>
      </div>

      {/* Pending count */}
      {data && (
        <div className="flex gap-3 text-xs mb-3 flex-wrap">
          <span className="text-yellow-400">Pending: <span className="font-mono">{data.pending_articles}</span></span>
          <span className="text-green-400">Enriched: <span className="font-mono">{data.enriched_articles}</span></span>
          {data.error_articles > 0 && <span className="text-red-400">Errors: <span className="font-mono">{data.error_articles}</span></span>}
        </div>
      )}

      {run && (
        <div className="bg-navy-900/80 rounded p-3 text-xs space-y-2">
          <div className="flex items-center gap-2">
            <RunStatusBadge status={run.status} />
            <span className="text-slate-500">{run.elapsed_seconds}s</span>
            {run.total > 0 && (
              <span className="text-slate-400 ml-auto">{run.processed}/{run.total}</span>
            )}
          </div>

          {/* Progress bar */}
          {run.total > 0 && (
            <div className="bg-navy-700 rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${run.status === "completed" ? "bg-green-500" : run.status === "paused" ? "bg-yellow-500" : "bg-brand-500"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          )}

          {/* Currently processing */}
          {run.current_title && (
            <div className="flex items-center gap-1.5 text-slate-400">
              <Spinner size="sm" />
              <span className="truncate">{run.current_title}</span>
            </div>
          )}

          {/* Stats */}
          <div className="flex gap-3 text-slate-500">
            <span className="text-green-400">✓ {run.succeeded}</span>
            {run.failed > 0 && <span className="text-red-400">✗ {run.failed}</span>}
          </div>

          {/* Error list */}
          {run.errors?.length > 0 && (
            <details>
              <summary className="text-red-400 cursor-pointer select-none">
                {run.errors.length} error{run.errors.length !== 1 ? "s" : ""}
              </summary>
              <div className="mt-1.5 space-y-1 max-h-40 overflow-y-auto">
                {run.errors.map((e, i) => (
                  <div key={i} className="bg-red-900/20 rounded px-2 py-1">
                    <div className="text-slate-300 truncate">{e.title}</div>
                    <div className="text-red-400 truncate">{e.error}</div>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function RunStatusBadge({ status }) {
  const styles = {
    running:   "bg-blue-900/50 text-blue-300",
    paused:    "bg-yellow-900/50 text-yellow-300",
    completed: "bg-green-900/50 text-green-300",
    error:     "bg-red-900/50 text-red-300",
    idle:      "bg-navy-800 text-slate-400",
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${styles[status] || styles.idle}`}>
      {status}
    </span>
  );
}

// ─── Scheduler Section ────────────────────────────────────────────────────────

const JOB_NEON = {
  ingest:   { hex: "#0088A8", dim: "rgba(0,136,168,0.05)",  border: "rgba(0,136,168,0.24)"  },
  enrich:   { hex: "#5558D4", dim: "rgba(85,88,212,0.05)",  border: "rgba(85,88,212,0.24)"  },
  cve_sync: { hex: "#B85018", dim: "rgba(184,80,24,0.05)",  border: "rgba(184,80,24,0.24)"  },
  bulletin: { hex: "#7722AA", dim: "rgba(119,34,170,0.05)", border: "rgba(119,34,170,0.22)" },
};

function timeUntil(isoString) {
  if (!isoString) return null;
  const diff = new Date(isoString) - Date.now();
  if (diff < 0) return "overdue";
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  if (h > 0) return `in ${h}h ${m}m`;
  return `in ${m}m`;
}

function SchedulerSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["scheduler-status"],
    queryFn: settingsApi.scheduler,
    refetchInterval: 60_000,
  });

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-white">Scheduler</h2>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">
            {data?.running
              ? <span className="text-emerald-400">● running</span>
              : <span className="text-red-400">○ stopped</span>}
          </p>
        </div>
        <span className="text-[10px] font-mono text-slate-600 uppercase tracking-widest">APScheduler</span>
      </div>

      {isLoading ? <Spinner /> : (
        <>
          <div className="grid grid-cols-2 gap-3 mb-4">
            {(data?.jobs || []).map(job => {
              const n = JOB_NEON[job.id] || JOB_NEON.ingest;
              const until = timeUntil(job.next_run);
              return (
                <div
                  key={job.id}
                  className="rounded-xl p-3"
                  style={{
                    background: "#09101E",
                    border: `1px solid ${n.border}`,
                    borderLeft: `2px solid ${n.hex}`,
                    boxShadow: `inset 2px 0 8px ${n.dim}`,
                  }}
                >
                  <div className="text-[10px] font-mono font-semibold uppercase tracking-widest mb-1" style={{ color: n.hex }}>
                    {job.name}
                  </div>
                  <div className="text-sm font-mono text-white font-bold">{job.schedule}</div>
                  {until && (
                    <div className="text-[11px] font-mono text-slate-500 mt-1">{until}</div>
                  )}
                  {!job.active && (
                    <div className="text-[10px] font-mono text-red-400 mt-1">not scheduled</div>
                  )}
                </div>
              );
            })}
          </div>
          {data?.note && (
            <p className="text-[11px] text-slate-600 font-mono leading-relaxed">{data.note}</p>
          )}
        </>
      )}
    </Card>
  );
}

// ─── Controls Card (ingest + enrich + other buttons) ─────────────────────────

function ControlsSection() {
  const qc = useQueryClient();
  const bulletinMut = useMutation({ mutationFn: bulletinApi.build, onSuccess: () => qc.invalidateQueries({ queryKey: ["bulletin-today"] }) });
  const cveSyncMut = useMutation({ mutationFn: cve.sync });

  return (
    <Card className="p-5 space-y-5">
      <h2 className="text-base font-semibold text-white">Pipeline</h2>

      <IngestTracker />
      <Divider />
      <EnrichTracker />
      <Divider />

      <div className="flex gap-2">
        <Button variant="secondary" size="sm" onClick={() => cveSyncMut.mutate()} disabled={cveSyncMut.isPending}>
          {cveSyncMut.isPending ? <><Spinner size="sm" /> Syncing CVEs…</> : "Sync CVEs"}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => bulletinMut.mutate()} disabled={bulletinMut.isPending}>
          {bulletinMut.isPending ? <><Spinner size="sm" /> Building…</> : "Build Bulletin"}
        </Button>
      </div>
    </Card>
  );
}

// ─── System Prompt Viewer ─────────────────────────────────────────────────────

function SystemPromptSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["enrich-prompt"],
    queryFn: enrich.prompt,
    staleTime: Infinity,   // prompt doesn't change at runtime
  });
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(data?.prompt || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Card className="p-5">
      <details>
        <summary className="flex items-center justify-between cursor-pointer select-none list-none">
          <div>
            <h2 className="text-base font-semibold text-white">Enrichment System Prompt</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Exact prompt sent to {"{LLM}"} for every article — controls severity scoring, category, IOC/TTP extraction
            </p>
          </div>
          <span className="text-slate-600 text-xs ml-4">▼ show</span>
        </summary>

        <div className="mt-4">
          {isLoading ? <Spinner /> : (
            <>
              <div className="flex justify-end mb-1">
                <button onClick={copy} className="text-xs text-slate-600 hover:text-slate-300">
                  {copied ? "Copied ✓" : "Copy"}
                </button>
              </div>
              <pre className="bg-navy-800 rounded p-4 text-xs text-slate-300 whitespace-pre-wrap leading-relaxed overflow-x-auto max-h-96 overflow-y-auto font-mono">
                {data?.prompt}
              </pre>
              <p className="text-xs text-slate-600 mt-2">
                To customise severity scoring, edit <code className="text-slate-400">backend/app/services/enrichment_prompt.py</code> and restart the API.
              </p>
            </>
          )}
        </div>
      </details>
    </Card>
  );
}

// ─── Scoring Weights ──────────────────────────────────────────────────────────

function WeightSlider({ label, description, value, onChange }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div>
          <span className="text-sm text-gray-200">{label}</span>
          <span className="text-xs text-slate-500 ml-2">{description}</span>
        </div>
        <span className="text-sm font-mono text-brand-400 w-12 text-right">{(value * 100).toFixed(0)}%</span>
      </div>
      <input
        type="range" min="0" max="100" step="1"
        value={Math.round(value * 100)}
        onChange={e => onChange(e.target.value / 100)}
        className="w-full accent-brand-500"
      />
    </div>
  );
}

function ScoringSection() {
  const qc = useQueryClient();
  const { data: config, isLoading } = useQuery({ queryKey: ["scoring-config"], queryFn: settingsApi.getScoring });

  const [weights, setWeights] = useState(null);
  const [advanced, setAdvanced] = useState({});
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (config && !dirty) {
      setWeights({
        weight_ai_severity: config.weight_ai_severity,
        weight_feedback_signal: config.weight_feedback_signal,
        weight_profile_match: config.weight_profile_match,
        weight_kev_bonus: config.weight_kev_bonus,
        weight_recency: config.weight_recency,
      });
      setAdvanced({
        feedback_lookback_days: config.feedback_lookback_days,
        recency_half_life_days: config.recency_half_life_days,
        min_feedback_articles: config.min_feedback_articles,
      });
    }
  }, [config, dirty]);

  const saveMut = useMutation({
    mutationFn: (body) => settingsApi.updateScoring(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scoring-config"] }); setDirty(false); setError(null); },
    onError: (e) => setError(e.response?.data?.detail || "Save failed"),
  });
  const resetMut = useMutation({
    mutationFn: settingsApi.resetScoring,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scoring-config"] }); setDirty(false); setError(null); },
  });

  if (isLoading || !weights) return <Card className="p-5"><Spinner /></Card>;

  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const sumOk = Math.abs(total - 1.0) < 0.005;

  const updateWeight = (key, val) => { setWeights(prev => ({ ...prev, [key]: val })); setDirty(true); setError(null); };

  return (
    <Card className="p-5" id="scoring">
      <div className="flex items-start justify-between mb-1">
        <div>
          <h2 className="text-base font-semibold text-white">Scoring Weights</h2>
          <p className="text-xs text-slate-500 mt-0.5">Controls how articles are ranked in the bulletin</p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => resetMut.mutate()} disabled={resetMut.isPending}>Reset</Button>
      </div>

      <div className={`text-xs font-mono mb-4 ${sumOk ? "text-green-400" : "text-red-400"}`}>
        Total: {(total * 100).toFixed(1)}% {sumOk ? "✓" : "— must equal 100%"}
      </div>

      {/* Threat axis */}
      <div className="mb-1">
        <div className="text-[10px] font-mono font-semibold uppercase tracking-widest text-red-400/70 mb-2">Threat</div>
        <div className="space-y-4 pl-2 border-l border-red-900/40">
          <WeightSlider label="AI Severity" description="LLM-extracted 0–100 score" value={weights.weight_ai_severity} onChange={v => updateWeight("weight_ai_severity", v)} />
          <WeightSlider label="KEV Bonus" description="Contains a CISA KEV CVE" value={weights.weight_kev_bonus} onChange={v => updateWeight("weight_kev_bonus", v)} />
        </div>
      </div>

      {/* Relevance axis */}
      <div className="mt-4">
        <div className="text-[10px] font-mono font-semibold uppercase tracking-widest text-violet-400/70 mb-2">Relevance</div>
        <div className="space-y-4 pl-2 border-l border-violet-900/40">
          <WeightSlider label="Profile Match" description="Match against your interest profile" value={weights.weight_profile_match} onChange={v => updateWeight("weight_profile_match", v)} />
          <WeightSlider label="Feedback Signal" description="Overlap with your past rated articles" value={weights.weight_feedback_signal} onChange={v => updateWeight("weight_feedback_signal", v)} />
          <WeightSlider label="Recency" description={`Decay (half-life ${advanced.recency_half_life_days}d)`} value={weights.weight_recency} onChange={v => updateWeight("weight_recency", v)} />
        </div>
      </div>

      <Divider />

      <details className="mb-4">
        <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-300 select-none">Advanced</summary>
        <div className="mt-3 space-y-3">
          {[
            ["Feedback lookback (days)", "feedback_lookback_days", 7, 365, 1],
            ["Recency half-life (days)", "recency_half_life_days", 0.5, 30, 0.5],
            ["Min rated articles for feedback signal", "min_feedback_articles", 1, 50, 1],
          ].map(([label, key, min, max, step]) => (
            <div key={key} className="flex items-center gap-3">
              <label className="text-xs text-slate-400 w-52">{label}</label>
              <input type="number" min={min} max={max} step={step} value={advanced[key]}
                onChange={e => { setAdvanced(p => ({ ...p, [key]: +e.target.value })); setDirty(true); }}
                className="w-20 bg-navy-800 border border-navy-border rounded px-2 py-1 text-sm text-gray-100 focus:outline-none" />
            </div>
          ))}
        </div>
      </details>

      {error && <div className="text-red-400 text-xs mb-3">{error}</div>}
      <div className="flex gap-2 items-center">
        <Button onClick={() => { if (!sumOk) { setError(`Weights must sum to 100%`); return; } saveMut.mutate({ ...weights, ...advanced }); }} disabled={!dirty || !sumOk || saveMut.isPending}>
          {saveMut.isPending ? <><Spinner size="sm" /> Saving…</> : "Save Weights"}
        </Button>
        {dirty && <span className="text-xs text-yellow-400">Unsaved changes</span>}
        {saveMut.isSuccess && !dirty && <span className="text-xs text-green-400">Saved — rebuild bulletin to apply</span>}
      </div>
    </Card>
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

  if (isLoading || !profile) return <Card className="p-5"><Spinner /></Card>;

  const totalTags = Object.values(profile).flat().length;

  return (
    <Card className="p-5" id="profile">
      <div className="flex items-start justify-between mb-1">
        <div>
          <h2 className="text-base font-semibold text-white">Interest Profile</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Drives the Profile Match component of the recommended score — no ratings needed
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
    </Card>
  );
}

// ─── Sources ──────────────────────────────────────────────────────────────────

function SourceRow({ source, onDelete, onToggle }) {
  return (
    <div className="flex items-center gap-3 py-2 border-b border-navy-border last:border-0 group">
      <button onClick={() => onToggle(source)}
        className={`w-2 h-2 rounded-full flex-shrink-0 ${source.is_active ? "bg-green-500" : "bg-gray-600"}`}
        title={source.is_active ? "Active" : "Disabled"} />
      <div className="flex-1 min-w-0">
        <div className="text-sm text-gray-200">{source.name}</div>
        <div className="text-xs text-slate-500 truncate">{source.url}</div>
        {source.last_error && <div className="text-xs text-red-400 truncate">{source.last_error}</div>}
      </div>
      {source.consecutive_failures > 0 && <span className="text-xs text-red-400">{source.consecutive_failures} fails</span>}
      <button onClick={() => onDelete(source.id)} className="opacity-0 group-hover:opacity-100 text-xs text-slate-600 hover:text-red-400">✕</button>
    </div>
  );
}

function SourcesSection() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [importResult, setImportResult] = useState(null);

  const { data: sources, isLoading } = useQuery({ queryKey: ["sources"], queryFn: sourcesApi.list });

  const createMut = useMutation({
    mutationFn: () => sourcesApi.create({ name, url }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sources"] }); setName(""); setUrl(""); },
  });
  const deleteMut = useMutation({ mutationFn: (id) => sourcesApi.delete(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }) });
  const toggleMut = useMutation({ mutationFn: (src) => sourcesApi.update(src.id, { is_active: !src.is_active }), onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }) });
  const importMut = useMutation({
    mutationFn: (file) => sourcesApi.importCsv(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      setImportResult(data);
    },
  });

  const handleCsvFile = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportResult(null);
      importMut.mutate(file);
    }
    e.target.value = "";
  };

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-white">RSS Sources</h2>
        <label className={`text-xs font-mono px-2 py-1 rounded border cursor-pointer transition-colors ${
          importMut.isPending
            ? "border-slate-700 text-slate-600 cursor-not-allowed"
            : "border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"
        }`}>
          {importMut.isPending ? "Importing…" : "Import CSV"}
          <input type="file" accept=".csv,text/csv" className="hidden" onChange={handleCsvFile} disabled={importMut.isPending} />
        </label>
      </div>

      {importResult && (
        <div className="mb-4 text-xs font-mono bg-navy-900 border border-navy-border rounded px-3 py-2 space-y-1">
          <span className="text-green-400">+{importResult.added} added</span>
          {importResult.skipped > 0 && <span className="text-slate-500 ml-3">{importResult.skipped} skipped (duplicate)</span>}
          {importResult.errors?.length > 0 && (
            <details className="mt-1">
              <summary className="text-red-400 cursor-pointer">{importResult.errors.length} error{importResult.errors.length !== 1 ? "s" : ""}</summary>
              <div className="mt-1 space-y-0.5 pl-2">
                {importResult.errors.map((e, i) => (
                  <div key={i} className="text-red-300">row {e.row}: {e.error}</div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {isLoading ? <Spinner /> : (
        <div className="mb-4">
          {sources?.map(s => (
            <SourceRow key={s.id} source={s} onDelete={id => deleteMut.mutate(id)} onToggle={src => toggleMut.mutate(src)} />
          ))}
        </div>
      )}
      <div className="flex gap-2 pt-2">
        <Input value={name} onChange={e => setName(e.target.value)} placeholder="Name" className="w-36" />
        <Input value={url} onChange={e => setUrl(e.target.value)} placeholder="Feed URL" className="flex-1" />
        <Button size="sm" onClick={() => createMut.mutate()} disabled={!name || !url || createMut.isPending}>
          {createMut.isPending ? "Adding…" : "Add"}
        </Button>
      </div>
      {createMut.isError && (
        <p className="text-red-400 text-xs mt-2">
          {createMut.error?.response?.data?.detail || "Failed to add source. Is the API running?"}
        </p>
      )}
      <p className="text-[10px] text-slate-600 font-mono mt-2">CSV format: name,url (header row required)</p>
    </Card>
  );
}

// ─── Feedback Signal Transparency ────────────────────────────────────────────

function StorageField({ label, value }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-navy-border last:border-0">
      <span className="text-[11px] text-slate-500 w-44 flex-shrink-0 font-mono">{label}</span>
      <code className="text-[11px] text-brand-300 break-all">{value}</code>
    </div>
  );
}

function RatingChip({ rating }) {
  if (rating > 0) return <span className="text-[10px] font-bold font-mono text-emerald-400 bg-emerald-900/30 px-1.5 py-0.5 rounded">+1</span>;
  if (rating < 0) return <span className="text-[10px] font-bold font-mono text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">−1</span>;
  return <span className="text-[10px] font-mono text-slate-500 bg-navy-700 px-1.5 py-0.5 rounded">0</span>;
}

function FeedbackSignalSection() {
  const [open, setOpen] = useState(false);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["feedback-signal"],
    queryFn: settingsApi.feedbackSignal,
    enabled: open,
    staleTime: 30_000,
  });

  const isActive = data?.status === "active";

  return (
    <Card className="p-5">
      <button
        onClick={() => { setOpen(v => !v); if (!open) refetch(); }}
        className="w-full flex items-center justify-between group"
      >
        <div className="text-left">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-white">Feedback Signal</h2>
            {data && (
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-md border ${
                isActive
                  ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                  : "text-slate-500 border-slate-600/30 bg-navy-700"
              }`}>
                {isActive ? "● ACTIVE" : "○ INACTIVE"}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            How past ratings influence future bulletin scores — click to inspect
          </p>
        </div>
        <span className="text-slate-600 group-hover:text-slate-400 text-sm ml-4 flex-shrink-0">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="mt-5 space-y-5">
          {isLoading ? (
            <div className="flex justify-center py-4"><Spinner /></div>
          ) : !data ? null : (
            <>
              {/* Status + config */}
              <div className="bg-navy-900 border border-navy-border rounded-xl p-4 space-y-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className={`text-xs font-mono font-semibold ${isActive ? "text-emerald-400" : "text-slate-500"}`}>
                    {data.active_reason}
                  </span>
                </div>
                <div className="flex gap-4 text-xs font-mono text-slate-400 flex-wrap">
                  <span>lookback: <span className="text-white">{data.config.lookback_days}d</span></span>
                  <span>min rated: <span className="text-white">{data.config.min_feedback_articles}</span></span>
                  <span>weight in score: <span className="text-white">×{data.config.weight_in_score}</span></span>
                  <span>articles in window: <span className="text-white">{data.rated_in_window}</span></span>
                </div>
              </div>

              {/* Formula */}
              <div>
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Formula</div>
                <pre className="bg-navy-900 border border-navy-border rounded-xl p-4 text-[11px] text-slate-300 font-mono leading-relaxed whitespace-pre-wrap">
{data.formula}
                </pre>
              </div>

              {/* Storage */}
              <div>
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Storage Locations</div>
                <div className="bg-navy-900 border border-navy-border rounded-xl px-4 py-1">
                  <StorageField label="ratings table" value={data.storage.ratings_table} />
                  <StorageField label="ratings columns" value={data.storage.ratings_columns.join(", ")} />
                  <StorageField label="contributing articles" value={data.storage.contributing_articles_field} />
                  <StorageField label="config table" value={data.storage.config_table} />
                  <StorageField label="config columns" value={data.storage.config_columns.join(", ")} />
                </div>
              </div>

              {/* Rated articles */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    Rated Articles in Window ({data.rated_articles.length})
                  </div>
                  {!isActive && (
                    <span className="text-[10px] text-amber-400 font-mono">
                      Need {data.config.min_feedback_articles} to activate signal
                    </span>
                  )}
                </div>

                {data.rated_articles.length === 0 ? (
                  <p className="text-xs text-slate-600 italic py-2">
                    No rated articles in the last {data.config.lookback_days} days. Rate articles using 👍 / 👎 on the bulletin.
                  </p>
                ) : (
                  <div className="bg-navy-900 border border-navy-border rounded-xl overflow-hidden">
                    {data.rated_articles.map((a, i) => (
                      <div
                        key={a.article_id}
                        className={`px-4 py-3 ${i < data.rated_articles.length - 1 ? "border-b border-navy-border" : ""}`}
                      >
                        <div className="flex items-start gap-3">
                          <RatingChip rating={a.rating} />
                          <div className="flex-1 min-w-0">
                            <p className="text-xs text-slate-300 leading-snug mb-1 line-clamp-1">{a.title}</p>
                            <div className="flex flex-wrap gap-1.5">
                              {a.features?.threat_category && (
                                <span className="text-[10px] font-mono bg-blue-900/30 text-blue-300 border border-blue-500/20 px-1.5 py-0.5 rounded">
                                  cat:{a.features.threat_category}
                                </span>
                              )}
                              {(a.features?.ttps || []).map(t => (
                                <span key={t} className="text-[10px] font-mono bg-emerald-900/30 text-emerald-300 border border-emerald-500/20 px-1.5 py-0.5 rounded">
                                  {t}
                                </span>
                              ))}
                              {(a.features?.actors || []).map(ac => (
                                <span key={ac} className="text-[10px] font-mono bg-violet-900/30 text-violet-300 border border-violet-500/20 px-1.5 py-0.5 rounded">
                                  {ac}
                                </span>
                              ))}
                              {(a.features?.sectors || []).map(s => (
                                <span key={s} className="text-[10px] font-mono bg-orange-900/30 text-orange-300 border border-orange-500/20 px-1.5 py-0.5 rounded">
                                  {s}
                                </span>
                              ))}
                              {!a.features?.threat_category &&
                               !a.features?.ttps?.length &&
                               !a.features?.actors?.length &&
                               !a.features?.sectors?.length && (
                                <span className="text-[10px] text-slate-600 italic">no enriched features</span>
                              )}
                            </div>
                          </div>
                          <span className="text-[10px] text-slate-600 font-mono flex-shrink-0">
                            {a.rated_at ? new Date(a.rated_at).toLocaleDateString() : ""}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  );
}

// ─── Storage / Pruning ───────────────────────────────────────────────────────

function StorageSection() {
  const [result, setResult] = useState(null);
  const pruneMut = useMutation({
    mutationFn: settingsApi.prune,
    onSuccess: (data) => setResult(data),
  });

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-1">
        <div>
          <h2 className="text-base font-semibold text-white">Storage &amp; Retention</h2>
          <p className="text-xs text-slate-500 mt-0.5">Runs automatically every Sunday 03:00 UTC</p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => pruneMut.mutate()} disabled={pruneMut.isPending}>
          {pruneMut.isPending ? <><Spinner size="sm" /> Pruning…</> : "Run Now"}
        </Button>
      </div>

      <div className="mt-3 space-y-1 text-xs text-slate-500 font-mono">
        <div>• <span className="text-slate-400">scraped_text</span> nulled after 30 days (kept for article text view)</div>
        <div>• <span className="text-slate-400">error/no_text</span> articles deleted after 14 days</div>
        <div>• <span className="text-slate-400">pending</span> articles deleted after 30 days</div>
        <div>• <span className="text-slate-400">enriched</span> articles not in any bulletin deleted after 90 days</div>
        <div>• bulletins, feedback, CVE records, actors — kept forever</div>
      </div>

      {result && (
        <div className="mt-3 bg-navy-900 border border-navy-border rounded px-3 py-2 text-xs font-mono space-y-0.5">
          <div className="text-green-400">scraped_text freed: {result.scraped_text_freed}</div>
          <div className="text-slate-400">error/no_text deleted: {result.deleted_error_articles}</div>
          <div className="text-slate-400">stale pending deleted: {result.deleted_stale_pending}</div>
          <div className="text-slate-400">old unbulleted deleted: {result.deleted_old_unbulleted}</div>
        </div>
      )}
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Settings() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <h1 className="text-xl font-bold text-white">Settings</h1>
      <ControlsSection />
      <SchedulerSection />
      <ProfileSection />
      <ScoringSection />
      <FeedbackSignalSection />
      <SystemPromptSection />
      <SourcesSection />
      <StorageSection />
    </div>
  );
}
