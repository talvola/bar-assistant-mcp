"""OAuth 2.1 Authorization Server Provider for Bar Assistant MCP.

Authenticates users against the Bar Assistant API's /api/auth/login endpoint
and maps OAuth access tokens to BA Sanctum tokens for per-user API access.
"""

import secrets
import time
from dataclasses import dataclass, field

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class StoredAccessToken(AccessToken):
    """An OAuth access token with its associated BA Sanctum token.

    Extends the SDK's AccessToken so it's compatible with ProviderTokenVerifier.
    """

    ba_token: str  # The Bar Assistant Sanctum token
    ba_url: str  # The Bar Assistant API URL
    ba_bar_id: int  # The Bar Assistant bar ID


@dataclass
class PendingAuth:
    """Pending authorization waiting for user login."""

    params: AuthorizationParams
    client: OAuthClientInformationFull
    code: str
    created_at: float = field(default_factory=time.time)


class BarAssistantOAuthProvider:
    """OAuth provider that authenticates against Bar Assistant API.

    Implements the OAuthAuthorizationServerProvider protocol.
    Uses in-memory storage for tokens (suitable for single-instance deployment).
    """

    def __init__(self, ba_url: str, ba_bar_id: int = 1, issuer_url: str = ""):
        self.ba_url = ba_url
        self.ba_bar_id = ba_bar_id
        self.issuer_url = issuer_url

        # In-memory stores
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending_auths: dict[str, PendingAuth] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._auth_code_ba_tokens: dict[str, str] = {}  # code -> BA Sanctum token
        self._access_tokens: dict[str, StoredAccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        self._refresh_token_ba_tokens: dict[str, str] = {}  # refresh -> BA token

    # ===== Client Management =====

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id:
            self._clients[client_info.client_id] = client_info

    # ===== Authorization =====

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Start auth flow — return URL to our login page."""
        code = secrets.token_urlsafe(32)
        self._pending_auths[code] = PendingAuth(
            params=params,
            client=client,
            code=code,
        )
        # Redirect to our own login page with the pending code
        return f"{self.issuer_url}/auth/login?code_id={code}"

    async def complete_authorization(
        self, code_id: str, email: str, password: str
    ) -> str:
        """Complete authorization after user login. Returns redirect URL.

        Called by the login form handler after the user submits credentials.
        Authenticates against BA API and creates an authorization code.

        Raises:
            ValueError: If code_id is invalid/expired or BA login fails.
        """
        pending = self._pending_auths.pop(code_id, None)
        if not pending:
            raise ValueError("Invalid or expired authorization request")

        # Check expiry (10 minute window for login)
        if time.time() - pending.created_at > 600:
            raise ValueError("Authorization request expired")

        # Authenticate against Bar Assistant API
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.ba_url}/api/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "token_name": "mcp-oauth",
                },
            )
            if resp.status_code != 200:
                raise ValueError("Invalid email or password")
            ba_token = resp.json().get("data", {}).get("token")
            if not ba_token:
                raise ValueError("Failed to get token from Bar Assistant")

        # Create authorization code
        auth_code = AuthorizationCode(
            code=pending.code,
            scopes=pending.params.scopes or [],
            expires_at=time.time() + 300,  # 5 minute expiry
            client_id=pending.client.client_id or "",
            code_challenge=pending.params.code_challenge,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            resource=pending.params.resource,
        )
        self._auth_codes[pending.code] = auth_code
        self._auth_code_ba_tokens[pending.code] = ba_token

        # Build redirect URL back to Claude with the authorization code
        redirect = str(pending.params.redirect_uri)
        sep = "&" if "?" in redirect else "?"
        redirect += f"{sep}code={pending.code}"
        if pending.params.state:
            redirect += f"&state={pending.params.state}"

        return redirect

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._auth_codes.get(authorization_code)
        if code and code.expires_at > time.time():
            return code
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Remove the used authorization code
        self._auth_codes.pop(authorization_code.code, None)
        ba_token = self._auth_code_ba_tokens.pop(authorization_code.code, "")

        # Generate access and refresh tokens
        access_token_str = secrets.token_urlsafe(48)
        refresh_token_str = secrets.token_urlsafe(48)
        expires_in = 3600  # 1 hour

        # Store access token with BA token mapping
        self._access_tokens[access_token_str] = StoredAccessToken(
            token=access_token_str,
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + expires_in,
            ba_token=ba_token,
            ba_url=self.ba_url,
            ba_bar_id=self.ba_bar_id,
            resource=authorization_code.resource,
        )

        # Store refresh token
        self._refresh_tokens[refresh_token_str] = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
        )
        self._refresh_token_ba_tokens[refresh_token_str] = ba_token

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
            refresh_token=refresh_token_str,
        )

    # ===== Refresh Tokens =====

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return self._refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotate tokens
        old_refresh = refresh_token.token
        ba_token = self._refresh_token_ba_tokens.pop(old_refresh, "")
        self._refresh_tokens.pop(old_refresh, None)

        new_access_str = secrets.token_urlsafe(48)
        new_refresh_str = secrets.token_urlsafe(48)
        expires_in = 3600

        effective_scopes = scopes if scopes else refresh_token.scopes

        self._access_tokens[new_access_str] = StoredAccessToken(
            token=new_access_str,
            client_id=client.client_id or "",
            scopes=effective_scopes,
            expires_at=int(time.time()) + expires_in,
            ba_token=ba_token,
            ba_url=self.ba_url,
            ba_bar_id=self.ba_bar_id,
        )

        self._refresh_tokens[new_refresh_str] = RefreshToken(
            token=new_refresh_str,
            client_id=client.client_id or "",
            scopes=effective_scopes,
        )
        self._refresh_token_ba_tokens[new_refresh_str] = ba_token

        return OAuthToken(
            access_token=new_access_str,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(effective_scopes) if effective_scopes else None,
            refresh_token=new_refresh_str,
        )

    # ===== Token Verification =====

    async def load_access_token(self, token: str) -> StoredAccessToken | None:
        stored = self._access_tokens.get(token)
        if stored and stored.expires_at > time.time():
            return stored
        if stored:
            # Clean up expired token
            self._access_tokens.pop(token, None)
        return None

    # ===== Token Revocation =====

    async def revoke_token(
        self,
        token: StoredAccessToken | RefreshToken,
    ) -> None:
        if isinstance(token, StoredAccessToken):
            self._access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)
            self._refresh_token_ba_tokens.pop(token.token, None)

    def get_ba_token_for_access_token(self, access_token: str) -> StoredAccessToken | None:
        """Look up the BA Sanctum token associated with an OAuth access token."""
        stored = self._access_tokens.get(access_token)
        if stored and stored.expires_at > time.time():
            return stored
        return None


# ===== Login Page HTML =====

LOGIN_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bar Assistant - Sign In</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #1a1a2e;
            color: #eee;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .card {
            background: #16213e;
            border-radius: 12px;
            padding: 2rem;
            width: 100%;
            max-width: 380px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        h1 { font-size: 1.4rem; margin-bottom: 0.5rem; text-align: center; }
        .subtitle { color: #888; font-size: 0.85rem; text-align: center; margin-bottom: 1.5rem; }
        label { display: block; font-size: 0.85rem; color: #aaa; margin-bottom: 0.3rem; }
        input {
            width: 100%; padding: 0.7rem; border: 1px solid #333;
            border-radius: 6px; background: #0f3460; color: #eee;
            font-size: 1rem; margin-bottom: 1rem;
        }
        input:focus { outline: none; border-color: #e94560; }
        button {
            width: 100%; padding: 0.8rem; border: none; border-radius: 6px;
            background: #e94560; color: #fff; font-size: 1rem;
            cursor: pointer; font-weight: 600;
        }
        button:hover { background: #c73e54; }
        .error {
            background: #3d1a1a; border: 1px solid #e94560; border-radius: 6px;
            padding: 0.7rem; margin-bottom: 1rem; font-size: 0.85rem; color: #ff8a8a;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>Bar Assistant</h1>
        <p class="subtitle">Sign in to connect with Claude</p>
        $error
        <form method="POST" action="/auth/login">
            <input type="hidden" name="code_id" value="$code_id">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" required autofocus>
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required>
            <button type="submit">Sign In</button>
        </form>
    </div>
</body>
</html>"""
