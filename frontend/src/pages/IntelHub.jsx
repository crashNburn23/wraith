import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { search, cve as cveApi, enrich as enrichApi } from "../lib/api";
import { Input, Select, Tabs, Spinner, Badge } from "../components/ui";
import { formatDate, timeAgo, categoryColor, severityBg } from "../lib/utils";
import { useEntityModal } from "../components/EntityModalContext";

const TABS = [
  { id: "articles", label: "Articles" },
  { id: "iocs",     label: "IOCs"     },
  { id: "cves",     label: "CVEs"     },
  { id: "actors",   label: "Actors"   },
];

const CATEGORIES = ["", "Malware", "Ransomware", "APT", "Phishing", "Vulnerability", "Data Breach", "Supply Chain", "DDoS", "Insider Threat", "General"];

// ─── Articles tab ─────────────────────────────────────────────────────────────

function ArticlesTab() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [sevMin, setSevMin] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["search-articles", q, category, sevMin, page],
    queryFn: () => search.articles({ q: q || undefined, category: category || undefined, severity_min: sevMin || undefined, page, page_size: 20 }),
    placeholderData: (prev) => prev,
  });

  return (
    <div className="p-5">
      <div className="flex gap-2 mb-5 flex-wrap">
        <Input value={q} onChange={e => { setQ(e.target.value); setPage(1); }} placeholder="Search title / summary…" className="flex-1 min-w-48" />
        <Select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}>
          {CATEGORIES.map(c => <option key={c} value={c}>{c || "All categories"}</option>)}
        </Select>
        <Select value={sevMin} onChange={e => { setSevMin(e.target.value); setPage(1); }}>
          <option value="">Any severity</option>
          <option value="75">High (75+)</option>
          <option value="50">Medium (50+)</option>
          <option value="25">Low (25+)</option>
        </Select>
      </div>

      {isLoading ? <div className="flex justify-center py-10"><Spinner /></div> : (
        <>
          <div className="text-[11px] text-slate-600 font-mono mb-3">{data?.total ?? 0} results</div>
          <div>
            {(data?.items || []).map(a => (
              <div
                key={a.id}
                className="flex items-start gap-3 py-3 border-b border-navy-border last:border-0 group transition-all"
                style={{ borderLeft: "2px solid transparent" }}
                onMouseEnter={e => e.currentTarget.style.borderLeftColor = "rgba(85,88,212,0.45)"}
                onMouseLeave={e => e.currentTarget.style.borderLeftColor = "transparent"}
              >
                <div className="flex-1 min-w-0 pl-2">
                  <div className="flex flex-wrap gap-1.5 mb-1">
                    {a.threat_category && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-mono font-medium ${categoryColor(a.threat_category)}`}>{a.threat_category}</span>
                    )}
                    {a.ai_severity_score && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-mono ${severityBg(a.ai_severity_score)}`}>{a.ai_severity_score.toFixed(0)}</span>
                    )}
                    <span className="text-[10px] text-slate-600 font-mono">{formatDate(a.published_at)}</span>
                  </div>
                  <Link to={`/articles/${a.id}`} className="text-sm text-slate-200 hover:text-white font-medium leading-snug">{a.title}</Link>
                  {a.ai_summary && <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">{a.ai_summary}</p>}
                </div>
              </div>
            ))}
          </div>

          {data?.total > 20 && (
            <div className="flex gap-2 mt-5 justify-center items-center">
              <button
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                className="px-3 py-1.5 text-xs bg-navy-800 border border-navy-border rounded-lg disabled:opacity-30 text-slate-300 hover:border-brand-500/40 hover:text-brand-300 font-mono transition-colors"
              >←</button>
              <span className="text-xs text-slate-500 px-2 font-mono">page {page}</span>
              <button
                disabled={data?.items?.length < 20}
                onClick={() => setPage(p => p + 1)}
                className="px-3 py-1.5 text-xs bg-navy-800 border border-navy-border rounded-lg disabled:opacity-30 text-slate-300 hover:border-brand-500/40 hover:text-brand-300 font-mono transition-colors"
              >→</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── IOCs tab ─────────────────────────────────────────────────────────────────

const IOC_TYPES = ["ip", "domain", "hash", "url", "email"];
const IOC_TYPE_COLOR = { ip: "blue", domain: "purple", hash: "orange", url: "gray", email: "yellow" };

function IOCsTab() {
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const { open } = useEntityModal();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["search-ioc", q, typeFilter],
    queryFn: () => search.ioc(q, typeFilter),
    placeholderData: (prev) => prev,
  });

  const whitelistMutation = useMutation({
    mutationFn: async ({ ioc }) => {
      await enrichApi.addToWhitelist(ioc.value, ioc.ioc_type);
      await enrichApi.patchEntity("ioc", ioc.id, { delete: true });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["search-ioc"] }),
  });

  return (
    <div className="p-5">
      <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Search IP, domain, hash, URL…" className="w-full mb-3" />
      <div className="flex gap-1.5 mb-4 flex-wrap">
        <button
          onClick={() => setTypeFilter("")}
          className={`text-[11px] px-2.5 py-1 rounded-md font-mono border transition-colors ${typeFilter === "" ? "bg-brand-500/20 border-brand-500/50 text-brand-300" : "border-navy-border text-slate-500 hover:border-slate-500 hover:text-slate-300"}`}
        >
          all
        </button>
        {IOC_TYPES.map(t => (
          <button
            key={t}
            onClick={() => setTypeFilter(f => f === t ? "" : t)}
            className={`text-[11px] px-2.5 py-1 rounded-md font-mono border transition-colors ${typeFilter === t ? "bg-brand-500/20 border-brand-500/50 text-brand-300" : "border-navy-border text-slate-500 hover:border-slate-500 hover:text-slate-300"}`}
          >
            {t}
          </button>
        ))}
      </div>
      {isLoading && <Spinner />}
      <div className="text-[11px] text-slate-600 font-mono mb-3">{(data || []).length} results</div>
      <div>
        {(data || []).map(ioc => (
          <div
            key={ioc.id}
            className="flex items-center gap-3 py-2.5 border-b border-navy-border last:border-0 group transition-all pl-2"
            style={{ borderLeft: "2px solid rgba(0,136,168,0.18)" }}
            onMouseEnter={e => e.currentTarget.style.borderLeftColor = "rgba(0,136,168,0.55)"}
            onMouseLeave={e => e.currentTarget.style.borderLeftColor = "rgba(0,136,168,0.18)"}
          >
            <Badge color={IOC_TYPE_COLOR[ioc.ioc_type] || "gray"}>{ioc.ioc_type}</Badge>
            <button
              onClick={() => open("ioc", ioc.id, ioc.value)}
              className="text-sm font-mono flex-1 text-left break-all hover:underline underline-offset-2 transition-colors"
              style={{ color: "#0088A8" }}
            >
              {ioc.value}
            </button>
            {ioc.created_at && (
              <span className="text-[10px] text-slate-600 font-mono flex-shrink-0 hidden group-hover:inline" title={new Date(ioc.created_at).toLocaleString()}>
                {timeAgo(ioc.created_at)}
              </span>
            )}
            <Link
              to={`/articles/${ioc.article_id}`}
              className="text-[11px] text-slate-600 hover:text-brand-400 flex-shrink-0 opacity-0 group-hover:opacity-100 font-mono"
            >
              article →
            </Link>
            <button
              onClick={() => whitelistMutation.mutate({ ioc })}
              disabled={whitelistMutation.isPending}
              title="Whitelist: remove this IOC and never tag it again"
              className="text-[11px] text-slate-600 hover:text-yellow-400 flex-shrink-0 opacity-0 group-hover:opacity-100 font-mono transition-colors disabled:opacity-30"
            >
              [whitelist]
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── CVEs tab ─────────────────────────────────────────────────────────────────

function CVEsTab() {
  const [inKev, setInKev] = useState("");
  const [cvssMin, setCvssMin] = useState("");
  const { open } = useEntityModal();
  const { data, isLoading } = useQuery({
    queryKey: ["cve-list", inKev, cvssMin],
    queryFn: () => cveApi.list({ in_kev: inKev === "" ? undefined : inKev === "true", cvss_min: cvssMin || undefined }),
  });
  const statsQ = useQuery({ queryKey: ["cve-stats"], queryFn: cveApi.stats });

  return (
    <div className="p-5">
      {statsQ.data && (
        <div className="flex gap-5 mb-5 text-sm font-mono">
          <span className="text-slate-400">total: <span className="text-white font-bold">{statsQ.data.total}</span></span>
          <span style={{ color: "#B85018" }}>kev: <span className="font-bold">{statsQ.data.in_kev}</span></span>
          <span className="text-red-400">cvss 9+: <span className="font-bold">{statsQ.data.critical_cvss}</span></span>
        </div>
      )}
      <div className="flex gap-2 mb-4">
        <Select value={inKev} onChange={e => setInKev(e.target.value)}>
          <option value="">All CVEs</option>
          <option value="true">KEV only</option>
          <option value="false">Not KEV</option>
        </Select>
        <Select value={cvssMin} onChange={e => setCvssMin(e.target.value)}>
          <option value="">Any CVSS</option>
          <option value="9">Critical (9+)</option>
          <option value="7">High (7+)</option>
          <option value="4">Medium (4+)</option>
        </Select>
      </div>
      {isLoading ? <Spinner /> : (
        <div>
          {(data?.items || []).map(c => (
            <div
              key={c.id}
              className="flex items-center gap-3 py-2.5 border-b border-navy-border last:border-0 pl-2 transition-all"
              style={{ borderLeft: "2px solid rgba(184,80,24,0.18)" }}
              onMouseEnter={e => e.currentTarget.style.borderLeftColor = "rgba(184,80,24,0.55)"}
              onMouseLeave={e => e.currentTarget.style.borderLeftColor = "rgba(184,80,24,0.18)"}
            >
              <button
                onClick={() => open("cve", c.cve_id, c.cve_id)}
                className="text-sm font-mono w-32 flex-shrink-0 text-left hover:underline underline-offset-2 transition-colors font-bold"
                style={{ color: "#B85018" }}
              >
                {c.cve_id}
              </button>
              {c.cvss_score && <span className={`text-[11px] px-1.5 py-0.5 rounded font-mono ${severityBg(c.cvss_score * 10)}`}>CVSS {c.cvss_score}</span>}
              {c.epss_score && <span className="text-[11px] text-slate-400 font-mono">EPSS {(c.epss_score * 100).toFixed(1)}%</span>}
              {c.in_kev && <Badge color="red">KEV</Badge>}
              {c.kev_due_date && <span className="text-[11px] text-red-400 font-mono">due {c.kev_due_date}</span>}
              <p className="text-xs text-slate-500 flex-1 truncate">{c.nvd_description}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Actors tab ───────────────────────────────────────────────────────────────

function ActorsTab() {
  const [q, setQ] = useState("");
  const { open } = useEntityModal();
  const qc = useQueryClient();

  const { data: actors, isLoading } = useQuery({
    queryKey: ["actors", q],
    queryFn: () => search.actors(q),
  });

  const cleanupMut = useMutation({
    mutationFn: search.cleanupActors,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actors"] }),
  });

  return (
    <div className="p-5">
      <div className="flex gap-2 mb-3">
        <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Search actors…" className="flex-1" />
        <button
          onClick={() => cleanupMut.mutate()}
          disabled={cleanupMut.isPending}
          title="Remove actors with no article associations"
          className="text-[11px] font-mono px-2.5 py-1 rounded border border-slate-600/30 text-slate-600 hover:text-slate-300 hover:border-slate-500/50 transition-colors disabled:opacity-30 flex-shrink-0"
        >
          {cleanupMut.isPending ? "…" : cleanupMut.data ? `removed ${cleanupMut.data.removed}` : "clean orphans"}
        </button>
      </div>
      {isLoading ? <Spinner /> : (
        <div className="space-y-0.5">
          {(actors || []).map(a => (
            <button
              key={a.id}
              onClick={() => open("actor", a.id, a.name)}
              className="w-full text-left px-3 py-2 rounded-lg text-sm transition-all hover:bg-navy-800 text-slate-300 border border-transparent flex items-center gap-2"
              style={{ borderLeft: "2px solid rgba(119,34,170,0.18)" }}
              onMouseEnter={e => e.currentTarget.style.borderLeftColor = "rgba(119,34,170,0.55)"}
              onMouseLeave={e => e.currentTarget.style.borderLeftColor = "rgba(119,34,170,0.18)"}
            >
              <span className="flex-1 text-left min-w-0">
                {a.name}
                {a.aliases?.length > 0 && (
                  <span className="text-[11px] text-slate-500 ml-1.5 font-mono">{a.aliases.slice(0, 2).join(", ")}</span>
                )}
              </span>
              <span className="flex-shrink-0 flex items-center gap-2 text-[10px] font-mono text-slate-600">
                {a.article_count > 0 && <span className="text-slate-500">{a.article_count} article{a.article_count !== 1 ? "s" : ""}</span>}
                {a.last_seen && <span title={new Date(a.last_seen).toLocaleDateString()}>{timeAgo(a.last_seen)}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function IntelHub() {
  const [tab, setTab] = useState("articles");
  return (
    <div className="h-full flex flex-col">
      <div className="px-6 pt-6 pb-4 border-b border-navy-border">
        <h1 className="text-lg font-bold text-white mb-4 tracking-tight">Intel Hub</h1>
        <Tabs tabs={TABS} active={tab} onChange={setTab} />
      </div>
      <div className="flex-1 overflow-y-auto">
        {tab === "articles" && <ArticlesTab />}
        {tab === "iocs"     && <IOCsTab />}
        {tab === "cves"     && <CVEsTab />}
        {tab === "actors"   && <ActorsTab />}
      </div>
    </div>
  );
}
