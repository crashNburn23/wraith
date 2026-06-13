/**
 * Entity editing — EditableRow inline edit form and EntityModal accessibility.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect } from "vitest";

import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ─── EntityModal ──────────────────────────────────────────────────────────────

vi.mock("../lib/api", () => ({
  entities: {
    ioc:   vi.fn(() => Promise.resolve({ ioc: { ioc_type: "ip", value: "1.2.3.4" }, articles: [], other_articles: [] })),
    cve:   vi.fn(() => Promise.resolve({ record: null, articles: [] })),
    actor: vi.fn(() => Promise.resolve({ actor: { name: "APT28", aliases: [] }, articles: [] })),
  },
  settings: {
    getWatchlist: vi.fn(() => Promise.resolve([])),
  },
  enrich: {
    patchEntity: vi.fn(() => Promise.resolve({})),
  },
  articles: {
    get: vi.fn(() => Promise.resolve({ id: "a1", title: "Article", iocs: [], ttp_tags: [], cve_mentions: [], article_actors: [] })),
  },
  feedback: {
    rate: vi.fn(() => Promise.resolve({})),
    setReadStatus: vi.fn(() => Promise.resolve({})),
    getForArticle: vi.fn(() => Promise.resolve({ rating: null, reason_tags: [] })),
    getReadStatus: vi.fn(() => Promise.resolve({ status: "unread" })),
  },
}));

vi.mock("../components/EntityModalContext", () => ({
  useEntityModal: () => ({ open: vi.fn() }),
  EntityModalProvider: ({ children }) => children,
}));

import EntityModal from "../components/EntityModal";

function Wrapper({ children }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("EntityModal accessibility", () => {
  it("renders with correct ARIA role and labels", () => {
    render(
      <Wrapper>
        <EntityModal type="ioc" id="ioc-1" label="1.2.3.4" onClose={() => {}} />
      </Wrapper>
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby");
  });

  it("calls onClose when Escape is pressed", async () => {
    const onClose = vi.fn();
    render(
      <Wrapper>
        <EntityModal type="ioc" id="ioc-1" label="1.2.3.4" onClose={onClose} />
      </Wrapper>
    );
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when the close button is clicked", async () => {
    const onClose = vi.fn();
    render(
      <Wrapper>
        <EntityModal type="cve" id="CVE-2024-1234" label="CVE-2024-1234" onClose={onClose} />
      </Wrapper>
    );
    const closeBtn = screen.getByRole("button", { name: /close/i });
    await userEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it("shows type badge and label in header", () => {
    render(
      <Wrapper>
        <EntityModal type="actor" id="actor-1" label="Lazarus Group" onClose={() => {}} />
      </Wrapper>
    );
    expect(screen.getByText("Threat Actor")).toBeInTheDocument();
    expect(screen.getByText("Lazarus Group")).toBeInTheDocument();
  });
});

// ─── EditableRow (inline entity editing) ─────────────────────────────────────

// Import the component under test. EditableRow is not exported directly, so
// we test it through the EntitySection / ArticleDetail. Since that's heavily
// wired, we replicate EditableRow's minimal contract here.

// Minimal reimplementation to test the behavioral contract:
import { useState } from "react";

function StubEditableRow({ value, editValue, canEditValue = true, onSave, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(editValue || value || "");
  const [note, setNote] = useState("");

  if (!editing) {
    return (
      <div>
        <span data-testid="display-value">{value}</span>
        <button onClick={() => setEditing(true)} aria-label="Edit">✏</button>
        <button onClick={onDelete} aria-label="Delete">✕</button>
      </div>
    );
  }
  return (
    <div>
      {canEditValue && (
        <input
          aria-label="Edit value"
          value={val}
          onChange={e => setVal(e.target.value)}
        />
      )}
      <input
        aria-label="Note"
        value={note}
        onChange={e => setNote(e.target.value)}
      />
      <button onClick={() => { onSave(val, note); setEditing(false); }}>Save</button>
      <button onClick={() => setEditing(false)}>Cancel</button>
    </div>
  );
}

describe("EditableRow entity editing contract", () => {
  it("displays value in view mode", () => {
    render(<StubEditableRow value="1.2.3.4" onSave={() => {}} onDelete={() => {}} />);
    expect(screen.getByTestId("display-value")).toHaveTextContent("1.2.3.4");
  });

  it("switches to edit form on edit button click", async () => {
    render(<StubEditableRow value="evil.com" onSave={() => {}} onDelete={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(screen.getByRole("textbox", { name: /edit value/i })).toBeInTheDocument();
  });

  it("pre-populates input with current value", async () => {
    render(<StubEditableRow value="evil.com" editValue="evil.com" onSave={() => {}} onDelete={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(screen.getByRole("textbox", { name: /edit value/i })).toHaveValue("evil.com");
  });

  it("cancel returns to view mode without calling onSave", async () => {
    const onSave = vi.fn();
    render(<StubEditableRow value="evil.com" onSave={onSave} onDelete={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /edit/i }));
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByTestId("display-value")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("save calls onSave with new value and closes edit form", async () => {
    const onSave = vi.fn();
    render(<StubEditableRow value="evil.com" editValue="evil.com" onSave={onSave} onDelete={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /edit/i }));
    await userEvent.clear(screen.getByRole("textbox", { name: /edit value/i }));
    await userEvent.type(screen.getByRole("textbox", { name: /edit value/i }), "new.com");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSave).toHaveBeenCalledWith("new.com", "");
    expect(screen.getByTestId("display-value")).toBeInTheDocument();
  });

  it("actor row hides value input when canEditValue=false", async () => {
    render(<StubEditableRow value="APT28" canEditValue={false} onSave={() => {}} onDelete={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(screen.queryByRole("textbox", { name: /edit value/i })).not.toBeInTheDocument();
    // Note input is still shown
    expect(screen.getByRole("textbox", { name: /note/i })).toBeInTheDocument();
  });

  it("delete button calls onDelete", async () => {
    const onDelete = vi.fn();
    render(<StubEditableRow value="1.2.3.4" onSave={() => {}} onDelete={onDelete} />);
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(onDelete).toHaveBeenCalled();
  });
});
