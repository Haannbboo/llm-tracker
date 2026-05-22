from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "opencode"


def test_opencode_plugin_emits_status_for_failed_assistant_messages():
    if not shutil.which("npm") or not shutil.which("node"):
        pytest.skip("node and npm are required for the OpenCode plugin runtime test")
    if not (PLUGIN_DIR / "node_modules" / ".bin" / "tsc").exists():
        pytest.skip("OpenCode plugin npm dependencies are not installed")

    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=PLUGIN_DIR,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert build.returncode == 0, build.stderr

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

        const attrsFor = (payload) =>
          Object.fromEntries(
            payload.resourceLogs[0].scopeLogs[0].logRecords[0].attributes.map(
              (attr) => [attr.key, Object.values(attr.value)[0]],
            ),
          )

        console.log(JSON.stringify(payloads.map(attrsFor)))
        """
    )

    result = subprocess.run(
        ["node", "--input-type=module", "-e", harness],
        cwd=PLUGIN_DIR,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    payloads = json.loads(result.stdout)
    assert payloads[0]["event.name"] == "opencode.message_completed"
    assert payloads[0]["http.response.status_code"] == 429
    assert payloads[0]["status_code"] == 429
    assert payloads[0]["error.type"] == "APIError"
    assert "input_token_count" not in payloads[0]
    assert "output_token_count" not in payloads[0]

    assert payloads[1]["event.name"] == "opencode.message_completed"
    assert payloads[1]["http.response.status_code"] == 500
    assert payloads[1]["status_code"] == 500
    assert payloads[1]["error.type"] == "UnknownError"
