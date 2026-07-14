"""Windows-safe replacement for scripts.run_eval.run_single_query.

The original implementation polls the subprocess pipe with select.select(),
which only works on sockets on Windows (WinError 10038). This version reads
the pipe with a blocking line loop and relies on a watchdog timer to kill the
subprocess when the timeout expires (the kill closes the pipe, ending the
loop). Detection logic is otherwise identical to the original.
"""

import json
import os
import subprocess
import threading
import uuid
from pathlib import Path


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    project_root: str,
    model: str | None = None,
) -> bool:
    """Run a single query and return whether the skill was triggered."""
    unique_id = uuid.uuid4().hex[:8]
    clean_name = f"{skill_name}-skill-{unique_id}"
    project_commands_dir = Path(project_root) / ".claude" / "commands"
    command_file = project_commands_dir / f"{clean_name}.md"

    try:
        project_commands_dir.mkdir(parents=True, exist_ok=True)
        # Use YAML block scalar to avoid breaking on quotes in description
        indented_desc = "\n  ".join(skill_description.split("\n"))
        command_content = (
            f"---\n"
            f"description: |\n"
            f"  {indented_desc}\n"
            f"---\n\n"
            f"# {skill_name}\n\n"
            f"This skill handles: {skill_description}\n"
        )
        command_file.write_text(command_content, encoding="utf-8")

        cmd = [
            "claude",
            "-p", query,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if model:
            cmd.extend(["--model", model])

        # Remove CLAUDECODE env var to allow nesting claude -p inside a
        # Claude Code session.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=project_root,
            env=env,
        )

        triggered = False
        # Track state for stream event detection
        pending_tool_name = None
        accumulated_json = ""

        timed_out = []

        def _on_timeout():
            timed_out.append(True)
            process.kill()

        watchdog = threading.Timer(timeout, _on_timeout)
        watchdog.start()
        try:
            for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Early detection via stream events
                if event.get("type") == "stream_event":
                    se = event.get("event", {})
                    se_type = se.get("type", "")

                    if se_type == "content_block_start":
                        cb = se.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            tool_name = cb.get("name", "")
                            if tool_name in ("Skill", "Read"):
                                pending_tool_name = tool_name
                                accumulated_json = ""
                            else:
                                return False

                    elif se_type == "content_block_delta" and pending_tool_name:
                        delta = se.get("delta", {})
                        if delta.get("type") == "input_json_delta":
                            accumulated_json += delta.get("partial_json", "")
                            if clean_name in accumulated_json:
                                return True

                    elif se_type in ("content_block_stop", "message_stop"):
                        if pending_tool_name:
                            return clean_name in accumulated_json
                        if se_type == "message_stop":
                            return False

                # Fallback: full assistant message
                elif event.get("type") == "assistant":
                    message = event.get("message", {})
                    for content_item in message.get("content", []):
                        if content_item.get("type") != "tool_use":
                            continue
                        tool_name = content_item.get("name", "")
                        tool_input = content_item.get("input", {})
                        if tool_name == "Skill" and clean_name in tool_input.get("skill", ""):
                            triggered = True
                        elif tool_name == "Read" and clean_name in tool_input.get("file_path", ""):
                            triggered = True
                        return triggered

                elif event.get("type") == "result":
                    # An API error (rate limit, outage) must not be recorded
                    # as "did not trigger" — raise so the caller can retry.
                    subtype = event.get("subtype", "")
                    if subtype != "success":
                        raise RuntimeError(f"claude -p result subtype={subtype}")
                    return triggered
        finally:
            watchdog.cancel()
            # Clean up process on any exit path (return, exception, timeout)
            if process.poll() is None:
                process.kill()
            process.wait()

        # Stream ended without a result event or early detection. A timeout
        # keeps the original semantics (no trigger observed); anything else
        # exiting non-zero is an error, not a verdict.
        if not timed_out and process.returncode != 0:
            raise RuntimeError(
                f"claude -p exited {process.returncode} without a result event"
            )
        return triggered
    finally:
        if command_file.exists():
            command_file.unlink()
