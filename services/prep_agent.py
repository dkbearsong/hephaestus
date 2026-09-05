import json
import os
import shutil
import re
import logging
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple

from services.models import PrepSummary
from services.mcp_manager import MCPManager, extract_tool_result_text

logger = logging.getLogger("hephaestus.services.prep_agent")


def convert_mcp_tool_to_schema(tool: Any, provider: str = "openai") -> Dict[str, Any]:
    """
    Converts an MCP tool definition into the schema expected by the given LLM provider.
    Supports OpenAI, Anthropic, Gemini, and standard JSON schema.
    """
    name = getattr(tool, "name", "")
    description = getattr(tool, "description", "") or ""
    schema = getattr(tool, "inputSchema", {})

    if hasattr(schema, "model_dump"):
        schema = schema.model_dump()
    elif not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}

    p = provider.lower()
    if p in ("claude", "anthropic"):
        return {
            "name": name,
            "description": description,
            "input_schema": schema
        }
    else:
        # Standard function tool schema (OpenAI, Gemini, Grok, Groq, OpenRouter, etc.)
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema
            }
        }


class PreparationAgent:
    """
    Autonomous Workspace Preparation Agent Runtime.
    Loads built-in and user-configured MCP tools, executes a ReAct agentic loop,
    converts tool definitions to provider schemas, enforces non-destructive preparation,
    and produces prep_summary.json.
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def build_file_tree(self, root_dir: Path, max_depth: int = 4, max_entries: int = 150) -> str:
        """
        Generates a readable directory tree representation, excluding build artifacts, dependencies, and sandboxes.
        """
        lines = []
        ignore_dirs = {
            ".git", "__pycache__", ".venv", "venv", "node_modules", "sandboxes",
            ".pytest_cache", "build", "dist", ".next", ".turbo", "coverage",
            ".idea", ".vscode", ".ruff_cache", ".mypy_cache"
        }

        def _traverse(current_dir: Path, prefix: str = "", depth: int = 0):
            if depth > max_depth or len(lines) >= max_entries:
                return
            try:
                entries = sorted(list(current_dir.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
            except Exception:
                return

            for idx, entry in enumerate(entries):
                if len(lines) >= max_entries:
                    lines.append(f"{prefix}... [truncated]")
                    return
                if entry.name in ignore_dirs:
                    continue
                is_last = (idx == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
                if entry.is_dir():
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    _traverse(entry, next_prefix, depth + 1)

        lines.append(f"{root_dir.name}/")
        _traverse(root_dir)
        return "\n".join(lines)

    def detect_commands(self, working_dir: Path) -> Dict[str, Optional[str]]:
        """
        Infers build, test, and lint commands from repository layout and configuration files.
        """
        detected: Dict[str, Optional[str]] = {
            "build": None,
            "test": None,
            "lint": None
        }

        # 1. Python ecosystem
        if (working_dir / "pytest.ini").exists() or list(working_dir.glob("test*.py")) or list(working_dir.glob("tests")):
            detected["test"] = "pytest"
        if (working_dir / "pyproject.toml").exists() or (working_dir / "ruff.toml").exists() or (working_dir / ".flake8").exists():
            detected["lint"] = "ruff check ." if (working_dir / "ruff.toml").exists() else "flake8"

        # 2. Node/JS ecosystem
        pkg_json = working_dir / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                scripts = data.get("scripts", {})
                if "build" in scripts:
                    detected["build"] = "npm run build"
                if "test" in scripts:
                    detected["test"] = "npm test"
                if "lint" in scripts:
                    detected["lint"] = "npm run lint"
            except Exception:
                pass

        # 3. Rust / Cargo
        if (working_dir / "Cargo.toml").exists():
            detected["build"] = "cargo build"
            detected["test"] = "cargo test"
            detected["lint"] = "cargo clippy"

        # 4. Go
        if (working_dir / "go.mod").exists():
            detected["build"] = "go build"
            detected["test"] = "go test ./..."
            detected["lint"] = "golangci-lint run"

        return detected

    def _apply_deterministic_preparations(
        self,
        working_dir: Path,
        merged_instructions: str,
        files_modified: List[str]
    ) -> List[str]:
        """
        Applies baseline file movements from .harness_inbox or staged locations,
        and applies dependency additions based on preparations instructions.
        """
        inbox_dir = working_dir / ".harness_inbox"

        # 1. Relocate files from .harness_inbox if present
        if inbox_dir.exists() and inbox_dir.is_dir():
            for item in list(inbox_dir.rglob("*")):
                if item.is_file():
                    rel_to_inbox = item.relative_to(inbox_dir)
                    dest_match = re.search(
                        rf"(?:move|copy|place)\s+[`'\"]?{re.escape(item.name)}[`'\"]?\s+(?:to|into|under)\s+[`'\"]?([a-zA-Z0-9_\-\./]+)[`'\"]?",
                        merged_instructions,
                        re.IGNORECASE
                    )
                    if dest_match:
                        dest_folder = dest_match.group(1).strip()
                        dest_target = working_dir / dest_folder
                        if dest_folder.endswith(item.name):
                            dest_file = dest_target
                        else:
                            dest_file = dest_target / item.name
                    else:
                        dest_file = working_dir / rel_to_inbox

                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(dest_file))
                    rel_path = str(dest_file.relative_to(working_dir))
                    if rel_path not in files_modified:
                        files_modified.append(rel_path)
                    logger.info(f"Relocated inbox file {item.name} -> {rel_path}")

            try:
                shutil.rmtree(str(inbox_dir))
            except Exception:
                pass

        # 2. Check for dependencies mentioned in preparations
        dep_matches = re.findall(
            r"(?:add|install|require|dependency:?)\s+[`'\"]?([a-zA-Z0-9_\-\[\]]+(?:>=|==|<=)?[0-9\.]*)[`'\"]?",
            merged_instructions,
            re.IGNORECASE
        )
        if dep_matches:
            req_file = working_dir / "requirements.txt"
            existing_deps = []
            if req_file.exists():
                existing_deps = [l.strip() for l in req_file.read_text(encoding="utf-8").splitlines() if l.strip()]

            added = False
            for dep in dep_matches:
                dep_name = dep.split("=")[0].split(">")[0].split("<")[0].strip()
                if not any(dep_name.lower() in ed.lower() for ed in existing_deps):
                    existing_deps.append(dep)
                    added = True

            if added:
                req_file.write_text("\n".join(existing_deps) + "\n", encoding="utf-8")
                rel_req = str(req_file.relative_to(working_dir))
                if rel_req not in files_modified:
                    files_modified.append(rel_req)
                logger.info(f"Updated dependency declarations in {rel_req}")

        return files_modified

    async def arun(
        self,
        working_dir: Path,
        branch_name: str,
        merged_instructions: str,
        prompt_md_path: Optional[Path] = None,
        block_on_intent: bool = False,
        prefs_path: Optional[Union[str, Path]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> PrepSummary:
        """
        Asynchronous execution loop for the Preparation Agent.
        1. Connects to MCP servers (built-in + external preferences).
        2. Converts MCP tools to provider-compatible schema.
        3. Formulates the non-destructive workspace configuration context.
        4. Runs an iterative ReAct tool-calling loop (max 15 turns).
        5. Concludes execution and persists prep_summary.json.
        """
        working_dir = Path(working_dir).resolve()
        logger.info(f"Preparation Agent arun starting for branch {branch_name} in {working_dir}")

        files_modified: List[str] = []

        # Read prompt.md if present
        prompt_content = ""
        if prompt_md_path and prompt_md_path.exists():
            prompt_content = prompt_md_path.read_text(encoding="utf-8")

        # Initial deterministic baseline preparations
        self._apply_deterministic_preparations(working_dir, merged_instructions, files_modified)

        # Build initial file tree and detect commands
        file_tree = self.build_file_tree(working_dir)
        detected_cmds = self.detect_commands(working_dir)

        # Baseline blocker check
        status: str = "READY"
        blocker_reason: Optional[str] = None
        if "BLOCK_TASK" in merged_instructions or "BLOCKED:" in merged_instructions or block_on_intent:
            status = "BLOCKED"
            blocker_reason = "Preparation detected unresolved blocker in preparations instructions"

        # Determine target LLM provider
        active_provider = (provider or "gemini").lower()

        # Connect to MCP Manager
        async with MCPManager.from_preferences(prefs_path, working_dir) as mcp:
            # Aggregate available MCP tools
            mcp_tools = await mcp.get_available_tools()
            formatted_tools = [convert_mcp_tool_to_schema(t, provider=active_provider) for t in mcp_tools]

            # Construct conversation context
            tool_names_str = ", ".join(t.name for t in mcp_tools)
            system_prompt = (
                "You are the Hephaestus Autonomous Workspace Preparation Agent.\n"
                "Your responsibility is non-destructive workspace preparation, configuration, and layout setup.\n\n"
                "MANDATORY OPERATIONAL RULES:\n"
                "1. Relocate inbox/staged files into proper modules, configure environment files (.env), "
                "and fulfill user preparation instructions using the available tools.\n"
                "2. NEVER implement feature code requested in downstream prompt.md.\n"
                f"3. Use the provided tools ({tool_names_str}) to inspect, coordinate, and configure the workspace.\n"
                "4. When preparations are complete or blocked, you MUST invoke 'complete_preparation' or emit a structured "
                "JSON matching the PrepSummary schema.\n"
            )

            user_message = (
                f"## WORKSPACE ROOT:\n{working_dir}\n\n"
                f"## BRANCH:\n{branch_name}\n\n"
                f"## PREPARATION INSTRUCTIONS & PROVIDER RULES:\n{merged_instructions}\n\n"
                f"## DOWNSTREAM PROMPT (DO NOT IMPLEMENT THIS CODE):\n{prompt_content}\n\n"
                f"## CURRENT WORKSPACE TREE:\n{file_tree}\n"
            )

            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            # Determine LLM client
            client = self.llm_client
            if client is None:
                try:
                    from backend.preprocessor.llm_client import llm_client as default_llm
                    client = default_llm
                except Exception as e:
                    logger.warning(f"Default LLM client could not be imported: {e}")

            # Run iterative ReAct tool calling loop (max 15 turns)
            max_turns = 15
            turn = 0
            completed_via_tool = False

            if client is not None:
                while turn < max_turns:
                    turn += 1
                    logger.info(f"[ReAct Loop] Turn {turn}/{max_turns}")

                    try:
                        resp = None
                        if hasattr(client, "call_chat"):
                            try:
                                resp = client.call_chat(
                                    messages=messages,
                                    tools=formatted_tools,
                                    provider=active_provider,
                                    model=model,
                                    temperature=0.1
                                )
                            except TypeError:
                                resp = client.call_chat(
                                    messages=messages,
                                    tools=formatted_tools,
                                    provider=active_provider,
                                    temperature=0.1
                                )
                        elif hasattr(client, "chat"):
                            resp = client.chat(messages=messages, tools=formatted_tools)

                        if resp is None:
                            logger.info("[ReAct Loop] Received empty response from LLM client.")
                            break

                        content = getattr(resp, "content", None) or ""
                        tool_calls = getattr(resp, "tool_calls", [])

                        # Append assistant response to messages
                        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
                        if tool_calls:
                            assistant_msg["tool_calls"] = [
                                {
                                    "id": getattr(tc, "id", f"call_{i}"),
                                    "name": getattr(tc, "name", tc.get("name", "") if isinstance(tc, dict) else ""),
                                    "args": getattr(tc, "args", tc.get("args", {}) if isinstance(tc, dict) else {})
                                }
                                for i, tc in enumerate(tool_calls)
                            ]
                        messages.append(assistant_msg)

                        # Process tool calls if emitted
                        if tool_calls:
                            for tc in tool_calls:
                                call_id = getattr(tc, "id", f"call_{os.urandom(3).hex()}")
                                call_name = getattr(tc, "name", tc.get("name", "") if isinstance(tc, dict) else "")
                                call_args = getattr(tc, "args", tc.get("args", {}) if isinstance(tc, dict) else {})

                                # Dispatch to MCP
                                logger.info(f"[ReAct Loop] Executing tool '{call_name}' with args {call_args}")
                                tool_result = await mcp.call_tool(call_name, call_args)
                                tool_text = extract_tool_result_text(tool_result)

                                # Feed tool result back to message history
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "name": call_name,
                                    "content": tool_text
                                })

                                # Check for completion tool invocation
                                if call_name == "complete_preparation":
                                    completed_via_tool = True
                                    if isinstance(call_args, dict):
                                        new_status = call_args.get("status", "").upper()
                                        is_hard_blocked = (
                                            "BLOCK_TASK" in merged_instructions
                                            or "BLOCKED:" in merged_instructions
                                            or block_on_intent
                                        )
                                        if new_status in ("READY", "BLOCKED"):
                                            if not is_hard_blocked:
                                                status = new_status
                                            elif new_status == "BLOCKED":
                                                status = "BLOCKED"
                                        if call_args.get("blocker_reason"):
                                            blocker_reason = call_args["blocker_reason"]
                                        if isinstance(call_args.get("detected_commands"), dict):
                                            detected_cmds.update(call_args["detected_commands"])
                                        if isinstance(call_args.get("files_modified"), list):
                                            for fm in call_args["files_modified"]:
                                                if fm not in files_modified:
                                                    files_modified.append(fm)
                                    break

                            if completed_via_tool:
                                logger.info("[ReAct Loop] Terminating: complete_preparation invoked.")
                                break
                            else:
                                continue

                        # If no tool calls, inspect content for structured JSON summary
                        if content:
                            json_match = re.search(r"\{[\s\S]*\}", content)
                            if json_match:
                                try:
                                    parsed = json.loads(json_match.group(0))
                                    new_status = parsed.get("status", "").upper()
                                    is_hard_blocked = (
                                        "BLOCK_TASK" in merged_instructions
                                        or "BLOCKED:" in merged_instructions
                                        or block_on_intent
                                    )
                                    if new_status in ("READY", "BLOCKED"):
                                        if not is_hard_blocked:
                                            status = new_status
                                        elif new_status == "BLOCKED":
                                            status = "BLOCKED"
                                    if parsed.get("blocker_reason"):
                                        blocker_reason = parsed["blocker_reason"]
                                    if isinstance(parsed.get("detected_commands"), dict):
                                        detected_cmds.update(parsed["detected_commands"])
                                    if isinstance(parsed.get("files_modified"), list):
                                        for fm in parsed["files_modified"]:
                                            if fm not in files_modified:
                                                files_modified.append(fm)
                                    logger.info("[ReAct Loop] Terminating: structured JSON summary received.")
                                    break
                                except Exception:
                                    pass

                        # If assistant finished without tool calls or JSON, stop
                        break

                    except Exception as e:
                        logger.warning(f"[ReAct Loop] Exception in iteration {turn}: {e}")
                        break

            # Collect files modified through MCP Manager
            for fm in mcp.files_modified:
                if fm not in files_modified:
                    files_modified.append(fm)

            # Re-verify detected commands
            refreshed_cmds = self.detect_commands(working_dir)
            for k, v in refreshed_cmds.items():
                if v and not detected_cmds.get(k):
                    detected_cmds[k] = v

        summary = PrepSummary(
            status=status,
            working_directory=str(working_dir.resolve()),
            branch_name=branch_name,
            detected_commands=detected_cmds,
            files_modified=sorted(list(set(files_modified))),
            blocker_reason=blocker_reason
        )

        # Output Contract: Persist prep_summary.json in the workspace root
        summary_file = working_dir / "prep_summary.json"
        try:
            summary_file.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
            logger.info(f"Persisted PrepSummary output contract to {summary_file}")
        except Exception as e:
            logger.error(f"Failed to persist prep_summary.json to {summary_file}: {e}")

        logger.info(
            f"Preparation Agent finished. Status: {summary.status}, "
            f"Files modified: {len(summary.files_modified)}, Commands: {summary.detected_commands}"
        )
        return summary

    def run(
        self,
        working_dir: Path,
        branch_name: str,
        merged_instructions: str,
        prompt_md_path: Optional[Path] = None,
        block_on_intent: bool = False,
        prefs_path: Optional[Union[str, Path]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> PrepSummary:
        """
        Synchronous wrapper around arun(...) ensuring compatibility with existing orchestrators.
        Safely executes in both running and fresh asyncio event loops.
        """
        coro = self.arun(
            working_dir=working_dir,
            branch_name=branch_name,
            merged_instructions=merged_instructions,
            prompt_md_path=prompt_md_path,
            block_on_intent=block_on_intent,
            prefs_path=prefs_path,
            provider=provider,
            model=model
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(coro)).result()
        else:
            return asyncio.run(coro)


prep_agent = PreparationAgent()
