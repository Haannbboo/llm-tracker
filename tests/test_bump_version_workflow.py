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


def test_bump_version_workflow_bumps_only_changed_packages_from_base_version():
    workflow = load_workflow()

    checkout_step = workflow["jobs"]["bump"]["steps"][0]
    bump_step = workflow["jobs"]["bump"]["steps"][1]

    assert checkout_step["with"]["ref"] == "${{ github.head_ref }}"
    assert checkout_step["with"]["fetch-depth"] == 0
    # The base ref goes through the environment: an inline ${{ }} would let a
    # branch name containing shell syntax run inside this script.
    assert bump_step["env"]["BASE_REF"] == "${{ github.base_ref }}"
    assert "github.base_ref" not in bump_step["run"]
    assert 'git fetch origin "$BASE_REF" --depth=1' in bump_step["run"]
    assert 'git diff --name-only "origin/$BASE_REF...HEAD"' in bump_step["run"]
    assert "client/*|plugins/*|scripts/hosted-install.sh)" in bump_step["run"]
    assert "server/*|src/*|frontend/*" in bump_step["run"]
    assert "protocol/*|scripts/configure-*)" in bump_step["run"]
    assert 'git show "origin/$BASE_REF:$FILE"' in bump_step["run"]
    assert "bump_file VERSION" in bump_step["run"]
    assert "bump_file client/VERSION" in bump_step["run"]
    assert "BASE_PATCH + 1" in bump_step["run"]


def test_bump_version_workflow_never_lowers_an_existing_patch_version():
    workflow = load_workflow()

    bump_step = workflow["jobs"]["bump"]["steps"][1]

    assert "CURRENT_PATCH > BASE_PATCH + 1" in bump_step["run"]
    assert "CURRENT_PATCH" in bump_step["run"]


def test_bump_version_workflow_fails_when_path_detection_fails():
    """A failed git diff must fail the job, not silently bump nothing."""
    workflow = load_workflow()

    bump_step = workflow["jobs"]["bump"]["steps"][1]

    # The diff is captured and status-checked; the loop no longer reads from a
    # process substitution, which discards git's exit status.
    assert (
        'if ! CHANGED_FILES=$(git diff --name-only "origin/$BASE_REF...HEAD"); then'
        in bump_step["run"]
    )
    assert '<<< "$CHANGED_FILES"' in bump_step["run"]
    assert "< <(git diff" not in bump_step["run"]


def test_bump_version_workflow_includes_version_in_bump_commit_message():
    workflow = load_workflow()

    assert "pull-requests" not in workflow.get("permissions", {})
    auto_commit_step = next(
        step
        for step in workflow["jobs"]["bump"]["steps"]
        if step.get("uses") == "stefanzweifel/git-auto-commit-action@v5"
    )

    assert (
        auto_commit_step["with"]["commit_message"]
        == "chore: bump version to ${{ steps.bump.outputs.new_version }}"
    )
    assert auto_commit_step["if"] == "steps.bump.outputs.changed == 'true'"
    assert auto_commit_step["with"]["file_pattern"] == "VERSION client/VERSION"
    assert not any(
        step.get("name") == "Append version to PR title"
        for step in workflow["jobs"]["bump"]["steps"]
    )
