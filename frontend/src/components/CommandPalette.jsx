import { useState, useEffect, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  articles as articlesApi,
  bulletin as bulletinApi,
  ingest as ingestApi,
  enrich as enrichApi,
} from "../lib/api";

export default function CommandPalette({ onClose }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef(null);
  const [actionMsg, setActionMsg] = useState(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const buildMut = useMutation({
    mutationFn: () => bulletinApi.build(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["bulletin-today"] }); setActionMsg("Bulletin build started"); },
  });
  const briefMut = useMutation({
    mutationFn: bulletinApi.generateBrief,
    onSuccess: () => setActionMsg("Brief regeneration started"),
  });
  const ingestMut = useMutation({
    mutationFn: ingestApi.run,
    onSuccess: () => setActionMsg("Ingest started"),
    onError: (e) => setActionMsg(e.response?.data?.detail || "Ingest failed to start"),
  });
  const enrichMut = useMutation({
    mutationFn: enrichApi.run,
    onSuccess: () => setActionMsg("Enrichment started"),
    onError: (e) => setActionMsg(e.response?.data?.detail || "Enrichment failed to start"),
  });

  const commands = useMemo(() => [
    { label: "Go to Bulletin",  hint: "g b", run: () => { navigate("/"); onClose(); } },
    { label: "Go to Intel Hub", hint: "g i", run: () => { navigate("/intel"); onClose(); } },
    { label: "Go to Chat",      hint: "g c", run: () => { navigate("/chat"); onClose(); } },
    { label: "Go to Feedback",  hint: "g f", run: () => { navigate("/feedback"); onClose(); } },
    { label: "Go to Settings",  hint: "g s", run: () => { navigate("/settings"); onClose(); } },
    { label: "Rebuild today's bulletin", hint: "action", run: () => buildMut.mutate() },
    { label: "Regenerate daily brief",   hint: "action", run: () => briefMut.mutate() },
    { label: "Run RSS ingest",           hint: "action", run: () => ingestMut.mutate() },
    { label: "Run enrichment",           hint: "action", run: () => enrichMut.mutate() },
  ], [navigate, onClose, buildMut, briefMut, ingestMut, enrichMut]);

  // Debounce article search
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 200);
    return () => clearTimeout(t);
  }, [query]);

  const { data: searchData } = useQuery({
    queryKey: ["palette-search", debounced],
    queryFn: () => articlesApi.list({ q: debounced, page_size: 6 }),
    enabled: debounced.trim().length >= 2,
  });

  const q = query.toLowerCase().trim();
  const filteredCommands = q
    ? commands.filter(c => c.label.toLowerCase().includes(q))
    : commands;

  const articleResults = (q.length >= 2 ? searchData?.items || [] : []).map(a => ({
    label: a.title,
    hint: "article",
    run: () => { navigate(`/articles/${a.id}`); onClose(); },
  }));

  const results = [...filteredCommands, ...articleResults];

  useEffect(() => { setSelected(0); }, [query, searchData]);

  const onKeyDown = (e) => {
    if (e.key === "Escape") { onClose(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setSelected(s => Math.min(s + 1, results.length - 1)); }
    if (e.key === "ArrowUp")   { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && results[selected]) { e.preventDefault(); results[selected].run(); }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm" />
      <div className="relative w-full max-w-lg bg-navy-800 border border-navy-border rounded-xl shadow-2xl overflow-hidden">
        <input
          ref={inputRef}
          value={query}
          onChange={e => { setQuery(e.target.value); setActionMsg(null); }}
          onKeyDown={onKeyDown}
          placeholder="Search articles or type a command…"
          className="w-full bg-transparent px-4 py-3 text-sm text-slate-100 placeholder-slate-600 focus:outline-none border-b border-navy-border"
        />
        <div className="max-h-80 overflow-y-auto py-1">
          {results.length === 0 && (
            <p className="px-4 py-3 text-xs text-slate-600 font-mono">No matches.</p>
          )}
          {results.map((r, i) => (
            <button
              key={`${r.hint}-${r.label}-${i}`}
              onClick={r.run}
              onMouseEnter={() => setSelected(i)}
              className={`w-full flex items-center gap-3 px-4 py-2 text-left transition-colors ${
                i === selected ? "bg-brand-600/15" : ""
              }`}
            >
              <span className={`flex-1 text-xs truncate ${i === selected ? "text-white" : "text-slate-300"}`}>
                {r.label}
              </span>
              <span className="text-[9px] font-mono text-slate-600 flex-shrink-0 uppercase">{r.hint}</span>
            </button>
          ))}
        </div>
        <div className="flex items-center justify-between px-4 py-2 border-t border-navy-border">
          <span className="text-[9px] font-mono text-slate-700">↑↓ navigate · Enter run · Esc close</span>
          {actionMsg && <span className="text-[10px] font-mono text-emerald-400">{actionMsg}</span>}
        </div>
      </div>
    </div>
  );
}
