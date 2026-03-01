# Enhanced OAuth Features - Sprint 7

**Status**: ✅ Completed (2026-03-01)  
**Priority**: P0 (Security Critical)

---

## Overview

Enhanced OAuth implementation with:
- **Refresh token rotation** for improved security
- **Multi-provider support** (Google, GitHub, Microsoft)
- **Token encryption at rest** 
- **Enhanced mobile OAuth** with security auditing
- **Automatic reuse detection** for token security breaches

---

## Features

### 1. Refresh Token Rotation

Implements secure token rotation following OAuth 2.0 best practices:

- **One-time use**: Each refresh token can only be used once
- **Automatic rotation**: Using a refresh token returns a new access + refresh token pair and revokes the old refresh token
- **Reuse detection**: If a revoked token is reused, the entire token family is revoked (security breach detection)
- **Token families**: Tracks token lineage for security auditing

**Benefits**:
- Mitigates stolen token attacks
- Automatic detection of compromised credentials
- Improved security audit trail

**Endpoints**:
- `POST /api/v1/auth/refresh` - Refresh access token (with automatic rotation)
- `POST /api/v1/auth/logout` - Revoke a single refresh token
- `POST /api/v1/auth/logout-all` - Revoke all tokens for a user (logout from all devices)

### 2. Multi-Provider OAuth Support

Support for multiple OAuth providers beyond Google:

#### Supported Providers

**Google OAuth** (existing + enhanced)
- Google Workspace integration (Docs, Sheets, Slides, Drive)
- Mobile SDK support (id_token validation)
- Offline access with refresh tokens

**GitHub OAuth** (new)
- User authentication via GitHub account
- Email verification from GitHub API
- Access to GitHub user profile data

**Microsoft OAuth** (new)
- Azure AD / Microsoft Account authentication
- Microsoft Graph API integration
- Support for enterprise (tenant-specific) and consumer (common) accounts

#### Provider Management

- `GET /api/v1/auth/me/providers` - List all connected OAuth providers for current user
- Users can connect multiple providers to the same account
- Automatic user linking by email address

### 3. Token Encryption at Rest

All OAuth tokens are encrypted before storage in the database:

**Implementation**:
- Uses `cryptography.fernet` for symmetric encryption
- Key derived from `SECRET_KEY` using PBKDF2 (100,000 iterations)
- Tokens stored in `oauth_connections` table with encrypted fields:
  - `access_token_encrypted`
  - `refresh_token_encrypted`

**Security**:
- Even if database is compromised, tokens remain encrypted
- Only the application with correct `SECRET_KEY` can decrypt
- Failed decryption returns `None` safely

### 4. Enhanced Mobile OAuth

Improved mobile authentication with security features:

**Features**:
- Device ID tracking for each session
- User agent and IP address logging for security auditing
- Token family tracking per device
- Support for guest mode (device-only authentication)

**Endpoints**:
- `POST /api/v1/auth/google/mobile` - Google Sign-In SDK integration
- `POST /api/v1/auth/guest` - Guest session (no OAuth required)

### 5. Automatic Token Cleanup

**Celery Task**: `oauth.cleanup_expired_tokens`
- **Schedule**: Daily at 2:00 AM UTC (via Celery Beat)
- **Actions**:
  - Deletes expired refresh tokens
  - Removes revoked tokens older than 30 days
  - Reduces database bloat

---

## Database Schema

### New Tables

#### `refresh_tokens`

Stores refresh tokens with rotation support:

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    device_id VARCHAR(255),
    user_agent VARCHAR(512),
    ip_address VARCHAR(45),
    token_family UUID NOT NULL,
    previous_token_id UUID REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Indexes**:
- `ix_refresh_tokens_user_id`
- `ix_refresh_tokens_token_hash` (unique)
- `ix_refresh_tokens_is_revoked`
- `ix_refresh_tokens_token_family`

#### `oauth_connections`

Stores OAuth provider connections with encrypted tokens:

```sql
CREATE TABLE oauth_connections (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,  -- 'GOOGLE', 'GITHUB', 'MICROSOFT'
    provider_user_id VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    access_token_encrypted VARCHAR(1024) NOT NULL,
    refresh_token_encrypted VARCHAR(1024),
    token_expires_at TIMESTAMP,
    scopes VARCHAR(1024),
    provider_data VARCHAR(2048),
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Indexes**:
- `ix_oauth_connections_user_id`
- `ix_oauth_connections_provider`
- `ix_oauth_connections_provider_user_id`

---

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Google OAuth (existing)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback

# GitHub OAuth (new)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GITHUB_REDIRECT_URI=http://localhost:8000/api/v1/auth/github/callback

# Microsoft OAuth (new)
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret
MICROSOFT_TENANT_ID=common  # or your tenant ID for enterprise
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/v1/auth/microsoft/callback

# JWT Settings
SECRET_KEY=your_secret_key_for_jwt_and_encryption
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### Setting Up OAuth Providers

#### GitHub OAuth Setup

1. Go to https://github.com/settings/developers
2. Create a new OAuth App
3. Set Authorization callback URL: `http://localhost:8000/api/v1/auth/github/callback`
4. Copy Client ID and Client Secret to `.env`

#### Microsoft OAuth Setup

1. Go to https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade
2. Register a new application
3. Add redirect URI: `http://localhost:8000/api/v1/auth/microsoft/callback`
4. Create a client secret
5. Copy Application (client) ID, Directory (tenant) ID, and client secret to `.env`

---

## API Reference

### Authentication Flow

#### Google OAuth

```bash
# 1. Get authorization URL
GET /api/v1/auth/google
→ { "auth_url": "https://accounts.google.com/o/oauth2/auth?..." }

# 2. User visits auth_url and approves
# 3. Callback with code
POST /api/v1/auth/callback
{
  "code": "authorization_code_from_google",
  "state": "csrf_state_token"
}
→ {
  "access_token": "jwt_access_token",
  "refresh_token": "secure_refresh_token",
  "token_type": "bearer",
  "user": { "id": "...", "email": "...", "full_name": "..." }
}
```

#### GitHub OAuth

```bash
# 1. Get authorization URL
GET /api/v1/auth/github
→ { "auth_url": "https://github.com/login/oauth/authorize?..." }

# 2. User authorizes on GitHub
# 3. Callback with code
POST /api/v1/auth/github/callback
{
  "code": "github_authorization_code",
  "state": "csrf_state_token"
}
→ { "access_token": "...", "refresh_token": "...", "user": {...} }
```

#### Microsoft OAuth

```bash
# 1. Get authorization URL
GET /api/v1/auth/microsoft
→ { "auth_url": "https://login.microsoftonline.com/..." }

# 2. User authorizes with Microsoft
# 3. Callback with code
POST /api/v1/auth/microsoft/callback
{
  "code": "microsoft_authorization_code",
  "state": "csrf_state_token"
}
→ { "access_token": "...", "refresh_token": "...", "user": {...} }
```

### Token Management

#### Refresh Token (with Rotation)

```bash
POST /api/v1/auth/refresh
Headers:
  X-Device-ID: device_identifier (optional)
{
  "refresh_token": "current_refresh_token"
}
→ {
  "access_token": "new_jwt_access_token",
  "refresh_token": "new_refresh_token",  # Old token is revoked!
  "user": {...}
}
```

**Important**: The old refresh token is revoked and can no longer be used. Always use the new refresh token for future refreshes.

#### Logout (Single Device)

```bash
POST /api/v1/auth/logout
Headers:
  Authorization: Bearer {access_token}
{
  "refresh_token": "refresh_token_to_revoke"
}
→ { "message": "Logged out successfully" }
```

#### Logout All Devices

```bash
POST /api/v1/auth/logout-all
Headers:
  Authorization: Bearer {access_token}
→ { "message": "Logged out from all devices successfully" }
```

### User Info

#### Get Current User

```bash
GET /api/v1/auth/me
Headers:
  Authorization: Bearer {access_token}
→ {
  "id": "user_uuid",
  "email": "user@example.com",
  "full_name": "User Name"
}
```

#### Get Connected Providers

```bash
GET /api/v1/auth/me/providers
Headers:
  Authorization: Bearer {access_token}
→ [
  {
    "provider": "google",
    "connected": true,
    "email": "user@gmail.com",
    "last_used": "2026-03-01T10:30:00Z"
  },
  {
    "provider": "github",
    "connected": true,
    "email": "user@example.com",
    "last_used": "2026-03-01T08:15:00Z"
  }
]
```

---

## Security Best Practices

### Token Storage (Client-Side)

**Access Token**:
- Store in memory (React state/context)
- Never in localStorage (XSS risk)
- Short-lived (30 minutes default)

**Refresh Token**:
- Store in httpOnly cookie (preferred) or secure storage
- Never in localStorage
- Longer-lived (7 days default)

### Token Rotation Flow

```
Client                    Server                  Database
  |                         |                         |
  |-- refresh_token_A ----->|                         |
  |                         |-- verify token_A ------>|
  |                         |<- token_A valid --------|
  |                         |-- revoke token_A ------>|
  |                         |-- create token_B ------>|
  |<- access_token_new -----|                         |
  |   refresh_token_B       |                         |
  |                         |                         |
```

**Security**: If `token_A` is reused after being revoked → entire token family is revoked (breach detected).

### Reuse Detection

If a revoked token is used:

1. Server detects reuse (token is marked `is_revoked=true`)
2. All tokens in the `token_family` are revoked immediately
3. User must re-authenticate
4. Security team is notified (implement logging/alerting as needed)

### Token Encryption

All provider tokens (Google, GitHub, Microsoft) are encrypted using:

- Algorithm: Fernet (symmetric encryption)
- Key derivation: PBKDF2-SHA256 (100,000 iterations)
- Salt: Static salt (`agenthq_oauth_salt`)
- Master key: `SECRET_KEY` from environment

**Important**: Keep `SECRET_KEY` secure and rotate periodically. Changing `SECRET_KEY` will invalidate all encrypted tokens.

---

## Migration

### Running the Migration

```bash
cd backend
alembic upgrade head
```

This will:
1. Create `refresh_tokens` table
2. Create `oauth_connections` table
3. Migrate existing Google OAuth tokens to `oauth_connections`

**Note**: Existing tokens are migrated as-is (not encrypted). New tokens will be encrypted on next login.

### Data Migration

Existing users with Google OAuth:
- Their `google_access_token` and `google_refresh_token` are copied to `oauth_connections`
- Original fields in `users` table remain (backward compatibility)
- After migration, users should re-authenticate for encrypted tokens

---

## Testing

### Manual Testing

#### Test Token Rotation

```bash
# 1. Login and get tokens
curl -X POST http://localhost:8000/api/v1/auth/callback \
  -H "Content-Type: application/json" \
  -d '{"code": "...", "state": "..."}'

# Save refresh_token_1

# 2. Refresh token (first time)
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "refresh_token_1"}'

# Save refresh_token_2

# 3. Try to reuse refresh_token_1 (should fail!)
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "refresh_token_1"}'

# Should return 401 Unauthorized with "Token reuse detected" message
```

#### Test Multi-Provider

```bash
# 1. Login with Google
# 2. Get providers
curl -X GET http://localhost:8000/api/v1/auth/me/providers \
  -H "Authorization: Bearer {access_token}"

# 3. Connect GitHub (use same email)
# 4. Get providers again (should show both)
```

### Unit Tests

Run tests:

```bash
cd backend
pytest tests/test_oauth.py -v
```

---

## Monitoring & Maintenance

### Metrics to Monitor

1. **Token rotation rate**: How often tokens are refreshed
2. **Reuse detections**: Count of security breach attempts
3. **Token cleanup**: Number of expired tokens cleaned daily
4. **Provider distribution**: Usage breakdown by OAuth provider

### Logging

Key events logged:

- OAuth authentication (provider, user_id, timestamp)
- Token refresh (user_id, device_id, IP address)
- Token reuse detection (user_id, token_family, revoked count)
- Token cleanup (count, date)

### Celery Task Status

Check token cleanup task:

```bash
# View Celery Flower (task monitoring UI)
http://localhost:5555

# Or check logs
docker logs agenthq-celery-worker | grep oauth.cleanup_expired_tokens
```

---

## Rollback Plan

If issues arise:

1. **Disable new endpoints**: Comment out routes in `auth_enhanced.py`
2. **Revert migration**: `alembic downgrade -1`
3. **Use legacy auth**: Old endpoints in `auth.py` still work
4. **Data preserved**: Original Google OAuth tokens remain in `users` table

---

## Future Enhancements

### Planned (Sprint 8+)

- [ ] **Social providers**: Twitter/X, LinkedIn, Facebook
- [ ] **Enterprise SSO**: SAML 2.0, LDAP integration
- [ ] **WebAuthn**: Passwordless authentication with biometrics
- [ ] **2FA**: TOTP-based two-factor authentication
- [ ] **OAuth scopes**: Granular permission management
- [ ] **Token introspection**: RFC 7662 compliance
- [ ] **Device management**: User-facing UI to view/revoke devices

---

## Troubleshooting

### Common Issues

**Issue**: "Invalid refresh token" on first refresh  
**Solution**: Ensure migration ran successfully (`alembic history` should show `007_enhanced_oauth`)

**Issue**: "Token reuse detected" immediately after login  
**Solution**: Check for multiple clients using the same refresh token (e.g., mobile + web)

**Issue**: Encrypted tokens fail to decrypt  
**Solution**: Verify `SECRET_KEY` hasn't changed since token creation

**Issue**: GitHub/Microsoft OAuth fails  
**Solution**: 
- Check OAuth app settings (callback URLs)
- Verify `GITHUB_CLIENT_ID` / `MICROSOFT_CLIENT_ID` in `.env`
- Check provider-specific scopes and permissions

---

## References

- [OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
- [RFC 6819 - OAuth 2.0 Threat Model](https://datatracker.ietf.org/doc/html/rfc6819)
- [Refresh Token Rotation](https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation)

---

**Completion Date**: 2026-03-01  
**Contributors**: AI Agent (SuperAgent Dev)  
**Status**: ✅ Production Ready
