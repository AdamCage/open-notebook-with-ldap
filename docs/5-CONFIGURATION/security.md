# Security Configuration

Protect your Open Notebook deployment with authentication, role-based access control, and production hardening.

---

## Authentication Modes

Open Notebook supports four authentication modes, configured via the `AUTH_MODE` environment variable:

| Mode | `AUTH_MODE` | User Accounts | RBAC | Data Isolation | Best For |
|------|-------------|---------------|------|----------------|----------|
| **Open** | `none` (default) | No | No | No | Local development, single user |
| **Shared Password** | `password` | No | No | No | Simple deployments with basic protection |
| **Local Accounts** | `local` | Yes | Yes | Yes | Multi-user teams without LDAP |
| **LDAP / Active Directory** | `ldap` | Yes (auto-created) | Yes | Yes | Enterprise environments |

!!! warning
    In `none` and `password` modes, **all role-based access controls are disabled**. Every user has full admin-level access. Use `local` or `ldap` mode for real multi-user security.

### Quick Start by Mode

**Open access (default):**
```bash
# No configuration needed -- this is the default
AUTH_MODE=none
```

**Shared password:**
```bash
AUTH_MODE=password
OPEN_NOTEBOOK_PASSWORD=your_secure_password
```

**Local accounts with RBAC:**
```bash
AUTH_MODE=local
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
JWT_SECRET=your-random-jwt-secret
```

**LDAP with RBAC:**
```bash
AUTH_MODE=ldap
ADMIN_USERNAME=admin
ENABLE_LDAP=true
JWT_SECRET=your-random-jwt-secret
# ... LDAP server settings (see LDAP section below)
```

### Mode Interactions

- `AUTH_MODE=local` and `AUTH_MODE=ldap` are **mutually exclusive** with `OPEN_NOTEBOOK_PASSWORD`. If `AUTH_MODE` is set to `local` or `ldap`, the shared password mechanism is ignored.
- When `AUTH_MODE=ldap`, users are automatically registered in the `app_user` table upon their first successful LDAP login.
- When `AUTH_MODE=local`, users self-register and must wait for an administrator to approve their account before gaining access.

---

## Role-Based Access Control (RBAC)

RBAC is active only in `local` and `ldap` modes. Three roles are available:

| Role | Scope | Capabilities |
|------|-------|-------------|
| **super_admin** | System-wide | Manage users (approve, deactivate, promote/demote), all admin capabilities |
| **admin** | System-wide (config only) | Configure AI models, credentials, settings, transformations |
| **user** | Own data only | Create and work within own notebooks, sources, notes, chat |

### Key Principles

- **Data isolation is absolute**: admins and super_admins **cannot** view, edit, or delete other users' notebooks, sources, notes, or chat sessions. Every record is scoped to its owner.
- **Admin panel access**: only `admin` and `super_admin` roles can access the Settings, Models, Credentials, and Transformations pages.
- **User management**: only `super_admin` can view the user list, approve registrations, and change user roles.

### Bootstrapping the Super Admin

The initial super administrator is created automatically on first API startup when `AUTH_MODE=local`:

```bash
ADMIN_USERNAME=admin        # Required: the super-admin username
ADMIN_PASSWORD=changeme     # Required for local mode: initial password
```

- If the user already exists, the startup process skips creation.
- For `AUTH_MODE=ldap`, only `ADMIN_USERNAME` is needed; the password comes from LDAP.
- Change the default password immediately after first login.

---

## User Registration and Approval

### Local Mode (`AUTH_MODE=local`)

1. A new user visits the login page and clicks **Register**
2. They fill in username, email, and password (min 6 characters)
3. The account is created with status `pending`
4. The user sees a "Your account is awaiting approval" page
5. A super admin navigates to **Admin > Users** and approves the account
6. The user can now log in normally

### LDAP Mode (`AUTH_MODE=ldap`)

1. A user logs in with their LDAP credentials
2. On first successful LDAP authentication, an `app_user` record is auto-created with status `active`
3. No manual approval is needed -- LDAP itself serves as the identity provider

### User Lifecycle

```
[Register/LDAP Login] → pending* → active → deactivated
                                      ↑          ↓
                                      └──────────┘ (re-activate)

* LDAP users skip the pending state
```

- **Deactivation**: a super admin can deactivate any user. The user's data is preserved but they cannot log in.
- **Re-activation**: a super admin can re-activate a deactivated user.
- **Self-service**: local users can change their own password and profile. LDAP users cannot (their identity is managed externally).

---

## JWT Secret Configuration

In `local` and `ldap` modes, session tokens are signed JWTs. The signing secret is resolved with the following priority:

| Priority | Variable | Notes |
|----------|----------|-------|
| 1 (highest) | `JWT_SECRET` | Dedicated secret for JWT signing |
| 2 | `LDAP_JWT_SECRET` | Legacy variable, still supported |
| 3 (fallback) | `OPEN_NOTEBOOK_ENCRYPTION_KEY` | Used if neither of the above is set |

**Production recommendation**: always set a dedicated `JWT_SECRET` that is different from your encryption key:

```bash
JWT_SECRET=$(openssl rand -base64 32)
```

- Tokens expire after **24 hours**; users must re-authenticate.
- The middleware performs a cached database check (60-second TTL) to verify the user is still `active` on each request.

---

## API Key Encryption

Open Notebook encrypts API keys stored in the database using Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).

### Configuration Methods

| Method | Documentation |
|--------|---------------|
| **Settings UI** | [API Configuration Guide](../3-USER-GUIDE/api-configuration.md) |
| **Environment Variables** | This page (below) |

### Setup

Set the encryption key to any secret string:

```bash
# .env or docker.env
OPEN_NOTEBOOK_ENCRYPTION_KEY=my-secret-passphrase
```

Any string works — it will be securely derived via SHA-256 internally. Use a strong passphrase for production deployments.

### Default Credentials

| Setting | Default | Security Level |
|---------|---------|----------------|
| Password | `open-notebook-change-me` | Development only |
| Encryption Key | **None** (must be configured) | Required for API key storage |

**The encryption key has no default.** You must set `OPEN_NOTEBOOK_ENCRYPTION_KEY` before using the API key configuration feature. Without it, encrypting/decrypting API keys will fail.

### Docker Secrets Support

Both settings support Docker secrets via `_FILE` suffix:

```yaml
environment:
  - OPEN_NOTEBOOK_PASSWORD_FILE=/run/secrets/app_password
  - OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE=/run/secrets/encryption_key
```

### Security Notes

| Scenario | Behavior |
|----------|----------|
| Key configured | API keys encrypted with your key |
| No key configured | Encryption/decryption will fail (key is required) |
| Key changed | Old encrypted keys become unreadable |
| Legacy data | Unencrypted keys still work (graceful fallback) |

### Key Management

- **Keep secret**: Never commit the encryption key to version control
- **Backup securely**: Store the key separately from database backups
- **No rotation yet**: Changing the key requires re-saving all API keys
- **Per-deployment**: Each instance should have its own encryption key

---

## When to Use Password Protection

### Use it for:
- Public cloud deployments (PikaPods, Railway, DigitalOcean)
- Shared network environments
- Any deployment accessible beyond localhost

### You can skip it for:
- Local development on your machine
- Private, isolated networks
- Single-user local setups

---

## Quick Setup

### Docker Deployment

```yaml
# docker-compose.yml
services:
  open_notebook:
    image: lfnovo/open_notebook:v1-latest-single
    pull_policy: always
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=your-secret-encryption-key
      - OPEN_NOTEBOOK_PASSWORD=your_secure_password
    # ... rest of config
```

Or using environment file:

```bash
# docker.env
OPEN_NOTEBOOK_ENCRYPTION_KEY=your-secret-encryption-key
OPEN_NOTEBOOK_PASSWORD=your_secure_password
```

> **Important**: The encryption key is **required** for credential storage. Without it, you cannot save AI provider credentials via the Settings UI. If you change or lose the encryption key, all stored credentials become unreadable.

### Development Setup

```bash
# .env
OPEN_NOTEBOOK_PASSWORD=your_secure_password
```

---

## Password Requirements

### Good Passwords

```bash
# Strong: 20+ characters, mixed case, numbers, symbols
OPEN_NOTEBOOK_PASSWORD=MySecure2024!Research#Tool
OPEN_NOTEBOOK_PASSWORD=Notebook$Dev$2024$Strong!

# Generated (recommended)
OPEN_NOTEBOOK_PASSWORD=$(openssl rand -base64 24)
```

### Bad Passwords

```bash
# DON'T use these
OPEN_NOTEBOOK_PASSWORD=password123
OPEN_NOTEBOOK_PASSWORD=opennotebook
OPEN_NOTEBOOK_PASSWORD=admin
```

---

## How It Works

### Frontend Protection

1. Login form appears on first visit
2. Password stored in browser session
3. Session persists until browser closes
4. Clear browser data to log out

### API Protection

All API endpoints require authentication:

```bash
# Authenticated request
curl -H "Authorization: Bearer your_password" \
  http://localhost:5055/api/notebooks

# Unauthenticated (will fail)
curl http://localhost:5055/api/notebooks
# Returns: {"detail": "Missing authorization header"}
```

### Unprotected Endpoints

These work without authentication:

- `/health` - System health check
- `/docs` - API documentation
- `/openapi.json` - OpenAPI spec

---

## API Authentication Examples

### curl

```bash
# List notebooks
curl -H "Authorization: Bearer your_password" \
  http://localhost:5055/api/notebooks

# Create notebook
curl -X POST \
  -H "Authorization: Bearer your_password" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Notebook", "description": "Research notes"}' \
  http://localhost:5055/api/notebooks

# Upload file
curl -X POST \
  -H "Authorization: Bearer your_password" \
  -F "file=@document.pdf" \
  http://localhost:5055/api/sources/upload
```

### Python

```python
import requests

class OpenNotebookClient:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {password}"}

    def get_notebooks(self):
        response = requests.get(
            f"{self.base_url}/api/notebooks",
            headers=self.headers
        )
        return response.json()

    def create_notebook(self, name: str, description: str = None):
        response = requests.post(
            f"{self.base_url}/api/notebooks",
            headers=self.headers,
            json={"name": name, "description": description}
        )
        return response.json()

# Usage
client = OpenNotebookClient("http://localhost:5055", "your_password")
notebooks = client.get_notebooks()
```

### JavaScript/TypeScript

```javascript
const API_URL = 'http://localhost:5055';
const PASSWORD = 'your_password';

async function getNotebooks() {
  const response = await fetch(`${API_URL}/api/notebooks`, {
    headers: {
      'Authorization': `Bearer ${PASSWORD}`
    }
  });
  return response.json();
}
```

---

## Production Hardening

### Docker Security

```yaml
services:
  open_notebook:
    image: lfnovo/open_notebook:v1-latest-single
    pull_policy: always
    ports:
      - "127.0.0.1:8502:8502"  # Bind to localhost only
    environment:
      - OPEN_NOTEBOOK_PASSWORD=your_secure_password
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.0"
    restart: always
```

### Firewall Configuration

```bash
# UFW (Ubuntu)
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8502/tcp   # Block direct access
sudo ufw deny 5055/tcp   # Block direct API access
sudo ufw enable

# iptables
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 8502 -j DROP
iptables -A INPUT -p tcp --dport 5055 -j DROP
```

### Reverse Proxy with SSL

See [Reverse Proxy Configuration](reverse-proxy.md) for complete nginx/Caddy/Traefik setup with HTTPS.

---

## Security Limitations

| Feature | `none` / `password` modes | `local` / `ldap` modes |
|---------|--------------------------|----------------------|
| Password transmission | Plain text (use HTTPS!) | Plain text (use HTTPS!) |
| Password storage | In memory / not applicable | Bcrypt hash in database |
| User management | None / single shared password | Per-user accounts with roles |
| Session tokens | None | JWT (24h expiry, DB-backed status check) |
| Data isolation | None | Owner-scoped (enforced at DB layer) |
| Rate limiting | None | None |
| Audit logging | None | None |

### Risk Mitigation

1. **Always use HTTPS** - Encrypt traffic with TLS
2. **Strong passwords** - 20+ characters, complex
3. **Network security** - Firewall, VPN for sensitive deployments
4. **Regular updates** - Keep containers and dependencies updated
5. **Monitoring** - Check logs for suspicious activity
6. **Backups** - Regular backups of data

---

## Enterprise Considerations

For deployments requiring advanced security:

| Need | Built-in | Additional Steps |
|------|----------|-----------------|
| Multi-user accounts | Yes (`local` or `ldap` mode) | -- |
| Role-based access | Yes (super_admin / admin / user) | -- |
| LDAP / Active Directory | Yes (`AUTH_MODE=ldap`) | Configure LDAP settings |
| Per-user data isolation | Yes (owner-scoped records) | -- |
| SSO/OAuth | Not built-in | Implement OAuth2/SAML proxy |
| Audit logging | Not built-in | Log aggregation service |
| Rate limiting | Not built-in | API gateway or nginx |
| Data encryption at rest | Not built-in | Encrypt volumes at rest |
| Network segmentation | Not built-in | Docker networks, VPC |

---

## Troubleshooting

### Password Not Working

```bash
# Check env var is set
docker exec open-notebook env | grep OPEN_NOTEBOOK_PASSWORD

# Check logs
docker logs open-notebook | grep -i auth

# Test API directly
curl -H "Authorization: Bearer your_password" \
  http://localhost:5055/health
```

### 401 Unauthorized Errors

```bash
# Check header format
curl -v -H "Authorization: Bearer your_password" \
  http://localhost:5055/api/notebooks

# Verify password matches
echo "Password length: $(echo -n $OPEN_NOTEBOOK_PASSWORD | wc -c)"
```

### Cannot Access After Setting Password

1. Clear browser cache and cookies
2. Try incognito/private mode
3. Check browser console for errors
4. Verify password is correct in environment

### Security Testing

```bash
# Without password (should fail)
curl http://localhost:5055/api/notebooks
# Expected: {"detail": "Missing authorization header"}

# With correct password (should succeed)
curl -H "Authorization: Bearer your_password" \
  http://localhost:5055/api/notebooks

# Health check (should work without password)
curl http://localhost:5055/health
```

---

## Reporting Security Issues

If you discover security vulnerabilities:

1. **Do NOT open public issues**
2. Contact maintainers directly
3. Provide detailed information
4. Allow time for fixes before disclosure

---

## LDAP Authentication

Open Notebook supports LDAP authentication (Active Directory, OpenLDAP, etc.) for enterprise environments. Set `AUTH_MODE=ldap` and `ENABLE_LDAP=true` to activate this mode. Users are auto-registered in the system on their first successful LDAP login.

### How It Works

1. User enters LDAP username and password on the login form
2. The API binds to the LDAP server with a service account (or anonymously)
3. Searches for the user by username attribute
4. Verifies the password by binding as the found user DN
5. Issues a JWT session token (valid for 24 hours)
6. Subsequent API requests use this JWT as a Bearer token

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_LDAP` | `false` | Enable LDAP authentication |
| `LDAP_SERVER_HOST` | `localhost` | LDAP server hostname or IP |
| `LDAP_SERVER_PORT` | `389` | LDAP server port (389 for LDAP, 636 for LDAPS) |
| `LDAP_USE_TLS` | `true` | Use TLS/SSL for LDAP connection |
| `LDAP_VALIDATE_CERT` | `true` | Validate TLS certificate |
| `LDAP_CA_CERT_FILE` | _(empty)_ | Path to CA certificate file |
| `LDAP_CIPHERS` | `ALL` | Allowed TLS ciphers |
| `LDAP_ATTRIBUTE_FOR_USERNAME` | `uid` | LDAP attribute for username lookup |
| `LDAP_ATTRIBUTE_FOR_MAIL` | `mail` | LDAP attribute for user email |
| `LDAP_APP_DN` | _(empty)_ | Service account DN for search (empty = anonymous bind) |
| `LDAP_APP_PASSWORD` | _(empty)_ | Service account password |
| `LDAP_SEARCH_BASE` | _(empty)_ | Base DN for user search |
| `LDAP_SEARCH_FILTERS` | _(empty)_ | Additional LDAP search filter (appended to username filter) |
| `LDAP_SERVER_LABEL` | `LDAP Server` | Display label for the LDAP server |
| `LDAP_JWT_SECRET` | _(falls back to `OPEN_NOTEBOOK_ENCRYPTION_KEY`)_ | Secret for signing LDAP session JWTs |

Docker secrets are supported for `LDAP_APP_PASSWORD` via the `LDAP_APP_PASSWORD_FILE` suffix.

### Example: Active Directory

```bash
ENABLE_LDAP=true
LDAP_SERVER_HOST=ad.company.com
LDAP_SERVER_PORT=636
LDAP_USE_TLS=true
LDAP_VALIDATE_CERT=true
LDAP_ATTRIBUTE_FOR_USERNAME=sAMAccountName
LDAP_ATTRIBUTE_FOR_MAIL=mail
LDAP_APP_DN=CN=svc-opennotebook,OU=Service Accounts,DC=company,DC=com
LDAP_APP_PASSWORD=service_account_password
LDAP_SEARCH_BASE=OU=Users,DC=company,DC=com
LDAP_SEARCH_FILTERS=(objectClass=person)
```

### Example: OpenLDAP

```bash
ENABLE_LDAP=true
LDAP_SERVER_HOST=ldap.example.org
LDAP_SERVER_PORT=389
LDAP_USE_TLS=false
LDAP_ATTRIBUTE_FOR_USERNAME=uid
LDAP_ATTRIBUTE_FOR_MAIL=mail
LDAP_APP_DN=cn=readonly,dc=example,dc=org
LDAP_APP_PASSWORD=readonly_password
LDAP_SEARCH_BASE=ou=people,dc=example,dc=org
```

### Docker Compose

```yaml
services:
  open_notebook:
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=your-secret-string
      - ENABLE_LDAP=true
      - LDAP_SERVER_HOST=ldap.example.com
      - LDAP_SERVER_PORT=636
      - LDAP_USE_TLS=true
      - LDAP_APP_DN=cn=admin,dc=example,dc=com
      - LDAP_APP_PASSWORD=admin_password
      - LDAP_SEARCH_BASE=ou=users,dc=example,dc=com
```

### Auth Mode Integration

When `AUTH_MODE=ldap`, the shared `OPEN_NOTEBOOK_PASSWORD` mechanism is disabled. All authentication goes through LDAP:

- The login page shows the LDAP login form
- Successful authentication issues a JWT session token
- The JWT is used as a Bearer token for all subsequent API requests
- RBAC and user management are fully active (see [RBAC](#role-based-access-control-rbac) above)
- The `ADMIN_USERNAME` env var designates which LDAP user becomes the super admin

### Security Considerations

- **TLS strongly recommended**: Always use `LDAP_USE_TLS=true` in production
- **Input escaping**: Usernames are escaped with `ldap3.escape_filter_chars` to prevent LDAP injection
- **Passwords never stored**: LDAP passwords are used only for bind verification; only a JWT is returned
- **Service account password**: Never exposed via the admin config API (masked in responses)
- **JWT secret**: Uses `LDAP_JWT_SECRET` if set, otherwise falls back to `OPEN_NOTEBOOK_ENCRYPTION_KEY`
- **Token expiry**: LDAP session tokens expire after 24 hours; users must re-authenticate

---

## Related

- **[Reverse Proxy](reverse-proxy.md)** - HTTPS and SSL setup
- **[Advanced Configuration](advanced.md)** - Ports, timeouts, and SSL settings
- **[Environment Reference](environment-reference.md)** - All configuration options
