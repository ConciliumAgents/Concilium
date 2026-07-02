# Roundtable Persistent Memory

`roundtable-memory/` is git-versioned persistent memory for Concilium roundtable runs. Any cloned agent can read this directory without access to a private memory store.

- `INDEX.md`: outcome index, grouped by project and topic.
- `<project>/<topic>.md`: archived conclusions for a topic.
- `LESSONS.md`: general and project-specific lessons used during recall.

## Writer

`archive_to_memory()` in `skills/loop-engine/bin/conductor.py` appends PASS outcomes to topic leaves and updates `INDEX.md`. It also extracts lesson sections from roundtable minutes and writes them into `LESSONS.md`.

Humans may edit archived leaves when preparing future roundtable input.

## Write Discipline

- Search `General Rules` before adding a new lesson.
- Merge similar lessons instead of adding duplicates.
- Mark outdated lessons as `SUPERSEDED` with a short reason.
- Keep general rules small and stable.
- Project-specific sections may grow linearly with real project history.

## Format Rules

- Use standard Markdown links: `[display name](relative/path)`.
- Do not use wiki links.
- Do not use frontmatter; put metadata below the title.
- Write source pointers relative to the repository root.
- Prefer ASCII topic filenames for public release compatibility.
