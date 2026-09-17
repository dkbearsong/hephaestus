import os
import json
import logging
from backend.db.service import append_event
from pathlib import Path
from typing import Dict, Any, List, Optional, TypedDict, Union
from langgraph.graph import StateGraph, START, END
from backend.config import preferences, ROOT_DIR
from backend.harness.mcp_loader import mcp_loader
from backend.preprocessor.llm_client import llm_client, LLMResponse

logger = logging.getLogger("hephaestus.preparations_graph")

class PreparationsState(TypedDict):
    task_id: str
    preparations_prompt: str
    messages: List[Dict[str, Any]]
    provider: str
    model: str
    available_tools: List[Dict[str, Any]]
    pending_tool_calls: List[Dict[str, Any]]
    step_logs: List[Dict[str, Any]]
    iteration: int
    max_iterations: int
    completed: bool
    end_token_received: bool
    end_reason: str
    final_response: Optional[str]
    staging_dir: Optional[str]
    run_id: Optional[str]
    error: Optional[str]

class PreparationsGraphRunner:
    """
    LangGraph Workflow Engine for the Preparations Stage.
    Runs immediately after prompt.md and preparations.md are staged,
    and before Docker container creation.
    """

    def __init__(self):
        self.graph = self._compile_graph()

    def _compile_graph(self):
        workflow = StateGraph(PreparationsState)

        def llm_node(state: PreparationsState) -> PreparationsState:
            state["iteration"] = state.get("iteration", 0) + 1
            provider = state.get("provider") or preferences.preparations_step.provider
            model = state.get("model") or preferences.preparations_step.model

            logger.info("[LangGraph: Preparations] LLM Node invoked (iteration %d, provider: %s, model: %s)", 
                        state["iteration"], provider, model)

            try:
                resp: LLMResponse = llm_client.call_chat(
                    messages=state["messages"],
                    tools=state.get("available_tools", []),
                    provider=provider,
                    model=model,
                    temperature=getattr(preferences.preparations_step, "temperature", 0.2)
                )

                tool_calls_data = [tc.model_dump() for tc in resp.tool_calls]
                step_log = {
                    "step": "llm_node",
                    "iteration": state["iteration"],
                    "provider": provider,
                    "model": model,
                    "content": resp.content,
                    "tool_calls": tool_calls_data,
                    "finish_reason": resp.finish_reason,
                    "is_end_of_token": resp.is_end_of_token
                }
                state["step_logs"].append(step_log)

                if resp.content:
                    state["messages"].append({
                        "role": "assistant",
                        "content": resp.content
                    })

                if resp.tool_calls:
                    state["pending_tool_calls"] = tool_calls_data
                    state["messages"].append({
                        "role": "assistant",
                        "content": resp.content or "",
                        "tool_calls": tool_calls_data
                    })
                    state["end_token_received"] = False
                else:
                    state["pending_tool_calls"] = []
                    if resp.is_end_of_token:
                        state["end_token_received"] = True
                        state["final_response"] = resp.content
                        state["end_reason"] = resp.finish_reason
                        logger.info("[LangGraph: Preparations] Received END OF TOKEN from %s. Final response ready.", provider)

            except Exception as e:
                logger.error("[LangGraph: Preparations] Error in LLM Node: %s", e)
                state["error"] = str(e)
                state["step_logs"].append({
                    "step": "llm_node_error",
                    "iteration": state["iteration"],
                    "error": str(e)
                })

            return state

        def mcp_tool_node(state: PreparationsState) -> PreparationsState:
            logger.info("[LangGraph: Preparations] MCP Tool Node invoked with %d pending tool call(s)", len(state.get("pending_tool_calls", [])))
            executed = []

            for tc in state.get("pending_tool_calls", []):
                func_name = tc.get("name")
                args = tc.get("args", {})
                call_id = tc.get("id", "call_unknown")

                logger.info("[LangGraph: MCP Execution] Executing tool '%s' with args %s", func_name, args)
                try:
                    res = mcp_loader.execute_tool(func_name, args)
                    res_str = json.dumps(res) if isinstance(res, (dict, list)) else str(res)
                except Exception as ex:
                    logger.error("[LangGraph: MCP Execution] Error executing '%s': %s", func_name, ex)
                    res = {"error": str(ex)}
                    res_str = json.dumps(res)


                # Append telemetry event safely
                try:
                    import threading
                    import asyncio
                    def _track_event():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(append_event(
                                run_id=state.get("run_id"),
                                event_type="MCP_TOOL_CALL",
                                payload={
                                    "func_name": func_name,
                                    "args": args,
                                    "result": res_str
                                },
                                level="INFO"
                            ))
                        except Exception:
                            pass
                        finally:
                            loop.close()
                    threading.Thread(target=_track_event, daemon=True).start()
                except Exception:
                    pass
                executed.append({
                    "id": call_id,
                    "name": func_name,
                    "args": args,
                    "result": res
                })

                # Append tool result to messages history
                state["messages"].append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": func_name,
                    "content": res_str
                })

            state["step_logs"].append({
                "step": "mcp_tool_node",
                "iteration": state["iteration"],
                "executed_tools": executed
            })
            state["pending_tool_calls"] = []
            return state

        def finish_node(state: PreparationsState) -> PreparationsState:
            logger.info("[LangGraph: Preparations] Finish Node reached. Emitting End-of-Token confirmation.")
            state["completed"] = True
            provider = (state.get("provider") or "").lower()
            model = state.get("model") or ""

            # Explicit memory cleanup: Drop model from memory for local providers (LM Studio & Ollama)
            unloaded_info = None
            if provider in ("lm_studio", "lmstudio", "ollama"):
                logger.info("[LangGraph: Memory Management] End of token received. Dropping model '%s' from %s memory...", model, provider)
                unloaded_info = llm_client.unload_model_from_memory(provider=provider, model=model)
                state["step_logs"].append({
                    "step": "unload_model_from_memory",
                    "provider": provider,
                    "model": model,
                    "unloaded": True,
                    "details": unloaded_info
                })

            state["step_logs"].append({
                "step": "finish_node",
                "completed": True,
                "end_token_received": state.get("end_token_received", True),
                "end_reason": state.get("end_reason", "completed"),
                "final_response": state.get("final_response"),
                "model_unloaded": bool(unloaded_info)
            })

            # Save execution trace to staging directory if provided
            staging = state.get("staging_dir")
            if staging:
                try:
                    st_path = Path(staging)
                    st_path.mkdir(parents=True, exist_ok=True)
                    exec_file = st_path / "preparations_execution.json"
                    with open(exec_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "task_id": state.get("task_id"),
                            "provider": state.get("provider"),
                            "model": state.get("model"),
                            "completed": state.get("completed"),
                            "end_token_received": state.get("end_token_received"),
                            "final_response": state.get("final_response"),
                            "step_logs": state.get("step_logs")
                        }, f, indent=2)
                    logger.info("Saved preparations execution trace to %s", exec_file)
                except Exception as e:
                    logger.warning("Could not write preparations_execution.json: %s", e)

            return state

        def router(state: PreparationsState) -> str:
            if state.get("error"):
                return "finish"
            if state.get("pending_tool_calls"):
                return "tools"
            if state.get("end_token_received") or state["iteration"] >= state.get("max_iterations", 10):
                return "finish"
            return "finish"

        workflow.add_node("llm", llm_node)
        workflow.add_node("tools", mcp_tool_node)
        workflow.add_node("finish", finish_node)

        workflow.add_edge(START, "llm")
        workflow.add_conditional_edges("llm", router, {
            "tools": "tools",
            "finish": "finish"
        })
        workflow.add_edge("tools", "llm")
        workflow.add_edge("finish", END)

        return workflow.compile()

    def run_preparations(
        self,
        task_id: str,
        preparations_prompt: str,
        staging_dir: Optional[str] = None,
        run_id: Optional[Union[str, Any]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_iterations: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Runs the preparations LangGraph pipeline.
        Returns dictionary containing completed status, LLM responses, tool outputs, and trace.
        """
        prov = provider or preferences.preparations_step.provider or "gemini"
        mod = model or preferences.preparations_step.model
        tool_schemas = tools if tools is not None else mcp_loader.get_tool_schemas(enabled_only=True)
        max_iter = max_iterations or getattr(preferences.preparations_step, "max_iterations", 10)

        system_message = (
            "You are the Hephaestus Preparations Agent. "
            "Your task is to analyze setup and preparation instructions before Docker container initialization. "
            "You have access to MCP tools to inspect environment details, query database schema, check date/time, or verify tests. "
            "When all necessary preparation tasks and tool queries are done, provide a final confirmation summary to emit the end-of-token."
        )

        initial_state: PreparationsState = {
            "task_id": task_id,
            "preparations_prompt": preparations_prompt,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": preparations_prompt}
            ],
            "provider": prov,
            "model": mod,
            "available_tools": tool_schemas,
            "pending_tool_calls": [],
            "step_logs": [],
            "iteration": 0,
            "max_iterations": max_iter,
            "completed": False,
            "end_token_received": False,
            "end_reason": "",
            "final_response": None,
            "staging_dir": staging_dir,
            "run_id": str(run_id) if run_id else None,
            "error": None
        }

        logger.info("[LangGraph] Starting preparations graph execution for task %s (provider: %s, model: %s, tools: %d)",
                    task_id, prov, mod, len(tool_schemas))

        result_state = self.graph.invoke(initial_state)

        return {
            "task_id": task_id,
            "provider": result_state["provider"],
            "model": result_state["model"],
            "completed": result_state["completed"],
            "end_token_received": result_state["end_token_received"],
            "end_reason": result_state["end_reason"],
            "final_response": result_state["final_response"],
            "step_logs": result_state["step_logs"],
            "error": result_state.get("error")
        }

preparations_runner = PreparationsGraphRunner()
