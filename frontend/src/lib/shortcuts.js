// Shared keyboard helpers — every shortcut handler should use isTypingTarget
// so keys never fire while the user is typing.

export function isTypingTarget(e) {
  const t = e.target;
  if (!t) return false;
  const tag = t.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    t.isContentEditable
  );
}

// Binding reference rendered by the ? help overlay.
// Designed for one-handed use: everything lives in the right-hand home cluster.
export const SHORTCUT_GROUPS = [
  {
    title: "Bulletin",
    keys: [
      ["j / k", "next / previous article"],
      ["h or Esc", "back to daily brief"],
      ["o or Enter", "open full article page"],
      ["m", "dismiss (mute) + advance"],
      ["u", "thumbs up + advance"],
      ["n", "thumbs down (nope) + advance"],
      ["i", "cycle read status"],
      ["Space / Shift+Space", "scroll reading pane"],
      [", / .", "previous / next page"],
      ["1–9", "jump to rank N"],
      ["y", "copy source URL"],
      ["t", "triage mode"],
    ],
  },
  {
    title: "Article page",
    keys: [
      ["j / k", "next / previous article"],
      ["u / n", "thumbs up / down"],
      ["m", "dismiss + back"],
      ["e", "raw text popout (highlighted enrichments)"],
      ["y", "copy source URL"],
      ["c or Esc", "back to bulletin"],
    ],
  },
  {
    title: "Global",
    keys: [
      ["g then b / i / c / f / s", "go to Bulletin / Intel / Chat / Feedback / Settings"],
      ["Ctrl+K", "command palette"],
      ["?", "this help"],
    ],
  },
];
