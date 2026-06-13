import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { investigations as invApi } from "../lib/api";
import { Button, Input, Spinner, EmptyState } from "../components/ui";
import { formatDate } from "../lib/utils";

function NewInvestigationModal({ onClose }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: () => invApi.create({ name: name.trim(), description: description.trim() || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["investigations"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-navy-900 border border-navy-border rounded-xl shadow-2xl w-full max-w-md p-6"
        onClick={e => e.stopPropagation()}
      >
        <h2 className="text-sm font-semibold text-white mb-4">New Investigation</h2>
        <label className="block text-xs text-slate-500 mb-1">Name</label>
        <Input
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Investigation name…"
          className="w-full mb-3"
          autoFocus
        />
        <label className="block text-xs text-slate-500 mb-1">Description (optional)</label>
        <Input
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Brief description…"
          className="w-full mb-5"
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => create.mutate()}
            disabled={!name.trim() || create.isPending}
          >
            {create.isPending ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}

const STATUS_COLOR = {
  open:   "text-emerald-400 bg-emerald-900/30",
  closed: "text-slate-500 bg-navy-800",
};

export default function Investigations() {
  const [showNew, setShowNew] = useState(false);
  const qc = useQueryClient();

  const { data: invs = [], isLoading } = useQuery({
    queryKey: ["investigations"],
    queryFn: invApi.list,
  });

  const del = useMutation({
    mutationFn: invApi.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["investigations"] }),
  });

  return (
    <div className="max-w-4xl mx-auto p-6">
      {showNew && <NewInvestigationModal onClose={() => setShowNew(false)} />}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-white">Investigations</h1>
          <p className="text-xs text-slate-500 mt-0.5">Analyst workspaces for collecting articles and notes</p>
        </div>
        <Button onClick={() => setShowNew(true)}>+ New</Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : invs.length === 0 ? (
        <EmptyState title="No investigations" description="Create an investigation to start collecting articles." />
      ) : (
        <div className="space-y-2">
          {invs.map(inv => (
            <div
              key={inv.id}
              className="flex items-center gap-4 p-4 rounded-lg border border-navy-border bg-navy-900 hover:border-brand-500/30 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <Link
                    to={`/investigations/${inv.id}`}
                    className="text-sm font-medium text-slate-100 hover:text-white truncate"
                  >
                    {inv.name}
                  </Link>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${STATUS_COLOR[inv.status] || STATUS_COLOR.open}`}>
                    {inv.status}
                  </span>
                </div>
                {inv.description && (
                  <p className="text-xs text-slate-500 truncate">{inv.description}</p>
                )}
              </div>
              <div className="flex items-center gap-4 text-xs text-slate-600 font-mono flex-shrink-0">
                <span>{inv.article_count} article{inv.article_count !== 1 ? "s" : ""}</span>
                <span>{formatDate(inv.created_at)}</span>
                <button
                  onClick={() => { if (confirm(`Delete "${inv.name}"?`)) del.mutate(inv.id); }}
                  className="text-slate-700 hover:text-red-400 transition-colors"
                  title="Delete investigation"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
