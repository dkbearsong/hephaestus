# WORKSPACE PREPARATION INSTRUCTIONS

## PLATFORM EXECUTION RULES & CONSTRAINTS
- Target Platform: **GOOGLE_JULES**
- Rules Enforced:
  * Enforce zero uncommitted files
  * Generate/update .jules/ configuration
  * Set build/test hooks into standard repo configs
- Generated Manifest Files: .jules/config.yaml, pytest.ini
- Configured Hooks: {"test": "pytest"}

## USER PREPARATIONS INSTRUCTIONS (preparations.md)
Verify zero uncommitted files rule for Jules.

## AGENT OBJECTIVE
1. Inspect files currently staged in the workspace or in .harness_inbox/.
2. Relocate staged/inbox files to their appropriate repository module paths.
3. Update dependency declarations (e.g. requirements.txt, pyproject.toml, package.json) if indicated by the preparations instructions.
4. NEVER write the actual feature code requested in prompt.md.
5. Detect build, test, and lint commands and report the final PrepSummary status.