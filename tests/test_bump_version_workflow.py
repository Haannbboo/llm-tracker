from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "bump-version.yml"


def load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_bump_version_workflow_runs_for_prs_targeting_main():
    workflow = load_workflow()

    triggers = workflow["on"]

    assert "push" not in triggers
    assert triggers["pull_request"]["branches"] == ["main"]
    assert triggers["pull_request"]["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    ]


def test_bump_version_workflow_skips_its_own_bump_commit():
    workflow = load_workflow()

    bump_job = workflow["jobs"]["bump"]

    assert bump_job["if"] == (
        "github.actor != 'github-actions[bot]' && "
        "github.event.pull_request.head.repo.full_name == github.repository"
    )


def test_bump_version_workflow_bumps_pr_branch_from_base_version():
    workflow = load_workflow()

    checkout_step = workflow["jobs"]["bump"]["steps"][0]
    bump_step = workflow["jobs"]["bump"]["steps"][1]

    assert checkout_step["with"]["ref"] == "${{ github.head_ref }}"
    assert checkout_step["with"]["fetch-depth"] == 0
    assert 'git fetch origin "${{ github.base_ref }}" --depth=1' in bump_step["run"]
    assert (
        'BASE_VERSION=$(git show "origin/${{ github.base_ref }}:VERSION" 2>/dev/null '
        '|| echo "0.0.0")'
    ) in bump_step["run"]
    assert "BASE_PATCH + 1" in bump_step["run"]


def test_bump_version_workflow_includes_version_in_bump_commit_message():
    workflow = load_workflow()

    assert "pull-requests" not in workflow["permissions"]
    auto_commit_step = next(
        step
        for step in workflow["jobs"]["bump"]["steps"]
        if step.get("uses") == "stefanzweifel/git-auto-commit-action@v5"
    )

    assert (
        auto_commit_step["with"]["commit_message"]
        == "chore: bump version to ${{ steps.bump.outputs.new_version }}"
    )
    assert not any(
        step.get("name") == "Append version to PR title"
        for step in workflow["jobs"]["bump"]["steps"]
    )
