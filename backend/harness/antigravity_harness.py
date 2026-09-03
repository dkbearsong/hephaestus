"""
DEPRECATED: Antigravity Headless Harness (Archived in old_code/antigravity_harness.py)
Superceded by Google Jules and the Coding Agent Orchestrator (backend/coding_agents/).
This module provides backward compatibility mapping to GoogleJulesOrchestrator.
"""

import logging
from backend.coding_agents.google_jules import GoogleJulesOrchestrator

logger = logging.getLogger("hephaestus.antigravity_harness.deprecated")

class AntigravityHeadlessHarness(GoogleJulesOrchestrator):
    """
    Deprecated alias for GoogleJulesOrchestrator.
    """
    def __init__(self):
        super().__init__()
        logger.info("[AntigravityHeadlessHarness] Legacy Antigravity harness called; delegated to Google Jules.")
