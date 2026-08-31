import json
import logging
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from test_harness.base import BaseTestComponent, ComponentStatus

TEST_TYPE_MAPPING = {
    "normal": "NORMAL CASE (80% OF SUITE)",
    "edge_under": "EDGE CASE - UNDER NORMAL SITUATIONS (10% OF SUITE)",
    "edge_over": "EDGE CASE - OVER NORMAL SITUATIONS (10% OF SUITE)",
    "reception": "WEBHOOK RECEPTION & DELIVERY TEST",
    "live_template": "LIVE WEBHOOK TEMPLATE ADAPTER TEST",
    "formatting": "PAYLOAD FORMATTING & SCHEMA SPECIFICATION TEST",
    "ai_pluggability": "AI COMPONENT PLUGGABILITY (STUB/MOCK/VIRTUALIZATION)",
}

class TestExecutionLogger(BaseTestComponent):
    """
    Component that writes comprehensive test logs and structured JSON execution reports
    to the tests/test_logs folder, generating a unique log and report file for each run.
    Clearly displays the test type in all logs.
    """
    __test__ = False

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        name: str = "test_execution_logger"
    ):
        super().__init__(name=name)
        root = Path(__file__).resolve().parent.parent.parent
        self.log_dir = log_dir or (root / "tests" / "test_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = []
        self.run_id: str = ""
        self.log_file: Optional[Path] = None
        self.report_file: Optional[Path] = None
        self.start_new_run()
        self.status = ComponentStatus.ACTIVE

    def start_new_run(self, run_id: Optional[str] = None, prefix: str = "webhook_watcher") -> str:
        """
        Initializes a brand-new unique run. Generates a unique log file
        and report file named with the prefix, timestamp, and unique run ID.
        """
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:6]
        self.run_id = run_id or f"run_{timestamp_str}_{unique_suffix}"
        self.records.clear()

        # Unique file paths for this specific test run
        self.log_file = self.log_dir / f"{prefix}_{self.run_id}.log"
        self.report_file = self.log_dir / f"{prefix}_report_{self.run_id}.json"

        # Initialize the unique log file with header
        sep = "=" * 80
        header = (
            f"{sep}\n"
            f"🔥 HEPHAESTUS TEST HARNESS - {prefix.upper()} EXECUTION LOG\n"
            f"RUN ID     : {self.run_id}\n"
            f"STARTED AT : {now.isoformat()}\n"
            f"LOG FILE   : {self.log_file.name}\n"
            f"REPORT FILE: {self.report_file.name}\n"
            f"{sep}\n\n"
        )
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(header)

        return self.run_id


    def log_test_case(
        self,
        case_id: str,
        category: str,
        description: str,
        raw_comment: str,
        detected_tag: Optional[str],
        stripped_comment: str,
        passed: bool,
        duration_ms: float,
        error_msg: Optional[str] = None,
        test_type: Optional[str] = None,
        preparations: Optional[str] = None
    ):
        """
        Logs an individual test case run to memory and appends a structured entry
        to the unique log file with the test type and preparations prominently displayed.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        resolved_test_type = test_type or TEST_TYPE_MAPPING.get(category, category.upper())

        record = {
            "timestamp": now_str,
            "run_id": self.run_id,
            "case_id": case_id,
            "test_type": resolved_test_type,
            "category": category,
            "description": description,
            "raw_comment_snippet": raw_comment[:120],
            "detected_tag": detected_tag,
            "preparations": preparations,
            "stripped_comment_snippet": stripped_comment[:120],
            "passed": passed,
            "duration_ms": round(duration_ms, 3),
            "error": error_msg
        }
        self.records.append(record)

        # Build prominent, clearly formatted human-readable entry
        status_banner = "✅ PASSED" if passed else "❌ FAILED"
        tag_stripped_info = "Yes (<|prompt...> tag removed)" if detected_tag else "N/A (No trigger tag)"
        prep_info = repr(preparations[:80]) if preparations else "None"

        log_entry = (
            f"--------------------------------------------------------------------------------\n"
            f"[{now_str}] {status_banner} | Case: {case_id}\n"
            f"  TEST TYPE   : {resolved_test_type}\n"
            f"  DESCRIPTION : {description}\n"
            f"  RAW COMMENT : {repr(raw_comment[:100])}\n"
            f"  DETECTED TAG: {detected_tag} (is_ai_trigger={detected_tag is not None})\n"
            f"  PREPARATIONS: {prep_info}\n"
            f"  IN-MEMORY   : {repr(stripped_comment[:100])}\n"
            f"  TAG STRIPPED: {tag_stripped_info}\n"
            f"  DURATION    : {record['duration_ms']} ms\n"
        )
        if error_msg:
            log_entry += f"  ERROR       : {error_msg}\n"
        log_entry += f"--------------------------------------------------------------------------------\n\n"

        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)

    def write_summary_report(self) -> Dict[str, Any]:
        """
        Generates and writes a full structured JSON summary report for this unique run,
        and maintains a copy as latest for convenience.
        """
        total = len(self.records)
        passed = sum(1 for r in self.records if r["passed"])
        failed = total - passed

        by_cat: Dict[str, Any] = {}
        for r in self.records:
            ttype = r["test_type"]
            cat = r["category"]
            key = f"{ttype} [{cat}]"
            if key not in by_cat:
                by_cat[key] = {"category": cat, "test_type": ttype, "total": 0, "passed": 0, "failed": 0}
            by_cat[key]["total"] += 1
            if r["passed"]:
                by_cat[key]["passed"] += 1
            else:
                by_cat[key]["failed"] += 1

        summary = {
            "run_id": self.run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "log_file": str(self.log_file.resolve()) if self.log_file else "",
            "report_file": str(self.report_file.resolve()) if self.report_file else "",
            "total_cases_executed": total,
            "passed": passed,
            "failed": failed,
            "success_rate_percent": round((passed / total * 100) if total else 0.0, 2),
            "breakdown_by_test_type": by_cat,
            "case_details": self.records
        }

        if self.report_file:
            with open(self.report_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

        # Also maintain latest pointers for convenience
        latest_report = self.log_dir / "test_run_report_latest.json"
        latest_log = self.log_dir / "webhook_watcher_latest.log"
        try:
            if self.report_file and self.report_file.exists():
                shutil.copyfile(self.report_file, latest_report)
            if self.log_file and self.log_file.exists():
                shutil.copyfile(self.log_file, latest_log)
        except Exception:
            pass

        return summary

    def reset(self):
        self.records.clear()
