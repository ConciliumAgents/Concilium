# Public Release Workflow

Concilium has two working surfaces:

- Internal development workspace: day-to-day dogfood, private context, and native roundtable validation.
- Public release repository: sanitized open-source distribution at `https://github.com/ConciliumAgents/Concilium.git`.

The public repository is a release mirror, not the source of all local work. Push to it only after the release gates below pass.

## Repository Remotes

Expected local remotes in the release worktree:

```text
origin    https://github.com/liting0216/loop-engine.git
concilium https://github.com/ConciliumAgents/Concilium.git
```

Do not replace `origin` with the public repository. Keeping a separate `concilium` remote makes public publishing an explicit action.

## Update Flow

1. Start from the internal development branch or a release worktree.
2. Create a public release branch for the update.
3. Apply only changes intended for the public repository.
4. Run the public-safety checks.
5. Push the release branch to the private public repository for precheck.
6. Fresh-clone the public repository and run smoke checks.
7. Make the repository public or tag a release only after owner approval.

## Public-Safety Checks

Run these before pushing:

```bash
git status --short --branch
git diff --check
git ls-files .roundtable
rg -n 'sk-[A-Za-z0-9]|gho''_[A-Za-z0-9]|github''_pat_|ANTHROPIC''_API_KEY|OPENAI''_API_KEY|MOONSHOT''_API_KEY|DEEPSEEK''_API_KEY' .
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
```

Expected results:

- Working tree contains only intended public-release changes.
- `git diff --check` prints no errors.
- `git ls-files .roundtable` prints nothing.
- Secret scan has no live credential matches.
- Unit tests pass.

The secret scan is intentionally broad. Review matches before treating the gate as passed.

## Push To Private Precheck

Use the explicit public remote:

```bash
git push concilium HEAD:main
```

Avoid force-pushing the public `main` branch unless the owner explicitly approves the rewrite.

## Fresh-Clone Smoke Test

After pushing, verify the public repository from a clean clone:

```bash
tmpdir=$(mktemp -d)
git clone --depth 1 https://github.com/ConciliumAgents/Concilium.git "$tmpdir/Concilium"
cd "$tmpdir/Concilium"
./roundtable --version
./roundtable --doctor
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
```

The clone should report the pushed commit on `main`, detect available local seats, and pass the test suite.

## Public Boundary

Do not publish:

- `.roundtable/sessions/**`
- provider credentials or local token files
- private memory, raw seat transcripts, or unsanitized support logs
- local account details, billing screenshots, or private proxy/provider notes
- internal-only project notes that assume private context

Public docs should explain Concilium from first principles: what problem it solves, how it works, how to run it, and how to contribute safely.
