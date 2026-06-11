import { SHORTCUT_GROUPS } from "../lib/shortcuts";

export default function ShortcutHelp({ onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm" />
      <div className="relative w-full max-w-2xl bg-navy-800 border border-navy-border rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-navy-border">
          <h2 className="text-sm font-semibold text-white">Keyboard shortcuts</h2>
          <span className="text-[10px] font-mono text-slate-600">? or Esc to close</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-4 p-5 max-h-[70vh] overflow-y-auto">
          {SHORTCUT_GROUPS.map(group => (
            <div key={group.title}>
              <div className="text-[10px] font-mono font-semibold uppercase tracking-widest text-brand-400 mb-2">
                {group.title}
              </div>
              <div className="space-y-1.5">
                {group.keys.map(([key, desc]) => (
                  <div key={key} className="flex items-baseline gap-2">
                    <kbd className="text-[10px] font-mono text-slate-200 bg-navy-900 border border-navy-border rounded px-1.5 py-0.5 whitespace-nowrap">
                      {key}
                    </kbd>
                    <span className="text-[11px] text-slate-400 leading-snug">{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="px-5 py-2.5 border-t border-navy-border">
          <p className="text-[10px] font-mono text-slate-600">
            Designed for one-handed triage — every bulletin action sits in the right-hand home cluster.
          </p>
        </div>
      </div>
    </div>
  );
}
