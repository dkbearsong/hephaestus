# 📦 Hephaestus Legacy Code Archive

This directory contains legacy modules that have been deprecated and disabled from the active Hephaestus execution pipeline:

## Archived Components:

1. `container_service.py`:
   - **Original Purpose**: Direct Docker container creation, branch environment setup, checkpoint commit images (`hephaestus-checkpoint:...`), and container cleanup on branch merge.
   - **Reason for Deprecation**: Managing raw Docker container state and ad-hoc container injection is impractical when specialized agent platforms handle their own containerized execution environments.

2. `antigravity_harness.py`:
   - **Original Purpose**: Antigravity headless daemon plugged directly into container sockets to inject code changes.
   - **Reason for Deprecation**: Superseded by the new multi-agent **Coding Agent Orchestrator** supporting dedicated coding agent platforms.

## Current Architecture:
All container initiation and task execution is now orchestrated by `backend/coding_agents/` across:
- **Google Jules** (Google Cloud Workspace containers)
- **Grok Build** (xAI containerized build environments)
- **OpenAI Codex (in cloud)** (OpenAI cloud sandboxes)
- **Docker Sandbox with Claude Code or OpenAI Codex** (Docker containerized Claude Code/Codex CLI)
- **Devin AI** (Cognition Devin AI session sandbox containers)
- **Openhands with Agent Canvas** (OpenHands container runtime with visual Agent Canvas)
