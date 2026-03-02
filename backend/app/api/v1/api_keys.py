"""
API Key Management — POST/GET/DELETE /v1/auth/api-keys

Design partners and SDK users authenticate via API keys.
Keys are generated here, stored as SHA-256 hashes, and shown plaintext ONCE at creation.

Auth required: Clerk JWT (human user creating keys for their workspace).
"""

import hashlib
import secrets
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection
from ulid import ULID

import sqlalchemy as sa

from app.database.postgres import get_connection
from app.middleware.auth import AuthContext, require_auth

logger = structlog.get_logger(__name__)
router = APIRouter()

_API_KEY_PREFIX = "sk-lore-"
_API_KEY_BYTES = 32   # 256 bits of entropy → 64-char hex string


# ── Pydantic models ───────────────────────────────────────────────────────────


class ApiKeyCreateRequest(BaseModel):
    name: str
    """Human-readable label, e.g. 'Production SDK key'."""
    scopes: list[str] = ["read", "write"]
    expires_at: datetime | None = None


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    key: str
    """Plaintext key — shown ONCE. Store it securely."""
    scopes: list[str]
    workspace_id: str
    created_at: datetime
    expires_at: datetime | None


class ApiKeyListItem(BaseModel):
    id: str
    name: str
    scopes: list[str]
    workspace_id: str
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime | None


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyListItem]
    total: int


class ApiKeyRevokeResponse(BaseModel):
    id: str
    revoked: bool


# ── Helpers ───────────────────────────────────────────────────────────────────


def _generate_key() -> str:
    return _API_KEY_PREFIX + secrets.token_hex(_API_KEY_BYTES)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key",
    description=(
        "Generate a new API key for this workspace. "
        "The plaintext key is returned **once** — store it securely. "
        "Subsequent requests only return the key ID and metadata."
    ),
)
async def create_api_key(
    body: ApiKeyCreateRequest,
    auth: AuthContext = Depends(require_auth),
    conn: AsyncConnection = Depends(get_connection),
) -> ApiKeyCreateResponse:
    key_id = f"key_{ULID()}"
    raw_key = _generate_key()
    key_hash = _hash_key(raw_key)

    await conn.execute(
        sa.text(
            """
            INSERT INTO api_keys (id, workspace_id, key_hash, name, scopes, created_by, expires_at)
            VALUES (:id, :workspace_id, :key_hash, :name, :scopes, :created_by, :expires_at)
            """
        ),
        {
            "id": key_id,
            "workspace_id": auth.workspace_id,
            "key_hash": key_hash,
            "name": body.name,
            "scopes": body.scopes,
            "created_by": auth.user_id,
            "expires_at": body.expires_at,
        },
    )

    row = await conn.execute(
        sa.text("SELECT id, workspace_id, name, scopes, created_at, expires_at FROM api_keys WHERE id = :id"),
        {"id": key_id},
    )
    record = row.fetchone()

    logger.info("api_key_created", key_id=key_id, workspace_id=auth.workspace_id, name=body.name)

    return ApiKeyCreateResponse(
        id=record.id,
        name=record.name,
        key=raw_key,             # only time the plaintext is returned
        scopes=record.scopes,
        workspace_id=record.workspace_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


@router.get(
    "",
    response_model=ApiKeyListResponse,
    summary="List API keys",
    description="List all API keys for the authenticated workspace. Plaintext keys are never returned.",
)
async def list_api_keys(
    auth: AuthContext = Depends(require_auth),
    conn: AsyncConnection = Depends(get_connection),
) -> ApiKeyListResponse:
    rows = await conn.execute(
        sa.text(
            """
            SELECT id, name, scopes, workspace_id, last_used_at, created_at, expires_at
              FROM api_keys
             WHERE workspace_id = :workspace_id
             ORDER BY created_at DESC
            """
        ),
        {"workspace_id": auth.workspace_id},
    )
    records = rows.fetchall()

    items = [
        ApiKeyListItem(
            id=r.id,
            name=r.name,
            scopes=r.scopes,
            workspace_id=r.workspace_id,
            last_used_at=r.last_used_at,
            created_at=r.created_at,
            expires_at=r.expires_at,
        )
        for r in records
    ]

    return ApiKeyListResponse(keys=items, total=len(items))


@router.delete(
    "/{key_id}",
    response_model=ApiKeyRevokeResponse,
    summary="Revoke an API key",
    description="Permanently revoke an API key. The key will stop working immediately.",
)
async def revoke_api_key(
    key_id: str,
    auth: AuthContext = Depends(require_auth),
    conn: AsyncConnection = Depends(get_connection),
) -> ApiKeyRevokeResponse:
    result = await conn.execute(
        sa.text(
            """
            DELETE FROM api_keys
             WHERE id = :key_id AND workspace_id = :workspace_id
            """
        ),
        {"key_id": key_id, "workspace_id": auth.workspace_id},
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found in this workspace.",
        )

    logger.info("api_key_revoked", key_id=key_id, workspace_id=auth.workspace_id)
    return ApiKeyRevokeResponse(id=key_id, revoked=True)
