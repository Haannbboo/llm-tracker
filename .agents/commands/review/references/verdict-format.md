# Verdict Format

```markdown
## Intent
<what the author is trying to achieve>

## Verdict: PASS | CONTESTED | REJECT
<one-line summary>

## Findings
<numbered list, ordered by severity (high -> medium -> low)>

For each finding:
- **[severity]** Description with file:line references
- Lens: which reviewer raised it
- Recommendation: concrete action, not vague advice

## What Went Well
<1-3 things the reviewers found no issue with — acknowledge good work>

## Lead Judgment
<for each finding: accept or reject with a one-line rationale>
```

## Verdict Logic

- **PASS** — no unresolved high-severity findings and no unresolved security, privacy, secret, cost, or schema findings at any severity
- **CONTESTED** — high-severity findings but reviewers disagree on them
- **REJECT** — high-severity findings with reviewer consensus
