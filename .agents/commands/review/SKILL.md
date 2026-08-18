# Adversarial Review

Spawn reviewers on the **opposite tool** to challenge work. Reviewers attack from distinct
lenses grounded in project standards. The deliverable is a synthesized verdict — do NOT make
changes.

**Hard constraint:** Reviewers MUST run via the opposite tool's CLI (`claude -p` or
`opencode -p`). Do NOT use subagents, the Agent tool, or any internal delegation mechanism as
reviewers — those run on *your own* model, which defeats the purpose.

## Step 1 — Load Context

Read `AGENTS.md` and `.agents/commands/llm-tracker.md`. These govern reviewer judgments.

## Step 2 — Determine Scope and Intent

Identify what to review from context (recent diffs, referenced plans, user message).

```bash
git status --short
git branch --show-current
git diff --stat main
git diff main
git ls-files --others --exclude-standard
```

If not on a feature branch, say so. If the diff contains unrelated changes, flag them.

`git diff main` includes committed branch changes plus staged and unstaged tracked changes. `git ls-files --others --exclude-standard` lists untracked paths; read and include the contents of every intended untracked file because Git diff omits them.

Determine the **intent** — what the author is trying to achieve. This is critical: reviewers
challenge whether the work *achieves the intent well*, not whether the intent is correct.
State the intent explicitly before proceeding.

Assess change size:

| Size | Threshold | Reviewers |
|------|-----------|-----------|
| Small | < 50 lines, 1-2 files | 1 (Skeptic) |
| Medium | 50-199 lines, 3-5 files | 2 (Skeptic + Architect) |
| Large | 200+ lines or 5+ files | 3 (Skeptic + Architect + Minimalist) |

Read `references/reviewer-lenses.md` for lens definitions.

## Step 3 — Detect Tool and Spawn Reviewers

Create a temp directory for reviewer output and retain every background process handle:

```sh
REVIEW_DIR=$(mktemp -d /tmp/adversarial-review.XXXXXX)
REVIEW_TIMEOUT_SECONDS=300
review_pids=()
```

Run all reviewer spawn commands and the wait loop within one shell invocation. PIDs and arrays are shell-local; if the host tool cannot preserve shell state, use its native process handles or a single script that performs both steps.

Determine which tool you are, then spawn reviewers on the opposite:

**If you are opencode** — spawn claude code reviewers via `claude` CLI:

```sh
timeout "$REVIEW_TIMEOUT_SECONDS" claude -p "prompt" \
  > "$REVIEW_DIR/skeptic.md" 2> "$REVIEW_DIR/skeptic.stderr" &
review_pids+=("$!")
```

Start each reviewer this way and retain its PID. Use the corresponding `opencode` command when that is the opposite tool.

**If you are claude code** — spawn opencode reviewers via `opencode` CLI:

```sh
timeout "$REVIEW_TIMEOUT_SECONDS" opencode -p "prompt" \
  > "$REVIEW_DIR/skeptic.md" 2> "$REVIEW_DIR/skeptic.stderr" &
review_pids+=("$!")
```

Use the same timeout and PID handling for each reviewer.

Name each output file after the lens: `skeptic.md`, `architect.md`, `minimalist.md`.

Wait for every retained PID before reading any output:

```sh
review_status=()
for pid in "${review_pids[@]}"; do
  if wait "$pid"; then
    status=0
  else
    status=$?
  fi
  review_status+=("$status")
done
```

Record timeout exit status 124 and every other non-zero exit as an incomplete or failed reviewer; do not treat missing, empty, or partial output as a completed review.

Build each reviewer's prompt using the template in `references/reviewer-prompt.md`.

## Step 4 — Verify and Synthesize Verdict

Before reading reviewer output, confirm that the wait loop completed, log which CLI was used, and confirm the output files exist:

```sh
echo "reviewer_cli=opencode|claude"
ls "$REVIEW_DIR"/*.md
```

If any reviewer timed out, exited non-zero, or produced missing or empty output, note the failure
in the verdict — do not silently skip a reviewer.

Read each reviewer's output file from `$REVIEW_DIR/`. Deduplicate overlapping findings.
Produce a single verdict using the format in `references/verdict-format.md`.

## Step 5 — Render Judgment

After synthesizing the reviewers, apply your own judgment. Using the stated intent and
project standards as your frame, state which findings you would accept and which you would
reject — and why. Reviewers are adversarial by design; not every finding warrants action. Call
out false positives, overreach, and findings that mistake style for substance.

Append the Lead Judgment section to the verdict (see `references/verdict-format.md`).

## Rules

- Do not rewrite code during review unless explicitly asked for fixes.
- Do not approve if secrets/privacy/cost/schema risks are unresolved.
- Do not nitpick formatting that tools handle.
- Prefer concrete file/function feedback over vague vibes.
