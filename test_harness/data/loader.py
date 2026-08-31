import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from test_harness.base import BaseTestComponent, ComponentStatus
from test_harness.data.generator import TestCaseGenerator

class TestDataLoader(BaseTestComponent):
    """
    Test data provider component. Loads test cases from disk or dynamically generates them.
    Provides filtered access by category: normal, edge_under, edge_over.
    """
    __test__ = False

    def __init__(self, data_path: Optional[Path] = None, name: str = "test_data_loader"):
        super().__init__(name=name)
        root = Path(__file__).resolve().parent.parent.parent
        self.primary_path = data_path or (root / "test" / "test_data" / "cases.json")
        self.fallback_path = root / "tests" / "test_data" / "cases.json"
        self._cases: List[Dict[str, Any]] = []
        self.status = ComponentStatus.ACTIVE

    def load_cases(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        """Loads cases from disk, generating them if not already present."""
        if self._cases and not force_reload:
            return self._cases

        target = self.primary_path
        if not target.exists() and self.fallback_path.exists():
            target = self.fallback_path

        if not target.exists():
            # Generate and persist automatically
            self._cases = TestCaseGenerator.save_cases_to_file(self.primary_path)
            # Also mirror to fallback path
            TestCaseGenerator.save_cases_to_file(self.fallback_path)
        else:
            with open(target, "r", encoding="utf-8") as f:
                self._cases = json.load(f)

        return self._cases

    def get_all_cases(self) -> List[Dict[str, Any]]:
        return self.load_cases()

    def get_normal_cases(self) -> List[Dict[str, Any]]:
        return [c for c in self.load_cases() if c.get("category") == "normal"]

    def get_edge_under_cases(self) -> List[Dict[str, Any]]:
        return [c for c in self.load_cases() if c.get("category") == "edge_under"]

    def get_edge_over_cases(self) -> List[Dict[str, Any]]:
        return [c for c in self.load_cases() if c.get("category") == "edge_over"]

    def get_case_by_id(self, case_id: str) -> Optional[Dict[str, Any]]:
        for c in self.load_cases():
            if c.get("id") == case_id:
                return c
        return None

    def reset(self):
        self._cases.clear()
