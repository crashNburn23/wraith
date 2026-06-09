import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { sources as sourcesApi, ingest, enrich as enrichApi, bulletin as bulletinApi, settings as settingsApi, cve, feedback as feedbackApi } from "../lib/api";
import { Button, Input, Card, Spinner, Divider } from "../components/ui";

function TagInput({ tags, onChange, placeholder, color = "bg-navy-800 border-navy-border text-slate-300" }) {
  const [input, setInput] = useState("");

  const add = () => {
    const v = input.trim();
    if (v && !tags.includes(v)) onChange([...tags, v]);
    setInput("");
  };

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {tags.map(t => (
          <span key={t} className={`flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md border ${color}`}>
            {t}
            <button onClick={() => onChange(tags.filter(x => x !== t))} className="opacity-50 hover:opacity-100 hover:text-red-400 leading-none">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          className="flex-1 text-sm"
        />
        <Button size="sm" variant="secondary" onClick={add} disabled={!input.trim()}>Add</Button>
      </div>
    </div>
  );
}

function CollapsibleCard({ title, subtitle, defaultOpen = false, actions, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <button
          onClick={() => setOpen(v => !v)}
          className="flex items-start gap-2 text-left group flex-1 min-w-0"
        >
          <span className="text-slate-600 text-xs mt-0.5 flex-shrink-0 transition-transform" style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}>▶</span>
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-white group-hover:text-slate-200">{title}</h2>
            {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
        </button>
        {actions && <div className="flex-shrink-0 ml-3">{actions}</div>}
      </div>
      {open && <div className="mt-4">{children}</div>}
    </Card>
  );
}

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
  const retryMut = useMutation({
    mutationFn: enrichApi.retryErrors,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ingest-status"] }); qc.invalidateQueries({ queryKey: ["enrich-status"] }); },
  });
  const dismissMut = useMutation({
    mutationFn: enrichApi.dismissErrors,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ingest-status"] }); qc.invalidateQueries({ queryKey: ["enrich-status"] }); },
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
          {articles.error > 0 && (
            <span className="text-red-400 flex items-center gap-1.5">
              Errors: <span className="font-mono">{articles.error}</span>
              <button
                onClick={() => retryMut.mutate()}
                disabled={retryMut.isPending || dismissMut.isPending}
                className="text-[10px] font-mono text-red-400/60 hover:text-red-300 border border-red-500/20 rounded px-1 py-0.5 transition-colors disabled:opacity-30"
                title="Reset errored articles to pending — they'll retry on next enrich run"
              >
                {retryMut.isPending ? "…" : "retry"}
              </button>
              <button
                onClick={() => dismissMut.mutate()}
                disabled={retryMut.isPending || dismissMut.isPending}
                className="text-[10px] font-mono text-slate-600 hover:text-slate-400 border border-slate-600/30 rounded px-1 py-0.5 transition-colors disabled:opacity-30"
                title="Permanently dismiss these errors — they won't retry"
              >
                {dismissMut.isPending ? "…" : "remove"}
              </button>
            </span>
          )}
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
    queryFn: enrichApi.status,
    refetchInterval: (query) => {
      const run = query.state.data?.current_run;
      return run?.status === "running" ? 2000 : 10000;
    },
  });

  const runMut = useMutation({
    mutationFn: enrichApi.run,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrich-status"] }),
    onError: (e) => alert(e.response?.data?.detail || "Failed to start enrichment"),
  });
  const pauseMut = useMutation({
    mutationFn: enrichApi.pause,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrich-status"] }),
  });
  const stopMut = useMutation({
    mutationFn: enrichApi.stop,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrich-status"] }),
  });
  const resumeMut = useMutation({
    mutationFn: enrichApi.resume,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrich-status"] }),
  });
  const retryMut = useMutation({
    mutationFn: enrichApi.retryErrors,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["enrich-status"] }); qc.invalidateQueries({ queryKey: ["ingest-status"] }); },
  });
  const dismissMut = useMutation({
    mutationFn: enrichApi.dismissErrors,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["enrich-status"] }); qc.invalidateQueries({ queryKey: ["ingest-status"] }); },
  });

  const run = data?.current_run;
  const isRunning = run?.status === "running";
  const isPaused = run?.status === "paused" || data?.paused;
  const isStopped = run?.status === "stopped";
  const pct = run?.total > 0 ? Math.round((run.processed / run.total) * 100) : 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-300">Enrich</h3>
        <div className="flex gap-1.5">
          {isRunning ? (
            <>
              <Button size="sm" variant="secondary" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending || stopMut.isPending}>
                Pause
              </Button>
              <Button size="sm" variant="danger" onClick={() => stopMut.mutate()} disabled={stopMut.isPending || pauseMut.isPending}>
                Stop
              </Button>
            </>
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
          {data.error_articles > 0 && (
            <span className="text-red-400 flex items-center gap-1.5">
              Errors: <span className="font-mono">{data.error_articles}</span>
              <button
                onClick={() => retryMut.mutate()}
                disabled={retryMut.isPending || dismissMut.isPending}
                className="text-[10px] font-mono text-red-400/60 hover:text-red-300 border border-red-500/20 rounded px-1 py-0.5 transition-colors disabled:opacity-30"
                title="Reset errored articles to pending — they'll retry on next enrich run"
              >
                {retryMut.isPending ? "…" : "retry"}
              </button>
              <button
                onClick={() => dismissMut.mutate()}
                disabled={retryMut.isPending || dismissMut.isPending}
                className="text-[10px] font-mono text-slate-600 hover:text-slate-400 border border-slate-600/30 rounded px-1 py-0.5 transition-colors disabled:opacity-30"
                title="Permanently dismiss these errors — they won't retry"
              >
                {dismissMut.isPending ? "…" : "remove"}
              </button>
            </span>
          )}
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
                className={`h-full rounded-full transition-all ${run.status === "completed" ? "bg-green-500" : run.status === "paused" ? "bg-yellow-500" : run.status === "stopped" ? "bg-orange-500" : "bg-brand-500"}`}
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
              <div className="mt-1.5 space-y-1.5 max-h-64 overflow-y-auto">
                {run.errors.map((e, i) => {
                  const s = (e.error || "").toLowerCase();
                  const errType = !e.error || e.error === "error" ? "enrichment failed"
                    : e.error === "no_text" ? "no article text"
                    : s.includes("timeout") ? "LLM timeout"
                    : s.includes("jsondecodeerror") || s.includes("expecting value") ? "JSON parse"
                    : s.includes("connecterror") || s.includes("refused") ? "connection error"
                    : "error";
                  const showDetail = e.error && e.error !== "error" && e.error !== "no_text";
                  return (
                    <div key={i} className="bg-red-900/20 rounded px-2 py-1.5 space-y-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-slate-300 text-xs break-words leading-snug">{e.title}</span>
                        <span className="flex-shrink-0 text-[10px] font-mono text-red-400/80 bg-red-900/30 px-1.5 py-0.5 rounded border border-red-500/20">{errType}</span>
                      </div>
                      {showDetail && (
                        <div className="text-red-400/70 text-[10px] font-mono break-all leading-relaxed">{e.error}</div>
                      )}
                    </div>
                  );
                })}
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
    stopped:   "bg-orange-900/50 text-orange-300",
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

  const statusLabel = data?.running
    ? <span className="text-emerald-400 font-mono text-xs">● running</span>
    : <span className="text-red-400 font-mono text-xs">○ stopped</span>;

  return (
    <CollapsibleCard title="Scheduler" subtitle={null} actions={statusLabel}>
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
    </CollapsibleCard>
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

      {/* CVE Sync */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-slate-300">Sync CVEs</h3>
          <Button variant="secondary" size="sm" onClick={() => cveSyncMut.mutate()} disabled={cveSyncMut.isPending}>
            {cveSyncMut.isPending ? <><Spinner size="sm" /> Syncing…</> : "Run Now"}
          </Button>
        </div>
        {cveSyncMut.isSuccess && <p className="text-xs text-green-400 font-mono">CVE sync complete</p>}
        {cveSyncMut.isError && <p className="text-xs text-red-400 font-mono">Sync failed</p>}
      </div>

      <Divider />

      {/* Build Bulletin */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-slate-300">Build Bulletin</h3>
          <Button variant="secondary" size="sm" onClick={() => bulletinMut.mutate()} disabled={bulletinMut.isPending}>
            {bulletinMut.isPending ? <><Spinner size="sm" /> Building…</> : "Run Now"}
          </Button>
        </div>
        {bulletinMut.isSuccess && <p className="text-xs text-green-400 font-mono">Bulletin built</p>}
        {bulletinMut.isError && <p className="text-xs text-red-400 font-mono">Build failed</p>}
      </div>
    </Card>
  );
}

// ─── System Prompt Viewer ─────────────────────────────────────────────────────

function SystemPromptSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["enrich-prompt"],
    queryFn: enrichApi.prompt,
  });
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(data?.prompt || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <CollapsibleCard
      title="Enrichment System Prompt"
      subtitle={`Exact prompt sent to the LLM for every article — controls severity scoring, category, IOC/TTP extraction`}
      actions={
        !isLoading && (
          <button onClick={copy} className="text-xs text-slate-600 hover:text-slate-300">
            {copied ? "Copied ✓" : "Copy"}
          </button>
        )
      }
    >
      {isLoading ? <Spinner /> : (
        <>
          <pre className="bg-navy-800 rounded p-4 text-xs text-slate-300 whitespace-pre-wrap leading-relaxed overflow-x-auto max-h-96 overflow-y-auto font-mono">
            {data?.prompt}
          </pre>
          <p className="text-xs text-slate-600 mt-2">
            To customise, edit <code className="text-slate-400">backend/app/services/enrichment_prompt.py</code> and restart the API.
          </p>
        </>
      )}
    </CollapsibleCard>
  );
}

// ─── Interest Profile ─────────────────────────────────────────────────────────

const PRESET_SECTORS = ["Finance", "Healthcare", "Government", "Energy", "Technology", "Retail", "Education", "Defense", "Critical Infrastructure"];
const PRESET_CATEGORIES = ["Malware", "Ransomware", "APT", "Phishing", "Vulnerability", "Data Breach", "Supply Chain", "DDoS", "Insider Threat"];

function ProfileSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["profile"], queryFn: settingsApi.getProfile });

  const [profile, setProfile] = useState(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data && !dirty) setProfile(data);
  }, [data, dirty]);

  const saveMut = useMutation({
    mutationFn: (body) => settingsApi.updateProfile(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["profile"] }); setDirty(false); },
  });

  if (isLoading || !profile) return <Card className="p-5"><Spinner /></Card>;

  const update = (field, value) => { setProfile(p => ({ ...p, [field]: value })); setDirty(true); };

  const FIELDS = [
    { key: "sectors",      label: "Sectors",           placeholder: "e.g. Finance",   presets: PRESET_SECTORS,
      hint: "Articles targeting these sectors score higher",
      color: "bg-blue-900/30 text-blue-300 border-blue-500/20" },
    { key: "categories",   label: "Threat Categories", placeholder: "e.g. Ransomware", presets: PRESET_CATEGORIES,
      hint: "Boost articles matching these threat types",
      color: "bg-orange-900/30 text-orange-300 border-orange-500/20" },
    { key: "threat_actors", label: "Threat Actors",    placeholder: "e.g. APT28",
      hint: "Boost articles mentioning these actors",
      color: "bg-violet-900/30 text-violet-300 border-violet-500/20" },
    { key: "keywords",     label: "Keywords",           placeholder: "e.g. zero-day",
      hint: "Matched against title and summary",
      color: "bg-emerald-900/30 text-emerald-300 border-emerald-500/20" },
    { key: "geo_targets",  label: "Geo Targets",        placeholder: "e.g. US, EU",
      hint: "Boost articles where your regions are targeted",
      color: "bg-cyan-900/30 text-cyan-300 border-cyan-500/20" },
    { key: "geo_origins",  label: "Threat Origins",     placeholder: "e.g. China, Russia",
      hint: "Boost articles originating from tracked adversary nations",
      color: "bg-red-900/30 text-red-300 border-red-500/20" },
  ];

  return (
    <CollapsibleCard title="Interest Profile" subtitle="Shapes relevance scoring — what you care about surfaces higher in the bulletin">
      <div className="space-y-5">
        {FIELDS.map(({ key, label, placeholder, presets, hint, color }) => (
          <div key={key}>
            <div className="flex items-baseline gap-2 mb-1.5">
              <span className="text-sm text-slate-300 font-medium">{label}</span>
              <span className="text-[11px] text-slate-600">{hint}</span>
            </div>
            {presets && (
              <div className="flex flex-wrap gap-1 mb-2">
                {presets.map(p => {
                  const active = (profile[key] || []).includes(p);
                  return (
                    <button
                      key={p}
                      onClick={() => update(key, active ? profile[key].filter(x => x !== p) : [...(profile[key] || []), p])}
                      className={`text-[10px] px-2 py-0.5 rounded font-mono border transition-colors ${active ? "bg-brand-500/20 border-brand-500/50 text-brand-300" : "border-navy-border text-slate-600 hover:border-slate-500 hover:text-slate-400"}`}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            )}
            <TagInput
              tags={profile[key] || []}
              onChange={v => update(key, v)}
              placeholder={placeholder}
              color={color}
            />
          </div>
        ))}
      </div>
      <Divider />
      <div className="flex gap-2 items-center">
        <Button onClick={() => saveMut.mutate(profile)} disabled={!dirty || saveMut.isPending}>
          {saveMut.isPending ? <><Spinner size="sm" /> Saving…</> : "Save Profile"}
        </Button>
        {dirty && <span className="text-xs text-yellow-400">Unsaved changes</span>}
        {saveMut.isSuccess && !dirty && <span className="text-xs text-green-400">Saved — rebuild bulletin to apply</span>}
      </div>
    </CollapsibleCard>
  );
}

// ─── Natural Language Feedback ────────────────────────────────────────────────

const NL_PROFILE_LABELS = {
  sectors:       { label: "Sectors",       color: "text-orange-300 bg-orange-900/30 border-orange-500/20" },
  categories:    { label: "Categories",    color: "text-blue-300 bg-blue-900/30 border-blue-500/20"       },
  keywords:      { label: "Keywords",      color: "text-emerald-300 bg-emerald-900/30 border-emerald-500/20" },
  threat_actors: { label: "Threat Actors", color: "text-violet-300 bg-violet-900/30 border-violet-500/20" },
};

function NaturalLanguageFeedbackSection() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const mut = useMutation({
    mutationFn: () => feedbackApi.applyNote(text),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profile"] }),
  });
  const anyAdded = mut.data && Object.values(mut.data.added).some(arr => arr.length > 0);

  return (
    <CollapsibleCard title="Natural Language Feedback" subtitle="Describe your interests in plain English — extracts and adds preferences to your profile">
      <textarea
        value={text}
        onChange={e => { setText(e.target.value); mut.reset(); }}
        placeholder="e.g. I'm most interested in ransomware targeting healthcare and critical infrastructure. I'd also like to see more on living-off-the-land techniques and APT28 activity…"
        rows={3}
        className="w-full bg-navy-800 border border-navy-border rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-500/50 resize-none font-sans leading-relaxed mb-3"
      />
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0 mr-3">
          {mut.isError && <p className="text-[11px] text-red-400 font-mono">{mut.error?.response?.data?.detail || "Something went wrong."}</p>}
          {mut.isSuccess && !anyAdded && <p className="text-[11px] text-slate-500 font-mono">Nothing new — those preferences are already in your profile.</p>}
        </div>
        <Button size="sm" onClick={() => mut.mutate()} disabled={mut.isPending || !text.trim()}>
          {mut.isPending ? <><Spinner size="sm" /> Applying…</> : "Apply to profile"}
        </Button>
      </div>
      {mut.isSuccess && anyAdded && (
        <div className="mt-3 pt-3 border-t border-navy-border">
          <p className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-2">Added to your profile</p>
          <div className="space-y-1.5">
            {Object.entries(NL_PROFILE_LABELS).map(([key, meta]) => {
              const added = mut.data.added[key] || [];
              if (!added.length) return null;
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-600 font-mono w-24 flex-shrink-0">{meta.label}</span>
                  <div className="flex flex-wrap gap-1">
                    {added.map(v => (
                      <span key={v} className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${meta.color}`}>{v}</span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </CollapsibleCard>
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
        feedback_decay_half_life_days: config.feedback_decay_half_life_days,
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
    <CollapsibleCard
      title="Scoring Weights"
      subtitle="Controls how articles are ranked in the bulletin"
      actions={<Button size="sm" variant="ghost" onClick={() => resetMut.mutate()} disabled={resetMut.isPending}>Reset</Button>}
    >
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
            ["Feedback decay half-life (days)", "feedback_decay_half_life_days", 1, 365, 1],
            ["Recency half-life (days)", "recency_half_life_days", 0.5, 30, 0.5],
            ["Min signals to activate feedback loop", "min_feedback_articles", 1, 50, 1],
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
      <div className="flex gap-2 items-center flex-wrap">
        <Button onClick={() => { if (!sumOk) { setError(`Weights must sum to 100%`); return; } saveMut.mutate({ ...weights, ...advanced }); }} disabled={!dirty || !sumOk || saveMut.isPending}>
          {saveMut.isPending ? <><Spinner size="sm" /> Saving…</> : "Save Weights"}
        </Button>
        <RebuildScoresButton />
        {dirty && <span className="text-xs text-yellow-400">Unsaved changes</span>}
        {saveMut.isSuccess && !dirty && <span className="text-xs text-green-400">Saved</span>}
      </div>
    </CollapsibleCard>
  );
}

function RebuildScoresButton() {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: bulletinApi.rebuildScores,
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["bulletin-today"] }),
  });
  return (
    <div className="flex items-center gap-2">
      <Button variant="secondary" size="sm" onClick={() => mut.mutate()} disabled={mut.isPending}>
        {mut.isPending ? <><Spinner size="sm" /> Rebuilding…</> : "Rebuild Today's Scores"}
      </Button>
      {mut.isSuccess && <span className="text-xs text-green-400">{mut.data?.recomputed} items rescored</span>}
      {mut.isError && <span className="text-xs text-red-400">{mut.error?.response?.data?.detail || "No bulletin for today"}</span>}
    </div>
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

  const csvLabel = (
    <label className={`text-xs font-mono px-2 py-1 rounded border cursor-pointer transition-colors ${
      importMut.isPending
        ? "border-slate-700 text-slate-600 cursor-not-allowed"
        : "border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"
    }`}>
      {importMut.isPending ? "Importing…" : "Import CSV"}
      <input type="file" accept=".csv,text/csv" className="hidden" onChange={handleCsvFile} disabled={importMut.isPending} />
    </label>
  );

  return (
    <CollapsibleCard title="RSS Sources" actions={csvLabel}>
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
    </CollapsibleCard>
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
    <CollapsibleCard
      title="Storage & Retention"
      subtitle="Runs automatically every Sunday 03:00 UTC"
      actions={
        <Button size="sm" variant="secondary" onClick={() => pruneMut.mutate()} disabled={pruneMut.isPending}>
          {pruneMut.isPending ? <><Spinner size="sm" /> Pruning…</> : "Run Now"}
        </Button>
      }
    >
      <div className="space-y-1 text-xs text-slate-500 font-mono">
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
    </CollapsibleCard>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Settings() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <h1 className="text-xl font-bold text-white">Settings</h1>
      <ControlsSection />
      <ProfileSection />
      <NaturalLanguageFeedbackSection />
      <ScoringSection />
      <SystemPromptSection />
      <SourcesSection />
      <StorageSection />
      <SchedulerSection />
    </div>
  );
}
