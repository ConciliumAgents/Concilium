# Release Workflow

Concilium has two working surfaces:

- Internal development workspace: day-to-day development, dogfood runs, private context, local notes, and native roundtable validation.
- Public release repository: the sanitized open-source distribution at `https://github.com/ConciliumAgents/Concilium.git`.

The public repository is a release surface. It should receive reviewed, public-safe changes from the internal workspace, not every local change by default.

## Success Criteria

A public update is ready only when all of the following are true:

1. The intended code or documentation change is complete in the internal workspace.
2. The public release branch contains only changes intended for the open-source repository.
3. English is the default language for project files, with `README.zh-CN.md` as the Chinese translation.
4. Private paths, private project names, local transcripts, credentials, and internal-only notes are absent.
5. Tests, diff checks, public-safety scans, and remote verification pass.

## Repository Remotes

In the public release worktree, use explicit remotes:

```text
concilium  https://github.com/ConciliumAgents/Concilium.git
```

An `origin` remote may exist because the release worktree can share Git metadata with internal linked worktrees. Do not use `origin` for public release pushes.

Set the default push remote to the public repository in the release worktree:

```bash
git config extensions.worktreeConfig true
git config --worktree remote.pushDefault concilium
```

`concilium` is the only remote used for public release pushes. Worktree-scoped configuration avoids changing the internal workspace while still making accidental pushes from the release worktree safer.

Before any public push, verify:

```bash
git remote -v
git config --get remote.pushDefault
git ls-remote concilium refs/heads/main
```

## Update Flow

1. Finish the change in the internal workspace.
2. Create a release branch from the current public baseline.
3. Bring over only the public-safe code and documentation changes.
4. Apply the public transform:
   - keep project-facing files in English;
   - update `README.md` and `README.zh-CN.md` together when reader-facing behavior changes;
   - remove private paths, local account details, raw seat transcripts, and internal-only project notes;
   - describe the tool from first principles instead of relying on private roadmap or phase language.
5. Run the public release gates.
6. Push the release branch to `concilium`.
7. Review the pushed branch or pull request.
8. Merge to `main` only after the gates and review are clean.

For small documentation-only fixes, a direct `main` push is acceptable only when the scope is obvious, the working tree is clean, and the public-safety checks pass.

## Public Release Gates

Run these before pushing:

```bash
git status --short --branch
git diff --check
git ls-files .roundtable
rg -n --hidden --no-ignore --pcre2 "\p{Han}" . --glob '!.git' --glob '!.git/**' --glob '!.roundtable/**' --glob '!README.zh-CN.md'
rg -n --hidden --no-ignore "/Users/"'melee'"|amazon-"'fba'"|fin"'ance'"|liting"'0216' . --glob '!.git' --glob '!.git/**' --glob '!.roundtable/**'
rg -n --hidden --no-ignore 'sk-[A-Za-z0-9]{20,}|gho''_[A-Za-z0-9]{20,}|github''_pat_[A-Za-z0-9_]{20,}' . --glob '!.git' --glob '!.git/**' --glob '!.roundtable/**'
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
```

Expected results:

- Working tree contains only intended public-release changes.
- `git diff --check` prints no errors.
- `git ls-files .roundtable` prints nothing.
- The Chinese-language scan has no matches outside `README.zh-CN.md`.
- Private-path, private-project, and secret scans have no live or sensitive matches.
- Unit tests pass.

The scans are intentionally conservative. They exclude local Git metadata and untracked `.roundtable` session artifacts because those are not publishable content; `git ls-files .roundtable` separately verifies that no session artifacts are tracked. Review any match before treating the gate as passed.

## Push And Verify

Use the explicit public remote:

```bash
git push concilium HEAD:<release-branch>
```

After merge or direct push to `main`, verify the public branch:

```bash
git ls-remote https://github.com/ConciliumAgents/Concilium.git refs/heads/main
```

Run tests from a clean clone so Git metadata is available:

```bash
tmpdir=$(mktemp -d)
git clone --depth 1 https://github.com/ConciliumAgents/Concilium.git "$tmpdir/Concilium"
cd "$tmpdir/Concilium"
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
```

Then verify the downloadable archive for public content only. GitHub source archives do not include `.git` metadata, so tests that report branch or commit identity should be run from the clean clone above instead of from the tarball.

```bash
tmpdir=$(mktemp -d)
curl -fsSL https://github.com/ConciliumAgents/Concilium/archive/refs/heads/main.tar.gz -o "$tmpdir/concilium-main.tar.gz"
tar -xzf "$tmpdir/concilium-main.tar.gz" -C "$tmpdir"
cd "$tmpdir"/Concilium-main
rg -n --hidden --no-ignore --pcre2 "\p{Han}" . --glob '!.git' --glob '!.git/**' --glob '!.roundtable/**' --glob '!README.zh-CN.md'
rg -n --hidden --no-ignore "/Users/"'melee'"|amazon-"'fba'"|fin"'ance'"|liting"'0216' . --glob '!.git' --glob '!.git/**' --glob '!.roundtable/**'
rg -n --hidden --no-ignore 'sk-[A-Za-z0-9]{20,}|gho''_[A-Za-z0-9]{20,}|github''_pat_[A-Za-z0-9_]{20,}' . --glob '!.git' --glob '!.git/**' --glob '!.roundtable/**'
```

## Public Boundary

Do not publish:

- `.roundtable/sessions/**`
- provider credentials or local token files
- private memory, raw seat transcripts, or unsanitized support logs
- local account details, billing screenshots, or private proxy/provider notes
- internal-only project notes that assume private context
- private business project names or paths unrelated to Concilium

Public docs should explain Concilium from first principles: what problem it solves, how it works, how to run it, and how to contribute safely.

## Backport Flow

If a public issue or pull request changes core behavior:

1. Review and verify the public contribution in the public repository.
2. Bring the accepted change back into the internal workspace.
3. Re-run internal dogfood or roundtable checks if the change touches orchestration behavior.
4. Keep the public and internal behavior aligned through code, not through private notes.
