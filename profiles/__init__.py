"""
Execution Profiles Module
Provides deterministic runtime profiles, baseline environments, and validation checks.
"""

from profiles.base import (
    TargetPlatform,
    ContainerSpec,
    PlatformConfig,
    ExecutionProfile,
    ValidationResult,
    BaselineConfig,
    apply_baseline_environment,
)
from profiles.registry import (
    get_execution_profile,
    inject_profile_configurations,
    validate_profile_environment,
    PROFILES_REGISTRY,
    strip_json_comments,
    generate_repo_tree
)
from profiles.engine import (
    ExecutionProfileEngine,
    execution_profile_engine
)

__all__ = [
    "TargetPlatform",
    "ContainerSpec",
    "PlatformConfig",
    "ExecutionProfile",
    "ValidationResult",
    "BaselineConfig",
    "apply_baseline_environment",
    "get_execution_profile",
    "inject_profile_configurations",
    "validate_profile_environment",
    "PROFILES_REGISTRY",
    "strip_json_comments",
    "generate_repo_tree",
    "ExecutionProfileEngine",
    "execution_profile_engine",
]
