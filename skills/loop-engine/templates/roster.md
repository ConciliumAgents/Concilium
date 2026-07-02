# Seat Roster (KB)

> The chair reads this during planning and assigns subtasks based on each seat's strengths. Add, remove, or adjust seats as the local environment changes.

## claude (Claude Code)

- **Strong at:** orchestration, planning, synthesis, long-context review, multi-file reasoning.
- **Best for:** chair duties, high-context edits, final synthesis, and read-only review.
- **Call:** `seat-claude.sh <repo> plan|exec|review`.

## codex (OpenAI Codex CLI)

- **Strong at:** code review, bug finding, focused implementation, terminal-based verification.
- **Best for:** independent code review and targeted coding tasks when reachable.
- **Note:** use native severity markers such as `[P0]` and `[P1]` as blocking signals.
- **Call:** `seat-codex.sh <repo> review|exec`.

## hermes (NousResearch Hermes)

- **Strong at:** broad tool use, browser/computer-use workflows, environment checks, alternative provider backends.
- **Best for:** execution, external checks, and heterogeneous review.
- **Call:** `seat-hermes.sh <repo> exec|review "<brief>" [provider] [model]`.

## kimi (Kimi)

- **Strong at:** strict review, coding, and independent reasoning from a different provider lineage.
- **Best for:** implementation, deep review, and heterogeneous cross-checks.
- **Call:** `seat-kimi.sh <repo> exec|review "<brief>"`.

---

To add a local agent, create a new section with strengths, best-fit tasks, and the exact call pattern.
