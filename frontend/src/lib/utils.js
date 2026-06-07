export function formatDate(dateStr) {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function timeAgo(dateStr) {
  if (!dateStr) return "—";
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function severityColor(score) {
  if (!score) return "text-gray-400";
  if (score >= 75) return "text-red-400";
  if (score >= 50) return "text-orange-400";
  if (score >= 25) return "text-yellow-400";
  return "text-green-400";
}

export function severityBg(score) {
  if (!score) return "bg-gray-800 text-gray-400";
  if (score >= 75) return "bg-red-900/40 text-red-300";
  if (score >= 50) return "bg-orange-900/40 text-orange-300";
  if (score >= 25) return "bg-yellow-900/40 text-yellow-300";
  return "bg-green-900/40 text-green-300";
}

export function categoryColor(cat) {
  const map = {
    Ransomware: "bg-red-900/50 text-red-300",
    APT: "bg-purple-900/50 text-purple-300",
    Malware: "bg-orange-900/50 text-orange-300",
    Phishing: "bg-yellow-900/50 text-yellow-300",
    Vulnerability: "bg-blue-900/50 text-blue-300",
    "Data Breach": "bg-pink-900/50 text-pink-300",
    "Supply Chain": "bg-teal-900/50 text-teal-300",
    DDoS: "bg-cyan-900/50 text-cyan-300",
    "Insider Threat": "bg-indigo-900/50 text-indigo-300",
    General: "bg-gray-800 text-gray-400",
  };
  return map[cat] || "bg-gray-800 text-gray-400";
}

export function clamp(val, min, max) {
  return Math.min(Math.max(val, min), max);
}

export function pct(raw, decimals = 1) {
  return `${(raw * 100).toFixed(decimals)}%`;
}
