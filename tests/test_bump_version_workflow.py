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


def test_bump_version_workflow_appends_version_to_pr_title():
    workflow = load_workflow()

    assert workflow["permissions"]["pull-requests"] == "write"
    update_title_step = next(
        step
        for step in workflow["jobs"]["bump"]["steps"]
        if step.get("name") == "Append version to PR title"
    )

    assert update_title_step["name"] == "Append version to PR title"
    assert update_title_step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "version ${{ steps.bump.outputs.new_version }}" in update_title_step["run"]
    assert (
        'gh pr edit "${{ github.event.pull_request.number }}"'
        in update_title_step["run"]
    )
