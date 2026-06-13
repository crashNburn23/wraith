import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { investigations as invApi } from "../lib/api";
import { Button, Input, Spinner } from "./ui";

export function AddToInvestigationModal({ articleId, articleTitle, onClose }) {
  const [note, setNote] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const qc = useQueryClient();

  const { data: invs = [], isLoading } = useQuery({
    queryKey: ["investigations"],
    queryFn: invApi.list,
  });

  const add = useMutation({
    mutationFn: async (invId) => {
      await invApi.addArticle(invId, { article_id: articleId, note: note.trim() || undefined });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["investigations"] });
      onClose();
    },
  });

  const createAndAdd = useMutation({
    mutationFn: async () => {
      const inv = await invApi.create({ name: newName.trim() });
      await invApi.addArticle(inv.id, { article_id: articleId, note: note.trim() || undefined });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["investigations"] });
      onClose();
    },
  });

  const openInvs = invs.filter(i => i.status === "open");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-navy-900 border border-navy-border rounded-xl shadow-2xl w-full max-w-sm p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-sm font-semibold text-white mb-1">Add to Investigation</h2>
        <p className="text-xs text-slate-500 mb-4 truncate">{articleTitle}</p>

        {isLoading ? (
          <div className="flex justify-center py-4"><Spinner /></div>
        ) : (
          <>
            {openInvs.length > 0 && !creating && (
              <div className="space-y-1 mb-3 max-h-48 overflow-y-auto">
                {openInvs.map(inv => (
                  <button
                    key={inv.id}
                    onClick={() => setSelectedId(inv.id === selectedId ? null : inv.id)}
                    className={`w-full text-left px-3 py-2 rounded-lg border text-xs transition-colors ${
                      selectedId === inv.id
                        ? "border-brand-500/60 bg-brand-900/20 text-brand-300"
                        : "border-navy-border text-slate-300 hover:border-brand-500/30 hover:text-white"
                    }`}
                  >
                    <span className="font-medium">{inv.name}</span>
                    <span className="ml-2 text-slate-600">{inv.article_count} articles</span>
                  </button>
                ))}
              </div>
            )}

            {!creating && (
              <button
                onClick={() => setCreating(true)}
                className="w-full text-left px-3 py-2 rounded-lg border border-dashed border-navy-border text-xs text-slate-500 hover:text-slate-300 hover:border-brand-500/30 mb-3 transition-colors"
              >
                + New investigation
              </button>
            )}

            {creating && (
              <div className="mb-3">
                <Input
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  placeholder="Investigation name…"
                  className="w-full mb-2"
                  autoFocus
                />
                <button
                  onClick={() => { setCreating(false); setNewName(""); }}
                  className="text-xs text-slate-600 hover:text-slate-400"
                >
                  ← back to list
                </button>
              </div>
            )}

            <label className="block text-xs text-slate-500 mb-1">Note (optional)</label>
            <Input
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Why is this relevant?"
              className="w-full mb-4"
            />

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose}>Cancel</Button>
              {creating ? (
                <Button
                  onClick={() => createAndAdd.mutate()}
                  disabled={!newName.trim() || createAndAdd.isPending}
                >
                  {createAndAdd.isPending ? "Adding…" : "Create & Add"}
                </Button>
              ) : (
                <Button
                  onClick={() => add.mutate(selectedId)}
                  disabled={!selectedId || add.isPending}
                >
                  {add.isPending ? "Adding…" : "Add"}
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
