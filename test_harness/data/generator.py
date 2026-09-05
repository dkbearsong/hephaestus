import json
from pathlib import Path
from typing import Dict, Any, List

class TestCaseGenerator:
    """
    Generates a suite of exactly 50 test cases adhering to:
    - 80% Normal Cases (40 cases)
    - 10% Edge Cases under Normal Situations (5 cases)
    - 10% Edge Cases over Normal Situations (5 cases)
    Supports <|prompt|>, <|prompt-new|>, and optional <|preparations|> tags.
    """
    __test__ = False

    @classmethod
    def generate_all_cases(cls) -> List[Dict[str, Any]]:
        cases = []

        # -------------------------------------------------------------
        # 1. NORMAL CASES (80% -> 40 Cases, 1 to 40)
        # -------------------------------------------------------------
        projects = ["PAY", "AUTH", "BILL", "CORE", "SEARCH", "DATA", "API", "NOTIF", "OPS", "UI"]

        # 1.1 Standard Jira comment_created with <|prompt|> (10 cases)
        for i, proj in enumerate(projects, start=1):
            body_text = f"<|prompt|> Implement unit tests and boundary validation for {proj} service."
            expected_prep = None

            if proj == "OPS":
                body_text = (
                    f"<|prompt|> Implement unit tests and boundary validation for {proj} service.\n"
                    f"<|preparations|> Start docker daemon and initialize redis MCP tool."
                )
                expected_prep = "Start docker daemon and initialize redis MCP tool."
            elif proj == "UI":
                body_text = (
                    f"<|prompt|> Implement unit tests and boundary validation for {proj} service.\n"
                    f"<|preparations|>\n- Install Node v20\n- Run npm install\n</|preparations|>"
                )
                expected_prep = "- Install Node v20\n- Run npm install"

            cases.append({
                "id": f"CASE-{i:03d}",
                "category": "normal",
                "description": f"Standard Jira comment_created with <|prompt|> on {proj}-{100 + i}",
                "payload_type": "jira_comment",
                "payload": {
                    "webhookEvent": "comment_created",
                    "comment": {
                        "id": f"{1000 + i}",
                        "body": body_text,
                        "author": {"displayName": f"Dev {proj}", "name": f"dev_{proj.lower()}"}
                    },
                    "issue": {
                        "key": f"{proj}-{100 + i}",
                        "fields": {
                            "summary": f"Feature requirement for {proj}",
                            "project": {"key": proj},
                            "labels": ["run_ai_orchestrator"]
                        }
                    }
                },
                "expected_tag": "prompt",
                "expected_is_ai_trigger": True,
                "expected_issue_key": f"{proj}-{100 + i}",
                "expected_project_key": proj,
                "expected_stripped_comment": f"Implement unit tests and boundary validation for {proj} service.",
                "expected_preparations": expected_prep
            })

        # 1.2 Standard Jira comment_created with <|prompt-new|> (6 cases, 11 to 16)
        new_projects = ["NEWPAY", "NEWAUTH", "GATEWAY", "WORKER", "ANALYTICS", "INGEST"]
        for i, proj in enumerate(new_projects, start=11):
            body_text = f"<|prompt-new|> Scaffold new microservice repo for {proj} using FastAPI and SQLAlchemy."
            expected_prep = None

            if proj == "INGEST":
                body_text = (
                    f"<|prompt-new|> Scaffold new microservice repo for {proj} using FastAPI and SQLAlchemy.\n"
                    f"<|preparations|> Mount postgres and rabbitmq MCP tools."
                )
                expected_prep = "Mount postgres and rabbitmq MCP tools."

            cases.append({
                "id": f"CASE-{i:03d}",
                "category": "normal",
                "description": f"Brand new project scaffold with <|prompt-new|> on {proj}-1",
                "payload_type": "jira_comment",
                "payload": {
                    "webhookEvent": "comment_created",
                    "comment": {
                        "id": f"{1000 + i}",
                        "body": body_text,
                        "author": {"displayName": "Architect Bob", "name": "arch_bob"}
                    },
                    "issue": {
                        "key": f"{proj}-1",
                        "fields": {
                            "summary": f"Scaffold {proj} architecture",
                            "project": {"key": proj},
                            "labels": ["run_ai_orchestrator"]
                        }
                    }
                },
                "expected_tag": "prompt-new",
                "expected_is_ai_trigger": True,
                "expected_issue_key": f"{proj}-1",
                "expected_project_key": proj,
                "expected_stripped_comment": f"Scaffold new microservice repo for {proj} using FastAPI and SQLAlchemy.",
                "expected_preparations": expected_prep
            })

        # 1.3 Jira issue_updated with nested comment containing <|prompt|> (8 cases, 17 to 24)
        issue_projects = ["PAY", "AUTH", "CORE", "SEARCH", "DATA", "API", "NOTIF", "OPS"]
        for i, proj in enumerate(issue_projects, start=17):
            cases.append({
                "id": f"CASE-{i:03d}",
                "category": "normal",
                "description": f"Jira issue_updated event with nested comment <|prompt|> on {proj}-{200 + i}",
                "payload_type": "jira_issue_update",
                "payload": {
                    "webhookEvent": "jira:issue_updated",
                    "issue": {
                        "key": f"{proj}-{200 + i}",
                        "fields": {
                            "summary": f"Refactor module {proj}",
                            "project": {"key": proj},
                            "comment": {
                                "comments": [
                                    {"id": f"old-{i}", "body": "Initial discussion"},
                                    {"id": f"{2000 + i}", "body": f"<|prompt|> Optimize thread pool size in {proj} client."}
                                ]
                            }
                        }
                    }
                },
                "expected_tag": "prompt",
                "expected_is_ai_trigger": True,
                "expected_issue_key": f"{proj}-{200 + i}",
                "expected_project_key": proj,
                "expected_stripped_comment": f"Optimize thread pool size in {proj} client.",
                "expected_preparations": None
            })

        # 1.4 Jira issue_updated with nested comment containing <|prompt-new|> (4 cases, 25 to 28)
        scaffold_projs = ["EXPORT", "METRICS", "CACHE", "CRON"]
        for i, proj in enumerate(scaffold_projs, start=25):
            cases.append({
                "id": f"CASE-{i:03d}",
                "category": "normal",
                "description": f"Jira issue_updated event with nested <|prompt-new|> on {proj}-10",
                "payload_type": "jira_issue_update",
                "payload": {
                    "webhookEvent": "jira:issue_updated",
                    "issue": {
                        "key": f"{proj}-10",
                        "fields": {
                            "summary": f"Bootstrap service {proj}",
                            "project": {"key": proj},
                            "comment": {
                                "comments": [
                                    {"id": f"{2000 + i}", "body": f"<|prompt-new|> Initialize standalone service for {proj}."}
                                ]
                            }
                        }
                    }
                },
                "expected_tag": "prompt-new",
                "expected_is_ai_trigger": True,
                "expected_issue_key": f"{proj}-10",
                "expected_project_key": proj,
                "expected_stripped_comment": f"Initialize standalone service for {proj}.",
                "expected_preparations": None
            })

        # 1.5 Direct JSON payloads (6 cases, 29 to 34)
        direct_configs = [
            ("DIRPAY-1", "DIRPAY", "<|prompt|> Direct JSON payload: implement webhook retry.", "prompt", "Direct JSON payload: implement webhook retry."),
            ("DIRAUTH-2", "DIRAUTH", "<|prompt|> Direct JSON payload: add OAuth2 refresh token.", "prompt", "Direct JSON payload: add OAuth2 refresh token."),
            ("DIRBILL-3", "DIRBILL", "<|prompt|> Direct JSON payload: calculate VAT tax.", "prompt", "Direct JSON payload: calculate VAT tax."),
            ("DIRSVC-4", "DIRSVC", "<|prompt-new|> Scaffold new microservice for auditing.", "prompt-new", "Scaffold new microservice for auditing."),
            ("DIRMQ-5", "DIRMQ", "<|prompt-new|> Scaffold RabbitMQ consumer worker.", "prompt-new", "Scaffold RabbitMQ consumer worker."),
            ("DIRCLI-6", "DIRCLI", "<|prompt-new|> Create CLI administration tool with Typer.", "prompt-new", "Create CLI administration tool with Typer.")
        ]
        for idx, (ikey, pkey, ctext, tag, stripped) in enumerate(direct_configs, start=29):
            cases.append({
                "id": f"CASE-{idx:03d}",
                "category": "normal",
                "description": f"Direct JSON payload with <|{tag}|> on {ikey}",
                "payload_type": "direct",
                "payload": {
                    "jira_issue_key": ikey,
                    "project_key": pkey,
                    "summary": f"Direct task for {ikey}",
                    "comment_text": ctext
                },
                "expected_tag": tag,
                "expected_is_ai_trigger": True,
                "expected_issue_key": ikey,
                "expected_project_key": pkey,
                "expected_stripped_comment": stripped,
                "expected_preparations": None
            })

        # 1.6 Normal comments WITHOUT prompt tags (6 cases, 35 to 40)
        no_tag_comments = [
            ("PAY-501", "PAY", "PR is approved and ready for QA testing."),
            ("AUTH-502", "AUTH", "Can we check whether this affects JWT token expiration?"),
            ("CORE-503", "CORE", "Updated staging deployment completed at 14:00 UTC."),
            ("SEARCH-504", "SEARCH", "Please add documentation in the wiki for new search filter syntax."),
            ("DATA-505", "DATA", "PostgreSQL database vacuum completed successfully with zero downtime."),
            ("UI-506", "UI", "Merged frontend styling fix for dark mode contrast.")
        ]
        for idx, (ikey, pkey, ctext) in enumerate(no_tag_comments, start=35):
            cases.append({
                "id": f"CASE-{idx:03d}",
                "category": "normal",
                "description": f"Normal comment without prompt tags on {ikey}",
                "payload_type": "jira_comment",
                "payload": {
                    "webhookEvent": "comment_created",
                    "comment": {
                        "id": f"{3000 + idx}",
                        "body": ctext,
                        "author": {"displayName": "Reviewer Alice", "name": "alice"}
                    },
                    "issue": {
                        "key": ikey,
                        "fields": {
                            "summary": f"Discussion on {ikey}",
                            "project": {"key": pkey}
                        }
                    }
                },
                "expected_tag": None,
                "expected_is_ai_trigger": False,
                "expected_issue_key": ikey,
                "expected_project_key": pkey,
                "expected_stripped_comment": ctext,
                "expected_preparations": None
            })

        # -------------------------------------------------------------
        # 2. EDGE CASES UNDER NORMAL SITUATIONS (10% -> 5 Cases, 41 to 45)
        # -------------------------------------------------------------
        cases.append({
            "id": "CASE-041",
            "category": "edge_under",
            "description": "Leading and trailing whitespace, tabs, and newlines surrounding <|prompt|>",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": "4001",
                    "body": "\n\n\t  <|prompt|>  Add connection pool keep-alive ping.  \n\t"
                },
                "issue": {"key": "EDGE-1", "fields": {"project": {"key": "EDGE"}}}
            },
            "expected_tag": "prompt",
            "expected_is_ai_trigger": True,
            "expected_issue_key": "EDGE-1",
            "expected_project_key": "EDGE",
            "expected_stripped_comment": "Add connection pool keep-alive ping.  \n\t",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-042",
            "category": "edge_under",
            "description": "Prompt tag directly followed by text without intervening space",
            "payload_type": "jira_comment",
            "comment_text": "<|prompt|>fix the memory leak in buffer_manager.py",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {"id": "4002", "body": "<|prompt|>fix the memory leak in buffer_manager.py"},
                "issue": {"key": "EDGE-2", "fields": {"project": {"key": "EDGE"}}}
            },
            "expected_tag": "prompt",
            "expected_is_ai_trigger": True,
            "expected_issue_key": "EDGE-2",
            "expected_project_key": "EDGE",
            "expected_stripped_comment": "fix the memory leak in buffer_manager.py",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-043",
            "category": "edge_under",
            "description": "Comment containing secondary prompt tags inside the prompt instructions body",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": "4003",
                    "body": "<|prompt|> Update documentation and explain how <|prompt|> and <|prompt-new|> work."
                },
                "issue": {"key": "EDGE-3", "fields": {"project": {"key": "EDGE"}}}
            },
            "expected_tag": "prompt",
            "expected_is_ai_trigger": True,
            "expected_issue_key": "EDGE-3",
            "expected_project_key": "EDGE",
            "expected_stripped_comment": "Update documentation and explain how <|prompt|> and <|prompt-new|> work.",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-044",
            "category": "edge_under",
            "description": "Prompt tag with empty comment body after tag",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {"id": "4004", "body": "<|prompt|>   \n\t  "},
                "issue": {"key": "EDGE-4", "fields": {"project": {"key": "EDGE"}}}
            },
            "expected_tag": "prompt",
            "expected_is_ai_trigger": True,
            "expected_issue_key": "EDGE-4",
            "expected_project_key": "EDGE",
            "expected_stripped_comment": "",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-045",
            "category": "edge_under",
            "description": "Unicode characters, emojis, and Windows CRLF line breaks",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": "4005",
                    "body": "<|prompt|> 🚀 Fix unicode parsing with ü, ñ, and 日本語\r\nLine 2 with CRLF\r\n"
                },
                "issue": {"key": "EDGE-5", "fields": {"project": {"key": "EDGE"}}}
            },
            "expected_tag": "prompt",
            "expected_is_ai_trigger": True,
            "expected_issue_key": "EDGE-5",
            "expected_project_key": "EDGE",
            "expected_stripped_comment": "🚀 Fix unicode parsing with ü, ñ, and 日本語\r\nLine 2 with CRLF\r\n",
            "expected_preparations": None
        })

        # -------------------------------------------------------------
        # 3. EDGE CASES OVER NORMAL SITUATIONS (10% -> 5 Cases, 46 to 50)
        # -------------------------------------------------------------
        huge_stacktrace = "Stack trace line: at com.hephaestus.core.Service.run(Service.java:120)\n" * 700
        cases.append({
            "id": "CASE-046",
            "category": "edge_over",
            "description": "Oversized payload (massive prompt body with >50KB stack trace dump)",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": "5001",
                    "body": f"<|prompt|> Analyze this oversized crash dump:\n{huge_stacktrace}"
                },
                "issue": {"key": "OVER-1", "fields": {"project": {"key": "OVER"}}}
            },
            "expected_tag": "prompt",
            "expected_is_ai_trigger": True,
            "expected_issue_key": "OVER-1",
            "expected_project_key": "OVER",
            "expected_stripped_comment": f"Analyze this oversized crash dump:\n{huge_stacktrace}",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-047",
            "category": "edge_over",
            "description": "Prompt tag embedded deep within conversational sentence (not at prefix)",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": "5002",
                    "body": "Please be careful not to include <|prompt|> in client-facing Jira tickets."
                },
                "issue": {"key": "OVER-2", "fields": {"project": {"key": "OVER"}}}
            },
            "expected_tag": None,
            "expected_is_ai_trigger": False,
            "expected_issue_key": "OVER-2",
            "expected_project_key": "OVER",
            "expected_stripped_comment": "Please be careful not to include <|prompt|> in client-facing Jira tickets.",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-048",
            "category": "edge_over",
            "description": "Near-miss or misspelled tag prefix (e.g. <|prompt-old|> or <prompt>)",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": "5003",
                    "body": "<|prompt-old|> Update legacy payment flow without new engine."
                },
                "issue": {"key": "OVER-3", "fields": {"project": {"key": "OVER"}}}
            },
            "expected_tag": None,
            "expected_is_ai_trigger": False,
            "expected_issue_key": "OVER-3",
            "expected_project_key": "OVER",
            "expected_stripped_comment": "<|prompt-old|> Update legacy payment flow without new engine.",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-049",
            "category": "edge_over",
            "description": "Malformed/incomplete payload structure missing issue and comment objects",
            "payload_type": "raw_incomplete",
            "payload": {
                "webhookEvent": "jira:system_heartbeat",
                "timestamp": 1724928000
            },
            "expected_tag": None,
            "expected_is_ai_trigger": False,
            "expected_issue_key": "DEFAULT-UNKNOWN",
            "expected_project_key": "DEFAULT",
            "expected_stripped_comment": "",
            "expected_preparations": None
        })

        cases.append({
            "id": "CASE-050",
            "category": "edge_over",
            "description": "Bracket-wrapped tag prefix ([<|prompt|>]) - should not trigger AI",
            "payload_type": "jira_comment",
            "payload": {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": "5005",
                    "body": "[<|prompt|>] Refactor database migrations."
                },
                "issue": {"key": "OVER-5", "fields": {"project": {"key": "OVER"}}}
            },
            "expected_tag": None,
            "expected_is_ai_trigger": False,
            "expected_issue_key": "OVER-5",
            "expected_project_key": "OVER",
            "expected_stripped_comment": "[<|prompt|>] Refactor database migrations.",
            "expected_preparations": None
        })

        return cases

    @classmethod
    def save_cases_to_file(cls, filepath: Path):
        """Saves generated cases to disk as formatted JSON."""
        cases = cls.generate_all_cases()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cases, f, indent=2)
        return cases

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent
    target_1 = root / "test" / "test_data" / "cases.json"
    target_2 = root / "tests" / "test_data" / "cases.json"
    TestCaseGenerator.save_cases_to_file(target_1)
    TestCaseGenerator.save_cases_to_file(target_2)
    print(f"Generated {len(TestCaseGenerator.generate_all_cases())} cases to {target_1} and {target_2}")
