# PKCE OAuth Flow

**Status**: ✅ Implemented (Sprint 16)  
**Priority**: P0  
**Feature**: `pkce=True`

---

## Overview

PKCE (Proof Key for Code Exchange, pronounced "pixie") is an OAuth 2.0 extension that makes the authorization code flow more secure for **public clients** like mobile apps, SPAs, and native applications that cannot securely store a client secret.

**Key Benefits:**
- **No client_secret required** - Mobile apps don't need to embed secrets
- **Protection against authorization code interception** - Even if code is stolen, it cannot be exchanged without the verifier
- **Recommended by OAuth 2.0 Security Best Practices** - RFC 7636

---

## How PKCE Works

### Standard OAuth Flow Problem

In traditional OAuth, public clients face a security challenge:
1. Client redirects user to authorization server
2. User authorizes, receives authorization code
3. Client exchanges code for tokens using client_secret
4. **Problem**: Mobile apps can't securely store client_secret (can be extracted from app binary)

### PKCE Solution

PKCE adds an extra layer of security using cryptographic challenges:

```
1. Client generates random code_verifier (128-char string)
2. Client computes code_challenge = SHA256(code_verifier)
3. Client includes code_challenge in authorization request
4. Authorization server stores code_challenge
5. User authorizes, receives authorization code
6. Client sends authorization code + code_verifier to token endpoint
7. Server verifies: SHA256(code_verifier) == stored code_challenge
8. If match, server returns access tokens
```

**Security:** Even if an attacker intercepts the authorization code, they cannot exchange it without the original `code_verifier` (which never leaves the client).

---

## API Endpoints

### 1. Get PKCE Status

Check if PKCE is enabled and which providers are supported.

**Endpoint:** `GET /api/v1/pkce/status`

**Response:**
```json
{
  "enabled": true,
  "supported_providers": ["google", "github", "microsoft"],
  "supported_methods": ["S256", "plain"]
}
```

---

### 2. Initiate PKCE Authorization

Start the PKCE OAuth flow by generating an authorization URL.

**Endpoint:** `POST /api/v1/pkce/authorize`

**Request Body:**
```json
{
  "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
  "code_challenge_method": "S256",
  "redirect_uri": "com.example.myapp://callback",
  "provider": "google"
}
```

**Fields:**
- `code_challenge` (required): SHA-256 hash of code_verifier (base64 URL-safe)
- `code_challenge_method` (required): `"S256"` (SHA-256) or `"plain"` (not recommended)
- `redirect_uri` (required): Your app's callback URL (custom scheme for mobile)
- `provider` (optional): `"google"` (default), `"github"`, or `"microsoft"`

**Response:**
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&code_challenge=...",
  "state": "xyz123_csrf_protection"
}
```

**Next Steps:**
1. Redirect user to `auth_url` in a browser (or in-app webview)
2. User authorizes your app
3. OAuth provider redirects back to your `redirect_uri` with authorization `code` and `state`

---

### 3. Exchange Code for Tokens

Exchange the authorization code for access and refresh tokens using PKCE verification.

**Endpoint:** `POST /api/v1/pkce/token`

**Request Body:**
```json
{
  "code": "4/0AfJohXk...",
  "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
  "state": "xyz123_csrf_protection",
  "redirect_uri": "com.example.myapp://callback"
}
```

**Fields:**
- `code` (required): Authorization code from OAuth provider
- `code_verifier` (required): Original code verifier (plain text, 128 chars)
- `state` (required): State parameter from authorization request (CSRF protection)
- `redirect_uri` (required): Same redirect_uri used in authorization request

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "def50200a1b2c3d4...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid code_verifier, expired challenge, redirect_uri mismatch
- `401 Unauthorized` - Token exchange failed with OAuth provider

---

## Client Implementation

### iOS (Swift) Example

```swift
import Foundation
import CommonCrypto

class PKCEManager {
    func generateCodeVerifier() -> String {
        var buffer = [UInt8](repeating: 0, count: 128)
        _ = SecRandomCopyBytes(kSecRandomDefault, buffer.count, &buffer)
        return Data(buffer).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
            .prefix(128)
            .description
    }
    
    func generateCodeChallenge(verifier: String) -> String {
        guard let data = verifier.data(using: .utf8) else { return "" }
        var digest = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        data.withUnsafeBytes {
            _ = CC_SHA256($0.baseAddress, CC_LONG(data.count), &digest)
        }
        return Data(digest).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
    
    func initiateAuth() async throws {
        // 1. Generate verifier and challenge
        let verifier = generateCodeVerifier()
        let challenge = generateCodeChallenge(verifier: verifier)
        
        // Save verifier for later (UserDefaults, Keychain)
        UserDefaults.standard.set(verifier, forKey: "pkce_verifier")
        
        // 2. Request authorization URL
        let response = try await apiClient.post("/api/v1/pkce/authorize", json: [
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "redirect_uri": "com.myapp://callback",
            "provider": "google"
        ])
        
        let authUrl = response["auth_url"] as! String
        let state = response["state"] as! String
        
        // Save state for CSRF protection
        UserDefaults.standard.set(state, forKey: "pkce_state")
        
        // 3. Open browser for user authorization
        if let url = URL(string: authUrl) {
            UIApplication.shared.open(url)
        }
    }
    
    func handleCallback(url: URL) async throws {
        // 4. Extract code and state from callback URL
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        guard let code = components?.queryItems?.first(where: { $0.name == "code" })?.value,
              let state = components?.queryItems?.first(where: { $0.name == "state" })?.value else {
            throw PKCEError.invalidCallback
        }
        
        // 5. Verify state matches
        let savedState = UserDefaults.standard.string(forKey: "pkce_state")
        guard state == savedState else {
            throw PKCEError.csrfDetected
        }
        
        // 6. Exchange code for tokens
        let verifier = UserDefaults.standard.string(forKey: "pkce_verifier")!
        
        let response = try await apiClient.post("/api/v1/pkce/token", json: [
            "code": code,
            "code_verifier": verifier,
            "state": state,
            "redirect_uri": "com.myapp://callback"
        ])
        
        let accessToken = response["access_token"] as! String
        let refreshToken = response["refresh_token"] as! String
        
        // 7. Save tokens securely (Keychain)
        try Keychain.save(accessToken, for: "access_token")
        try Keychain.save(refreshToken, for: "refresh_token")
        
        // 8. Clean up
        UserDefaults.standard.removeObject(forKey: "pkce_verifier")
        UserDefaults.standard.removeObject(forKey: "pkce_state")
    }
}
```

### Android (Kotlin) Example

```kotlin
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64

class PKCEManager(private val apiClient: ApiClient) {
    
    fun generateCodeVerifier(): String {
        val bytes = ByteArray(128)
        SecureRandom().nextBytes(bytes)
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes)
            .take(128)
    }
    
    fun generateCodeChallenge(verifier: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val hash = digest.digest(verifier.toByteArray())
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(hash)
    }
    
    suspend fun initiateAuth(context: Context) {
        // 1. Generate verifier and challenge
        val verifier = generateCodeVerifier()
        val challenge = generateCodeChallenge(verifier)
        
        // Save verifier for later
        context.getSharedPreferences("pkce", Context.MODE_PRIVATE)
            .edit()
            .putString("verifier", verifier)
            .apply()
        
        // 2. Request authorization URL
        val response = apiClient.post("/api/v1/pkce/authorize", mapOf(
            "code_challenge" to challenge,
            "code_challenge_method" to "S256",
            "redirect_uri" to "com.myapp://callback",
            "provider" to "google"
        ))
        
        val authUrl = response["auth_url"] as String
        val state = response["state"] as String
        
        // Save state for CSRF protection
        context.getSharedPreferences("pkce", Context.MODE_PRIVATE)
            .edit()
            .putString("state", state)
            .apply()
        
        // 3. Open browser for user authorization
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(authUrl))
        context.startActivity(intent)
    }
    
    suspend fun handleCallback(intent: Intent, context: Context) {
        // 4. Extract code and state from intent
        val uri = intent.data ?: throw PKCEException("No data in callback")
        val code = uri.getQueryParameter("code") ?: throw PKCEException("No code")
        val state = uri.getQueryParameter("state") ?: throw PKCEException("No state")
        
        // 5. Verify state matches
        val prefs = context.getSharedPreferences("pkce", Context.MODE_PRIVATE)
        val savedState = prefs.getString("state", null)
        if (state != savedState) {
            throw PKCEException("CSRF detected: state mismatch")
        }
        
        // 6. Exchange code for tokens
        val verifier = prefs.getString("verifier", null)!!
        
        val response = apiClient.post("/api/v1/pkce/token", mapOf(
            "code" to code,
            "code_verifier" to verifier,
            "state" to state,
            "redirect_uri" to "com.myapp://callback"
        ))
        
        val accessToken = response["access_token"] as String
        val refreshToken = response["refresh_token"] as String
        
        // 7. Save tokens securely
        SecureStorage.save(context, "access_token", accessToken)
        SecureStorage.save(context, "refresh_token", refreshToken)
        
        // 8. Clean up
        prefs.edit()
            .remove("verifier")
            .remove("state")
            .apply()
    }
}
```

### React Native Example

```javascript
import { generateRandom } from 'expo-crypto';
import * as AuthSession from 'expo-auth-session';
import * as SecureStore from 'expo-secure-store';

export class PKCEManager {
  async generateCodeVerifier() {
    const random = await generateRandom(128);
    return base64URLEncode(random);
  }

  async generateCodeChallenge(verifier) {
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return base64URLEncode(new Uint8Array(hash));
  }

  async initiateAuth() {
    // 1. Generate verifier and challenge
    const verifier = await this.generateCodeVerifier();
    const challenge = await this.generateCodeChallenge(verifier);

    // Save verifier for later
    await SecureStore.setItemAsync('pkce_verifier', verifier);

    // 2. Request authorization URL
    const response = await fetch('https://api.example.com/api/v1/pkce/authorize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code_challenge: challenge,
        code_challenge_method: 'S256',
        redirect_uri: 'com.myapp://callback',
        provider: 'google',
      }),
    });

    const { auth_url, state } = await response.json();

    // Save state for CSRF protection
    await SecureStore.setItemAsync('pkce_state', state);

    // 3. Open browser for authorization
    const result = await AuthSession.startAsync({ authUrl: auth_url });

    if (result.type === 'success') {
      await this.handleCallback(result.params);
    }
  }

  async handleCallback(params) {
    const { code, state } = params;

    // 4. Verify state
    const savedState = await SecureStore.getItemAsync('pkce_state');
    if (state !== savedState) {
      throw new Error('CSRF detected: state mismatch');
    }

    // 5. Exchange code for tokens
    const verifier = await SecureStore.getItemAsync('pkce_verifier');

    const response = await fetch('https://api.example.com/api/v1/pkce/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code,
        code_verifier: verifier,
        state,
        redirect_uri: 'com.myapp://callback',
      }),
    });

    const { access_token, refresh_token } = await response.json();

    // 6. Save tokens securely
    await SecureStore.setItemAsync('access_token', access_token);
    await SecureStore.setItemAsync('refresh_token', refresh_token);

    // 7. Clean up
    await SecureStore.deleteItemAsync('pkce_verifier');
    await SecureStore.deleteItemAsync('pkce_state');
  }
}

function base64URLEncode(buffer) {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}
```

---

## Security Considerations

### ✅ Best Practices

1. **Always use S256 method** - SHA-256 is more secure than plain
2. **Generate verifier on the client** - Never send verifier over network until token exchange
3. **Use secure random generation** - Use platform-provided crypto APIs
4. **Store verifier securely** - Use Keychain (iOS), Keystore (Android), SecureStore (React Native)
5. **Verify state parameter** - Protect against CSRF attacks
6. **Use custom URL schemes** - e.g., `com.myapp://callback` for mobile deep linking
7. **10-minute challenge expiration** - Challenges auto-expire for security

### ⚠️ Common Pitfalls

1. **Don't reuse code_verifier** - Generate new one for each auth attempt
2. **Don't log verifier or challenge** - Keep them secret
3. **Don't use "plain" method in production** - Always use S256
4. **Don't embed client_secret** - PKCE eliminates need for it

---

## Database Schema

### pkce_challenges Table

```sql
CREATE TABLE pkce_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state VARCHAR UNIQUE NOT NULL,
    code_challenge VARCHAR NOT NULL,
    code_challenge_method VARCHAR NOT NULL DEFAULT 'S256',
    redirect_uri VARCHAR NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    used_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pkce_state ON pkce_challenges(state);
CREATE INDEX idx_pkce_user_id ON pkce_challenges(user_id);
CREATE INDEX idx_pkce_expires_at ON pkce_challenges(expires_at);
```

---

## Testing

Run tests with:

```bash
cd /root/my-superagent/backend
pytest tests/api/test_pkce.py -v
```

**Test Coverage:**
- ✅ Code verifier generation (128 chars, URL-safe, unique)
- ✅ Code challenge generation (S256 and plain methods)
- ✅ Challenge storage and expiration
- ✅ Challenge verification (success and failure cases)
- ✅ Reuse protection (used challenges cannot be reused)
- ✅ Redirect URI validation (mismatch detection)
- ✅ Expired challenge cleanup
- ✅ End-to-end authorization flow
- ✅ Token exchange with PKCE verification

---

## Deployment

### Configuration

No additional configuration required! PKCE is enabled by default if OAuth providers are configured:

```env
# .env
GOOGLE_CLIENT_ID=your_google_client_id
GITHUB_CLIENT_ID=your_github_client_id
MICROSOFT_CLIENT_ID=your_microsoft_client_id
```

### Database Migration

Run migration to create `pkce_challenges` table:

```bash
cd /root/my-superagent/backend
alembic upgrade head
```

### Monitoring

PKCE operations are logged for security auditing:
- Challenge creation
- Challenge verification success/failure
- Token exchange attempts
- Expired challenge cleanup

---

## Future Enhancements

- [ ] **Rate limiting** - Prevent brute force attacks on challenges
- [ ] **Device fingerprinting** - Track device_id for additional security
- [ ] **Token binding** - Bind tokens to specific devices
- [ ] **Multiple concurrent flows** - Support multiple auth attempts per user
- [ ] **Admin dashboard** - Monitor PKCE usage and security events

---

## References

- [RFC 7636: PKCE](https://datatracker.ietf.org/doc/html/rfc7636)
- [OAuth 2.0 Security Best Current Practice](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
- [Google OAuth PKCE Support](https://developers.google.com/identity/protocols/oauth2/native-app#step1-code-verifier)
- [Microsoft PKCE Documentation](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)

---

**Status**: ✅ Ready for Production  
**Last Updated**: 2026-03-02  
**Completion**: Sprint 16 🎯
