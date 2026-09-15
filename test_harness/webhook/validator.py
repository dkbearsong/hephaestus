from typing import Optional, Dict, Any
from backend.watcher.webhook_watcher import FormattedWebhookPayload
from test_harness.base import BaseTestComponent, ComponentStatus

class WebhookPayloadValidator(BaseTestComponent):
    """
    Validator component that rigorously verifies:
    1. Schema correctness of formatted payloads.
    2. Accurate identification between <|prompt|>, <|prompt-new|>, and no prompt tags.
    3. Proper in-memory stripping of prompt tags without mutating raw_comment.
    """

    def __init__(self, name: str = "payload_validator"):
        super().__init__(name=name)
        self.status = ComponentStatus.ACTIVE

    def validate_schema(self, payload: FormattedWebhookPayload) -> bool:
        """Verifies that all required fields are present and validly typed."""
        assert isinstance(payload, FormattedWebhookPayload), f"Expected FormattedWebhookPayload, got {type(payload)}"
        assert bool(payload.jira_issue_key), "jira_issue_key must not be empty"
        assert bool(payload.project_key), "project_key must not be empty"
        assert isinstance(payload.is_ai_trigger, bool), "is_ai_trigger must be a boolean"
        assert isinstance(payload.in_memory_comment, str), "in_memory_comment must be a string"
        assert isinstance(payload.raw_comment, str), "raw_comment must be a string"
        assert isinstance(payload.metadata, dict), "metadata must be a dictionary"
        assert isinstance(payload.additional_values, dict), "additional_values must be a dictionary"
        assert isinstance(payload.has_additional_values, bool), "has_additional_values must be a boolean"
        assert isinstance(payload.additional_values_valid, bool), "additional_values_valid must be a boolean"
        assert payload.prompt_tag in ("prompt", "prompt-new", None), f"Invalid prompt_tag: {payload.prompt_tag}"
        return True

    def validate_additional_values_extraction(
        self,
        payload: FormattedWebhookPayload,
        expected_add_vals: Optional[dict] = None,
        expected_valid: bool = True
    ) -> bool:
        """Verifies <|additional values|> tag extraction and validity status."""
        assert payload.additional_values_valid == expected_valid, (
            f"additional_values_valid mismatch: expected {expected_valid}, got {payload.additional_values_valid}"
        )
        if expected_add_vals is not None and expected_valid:
            assert payload.additional_values == expected_add_vals, (
                f"additional_values mismatch: expected {expected_add_vals}, got {payload.additional_values}"
            )
        return True

    def validate_tag_identification(
        self,
        payload: FormattedWebhookPayload,
        expected_tag: Optional[str]
    ) -> bool:
        """
        Verifies that the prompt tag was accurately identified.
        expected_tag can be 'prompt', 'prompt-new', or None.
        """
        assert payload.prompt_tag == expected_tag, (
            f"Tag identification mismatch for issue {payload.jira_issue_key}: "
            f"expected '{expected_tag}', got '{payload.prompt_tag}'"
        )
        if expected_tag is not None:
            assert payload.is_ai_trigger is True, "is_ai_trigger must be True when tag is present"
        else:
            assert payload.is_ai_trigger is False, "is_ai_trigger must be False when no tag is present"
        return True

    def validate_tag_stripped_in_memory(
        self,
        payload: FormattedWebhookPayload,
        original_comment: str
    ) -> bool:
        """
        Verifies that:
        1. The in-memory copy of the comment has the <|prompt|> or <|prompt-new|> tag stripped.
        2. The raw_comment property still contains the full original comment.
        """
        assert payload.raw_comment == original_comment, "raw_comment was mutated or does not match original"

        in_mem = payload.in_memory_comment
        # Must not start with either tag
        assert not in_mem.startswith("<|prompt|>"), (
            f"in_memory_comment still begins with <|prompt|>: '{in_mem}'"
        )
        assert not in_mem.startswith("<|prompt-new|>"), (
            f"in_memory_comment still begins with <|prompt-new|>: '{in_mem}'"
        )

        # If it was an AI trigger, ensure in_memory_comment is stripped
        if payload.prompt_tag == "prompt":
            expected_stripped = original_comment.lstrip()
            if expected_stripped.startswith("<|prompt|>"):
                expected_stripped = expected_stripped[len("<|prompt|>"):].lstrip()
            assert in_mem == expected_stripped, (
                f"Stripped in-memory comment mismatch: expected '{expected_stripped}', got '{in_mem}'"
            )
        elif payload.prompt_tag == "prompt-new":
            expected_stripped = original_comment.lstrip()
            if expected_stripped.startswith("<|prompt-new|>"):
                expected_stripped = expected_stripped[len("<|prompt-new|>"):].lstrip()
            assert in_mem == expected_stripped, (
                f"Stripped in-memory comment mismatch: expected '{expected_stripped}', got '{in_mem}'"
            )
        return True

    def validate_preparations_extraction(
        self,
        payload: FormattedWebhookPayload,
        expected_preparations: Optional[str]
    ) -> bool:
        """
        Verifies that:
        1. The <|preparations|> instructions are extracted accurately.
        2. has_preparations flag matches presence of preparations.
        3. <|preparations|> tags are completely stripped from in_memory_comment.
        """
        assert payload.preparations == expected_preparations, (
            f"Preparations mismatch: expected {repr(expected_preparations)}, got {repr(payload.preparations)}"
        )
        assert payload.has_preparations == (expected_preparations is not None), (
            f"has_preparations mismatch: expected {expected_preparations is not None}, got {payload.has_preparations}"
        )
        assert "<|preparations|>" not in payload.in_memory_comment, (
            f"in_memory_comment still contains <|preparations|>: '{payload.in_memory_comment}'"
        )
        assert "</|preparations|>" not in payload.in_memory_comment, (
            f"in_memory_comment still contains </|preparations|>: '{payload.in_memory_comment}'"
        )
        return True

    def validate_files_extraction(
        self,
        payload: FormattedWebhookPayload,
        expected_files: list
    ) -> bool:
        """
        Verifies that:
        1. Referenced file paths are extracted accurately.
        2. has_files flag matches presence of files.
        3. prompt_instructions has <|files|> completely removed.
        """
        assert payload.files == expected_files, (
            f"Files mismatch: expected {expected_files}, got {payload.files}"
        )
        assert payload.has_files == (len(expected_files) > 0), (
            f"has_files mismatch: expected {len(expected_files) > 0}, got {payload.has_files}"
        )
        assert "<|files|>" not in payload.prompt_instructions, (
            f"prompt_instructions still contains <|files|>: '{payload.prompt_instructions}'"
        )
        return True
