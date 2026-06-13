/**
 * Bulletin cluster expansion logic — pure unit tests.
 *
 * The Bulletin component computes visibleItems via an inline algorithm.
 * These tests replicate that algorithm and verify the expand/collapse behavior,
 * orphan member handling, and dismissed-item filtering.
 */
import { describe, it, expect } from "vitest";

// ─── Inline replication of Bulletin's cluster algorithm ───────────────────────

function buildVisible(allItems, expandedClusters, showHidden = false) {
  const flatVisible = showHidden
    ? allItems
    : allItems.filter(i => i.status !== "dismissed");

  const clusterMemberMap = {};
  for (const item of flatVisible) {
    if (item.cluster_id && !item.is_cluster_lead) {
      (clusterMemberMap[item.cluster_id] ??= []).push(item);
    }
  }

  const visibleLeadClusters = new Set(
    flatVisible.filter(i => i.cluster_id && i.is_cluster_lead).map(i => i.cluster_id)
  );

  const visibleItems = [];
  for (const item of flatVisible) {
    if (item.cluster_id && !item.is_cluster_lead && visibleLeadClusters.has(item.cluster_id)) {
      continue; // member hidden until lead is expanded
    }
    visibleItems.push(item);
    if (item.cluster_id && item.is_cluster_lead && expandedClusters.has(item.cluster_id)) {
      visibleItems.push(...(clusterMemberMap[item.cluster_id] || []));
    }
  }

  return visibleItems;
}

// ─── Fixtures ────────────────────────────────────────────────────────────────

const lead = (id, cluster_id = "c1") => ({ id, cluster_id, is_cluster_lead: true });
const member = (id, cluster_id = "c1") => ({ id, cluster_id, is_cluster_lead: false });
const singleton = (id) => ({ id, cluster_id: null, is_cluster_lead: false });

describe("Bulletin cluster visibility", () => {
  it("shows only lead when cluster is collapsed", () => {
    const items = [lead("lead1"), member("m1"), member("m2"), singleton("s1")];
    const visible = buildVisible(items, new Set());
    expect(visible.map(i => i.id)).toEqual(["lead1", "s1"]);
  });

  it("injects members after lead when cluster is expanded", () => {
    const items = [lead("lead1"), member("m1"), member("m2"), singleton("s1")];
    const visible = buildVisible(items, new Set(["c1"]));
    expect(visible.map(i => i.id)).toEqual(["lead1", "m1", "m2", "s1"]);
  });

  it("preserves rank order for singletons among cluster leads", () => {
    const items = [singleton("s1"), lead("lead1"), singleton("s2"), member("m1")];
    const visible = buildVisible(items, new Set());
    expect(visible.map(i => i.id)).toEqual(["s1", "lead1", "s2"]);
  });

  it("shows orphaned member as standalone when lead is dismissed/absent", () => {
    // lead is dismissed → not in flatVisible; member has no visible lead → shows as standalone
    const items = [member("m1", "c99"), singleton("s1")];
    const visible = buildVisible(items, new Set());
    expect(visible.map(i => i.id)).toContain("m1");
  });

  it("handles multiple independent clusters", () => {
    const items = [
      lead("lead1", "c1"), member("m1", "c1"),
      lead("lead2", "c2"), member("m2", "c2"),
    ];
    // Only c1 expanded
    const visible = buildVisible(items, new Set(["c1"]));
    expect(visible.map(i => i.id)).toEqual(["lead1", "m1", "lead2"]);
  });

  it("toggles cluster correctly — expand then collapse", () => {
    const items = [lead("lead1"), member("m1"), member("m2")];

    const expanded = buildVisible(items, new Set(["c1"]));
    expect(expanded.map(i => i.id)).toEqual(["lead1", "m1", "m2"]);

    const collapsed = buildVisible(items, new Set());
    expect(collapsed.map(i => i.id)).toEqual(["lead1"]);
  });

  it("filters dismissed items when showHidden is false", () => {
    const items = [
      { ...singleton("s1"), status: "dismissed" },
      singleton("s2"),
    ];
    const visible = buildVisible(items, new Set(), false);
    expect(visible.map(i => i.id)).toEqual(["s2"]);
  });

  it("shows dismissed items when showHidden is true", () => {
    const items = [
      { ...singleton("s1"), status: "dismissed" },
      singleton("s2"),
    ];
    const visible = buildVisible(items, new Set(), true);
    expect(visible.map(i => i.id)).toEqual(["s1", "s2"]);
  });

  it("a cluster with no members renders lead alone", () => {
    const items = [lead("lead1")];
    const visible = buildVisible(items, new Set(["c1"]));
    expect(visible.map(i => i.id)).toEqual(["lead1"]);
  });
});
