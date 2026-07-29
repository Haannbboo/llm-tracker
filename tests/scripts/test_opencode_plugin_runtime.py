from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "plugins" / "opencode"


def _copy_clean_plugin_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "repo"
    plugins_dir = workspace / "plugins"
    plugins_dir.mkdir(parents=True)

    def ignore_ignored_artifacts(directory: str, names: list[str]) -> set[str]:
        ignored = {"dist", "node_modules", "CLAUDE.local.md"} & set(names)
        if Path(directory).name == "src":
            ignored |= {"shared"} & set(names)
        return ignored

    shutil.copytree(
        REPO_ROOT / "plugins" / "opencode",
        plugins_dir / "opencode",
        ignore=ignore_ignored_artifacts,
    )
    shutil.copytree(
        REPO_ROOT / "plugins" / "shared",
        plugins_dir / "shared",
        ignore=lambda _dir, names: {"CLAUDE.local.md"} & set(names),
    )
    return plugins_dir / "opencode"


@pytest.mark.slow
def test_opencode_plugin_emits_status_for_failed_assistant_messages(tmp_path):
    if not shutil.which("npm") or not shutil.which("node"):
        pytest.skip("node and npm are required for the OpenCode plugin runtime test")

    plugin_dir = _copy_clean_plugin_workspace(tmp_path)
    install = subprocess.run(
        ["npm", "install", "--no-package-lock"],
        cwd=plugin_dir,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert install.returncode == 0, install.stderr
    shared_src = plugin_dir.parent / "shared" / "src"
    shared_src.joinpath("PRIVATE.local.md").write_text("private\n", encoding="utf-8")
    shared_src.joinpath("generated.js").write_text("export {}\n", encoding="utf-8")
    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=plugin_dir,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert build.returncode == 0, build.stderr
    assert not plugin_dir.joinpath("src", "shared", "src", "PRIVATE.local.md").exists()
    assert not plugin_dir.joinpath("src", "shared", "src", "generated.js").exists()

    harness = textwrap.dedent(
        """
        const { default: plugin } = await import("./dist/index.js")

        const payloads = []
        globalThis.fetch = async (_url, options) => {
          payloads.push(JSON.parse(options.body))
          return { ok: true, status: 200 }
        }

        const hooks = await plugin({
          client: {
            session: {
              message: async () => undefined,
            },
          },
        }, { endpoint: "http://collector.example/v1/logs" })

        await hooks.event({
          event: {
            type: "message.updated",
            properties: {
              info: {
                id: "msg-api-error",
                sessionID: "ses-1",
                role: "assistant",
                time: { created: 1000, completed: 1250 },
                error: {
                  name: "APIError",
                  data: { statusCode: 429, isRetryable: true },
                },
                parentID: "user-1",
                modelID: "claude-sonnet",
                providerID: "anthropic",
              },
            },
          },
        })

        await hooks.event({
          event: {
            type: "message.updated",
            properties: {
              info: {
                id: "msg-unknown-error",
                sessionID: "ses-1",
                role: "assistant",
                time: { created: 2000, completed: 2200 },
                error: {
                  name: "UnknownError",
                  data: { message: "sanitized fixture" },
                },
                parentID: "user-2",
                modelID: "claude-sonnet",
                providerID: "anthropic",
              },
            },
          },
        })

        await hooks.event({
          event: {
            type: "message.updated",
            properties: {
              info: {
                id: "msg-token-edge",
                sessionID: "ses-1",
                role: "assistant",
                time: { created: 3000, completed: 3200 },
                tokens: {
                  input: -1,
                  output: 2,
                  reasoning: -3,
                  cache: { read: -4, write: 5 },
                },
                parentID: "user-3",
                modelID: "claude-sonnet",
                providerID: " Anthropic ",
              },
            },
          },
        })

        await hooks.event({
          event: {
            type: "message.updated",
            properties: {
              info: {
                id: "msg-unnamed-error",
                sessionID: "ses-1",
                role: "assistant",
                time: { created: 4000, completed: 4100 },
                error: {
                  data: { message: "sanitized fixture" },
                },
                parentID: "user-4",
                modelID: "claude-sonnet",
                providerID: "anthropic",
              },
            },
          },
        })

        const recordFor = (payload) => payload.resourceLogs[0].scopeLogs[0].logRecords[0]
        const attrsFor = (payload) =>
          Object.fromEntries(
            recordFor(payload).attributes.map(
              (attr) => [attr.key, Object.values(attr.value)[0]],
            ),
          )

        console.log(JSON.stringify({
          records: payloads.map(recordFor),
          attrs: payloads.map(attrsFor),
        }))
        """
    )

    result = subprocess.run(
        ["node", "--input-type=module", "-e", harness],
        cwd=plugin_dir,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    output = json.loads(result.stdout)
    records = output["records"]
    payloads = output["attrs"]
    assert records[0]["severityNumber"] == 17
    assert payloads[0]["event.name"] == "opencode.message_completed"
    assert payloads[0]["http.response.status_code"] == 429
    assert payloads[0]["status_code"] == 429
    assert payloads[0]["error.type"] == "APIError"
    assert "input_token_count" not in payloads[0]
    assert "output_token_count" not in payloads[0]

    assert records[1]["severityNumber"] == 17
    assert payloads[1]["event.name"] == "opencode.message_completed"
    assert payloads[1]["http.response.status_code"] == 500
    assert payloads[1]["status_code"] == 500
    assert payloads[1]["error.type"] == "UnknownError"

    assert records[2]["severityNumber"] == 9
    assert payloads[2]["provider"] == "anthropic"
    assert payloads[2]["output_token_count"] == 2
    assert payloads[2]["cache_creation_token_count"] == 5
    assert payloads[2]["total_token_count"] == 2
    assert "input_token_count" not in payloads[2]
    assert "reasoning_token_count" not in payloads[2]
    assert "cached_token_count" not in payloads[2]

    assert records[3]["severityNumber"] == 17
    assert payloads[3]["http.response.status_code"] == 500
    assert "error.type" not in payloads[3]


@pytest.mark.slow
def test_opencode_plugin_otlp_emit_uses_abort_signal(tmp_path):
    if not shutil.which("npm") or not shutil.which("node"):
        pytest.skip("node and npm are required for the OpenCode plugin runtime test")

    plugin_dir = _copy_clean_plugin_workspace(tmp_path)
    install = subprocess.run(
        ["npm", "install", "--no-package-lock"],
        cwd=plugin_dir,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert install.returncode == 0, install.stderr
    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=plugin_dir,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert build.returncode == 0, build.stderr

    harness = textwrap.dedent(
        """
        const { emitOtlp } = await import("./dist/shared/src/otlp.js")

        globalThis.fetch = async (_url, options) => {
          return new Promise((resolve, reject) => {
            options.signal?.addEventListener("abort", () => {
              reject(new DOMException("timed out", "AbortError"))
            })
            setTimeout(() => resolve({ ok: true, status: 200 }), 20)
          })
        }

        const emitted = await emitOtlp({}, "http://collector.example/v1/logs", 1)
        console.log(JSON.stringify({ emitted }))
        """
    )

    result = subprocess.run(
        ["node", "--input-type=module", "-e", harness],
        cwd=plugin_dir,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"emitted": False}
