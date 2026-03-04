"""
Bootstrap endpoint — first-time dashboard setup.

POST /v1/auth/bootstrap
  • Requires a valid Clerk JWT (Authorization: Bearer <clerk_jwt>)
  • NO workspace required — this creates the first user record
  • Each new user gets their own isolated Personal Workspace
  • Safe to call multiple times — fully idempotent
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection
from ulid import ULID

from app.database.postgres import get_connection
from app.middleware.auth import _get_jwks

router = APIRouter(prefix="/v1/auth", tags=["bootstrap"])

bearer_scheme = HTTPBearer(auto_error=True)


class BootstrapResponse(BaseModel):
    workspace_id: str
    user_id: str
    message: str


@router.post("", response_model=BootstrapResponse)
async def bootstrap(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    conn: AsyncConnection = Depends(get_connection),
):
    """
    First-time setup: validate Clerk JWT, ensure the user has a personal workspace,
    return workspace info. Idempotent — safe to call on every dashboard load.
    """
    from sqlalchemy import text

    token = credentials.credentials

    # ── 1. Validate JWT and extract clerk_user_id ───────────────────────
    from jose import JWTError, jwk, jwt as jose_jwt

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

    email = claims.get("email") or f"{clerk_user_id}@bootstrap.local"

    # ── 3. Look up existing workspace, or create a personal one ──────────────
    row = await conn.execute(
        text("SELECT workspace_id FROM users WHERE id = :uid"),
        {"uid": clerk_user_id},
    )
    existing = row.fetchone()

    if existing:
        workspace_id = existing.workspace_id
    else:
        workspace_id = f"ws_{ULID()}"
        await conn.execute(
            text("""
                INSERT INTO workspaces (workspace_id, name, plan)
                VALUES (:ws, 'Personal Workspace', 'starter')
                ON CONFLICT (workspace_id) DO NOTHING
            """),
            {"ws": workspace_id},
        )
        await conn.execute(
            text("""
                INSERT INTO users (id, workspace_id, email, role, created_at)
                VALUES (:id, :ws, :email, 'admin', now())
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": clerk_user_id, "ws": workspace_id, "email": email},
        )

    await conn.commit()

    return BootstrapResponse(
        workspace_id=workspace_id,
        user_id=clerk_user_id,
        message="Bootstrap complete.",
    )
