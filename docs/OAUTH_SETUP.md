# 🔐 Google OAuth Setup Guide

This guide walks through setting up Google OAuth for AgentHQ.

---

## Prerequisites

- Google Account
- Access to [Google Cloud Console](https://console.cloud.google.com/)

---

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** → **New Project**
3. Enter project details:
   - **Project Name**: `AgentHQ`
   - **Organization**: (Optional)
   - **Location**: (Optional)
4. Click **Create**

---

## Step 2: Enable Required APIs

Navigate to **APIs & Services** → **Library** and enable:

### Required APIs
- ✅ Google Docs API
- ✅ Google Sheets API
- ✅ Google Slides API
- ✅ Google Drive API

For each API:
1. Search for the API name
2. Click on the API
3. Click **Enable**

---

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **User Type**:
   - **External**: For personal Google accounts
   - **Internal**: For Google Workspace organization (recommended for teams)
3. Click **Create**

### App Information

```
App name: AgentHQ
User support email: your-email@example.com
Application logo: (Optional - upload your logo)
```

### App Domain (Optional for development)

```
Application home page: http://localhost:8000
Application privacy policy: http://localhost:8000/privacy
Application terms of service: http://localhost:8000/terms
```

### Authorized Domains

```
localhost
```

### Developer Contact

```
Email addresses: your-email@example.com
```

### Scopes

Click **Add or Remove Scopes** and add:

| Scope | Description |
|-------|-------------|
| `.../auth/documents` | View and manage Google Docs |
| `.../auth/spreadsheets` | View and manage Google Sheets |
| `.../auth/presentations` | View and manage Google Slides |
| `.../auth/drive.file` | View and manage files created by this app |

### Test Users (for External user type)

Add your email addresses:
```
user1@example.com
user2@example.com
```

Click **Save and Continue**

---

## Step 4: Create OAuth Credentials

### For Desktop Application (Tauri)

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Select **Application type**: `Desktop app`
4. Enter name: `AgentHQ Desktop`
5. Click **Create**

**Download the JSON file** and save as:
```
backend/credentials.json
```

### For Mobile Application (Flutter)

#### Android

1. Create credentials: **OAuth client ID**
2. Select **Application type**: `Android`
3. Fill in:
   ```
   Name: AgentHQ Android
   Package name: com.agenthq.mobile
   SHA-1 certificate fingerprint: (see below)
   ```

**Get SHA-1 fingerprint:**
```bash
cd mobile/android
./gradlew signingReport

# Copy the SHA-1 from "debug" variant
# Example: A1:B2:C3:D4:E5:F6:...
```

#### iOS

1. Create credentials: **OAuth client ID**
2. Select **Application type**: `iOS`
3. Fill in:
   ```
   Name: AgentHQ iOS
   Bundle ID: com.agenthq.mobile
   ```

---

## Step 5: Configure Environment Variables

### Backend (.env)

Create `backend/.env`:

```bash
# Copy from template
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```bash
# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback
GOOGLE_SCOPES=https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/presentations,https://www.googleapis.com/auth/drive.file

# JWT Secret (generate random string)
SECRET_KEY=$(openssl rand -hex 32)
```

### Desktop (Tauri)

Create `desktop/.env`:

```bash
VITE_API_URL=http://localhost:8000/api/v1
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

### Mobile (Flutter)

Edit `mobile/lib/config/env.dart`:

```dart
class Environment {
  static const String apiUrl = 'http://localhost:8000/api/v1';
  static const String googleClientId = 'your-client-id.apps.googleusercontent.com';
  
  // Android
  static const String androidClientId = 'your-android-client-id.apps.googleusercontent.com';
  
  // iOS
  static const String iosClientId = 'your-ios-client-id.apps.googleusercontent.com';
}
```

---

## Step 6: Test OAuth Flow

### Start Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Test Authentication

1. **Get Auth URL**:
```bash
curl http://localhost:8000/api/v1/auth/google
```

Response:
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

2. **Visit URL** in browser and authorize

3. **Copy authorization code** from redirect URL

4. **Exchange for tokens**:
```bash
curl -X POST http://localhost:8000/api/v1/auth/callback \
  -H "Content-Type: application/json" \
  -d '{"code": "authorization-code-here"}'
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## Step 7: Verify API Access

Test authenticated endpoint:

```bash
curl http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer your-access-token"
```

---

## Troubleshooting

### Error: "redirect_uri_mismatch"

**Solution**: Ensure redirect URI in code matches Google Console:
- Console: `http://localhost:8000/api/v1/auth/callback`
- Code: Same URL

### Error: "invalid_client"

**Solution**: Check `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`

### Error: "access_denied"

**Solution**: 
1. Check OAuth consent screen is configured
2. Add test users (for External user type)
3. Verify scopes are added

### Error: "insufficient_scopes"

**Solution**: Add required scopes in OAuth consent screen

---

## Production Deployment

### Domain Configuration

1. Add production domain to **Authorized domains**:
   ```
   agenthq.com
   api.agenthq.com
   ```

2. Update **Redirect URIs**:
   ```
   https://api.agenthq.com/api/v1/auth/callback
   ```

3. Update environment variables:
   ```bash
   GOOGLE_REDIRECT_URI=https://api.agenthq.com/api/v1/auth/callback
   ```

### OAuth Consent Screen Verification

For production with external users, submit for verification:

1. Go to **OAuth consent screen**
2. Click **Publish App**
3. Submit for verification (required for >100 users)

**Verification includes**:
- App review by Google
- Privacy policy URL
- Terms of service URL
- Homepage URL
- Scope justification

---

## Security Best Practices

1. **Never commit credentials**:
   ```bash
   # Already in .gitignore
   .env
   credentials.json
   ```

2. **Rotate secrets regularly**:
   - Regenerate `SECRET_KEY` monthly
   - Rotate OAuth credentials if compromised

3. **Use HTTPS in production**:
   - All redirect URIs must use HTTPS
   - Except `localhost` for development

4. **Implement rate limiting**:
   - Prevent brute force attacks
   - Already configured in backend

5. **Monitor OAuth usage**:
   - Check Google Cloud Console quotas
   - Set up alerts for unusual activity

---

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Google Workspace APIs](https://developers.google.com/workspace)
- [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)

---

**Need help?** Open an issue on GitHub or contact support.
