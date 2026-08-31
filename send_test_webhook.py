import requests
import json
import hmac
import hashlib
import time

secret = "OsTZPH8NznMOgklYPq5h"
payload = {
    "webhookEvent": "comment_created",
    "comment": {
        "body": "<|prompt|> Implement feature X"
    },
    "issue": {
        "key": "TEST-101",
        "fields": {
            "summary": "Test issue"
        }
    }
}
payload_bytes = json.dumps(payload).encode("utf-8")
signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

res = requests.post(
    "http://localhost:8000/api/webhooks/jira",
    data=payload_bytes,
    headers={
        "Content-Type": "application/json",
        "X-Hub-Signature-256": f"sha256={signature}"
    }
)
print("Status:", res.status_code)
print("Response:", res.text)
