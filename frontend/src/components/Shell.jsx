import { useState, useEffect, useRef } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { clearToken } from "../lib/auth";
import { isTypingTarget } from "../lib/shortcuts";
import ShortcutHelp from "./ShortcutHelp";
import CommandPalette from "./CommandPalette";

const BulletinIcon = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25Z" />
  </svg>
);

const IntelIcon = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
);

const ChatIcon = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
  </svg>
);

const SettingsIcon = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
  </svg>
);

const FeedbackIcon = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 15h2.25m8.024-9.75c.011.05.028.1.052.148.591 1.2.924 2.55.924 3.977a8.96 8.96 0 0 1-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.831 4.398-.306.774-1.086 1.227-1.918 1.227h-1.053c-.472 0-.745-.556-.5-.96a8.95 8.95 0 0 0 .303-.54m.023-8.25H16.48a4.5 4.5 0 0 1-1.423-.23l-3.114-1.04a4.5 4.5 0 0 0-1.423-.23H6.504c-.618 0-1.217.247-1.605.729A11.95 11.95 0 0 0 3 12c0 .434.023.863.068 1.285C3.427 15.306 4.806 16.5 6.504 16.5h1.423l3.114 1.04a4.5 4.5 0 0 0 1.423.23h1.294M7.5 15H6" />
  </svg>
);

const ShieldIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
  </svg>
);

const links = [
  { to: "/",         label: "Bulletin",  Icon: BulletinIcon },
  { to: "/intel",    label: "Intel Hub", Icon: IntelIcon    },
  { to: "/chat",     label: "Chat",      Icon: ChatIcon     },
  { to: "/feedback", label: "Feedback",  Icon: FeedbackIcon },
  { to: "/settings", label: "Settings",  Icon: SettingsIcon },
];

export default function Shell({ children }) {
  const navigate = useNavigate();

  function logout() {
    clearToken();
    navigate("/login", { replace: true });
  }

  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const chordRef = useRef(null);

  // Global shortcuts: ? help · Ctrl+K palette · g-then-key page navigation.
  // All sequential keys — fully usable with one hand.
  useEffect(() => {
    const PAGES = { b: "/", i: "/intel", c: "/chat", f: "/feedback", s: "/settings" };
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(v => !v);
        setHelpOpen(false);
        return;
      }
      if (isTypingTarget(e) || paletteOpen) return;
      if (e.key === "?") {
        e.preventDefault();
        setHelpOpen(v => !v);
        return;
      }
      if (helpOpen) {
        if (e.key === "Escape") setHelpOpen(false);
        return;
      }
      if (chordRef.current === "g") {
        chordRef.current = null;
        if (PAGES[e.key]) {
          e.preventDefault();
          e.stopImmediatePropagation();
          navigate(PAGES[e.key]);
        }
        return;
      }
      if (e.key === "g" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        chordRef.current = "g";
        setTimeout(() => { chordRef.current = null; }, 800);
      }
    };
    // capture phase so the g-chord wins over page-level handlers
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [navigate, helpOpen, paletteOpen]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-navy-950">
      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
      {/* Top navigation bar */}
      <header className="flex-shrink-0 flex items-center gap-1 px-4 border-b border-navy-border bg-navy-900" style={{ height: 44 }}>
        {/* Logo */}
        <div className="flex items-center gap-2 mr-4">
          <div className="w-6 h-6 rounded bg-brand-600 flex items-center justify-center text-white flex-shrink-0 shadow-glow">
            <ShieldIcon />
          </div>
          <span className="text-sm font-semibold text-white tracking-tight">Wraith</span>
        </div>

        <div className="w-px h-5 bg-navy-border mx-1" />

        {/* Nav links */}
        <nav className="flex items-center gap-0.5">
          {links.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                  isActive
                    ? "bg-brand-600/15 text-brand-400"
                    : "text-slate-400 hover:text-slate-100 hover:bg-navy-800"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span className={isActive ? "text-brand-400" : "text-slate-500"}>
                    <Icon />
                  </span>
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Right side */}
        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={() => setPaletteOpen(true)}
            className="text-[11px] text-slate-600 hover:text-slate-400 transition-colors font-mono"
            title="Command palette (Ctrl+K)"
          >
            ⌘K
          </button>
          <button
            onClick={() => setHelpOpen(true)}
            className="text-[11px] text-slate-600 hover:text-slate-400 transition-colors font-mono"
            title="Keyboard shortcuts (?)"
          >
            [?]
          </button>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] text-slate-600 font-mono">localhost</span>
          </div>
          <button
            onClick={logout}
            className="text-[11px] text-slate-600 hover:text-slate-400 transition-colors font-mono"
          >
            [logout]
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-navy-950">
        {children}
      </main>
    </div>
  );
}
