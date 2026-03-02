"""
Webhook router — receives raw payloads from third-party tools and
dispatches them to the appropriate integration handler.

POST /v1/webhooks/slack    — Slack Events API
POST /v1/webhooks/github   — GitHub App webhook
POST /v1/webhooks/linear   — Linear webhook

Each integration handler is responsible for:
  1. Verifying the request signature (HMAC-SHA256)
  2. Parsing the payload into a CaptureEventCreate
  3. Calling the EventCaptureService to persist the event
"""

from fastapi import APIRouter

from app.integrations.github import router as github_router
from app.integrations.linear import router as linear_router
from app.integrations.slack import router as slack_router

router = APIRouter()

router.include_router(slack_router, prefix="/slack")
router.include_router(github_router, prefix="/github")
router.include_router(linear_router, prefix="/linear")
