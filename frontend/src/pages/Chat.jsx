import { useState, useRef, useEffect } from "react";
import { Button, Spinner } from "../components/ui";
import api from "../lib/api";

function Message({ role, content }) {
  return (
    <div className={`flex ${role === "user" ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-2xl rounded-xl px-4 py-3 text-sm leading-relaxed ${
        role === "user"
          ? "bg-brand-600 text-white"
          : "bg-navy-800 border border-navy-border text-slate-200"
      }`}>
        <pre className="whitespace-pre-wrap font-sans">{content}</pre>
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  "What ransomware groups have been active recently?",
  "Show me articles mentioning CVE-2024",
  "What IOCs are associated with Lazarus Group?",
];

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
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
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: newHistory }),
        signal: controller.signal,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = "";
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6);
          if (raw === "[DONE]") break;
          try {
            const { text } = JSON.parse(raw);
            assistantContent += text;
            setMessages(prev => {
              const copy = [...prev];
              copy[copy.length - 1] = { role: "assistant", content: assistantContent };
              return copy;
            });
          } catch {}
        }
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
      <div className="px-6 py-4 border-b border-navy-border">
        <h1 className="text-lg font-semibold text-white">CTI Chat</h1>
        <p className="text-xs text-slate-500 mt-0.5">Ask about threats, IOCs, CVEs, or actors in your intel database</p>
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
        {messages.map((m, i) => <Message key={i} role={m.role} content={m.content} />)}
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
