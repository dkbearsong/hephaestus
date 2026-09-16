import re
from typing import Dict, Any, Tuple, Optional

AGENT_TAG_PATTERN = re.compile(r"<\|agent:(?P<agent_name>[a-zA-Z0-9_\-]+)\|>", re.IGNORECASE)

class QualifierParser:
    """
    Parses Jira comment body for qualifier tags such as <|agent:AGENT_NAME|>.
    Overrides default platform assignment and agent behavior when present.
    """

    @classmethod
    def parse_qualifiers(cls, comment_body: str) -> Dict[str, Any]:
        """
        Parses comment text for <|agent:AGENT_NAME|> qualifier tag.

        Returns a dict:
        {
            "agent_override": Optional[str],
            "target_platform": Optional[str], # "LOCAL_CONTAINER" if agent_override is set, else None
            "cleaned_comment": str # comment text with agent qualifier tag removed
        }
        """
        if not comment_body:
            return {
                "agent_override": None,
                "target_platform": None,
                "cleaned_comment": ""
            }

        match = AGENT_TAG_PATTERN.search(comment_body)
        if match:
            agent_name = match.group("agent_name")
            cleaned = comment_body[:match.start()] + comment_body[match.end():]
            return {
                "agent_override": agent_name,
                "target_platform": "LOCAL_CONTAINER",
                "cleaned_comment": cleaned.strip()
            }

        return {
            "agent_override": None,
            "target_platform": None,
            "cleaned_comment": comment_body
        }

qualifier_parser = QualifierParser()
