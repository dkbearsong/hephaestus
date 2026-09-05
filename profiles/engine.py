"""
Execution Profile Engine
Coordinates baseline setup, profile injections, and environment validations for target platforms.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from profiles.base import (
    TargetPlatform,
    ExecutionProfile,
    ValidationResult,
    apply_baseline_environment
)
from profiles.registry import (
    get_execution_profile,
    inject_profile_configurations,
    validate_profile_environment,
    PROFILES_REGISTRY
)

logger = logging.getLogger("hephaestus.profiles.engine")


class ExecutionProfileEngine:
    """
    Unified Execution Profile Engine.
    Enforces deterministic baseline environments, injects platform-specific configurations,
    and executes platform validation checks.
    """

    def __init__(self):
        logger.info("[ExecutionProfileEngine] Initialized profile engine for 6 target platforms.")

    def get_profile(self, platform: Union[TargetPlatform, str]) -> ExecutionProfile:
        """Retrieves the execution profile for the target platform."""
        return get_execution_profile(platform)

    def list_supported_platforms(self) -> List[str]:
        """Returns the list of all registered platform keys."""
        return [p.value for p in TargetPlatform]

    def apply_baseline(
        self,
        working_dir: Path,
        prompt_content: str = "",
        task_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Enforces baseline environment (POSIX tools, git config, safe.directory, .harness/ anchors)."""
        logger.info(f"[ExecutionProfileEngine] Applying baseline environment in {working_dir}")
        return apply_baseline_environment(
            working_dir=working_dir,
            prompt_content=prompt_content,
            task_context=task_context
        )

    def inject_profile(
        self,
        platform: Union[TargetPlatform, str],
        working_dir: Path,
        context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Injects platform-specific configuration files into the workspace."""
        ctx = context.copy() if context else {}
        logger.info(f"[ExecutionProfileEngine] Injecting profile for {platform} in {working_dir}")
        return inject_profile_configurations(platform=platform, working_dir=working_dir, context=ctx)

    def validate_environment(
        self,
        platform: Union[TargetPlatform, str],
        working_dir: Path,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Runs deterministic validation checks against the workspace for the platform."""
        logger.info(f"[ExecutionProfileEngine] Validating environment for {platform} in {working_dir}")
        return validate_profile_environment(platform=platform, working_dir=working_dir, context=context)

    def prepare_workspace(
        self,
        platform: Union[TargetPlatform, str],
        working_dir: Path,
        ticket_key: str,
        prompt_content: str = "",
        preparations_content: str = "",
        staging_dir: Optional[Path] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        End-to-end workspace preparation:
        1. Applies baseline environment.
        2. Injects platform configurations.
        3. Runs platform validation.
        4. Returns consolidated execution profile report.
        """
        normalized_platform = TargetPlatform.normalize(platform)
        working_path = Path(working_dir).resolve()

        # Build merged context
        ctx: Dict[str, Any] = {
            "ticket_key": ticket_key,
            "instructions": prompt_content,
            "preparations": preparations_content,
            "staging_dir": str(staging_dir.resolve()) if staging_dir else None
        }
        if context:
            ctx.update(context)

        # 1. Baseline
        baseline_res = self.apply_baseline(
            working_dir=working_path,
            prompt_content=prompt_content,
            task_context=f"# Context for {ticket_key}\nPlatform: {normalized_platform.value}\n"
        )

        # 2. Profile Injection
        injected_files = self.inject_profile(
            platform=normalized_platform,
            working_dir=working_path,
            context=ctx
        )

        # 3. Profile Validation
        val_result = self.validate_environment(
            platform=normalized_platform,
            working_dir=working_path,
            context=ctx
        )

        profile = self.get_profile(normalized_platform)

        return {
            "platform": normalized_platform.value,
            "ticket_key": ticket_key,
            "working_directory": str(working_path),
            "baseline": baseline_res,
            "injected_files": injected_files,
            "validation": val_result.model_dump(),
            "profile_rules": profile.rules,
            "valid": val_result.valid
        }


execution_profile_engine = ExecutionProfileEngine()
