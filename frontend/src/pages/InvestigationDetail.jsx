import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { investigations as invApi, exports as exportsApi } from "../lib/api";
import { Button, Input, Spinner } from "../components/ui";
import { formatDate, categoryColor } from "../lib/utils";

function NoteEditor({ invId, onSuccess }) {
  const [content, setContent] = useState("");
  const qc = useQueryClient();

  const add = useMutation({
    mutationFn: () => invApi.addNote(invId, content.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["investigation", invId] });
      setContent("");
      onSuccess?.();
    },
  });

  return (
    <div className="flex gap-2">
      <Input
        value={content}
        onChange={e => setContent(e.target.value)}
        placeholder="Add a note…"
        className="flex-1"
        onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && content.trim()) { e.preventDefault(); add.mutate(); } }}
      />
      <Button onClick={() => add.mutate()} disabled={!content.trim() || add.isPending} size="sm">
        {add.isPending ? "…" : "Add"}
      </Button>
    </div>
  );
}

function ArticleNoteRow({ ia, invId }) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(ia.note || "");
  const qc = useQueryClient();

  const updateNote = useMutation({
    mutationFn: () => invApi.updateArticle(invId, ia.id, { note: note.trim() || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["investigation", invId] }); setEditing(false); },
  });
  const remove = useMutation({
    mutationFn: () => invApi.removeArticle(invId, ia.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["investigation", invId] }),
  });

  const a = ia.article;
  if (!a) return null;

  return (
    <div className="py-3 border-b border-navy-border last:border-0">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap gap-1.5 mb-0.5">
            {a.threat_category && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${categoryColor(a.threat_category)}`}>
                {a.threat_category}
              </span>
            )}
            {a.ai_severity_score != null && (
              <span className="text-[10px] text-slate-500 font-mono">{Math.round(a.ai_severity_score)}</span>
            )}
          </div>
          <Link to={`/articles/${a.id}`} className="text-sm text-slate-200 hover:text-white font-medium leading-snug">
            {a.title}
          </Link>
          {editing ? (
            <div className="flex gap-2 mt-1.5">
              <Input
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="Analyst note…"
                className="flex-1 text-xs"
                autoFocus
              />
              <Button size="sm" onClick={() => updateNote.mutate()} disabled={updateNote.isPending}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setNote(ia.note || ""); }}>Cancel</Button>
            </div>
          ) : (
            <p
              className="text-xs text-slate-600 mt-0.5 cursor-pointer hover:text-slate-400 italic"
              onClick={() => setEditing(true)}
              title="Click to edit note"
            >
              {ia.note || "click to add note"}
            </p>
          )}
        </div>
        <button
          onClick={() => remove.mutate()}
          className="flex-shrink-0 text-slate-700 hover:text-red-400 text-xs transition-colors mt-0.5"
          title="Remove from investigation"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export default function InvestigationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [exporting, setExporting] = useState(null);

  const { data: inv, isLoading } = useQuery({
    queryKey: ["investigation", id],
    queryFn: () => invApi.get(id),
  });

  const updateStatus = useMutation({
    mutationFn: (status) => invApi.update(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["investigation", id] }),
  });

  const deleteNote = useMutation({
    mutationFn: (noteId) => invApi.deleteNote(id, noteId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["investigation", id] }),
  });

  const del = useMutation({
    mutationFn: () => invApi.delete(id),
    onSuccess: () => navigate("/investigations"),
  });

  async function doExport(format) {
    setExporting(format);
    try {
      if (format === "stix") await exportsApi.stixInvestigation(id, inv?.name);
      if (format === "json") {
        const data = await invApi.exportJson(id);
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const href = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = href; a.download = `wraith-inv-${id.slice(0, 8)}.json`; a.click();
        URL.revokeObjectURL(href);
      }
    } finally {
      setExporting(null);
    }
  }

  if (isLoading) return <div className="flex justify-center py-20"><Spinner /></div>;
  if (!inv) return <div className="p-6 text-sm text-slate-500">Investigation not found.</div>;

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-start gap-4 mb-6">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Link to="/investigations" className="text-xs text-slate-600 hover:text-slate-400 font-mono">← Investigations</Link>
          </div>
          <h1 className="text-lg font-semibold text-white">{inv.name}</h1>
          {inv.description && <p className="text-xs text-slate-500 mt-0.5">{inv.description}</p>}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => updateStatus.mutate(inv.status === "open" ? "closed" : "open")}
            className={`text-[10px] px-2 py-1 rounded font-mono border transition-colors ${
              inv.status === "open"
                ? "text-emerald-400 border-emerald-800 hover:bg-emerald-900/30"
                : "text-slate-500 border-navy-border hover:text-slate-300"
            }`}
          >
            {inv.status}
          </button>
          <div className="relative group">
            <Button size="sm" variant="ghost" className="text-xs">Export ▾</Button>
            <div className="absolute right-0 top-full mt-1 bg-navy-800 border border-navy-border rounded-lg shadow-xl z-20 min-w-36 hidden group-hover:block">
              {[
                { label: "STIX 2.1", key: "stix" },
                { label: "JSON Report", key: "json" },
              ].map(({ label, key }) => (
                <button
                  key={key}
                  onClick={() => doExport(key)}
                  disabled={!!exporting}
                  className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:text-white hover:bg-navy-700 transition-colors first:rounded-t-lg last:rounded-b-lg"
                >
                  {exporting === key ? "…" : label}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={() => { if (confirm(`Delete "${inv.name}"?`)) del.mutate(); }}
            className="text-slate-700 hover:text-red-400 text-xs transition-colors"
          >
            Delete
          </button>
        </div>
      </div>

      {/* Articles */}
      <section className="mb-6">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Articles ({inv.article_count ?? inv.articles?.length ?? 0})
        </h2>
        <div className="rounded-lg border border-navy-border bg-navy-900 px-4">
          {(!inv.articles || inv.articles.length === 0) ? (
            <p className="py-6 text-xs text-slate-600 text-center">
              No articles yet. Use the &ldquo;Add to investigation&rdquo; button on any article.
            </p>
          ) : (
            inv.articles.map(ia => <ArticleNoteRow key={ia.id} ia={ia} invId={id} />)
          )}
        </div>
      </section>

      {/* Notes */}
      <section>
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Notes ({inv.notes?.length ?? 0})
        </h2>
        <div className="space-y-2 mb-3">
          {(inv.notes || []).map(n => (
            <div key={n.id} className="flex gap-3 p-3 rounded-lg border border-navy-border bg-navy-900">
              <p className="flex-1 text-sm text-slate-300 leading-relaxed">{n.content}</p>
              <div className="flex items-start gap-2 flex-shrink-0">
                <span className="text-[10px] text-slate-600 font-mono mt-0.5">{formatDate(n.created_at)}</span>
                <button
                  onClick={() => deleteNote.mutate(n.id)}
                  className="text-slate-700 hover:text-red-400 text-xs transition-colors"
                  title="Delete note"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
        <NoteEditor invId={id} />
      </section>
    </div>
  );
}
