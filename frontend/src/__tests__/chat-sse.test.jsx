/**
 * Tests for Chat SSE streaming parser.
 *
 * The core logic is the `consumeEvents` loop inside `send()`. We test it by
 * mocking `fetch` with a ReadableStream that emits various SSE payloads and
 * asserting that messages are accumulated correctly.
 */
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, describe, it, expect, afterEach } from "vitest";
import Chat from "../pages/Chat";

// Minimal router + auth context
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/auth", () => ({ getToken: () => "test-token" }));

function makeStream(chunks) {
  let idx = 0;
  return new ReadableStream({
    pull(controller) {
      if (idx < chunks.length) {
        controller.enqueue(new TextEncoder().encode(chunks[idx++]));
      } else {
        controller.close();
      }
    },
  });
}

function Wrapper({ children }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Chat SSE streaming", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("accumulates streamed text tokens into assistant message", async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: makeStream([
          'data: {"text":"Hello"}\n\n',
          'data: {"text":", world"}\n\n',
          "data: [DONE]\n\n",
        ]),
      })
    );

    render(<Wrapper><Chat /></Wrapper>);

    const textarea = screen.getByPlaceholderText(/Ask about threats/i);
    fireEvent.change(textarea, { target: { value: "test query" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    await waitFor(() =>
      expect(screen.getByText("Hello, world")).toBeInTheDocument()
    );
  });

  it("handles events split across multiple chunks (frame-safe)", async () => {
    // SSE event split: first chunk has only half of the data line
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: makeStream([
          'data: {"te',          // incomplete line
          'xt":"Split"}\n\n',    // rest of event
          "data: [DONE]\n\n",
        ]),
      })
    );

    render(<Wrapper><Chat /></Wrapper>);

    const textarea = screen.getByPlaceholderText(/Ask about threats/i);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    await waitFor(() =>
      expect(screen.getByText("Split")).toBeInTheDocument()
    );
  });

  it("shows error message on HTTP failure", async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, body: null })
    );

    render(<Wrapper><Chat /></Wrapper>);

    const textarea = screen.getByPlaceholderText(/Ask about threats/i);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    await waitFor(() =>
      expect(screen.getByText(/HTTP 500/)).toBeInTheDocument()
    );
  });

  it("blocks re-send while streaming is in progress", async () => {
    let resolveStream;
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: new ReadableStream({
          start(controller) {
            // Never close until test resolves
            resolveStream = () => controller.close();
          },
        }),
      })
    );

    render(<Wrapper><Chat /></Wrapper>);

    const textarea = screen.getByPlaceholderText(/Ask about threats/i);
    fireEvent.change(textarea, { target: { value: "first" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    // Stop button should appear; the Send button should be gone
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Stop/i })).toBeInTheDocument()
    );

    // Sending again while streaming does nothing
    const callsBefore = global.fetch.mock.calls.length;
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(global.fetch.mock.calls.length).toBe(callsBefore);

    act(() => resolveStream());
  });
});

// ─── Pure SSE parse logic unit tests ─────────────────────────────────────────

describe("SSE event parsing (pure logic)", () => {
  // Mirrors the consumeEvents logic from Chat.jsx without React
  function parseSSE(rawBuffer) {
    const tokens = [];
    let buffer = rawBuffer;
    let done = false;

    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() || "";
    for (const event of events) {
      for (const line of event.split(/\r?\n/)) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6);
        if (raw === "[DONE]") { done = true; return { tokens, done, remainder: buffer }; }
        const { text } = JSON.parse(raw);
        tokens.push(text);
      }
    }
    return { tokens, done, remainder: buffer };
  }

  it("parses a single complete event", () => {
    const { tokens, done } = parseSSE('data: {"text":"hello"}\n\n');
    expect(tokens).toEqual(["hello"]);
    expect(done).toBe(false);
  });

  it("parses multiple events in one buffer", () => {
    const { tokens } = parseSSE('data: {"text":"a"}\n\ndata: {"text":"b"}\n\n');
    expect(tokens).toEqual(["a", "b"]);
  });

  it("stops at [DONE] and ignores subsequent data", () => {
    const { tokens, done } = parseSSE('data: {"text":"x"}\n\ndata: [DONE]\n\ndata: {"text":"y"}\n\n');
    expect(tokens).toEqual(["x"]);
    expect(done).toBe(true);
  });

  it("preserves incomplete trailing event as remainder", () => {
    const { tokens, remainder } = parseSSE('data: {"text":"a"}\n\ndata: {"tex');
    expect(tokens).toEqual(["a"]);
    expect(remainder).toBe('data: {"tex');
  });
});
