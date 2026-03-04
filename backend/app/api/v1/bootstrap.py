"""
Bootstrap endpoint — first-time dashboard setup.

POST /v1/auth/bootstrap
  • Requires a valid Clerk JWT (Authorization: Bearer <clerk_jwt>)
  • NO workspace required — this creates the first user record
  • Auto-assigns caller to the seed workspace
  • Creates a "dashboard" API key and returns its plaintext value
  • Safe to call multiple times — idempotent on user record, creates new key each call
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection
from ulid import ULID

from app.database.postgres import get_connection
from app.middleware.auth import _auth_clerk_jwt, _hash_key

router = APIRouter(prefix="/v1/auth", tags=["bootstrap"])

bearer_scheme = HTTPBearer(auto_error=True)


def _seed_workspace() -> str:
    from app.config import settings
    return settings.seed_workspace_id


class BootstrapResponse(BaseModel):
    plaintext_key: str
    workspace_id: str
    user_id: str
    message: str


@router.post("", response_model=BootstrapResponse)
async def bootstrap(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    conn: AsyncConnection = Depends(get_connection),
):
    """
    First-time setup: validate Clerk JWT, create user record in seed workspace,
    return a new API key.
    """
    from sqlalchemy import text

    token = credentials.credentials
    workspace_id = _seed_workspace()

    # ── 1. Ensure the seed workspace exists (idempotent) ─────────────────────
    await conn.execute(
        text(
            """
            INSERT INTO workspaces (workspace_id, name, plan)
            VALUES (:wid, 'Default Workspace', 'starter')
            ON CONFLICT (workspace_id) DO NOTHING
            """
        ),
        {"wid": workspace_id},
    )

    # ── 2. Validate JWT and extract clerk_user_id ─────────────────────────────
    from jose import JWTError, jwk, jwt as jose_jwt
    from app.middleware.auth import _get_jwks

    jwks = await _get_jwks()
    unverified_header = jose_jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    alg = unverified_header.get("alg", "RS256")

    signing_key = None
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            from jose import jwk as jose_jwk
            signing_key = jose_jwk.construct(key_data)
            break

    if not signing_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    try:
        claims = jose_jwt.decode(
            token, signing_key, algorithms=[alg], options={"verify_aud": False}
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}"
        )

    clerk_user_id: str = claims.get("sub", "")
    if not clerk_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub.")

    # ── 3. Upsert user into the seed workspace ────────────────────────────────
    user_id = str(ULID())
    email = (claims.get("email") or f"{clerk_user_id}@bootstrap.local")

    await conn.execute(
        text("""
            INSERT INTO users (id, workspace_id, email, role, created_at)
            VALUES (:id, :workspace_id, :email, 'admin', now())
            ON CONFLICT (id) DO UPDATE SET workspace_id = :workspace_id
        """),
        {"id": clerk_user_id, "workspace_id": workspace_id, "email": email},
    )

    # ── 4. Create API key ─────────────────────────────────────────────────────
    raw_key = "sk-lore-" + secrets.token_hex(32)
    key_hash = _hash_key(raw_key)
    key_id = str(ULID())

    await conn.execute(
        text("""
            INSERT INTO api_keys (id, workspace_id, key_hash, name, scopes, created_by, created_at)
            VALUES (:id, :workspace_id, :key_hash, 'dashboard', ARRAY['read','write'], :created_by, now())
        """),
        {
            "id": key_id,
            "workspace_id": workspace_id,
            "key_hash": key_hash,
            "created_by": clerk_user_id,
        },
    )

    return BootstrapResponse(
        plaintext_key=raw_key,
        workspace_id=workspace_id,
        user_id=clerk_user_id,
        message="Bootstrap complete. Save plaintext_key — it will not be shown again.",
    )
