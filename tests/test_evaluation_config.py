import os
import tempfile

from config.app import CONFIG, set_evaluation_evaluator


def test_set_evaluation_evaluator():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("evaluation:\n  evaluator: codex\n")
        f.flush()
        path = f.name

    try:
        set_evaluation_evaluator("claude", path)
        with open(path) as f:
            content = f.read()
        assert "evaluator: claude" in content
        assert CONFIG["evaluation"]["evaluator"] == "claude"
    finally:
        os.unlink(path)
