"""
Auth router.

Two distinct flows:
  1. Captive-portal login  POST /api/auth/captive-login
     Any valid user (even guest) passes through — sets a cookie / returns a
     short-lived token that the iptables-based portal checks.

  2. Admin login           POST /api/auth/login
     Full JWT; required for media management, network config, VNC proxy.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt

from config import settings
from models.schemas import CaptiveLoginRequest, LoginRequest, TokenResponse

log = logging.getLogger(__name__)
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# In-memory session store for captive-portal authorised MACs
# { mac_address: expiry_datetime }
_portal_sessions: dict[str, datetime] = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _verify_admin_password(plain: str) -> bool:
    if not settings.ADMIN_PASSWORD_HASH:
        log.error("No ADMIN_PASSWORD_HASH set! Run the installer to configure.")
        return False
    return bcrypt.checkpw(plain.encode(), settings.ADMIN_PASSWORD_HASH.encode())


async def get_current_admin(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str | None = payload.get("sub")
        is_admin: bool = payload.get("admin", False)
        if username is None or not is_admin:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse, summary="Admin login")
async def admin_login(form: OAuth2PasswordRequestForm = Depends()):
    """
    Returns a JWT for admin operations.
    Username must match ADMIN_USERNAME; password verified against bcrypt hash.
    """
    if form.username != settings.ADMIN_USERNAME or not _verify_admin_password(form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = _create_access_token({"sub": form.username, "admin": True})
    log.info(f"Admin login: {form.username}")
    return TokenResponse(access_token=token, is_admin=True)


@router.post("/captive-login", summary="Captive-portal splash-page login")
async def captive_login(request: Request, response: Response, body: CaptiveLoginRequest):
    """
    Validates credentials on the captive-portal splash page.
    On success:
      - Records the client MAC in the in-memory session store
      - Runs iptables ACCEPT rule for that MAC so traffic flows
      - Returns the frontend URL the browser should redirect to
    On failure returns 401 so the splash page can show an error.
    """
    if body.username != settings.ADMIN_USERNAME or not _verify_admin_password(body.password):
        # You could add guest accounts here — for now only admin gets in
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Authorise MAC in iptables (best-effort; may require root)
    if body.mac:
        await _authorize_mac(body.mac)
        _portal_sessions[body.mac] = datetime.now(timezone.utc) + timedelta(hours=24)
        log.info(f"Captive portal: authorised MAC {body.mac}")

    redirect_url = settings.FRONTEND_URL
    return {"status": "ok", "redirect": redirect_url}


@router.get("/captive-check", summary="Check if a MAC is already authorised")
async def captive_check(mac: str):
    """Used by the portal redirect to skip the splash page for known MACs."""
    if mac in _portal_sessions:
        if _portal_sessions[mac] > datetime.now(timezone.utc):
            return {"authorized": True}
        del _portal_sessions[mac]
    return {"authorized": False}


@router.post("/logout", summary="Revoke admin token (client-side)")
async def logout():
    # JWT is stateless; tell the client to discard it.
    # For MAC deauth, a separate endpoint can be added.
    return {"status": "logged out"}


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _authorize_mac(mac: str):
    """
    Insert an iptables rule to let the authorised MAC bypass the captive portal.
    Requires the process to run with appropriate privileges or via sudo.
    """
    import asyncio
    import re
    # Sanitize MAC address - only allow hex digits and colons
    if not re.match(r'^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$', mac):
        log.warning(f"Invalid MAC address format: {mac}")
        return
    cmd = (
        f"iptables -t nat -I PREROUTING 1 -m mac --mac-source {mac} "
        f"-j RETURN"
    )
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception as e:
        log.warning(f"iptables MAC authorisation failed (need root?): {e}")
