export function Button({ children, onClick, variant = "primary", size = "md", disabled, className = "", type = "button" }) {
  const base = "inline-flex items-center gap-1.5 rounded-lg font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-navy-900 disabled:opacity-40 disabled:cursor-not-allowed";
  const sizes = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm", lg: "px-5 py-2.5 text-base" };
  const variants = {
    primary:   "bg-brand-600 hover:bg-brand-500 text-white focus:ring-brand-500 shadow-sm",
    secondary: "bg-navy-700 hover:bg-navy-600 text-slate-200 border border-navy-border focus:ring-slate-500",
    ghost:     "hover:bg-navy-800 text-slate-400 hover:text-slate-100 focus:ring-slate-600",
    danger:    "bg-red-600/90 hover:bg-red-500 text-white focus:ring-red-500 shadow-sm",
    success:   "bg-emerald-600/90 hover:bg-emerald-500 text-white focus:ring-emerald-500 shadow-sm",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Badge({ children, color = "gray" }) {
  const colors = {
    gray:   "bg-navy-700 text-slate-400 border border-navy-border",
    red:    "bg-red-500/10 text-red-400 border border-red-500/20",
    orange: "bg-orange-500/10 text-orange-400 border border-orange-500/20",
    yellow: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
    green:  "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
    blue:   "bg-blue-500/10 text-blue-400 border border-blue-500/20",
    purple: "bg-violet-500/10 text-violet-400 border border-violet-500/20",
    indigo: "bg-brand-500/10 text-brand-400 border border-brand-500/20",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${colors[color] || colors.gray}`}>
      {children}
    </span>
  );
}

export function Card({ children, className = "" }) {
  return (
    <div className={`bg-navy-800 border border-navy-border rounded-xl shadow-card ${className}`}>
      {children}
    </div>
  );
}

export function Spinner({ size = "md" }) {
  const sz = { sm: "h-3.5 w-3.5", md: "h-5 w-5", lg: "h-9 w-9" };
  return (
    <svg className={`animate-spin ${sz[size]} text-brand-400`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
    </svg>
  );
}

export function Input({ value, onChange, placeholder, type = "text", className = "" }) {
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className={`bg-navy-900 border border-navy-border rounded-lg px-3 py-1.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 transition-colors ${className}`}
    />
  );
}

export function Select({ value, onChange, children, className = "" }) {
  return (
    <select
      value={value}
      onChange={onChange}
      className={`bg-navy-900 border border-navy-border rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 ${className}`}
    >
      {children}
    </select>
  );
}

export function Textarea({ value, onChange, placeholder, rows = 3, className = "" }) {
  return (
    <textarea
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      rows={rows}
      className={`bg-navy-900 border border-navy-border rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 w-full resize-none transition-colors ${className}`}
    />
  );
}

export function Divider({ className = "" }) {
  return <hr className={`border-navy-border my-4 ${className}`} />;
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-14 h-14 rounded-2xl bg-navy-800 border border-navy-border flex items-center justify-center mb-4">
        <svg className="w-7 h-7 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 13.5h3.86a2.25 2.25 0 0 1 2.012 1.244l.256.512a2.25 2.25 0 0 0 2.013 1.244h3.218a2.25 2.25 0 0 0 2.013-1.244l.256-.512a2.25 2.25 0 0 1 2.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 0 0-2.15-1.588H6.911a2.25 2.25 0 0 0-2.15 1.588L2.35 13.177a2.25 2.25 0 0 0-.1.661Z" />
        </svg>
      </div>
      <div className="text-slate-200 font-semibold">{title}</div>
      {description && <div className="text-slate-500 text-sm mt-1.5 max-w-xs leading-relaxed">{description}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1 bg-navy-900 border border-navy-border rounded-lg p-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-all duration-150 ${
            active === tab.id
              ? "bg-navy-700 text-slate-100 shadow-sm"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {tab.label}
          {tab.count != null && (
            <span className={`text-xs rounded px-1.5 py-0.5 font-mono ${
              active === tab.id ? "bg-brand-600/30 text-brand-300" : "bg-navy-800 text-slate-500"
            }`}>
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
