---
name: Test Failure
about: Report a failing test (backend or frontend)
title: '[TEST] '
labels: ['needs-triage']
assignees: []
---

## Test(s) Failing
<!-- Test file name and test names -->

## Failure Summary
<!-- Paste the key assertion / error message -->

## Regression Check
- [ ] This test used to pass
- [ ] This is a new test

## Environment
- Branch/Commit:
- `uv run python -m pytest -q` result:
- `cd frontend && npm test` result:
