"""
Auth middleware — FastAPI Depends() used by all protected /v1/ routes.

Two authentication paths:

  1. API key  (SDK / design partners / automation)
     Header: Authorization: Bearer sk-lore-<random>
     Flow:   SHA-256 hash → look up `api_keys` table → return workspace_id
     Use:    Python SDK, TypeScript SDK, direct API calls from production systems

  2. Clerk JWT  (dashboard / human users)
     Header: Authorization: Bearer <clerk_jwt>
     Flow:   Fetch JWKS from Clerk → validate RS256 signature → extract claims
     Use:    Dashboard UI (M4+), admin operations

Both paths return an `AuthContext` dataclass containing the validated workspace_id.
Routes that need it add `auth: AuthContext = Depends(require_auth)` to their signature.

Open routes (no auth required):
  GET  /health
  GET  /v1/health
  POST /integrations/*/webhook
  GET  /docs, /redoc, /openapi.json
"""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass
from typing import Literal

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database.postgres import get_connection

logger = structlog.get_logger(__name__)

# ── HTTP Bearer scheme ────────────────────────────────────────────────────────

bearer_scheme = HTTPBearer(auto_error=False)   # auto_error=False → we emit the 401 with context

# ── JWKS cache ────────────────────────────────────────────────────────────────
# Cached in-process memory; refreshed every JWKS_TTL_SECONDS.
# In a multi-worker setup, each worker fetches independently — acceptable at MVP scale.

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
JWKS_TTL_SECONDS: int = 3600  # 1 hour


def _clerk_jwks_url(publishable_key: str) -> str:
    """
    Derive the Clerk JWKS URL from the publishable key.

    Clerk publishable keys are base64url-encoded: pk_test_<b64(domain + "$")>
    Decoded domain → https://<domain>/.well-known/jwks.json
    """
    # Strip prefix  (pk_test_ or pk_live_)
    prefix = "pk_test_" if publishable_key.startswith("pk_test_") else "pk_live_"
    encoded = publishable_key[len(prefix):]

    # Add padding if needed
    padding = 4 - len(encoded) % 4
    if padding != 4:
        encoded += "=" * padding

    domain_bytes = base64.b64decode(encoded)
    domain = domain_bytes.decode("utf-8").rstrip("$")
    return f"https://{domain}/.well-known/jwks.json"


async def _get_jwks() -> dict:
    """Fetch and cache Clerk JWKS keys.

    Uses two strategies in order of preference:
    1. Authenticated Clerk Backend API  (GET api.clerk.com/v1/jwks + secret key)
       — most reliable; doesn't depend on publishable-key URL derivation.
    2. Publishable-key derived URL  (fallback if only publishable key is set).
    """
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < JWKS_TTL_SECONDS:
        return _jwks_cache

    from app.config import settings

    import httpx

    # Strategy 1 — authenticated backend API (preferred)
    if settings.clerk_secret_key:
        jwks_url = "https://api.clerk.com/v1/jwks"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    jwks_url,
                    headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
                )
                resp.raise_for_status()
                _jwks_cache = resp.json()
                _jwks_fetched_at = now
                logger.info("clerk_jwks_refreshed", source="backend_api")
                return _jwks_cache
        except Exception as exc:
            logger.warning("clerk_jwks_backend_api_failed", error=str(exc))
            # Fall through to strategy 2

    # Strategy 2 — derive URL from publishable key
    if not settings.clerk_publishable_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk is not configured — set CLERK_SECRET_KEY or CLERK_PUBLISHABLE_KEY.",
        )

    jwks_url = _clerk_jwks_url(settings.clerk_publishable_key)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = now
            logger.info("clerk_jwks_refreshed", source="publishable_key_url", url=jwks_url)
            return _jwks_cache
    except Exception as exc:
        logger.error("clerk_jwks_fetch_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch Clerk JWKS — authentication temporarily unavailable.",
        )


# ── AuthContext ───────────────────────────────────────────────────────────────


@dataclass
class AuthContext:
    """Validated authentication context, injected by require_auth."""

    workspace_id: str
    """The workspace this request is authorised to access."""

    auth_type: Literal["api_key", "clerk_jwt"]
    """How the request authenticated."""

    user_id: str | None = None
    """Clerk user ID (sub claim) — only present for JWT auth."""

    api_key_id: str | None = None
    """Row ID of the api_key used — only present for API key auth."""


# ── API key authentication ────────────────────────────────────────────────────

_API_KEY_PREFIX = "sk-lore-"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _auth_api_key(token: str, conn: AsyncConnection) -> AuthContext:
    """Validate an API key and return its workspace."""
    key_hash = _hash_key(token)

    row = await conn.execute(
        # language=SQL
        __import__("sqlalchemy").text(
            """
            SELECT id, workspace_id, expires_at
              FROM api_keys
             WHERE key_hash = :key_hash
               AND (expires_at IS NULL OR expires_at > now())
            """
        ),
        {"key_hash": key_hash},
    )
    record = row.fetchone()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fire-and-forget last_used_at update (don't await — non-critical)
    try:
        await conn.execute(
            __import__("sqlalchemy").text(
                "UPDATE api_keys SET last_used_at = now() WHERE id = :id"
            ),
            {"id": record.id},
        )
    except Exception:
        pass  # Never block a request for a non-critical update

    return AuthContext(
        workspace_id=record.workspace_id,
        auth_type="api_key",
        api_key_id=record.id,
    )


# ── Clerk JWT authentication ──────────────────────────────────────────────────


async def _auth_clerk_jwt(token: str, conn: AsyncConnection) -> AuthContext:
    """Validate a Clerk JWT and return workspace context."""
    jwks = await _get_jwks()

    try:
        # python-jose: find the matching key from JWKS and validate
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "RS256")

        # Find the matching public key by kid
        signing_key = None
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                signing_key = jwk.construct(key_data)
                break

        if not signing_key:
            raise JWTError("No matching JWKS key found for kid.")

        # Validate and decode. Clerk sets audience as the frontend domain.
        # We don't enforce audience here to keep it flexible for SDK callers.
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[alg],
            options={"verify_aud": False},
        )

    except JWTError as exc:
        logger.warning("clerk_jwt_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clerk_user_id: str = claims.get("sub", "")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Resolve workspace_id — check JWT claims in priority order, then DB.
    workspace_id: str | None = (
        claims.get("workspace_id")                              # custom session claim
        or claims.get("org_id")                                 # Clerk Organizations
        or (claims.get("public_metadata") or {}).get("workspace_id")
    )

    if not workspace_id:
        # Fall back to users table lookup
        row = await conn.execute(
            __import__("sqlalchemy").text(
                "SELECT workspace_id FROM users WHERE id = :user_id"
            ),
            {"user_id": clerk_user_id},
        )
        record = row.fetchone()
        if record:
            workspace_id = record.workspace_id

    if not workspace_id:
        # First-time user — auto-assign to the seed workspace.
        # Also ensure the workspace row exists (guards against missing migration).
        from app.config import settings as _settings
        import sqlalchemy
        seed = _settings.seed_workspace_id
        email = claims.get("email") or f"{clerk_user_id}@clerk"
        try:
            # Ensure workspace exists first (idempotent)
            await conn.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO workspaces (workspace_id, name, plan)
                    VALUES (:ws, 'Default Workspace', 'starter')
                    ON CONFLICT (workspace_id) DO NOTHING
                    """
                ),
                {"ws": seed},
            )
            # Now upsert the user
            await conn.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO users (id, workspace_id, email)
                    VALUES (:id, :ws, :email)
                    ON CONFLICT (id) DO UPDATE SET workspace_id = :ws
                    """
                ),
                {"id": clerk_user_id, "ws": seed, "email": email},
            )
            await conn.commit()
        except Exception as exc:
            logger.warning("user_upsert_failed", error=str(exc))
        workspace_id = seed

    return AuthContext(
        workspace_id=workspace_id,
        auth_type="clerk_jwt",
        user_id=clerk_user_id,
    )


# ── Main dependency ───────────────────────────────────────────────────────────


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: AsyncConnection = Depends(get_connection),
) -> AuthContext:
    """
    FastAPI dependency — validates the Bearer token and returns AuthContext.

    Usage:
        @router.get("/example")
        async def example(auth: AuthContext = Depends(require_auth)):
            return {"workspace": auth.workspace_id}
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    if token.startswith(_API_KEY_PREFIX):
        return await _auth_api_key(token, conn)
    else:
        return await _auth_clerk_jwt(token, conn)


# ── Optional auth (for endpoints that work both authenticated and not) ────────


async def optional_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: AsyncConnection = Depends(get_connection),
) -> AuthContext | None:
    """Like require_auth but returns None instead of raising 401 when no token provided."""
    if credentials is None:
        return None
    return await require_auth(credentials, conn)
