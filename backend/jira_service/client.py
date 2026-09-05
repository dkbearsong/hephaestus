import logging
from typing import Optional, Dict, Any, List
from jira import JIRA
from backend.config import (
    JIRA_SERVER, JIRA_USERNAME, JIRA_API_TOKEN, preferences
)

logger = logging.getLogger("hephaestus.jira")

class JiraService:
    def __init__(self):
        self.server = JIRA_SERVER
        self.username = JIRA_USERNAME
        self.api_token = JIRA_API_TOKEN
        self.jira: Optional[JIRA] = None
        self._initialize_client()

    def _initialize_client(self):
        if self.server and self.username and self.api_token:
            try:
                self.jira = JIRA(
                    server=self.server,
                    basic_auth=(self.username, self.api_token)
                )
                logger.info("Connected to Jira Cloud at %s", self.server)
            except Exception as e:
                logger.warning("Failed to connect to Jira Cloud: %s. Using simulated mode.", e)
                self.jira = None
        else:
            logger.info("Jira credentials not fully configured. Operating in simulated mode.")

    def remove_trigger_label(self, issue_key: str, label_to_remove: Optional[str] = None) -> bool:
        """
        Removes the trigger label (e.g. 'run_ai_orchestrator') so subsequent updates do not re-fire the webhook.
        """
        target_label = label_to_remove or preferences.jira.trigger_label
        if not self.jira:
            logger.info("[MOCK] Simulated removal of label '%s' from issue %s", target_label, issue_key)
            return True

        try:
            issue = self.jira.issue(issue_key)
            current_labels = issue.fields.labels or []
            if target_label in current_labels:
                current_labels.remove(target_label)
                issue.update(fields={"labels": current_labels})
                logger.info("Removed label '%s' from Jira issue %s", target_label, issue_key)
            return True
        except Exception as e:
            logger.error("Error removing label '%s' from %s: %s", target_label, issue_key, e)
            return False

    def mark_ticket_merged(self, issue_key: str) -> bool:
        """
        Adds completion label (e.g. 'ai-merged') and transitions ticket to Complete status upon branch merge.
        """
        completion_label = preferences.jira.completion_label
        target_status = preferences.jira.transition_on_merge

        if not self.jira:
            logger.info("[MOCK] Added label '%s' and transitioned issue %s to '%s'", completion_label, issue_key, target_status)
            return True

        try:
            issue = self.jira.issue(issue_key)
            # 1. Update labels
            current_labels = issue.fields.labels or []
            if completion_label not in current_labels:
                current_labels.append(completion_label)
                issue.update(fields={"labels": current_labels})
            
            # 2. Transition status if available
            transitions = self.jira.transitions(issue)
            for t in transitions:
                if t['name'].lower() == target_status.lower():
                    self.jira.transition_issue(issue, t['id'])
                    logger.info("Transitioned issue %s to '%s'", issue_key, target_status)
                    break
            return True
        except Exception as e:
            logger.error("Error marking ticket %s as merged: %s", issue_key, e)
            return False

    def get_issue_details(self, issue_key: str) -> Dict[str, Any]:
        """
        Retrieves project/ticket details from Jira to populate Project or Ticket views.
        """
        if not self.jira:
            return {
                "key": issue_key,
                "summary": f"Simulated issue details for {issue_key}",
                "description": "This is simulated description from Jira Cloud for demonstration.",
                "status": "In Progress"
            }

        try:
            issue = self.jira.issue(issue_key)
            return {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": issue.fields.description or "",
                "status": issue.fields.status.name if hasattr(issue.fields, "status") else "Unknown"
            }
        except Exception as e:
            logger.error("Error fetching issue %s: %s", issue_key, e)
            return {"key": issue_key, "error": str(e)}

    def update_issue_details(self, issue_key: str, summary: Optional[str] = None, description: Optional[str] = None) -> bool:
        """
        Pushes edits from the Project Details page back to the associated Jira ticket.
        """
        if not self.jira:
            logger.info("[MOCK] Pushed update to Jira issue %s: summary='%s'", issue_key, summary)
            return True

        try:
            fields = {}
            if summary:
                fields["summary"] = summary
            if description is not None:
                fields["description"] = description
            if fields:
                issue = self.jira.issue(issue_key)
                issue.update(fields=fields)
                logger.info("Updated Jira issue %s successfully", issue_key)
            return True
        except Exception as e:
            logger.error("Error updating Jira issue %s: %s", issue_key, e)
            return False

    def add_comment(self, issue_key: str, comment_text: str) -> bool:
        """
        Adds a comment to the specified Jira issue (e.g. for blocker notifications).
        """
        if not self.jira:
            logger.info("[MOCK] Added comment to Jira issue %s: %s", issue_key, comment_text[:80])
            return True

        try:
            self.jira.add_comment(issue_key, comment_text)
            logger.info("Added comment to Jira issue %s", issue_key)
            return True
        except Exception as e:
            logger.error("Error adding comment to Jira issue %s: %s", issue_key, e)
            return False

jira_service = JiraService()
