/**
 * TriageMode — failure handling, keyboard shortcuts, and UI state.
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import TriageMode from "../components/TriageMode";

import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api", () => ({
  feedback: {
    rate: vi.fn(),
    setReadStatus: vi.fn(),
  },
}));

import { feedback as feedbackApi } from "../lib/api";

function makeItem(id = "a1", title = "Test Article") {
  return {
    article: { id, title, threat_category: "Malware", ai_severity_score: 70 },
    score: { computed_score: 0.8 },
  };
}

function Wrapper({ children }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TriageMode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    feedbackApi.rate.mockResolvedValue({});
    feedbackApi.setReadStatus.mockResolvedValue({});
  });

  it("renders the first item's title", () => {
    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1", "CVE Deep Dive")]} onClose={() => {}} />
      </Wrapper>
    );
    expect(screen.getByText("CVE Deep Dive")).toBeInTheDocument();
  });

  it("shows progress counter", () => {
    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1"), makeItem("a2")]} onClose={() => {}} />
      </Wrapper>
    );
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("skip (j) advances without calling API", async () => {
    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1", "First"), makeItem("a2", "Second")]} onClose={() => {}} />
      </Wrapper>
    );

    await userEvent.keyboard("j");
    expect(feedbackApi.rate).not.toHaveBeenCalled();
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("like (u) calls feedbackApi.rate with +1 and advances", async () => {
    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1", "First"), makeItem("a2", "Second")]} onClose={() => {}} />
      </Wrapper>
    );

    await userEvent.keyboard("u");
    await waitFor(() => expect(feedbackApi.rate).toHaveBeenCalledWith("a1", 1));
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("dislike (n) calls feedbackApi.rate with -1 and advances", async () => {
    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1"), makeItem("a2")]} onClose={() => {}} />
      </Wrapper>
    );

    await userEvent.keyboard("n");
    await waitFor(() => expect(feedbackApi.rate).toHaveBeenCalledWith("a1", -1));
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("shows error and does NOT advance when API call fails", async () => {
    feedbackApi.rate.mockRejectedValue({
      response: { data: { detail: "Save failed" } },
    });

    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1", "First"), makeItem("a2", "Second")]} onClose={() => {}} />
      </Wrapper>
    );

    await userEvent.keyboard("u");

    await waitFor(() =>
      expect(screen.getByText("Save failed")).toBeInTheDocument()
    );
    // Counter should still show item 1 — did not advance
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("clears error on next successful action", async () => {
    feedbackApi.rate
      .mockRejectedValueOnce({ response: { data: { detail: "Oops" } } })
      .mockResolvedValue({});

    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1"), makeItem("a2"), makeItem("a3")]} onClose={() => {}} />
      </Wrapper>
    );

    // First action fails → error appears
    await userEvent.keyboard("u");
    await waitFor(() => expect(screen.getByText("Oops")).toBeInTheDocument());

    // Second action succeeds → error gone, advances
    await userEvent.keyboard("u");
    await waitFor(() => expect(screen.queryByText("Oops")).not.toBeInTheDocument());
  });

  it("blocks repeated key presses while saving (saving state)", async () => {
    let resolve;
    feedbackApi.rate.mockReturnValue(new Promise(r => { resolve = r; }));

    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1"), makeItem("a2"), makeItem("a3")]} onClose={() => {}} />
      </Wrapper>
    );

    await userEvent.keyboard("u"); // first press — starts saving
    await userEvent.keyboard("u"); // second press while saving — should be ignored

    act(() => resolve({}));

    // Only one API call despite two key presses
    await waitFor(() => expect(feedbackApi.rate).toHaveBeenCalledTimes(1));
  });

  it("shows triage-complete screen after last item", async () => {
    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1", "Only Article")]} onClose={() => {}} />
      </Wrapper>
    );

    await userEvent.keyboard("j"); // skip the only item
    expect(screen.getByText("Triage complete")).toBeInTheDocument();
  });

  it("calls onClose when exit key pressed on done screen", async () => {
    const onClose = vi.fn();
    render(
      <Wrapper>
        <TriageMode items={[makeItem("a1")]} onClose={onClose} />
      </Wrapper>
    );

    await userEvent.keyboard("j"); // skip → done
    await userEvent.keyboard("{Enter}");
    expect(onClose).toHaveBeenCalled();
  });
});
