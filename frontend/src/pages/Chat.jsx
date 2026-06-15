import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import { Button } from "../components/ui";
import { getToken } from "../lib/auth";

function ResultsPanel({ results }) {
  if (!results) return null;
  const citations = results.citations || [];
  const relationships = results.relationships || [];
  return (
    <div className="mt-3 pt-3 border-t border-navy-border space-y-3">
      {results.deterministic && (
        <div className="flex items-center justify-between bg-brand-900/10 border border-brand-500/15 rounded-lg px-3 py-2">
          <span className="text-[10px] uppercase tracking-widest text-brand-400 font-mono">{results.deterministic.kind}</span>
          <span className="text-lg text-white font-mono font-bold">{results.deterministic.value}</span>
        </div>
      )}
      {citations.length > 0 && (
        <details open={Boolean(results.deterministic)}>
          <summary className="text-[10px] uppercase tracking-widest text-slate-500 font-mono cursor-pointer">
            Sources ({citations.length})
          </summary>
          <div className="mt-2 space-y-2 max-h-72 overflow-y-auto">
            {citations.map((citation, index) => (
              <div key={citation.id} className="bg-navy-900 border border-navy-border rounded-lg px-3 py-2">
                <div className="flex items-start gap-2">
                  <span className="text-[10px] text-brand-400 font-mono">A{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <Link to={`/articles/${citation.id}`} className="text-xs text-slate-200 hover:text-brand-300 font-medium">
                      {citation.title}
                    </Link>
                    <div className="text-[10px] text-slate-600 font-mono mt-0.5">
                      {[citation.source, citation.published_at && new Date(citation.published_at).toLocaleDateString()].filter(Boolean).join(" · ")}
                    </div>
                    {citation.evidence?.map((excerpt, i) => (
                      <blockquote key={i} className="text-[10px] text-slate-500 border-l border-brand-500/30 pl-2 mt-1.5 line-clamp-2">{excerpt}</blockquote>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
      {relationships.length > 0 && (
        <details>
          <summary className="text-[10px] uppercase tracking-widest text-slate-500 font-mono cursor-pointer">
            Related entities ({relationships.length})
          </summary>
          <div className="mt-2 flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
            {relationships.map((item, index) => (
              <Link
                key={`${item.article_id}-${item.type}-${item.value}-${index}`}
                to={`/articles/${item.article_id}`}
                title={`${item.article_title}${item.evidence ? `\n${item.evidence}` : ""}`}
                className="text-[10px] font-mono px-2 py-1 rounded border border-navy-border bg-navy-900 text-slate-400 hover:text-brand-300 hover:border-brand-500/30"
              >
                {item.type}: {item.value}
              </Link>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function Message({ role, content, results }) {
  const citedContent = role === "assistant"
    ? (content || "").replace(/\[A(\d+)\]/g, (marker, number) => {
        const citation = results?.citations?.[Number(number) - 1];
        return citation ? `[${marker}](/articles/${citation.id})` : marker;
      })
    : content;
  return (
    <div className={`flex ${role === "user" ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-2xl rounded-xl px-4 py-3 text-sm leading-relaxed ${
        role === "user"
          ? "bg-brand-600 text-white"
          : "bg-navy-800 border border-navy-border text-slate-200"
      }`}>
        {role === "user" ? (
          <pre className="whitespace-pre-wrap font-sans">{content}</pre>
        ) : (
          <div className="chat-markdown">
            <ReactMarkdown
              components={{
                a: ({ href, children }) => href?.startsWith("/articles/")
                  ? <Link to={href}>{children}</Link>
                  : <a href={href} target="_blank" rel="noreferrer">{children}</a>,
              }}
            >
              {citedContent}
            </ReactMarkdown>
            <ResultsPanel results={results} />
          </div>
        )}
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  "How many ransomware articles were published in the last 30 days?",
  "Show a timeline for CVE-2024-3094",
  "What IOCs are associated with Lazarus Group?",
];

const SESSION_KEY = "cti-chat-history";

function loadHistory() {
  try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "[]"); }
  catch { return []; }
}

export default function Chat() {
  const [messages, setMessages] = useState(loadHistory);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(messages.slice(-100)));
  }, [messages]);

  const send = async () => {
    if (!input.trim() || streaming) return;
    const userMsg = { role: "user", content: input.trim() };
    const newHistory = [...messages, userMsg];
    setMessages(newHistory);
    setInput("");
    setStreaming(true);
    setError(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const token = getToken();
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ messages: newHistory }),
        signal: controller.signal,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = "";
      let buffer = "";
      let streamDone = false;
      let assistantResults = null;
      setMessages(prev => [...prev, { role: "assistant", content: "", results: null }]);

      const consumeEvents = () => {
        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop() || "";
        for (const event of events) {
          for (const line of event.split(/\r?\n/)) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6);
            if (raw === "[DONE]") {
              streamDone = true;
              return;
            }
            const eventData = JSON.parse(raw);
            if (eventData.type === "results") {
              assistantResults = eventData;
            } else {
              assistantContent += eventData.text || "";
            }
            setMessages(prev => {
              const copy = [...prev];
              copy[copy.length - 1] = { role: "assistant", content: assistantContent, results: assistantResults };
              return copy;
            });
          }
        }
      };

      while (!streamDone) {
        const { value, done } = await reader.read();
        if (done) {
          buffer += decoder.decode();
          if (buffer.trim()) {
            buffer += "\n\n";
            consumeEvents();
          }
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        consumeEvents();
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(`Error: ${e.message}`);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-navy-border flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white">CTI Chat</h1>
          <p className="text-xs text-slate-500 mt-0.5">Query counts, timelines, relationships, and evidence in your intel database</p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => { setMessages([]); sessionStorage.removeItem(SESSION_KEY); }}
            className="text-[11px] font-mono text-slate-600 hover:text-slate-400 transition-colors"
          >
            [clear]
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
            <div className="w-16 h-16 rounded-2xl bg-navy-800 border border-navy-border flex items-center justify-center">
              <svg className="w-8 h-8 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
              </svg>
            </div>
            <div>
              <p className="text-slate-300 font-medium">Ask about your threat intelligence</p>
              <p className="text-xs text-slate-600 mt-1">Searches your enriched articles, IOCs, CVEs, and actors</p>
            </div>
            <div className="flex flex-col gap-2 w-full max-w-sm">
              {SUGGESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="text-xs text-slate-400 hover:text-slate-100 bg-navy-800 hover:bg-navy-700 border border-navy-border rounded-lg px-4 py-2.5 transition-all text-left"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => <Message key={i} role={m.role} content={m.content} results={m.results} />)}
        {error && <div className="text-red-400 text-sm bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">{error}</div>}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-navy-border">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about threats… (Enter to send, Shift+Enter for newline)"
            rows={2}
            className="flex-1 bg-navy-800 border border-navy-border rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 resize-none transition-colors"
          />
          {streaming ? (
            <Button onClick={stop} variant="danger" className="self-end">Stop</Button>
          ) : (
            <Button onClick={send} disabled={!input.trim()} className="self-end">Send</Button>
          )}
        </div>
      </div>
    </div>
  );
}
