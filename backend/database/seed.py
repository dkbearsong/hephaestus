from datetime import datetime, timezone, timedelta
from backend.database.connection import SessionLocal
from backend.database.models import Project, Ticket, WorkLog, ChatMessage, AgentNotification

def seed_database():
    session = SessionLocal()
    try:
        # Check if projects already exist
        if session.query(Project).count() > 0:
            print("[INFO] Database already contains projects. Skipping seed.")
            return

        print("[INFO] Seeding Hephaestus database with realistic initial data...")

        # 1. Projects
        p1 = Project(
            name="Payment Service API",
            key="PAY",
            jira_key="PAY",
            jira_ticket_key="PAY-1",
            repo_url="https://github.com/example/payment-service.git",
            base_image="python:3.12-slim",
            system_prompt_additions="Ensure all payment tokens are masked. Output completed logs with security audit checklist.",
            color="#3B82F6" # Blue
        )
        p2 = Project(
            name="Identity & Auth Engine",
            key="AUTH",
            jira_key="AUTH",
            jira_ticket_key="AUTH-1",
            repo_url="https://github.com/example/auth-engine.git",
            base_image="python:3.12-slim",
            system_prompt_additions="Adhere to OAuth2 and JWT RFC standards. Document any token expiration changes in detail.",
            color="#8B5CF6" # Purple
        )
        p3 = Project(
            name="Notification Broker",
            key="NOTIF",
            jira_key="NOTIF",
            jira_ticket_key="NOTIF-1",
            repo_url="https://github.com/example/notif-broker.git",
            base_image="python:3.12-slim",
            system_prompt_additions="Use asynchronous batching for push delivery. Verify dead-letter queue routing.",
            color="#10B981" # Green
        )
        session.add_all([p1, p2, p3])
        session.commit()

        # 2. Tickets
        now = datetime.now(timezone.utc)
        
        t1 = Ticket(
            project_id=p1.id,
            jira_key="PAY-104",
            title="Fix idempotency key collision on recurring charge webhooks",
            description="Recurring charge events with matching idempotency keys fail silently instead of returning existing transaction reference.",
            branch_name="hephaestus/PAY-104-fix-idempotency",
            container_id="hephaestus_PAY_PAY_104_fix_idempotency",
            image_id="hephaestus-checkpoint:PAY-PAY-104",
            status="review_ready",
            created_at=now - timedelta(hours=2)
        )
        t2 = Ticket(
            project_id=p1.id,
            jira_key="PAY-105",
            title="External Stripe Sandbox API integration tests",
            description="Add integration testing for Stripe webhook payload signature verification.",
            branch_name="hephaestus/PAY-105-stripe-tests",
            container_id="hephaestus_PAY_PAY_105_stripe_tests",
            status="paused_waiting_input",
            created_at=now - timedelta(hours=1)
        )
        t3 = Ticket(
            project_id=p2.id,
            jira_key="AUTH-42",
            title="Upgrade JWT signature algorithm to RS256 with key rotation",
            description="Replace HS256 secret key verification with RS256 JWKS public key rotation endpoint.",
            branch_name="hephaestus/AUTH-42-rs256-rotation",
            container_id="hephaestus_AUTH_AUTH_42_rs256",
            status="review_ready",
            created_at=now - timedelta(minutes=45)
        )
        session.add_all([t1, t2, t3])
        session.commit()

        # Sample Git Diff
        sample_diff = """diff --git a/services/charge_service.py b/services/charge_service.py
index e69de29..4b825dc 100644
--- a/services/charge_service.py
+++ b/services/charge_service.py
@@ -34,8 +34,14 @@ class ChargeService:
     async def process_webhook(self, idempotency_key: str, payload: dict) -> dict:
-        existing = await self.db.find_charge(idempotency_key)
-        if existing:
-            raise DuplicateKeyError("Collision detected")
+        existing = await self.db.find_charge(idempotency_key)
+        if existing:
+            logger.info("Idempotent replay detected for key: %s", idempotency_key)
+            return {
+                "status": "replayed",
+                "transaction_id": existing.id,
+                "amount": existing.amount
+            }
 
         transaction = await self.gateway.charge(payload)
         await self.db.save_charge(idempotency_key, transaction)
"""

        # 3. Work Logs
        w1 = WorkLog(
            ticket_id=t1.id,
            project_id=p1.id,
            timestamp=now - timedelta(minutes=30),
            prompt_raw="<|prompt|> Update webhook handling so when an idempotency key collision occurs, instead of throwing an error it logs an idempotent replay and returns the existing transaction data.",
            prompt_processed="Update webhook handling so when an idempotency key collision occurs, instead of throwing an error it logs an idempotent replay and returns the existing transaction data.",
            staged_files=["services/charge_service.py"],
            status="completed",
            summary_changes="Replaced DuplicateKeyError exception with graceful idempotent replay returning existing transaction data and debug logging.",
            what_was_wrong="When an upstream webhook delivered a duplicate charge event, ChargeService was raising DuplicateKeyError, which resulted in a 500 server response and repeated retries from payment providers.",
            what_was_done="Refactored process_webhook to catch existing charge records by idempotency key, log an info message indicating replay, and return the already-persisted transaction reference with status 'replayed'.",
            user_check_items=[
                "Confirm that webhook response returns HTTP 200 with status='replayed'",
                "Verify no double-charges occur in database during high concurrency test",
                "Check that cloud logging dashboard picks up the new 'Idempotent replay detected' log"
            ],
            git_diff=sample_diff,
            full_log="[Docker] Container hephaestus_PAY_PAY_104_fix_idempotency checked out.\n[Harness] Antigravity Daemon started.\n[Test] Running pytest tests/test_webhooks.py ... PASSED 14 tests.\n[Git] Committed 4b825dc: 'fix: handle duplicate idempotency key gracefully'.\n[Docker] Container checkpointed and stopped."
        )

        w2 = WorkLog(
            ticket_id=t3.id,
            project_id=p2.id,
            timestamp=now - timedelta(minutes=15),
            prompt_raw="<|prompt|> Upgrade token verification from HS256 to RS256 with key rotation endpoint support.",
            prompt_processed="Upgrade token verification from HS256 to RS256 with key rotation endpoint support.",
            staged_files=["auth/jwt_validator.py", "auth/keys.py"],
            status="completed",
            summary_changes="Implemented JWKS fetching with cache TTL for RS256 verification and fallback key rotation.",
            what_was_wrong="Symmetric HS256 tokens required distributing shared secrets across microservices, increasing exposure risk.",
            what_was_done="Added PyJWT RS256 validator with background JWKS cache refreshing and automated fallback when kid is rotated.",
            user_check_items=[
                "Ensure public JWKS endpoint URL is accessible from staging cluster",
                "Verify expired token rejection test passes"
            ],
            git_diff="""diff --git a/auth/jwt_validator.py b/auth/jwt_validator.py
--- a/auth/jwt_validator.py
+++ b/auth/jwt_validator.py
@@ -12,2 +12,8 @@
-ALGORITHM = "HS256"
+ALGORITHM = "RS256"
+JWKS_CACHE_TTL = 3600
""",
            full_log="[Docker] Initialized branch hephaestus/AUTH-42-rs256-rotation.\n[Harness] Coding harness applied changes to auth/jwt_validator.py.\n[Docker] Checkpointed."
        )
        session.add_all([w1, w2])
        session.commit()

        # 4. Chat Messages (Human-in-the-loop)
        c1 = ChatMessage(
            ticket_id=t2.id,
            project_id=p1.id,
            sender="agent",
            message_type="question",
            content="I am setting up the integration test suite for Stripe webhooks, but I need external network access to https://api.stripe.com/v1 to retrieve the test sandbox public keys. Would you like me to mock these responses locally, or can you grant network access to api.stripe.com?",
            status="pending",
            created_at=now - timedelta(minutes=25)
        )
        session.add(c1)

        # 5. Agent Notifications
        # Red shaking notification (Needs user input)
        n1 = AgentNotification(
            ticket_id=t2.id,
            project_id=p1.id,
            type="needs_input",
            title="External Network Access Approval Required",
            message="Coding agent paused on PAY-105: Requesting permission to connect to api.stripe.com or switch to mock fixtures.",
            status="pending",
            action_url=f"/tickets/{t2.id}",
            created_at=now - timedelta(minutes=25)
        )
        # Yellow notification (Task completed)
        n2 = AgentNotification(
            ticket_id=t1.id,
            project_id=p1.id,
            type="completed",
            title="Task Review Ready: PAY-104",
            message="Agent finished implementing idempotency fix on branch hephaestus/PAY-104-fix-idempotency. Ready for user review.",
            status="pending",
            action_url=f"/tickets/{t1.id}",
            created_at=now - timedelta(minutes=30)
        )
        session.add_all([n1, n2])
        session.commit()

        print("[SUCCESS] Database successfully seeded with projects, tickets, diffs, and notifications!")
    finally:
        session.close()

if __name__ == "__main__":
    seed_database()
