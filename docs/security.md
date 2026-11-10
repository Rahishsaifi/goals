# Security

## Implemented

- Argon2id password hashing
- Normalized unique emails
- Invitation-only account creation for tenant users
- Email verification gate before login
- HttpOnly session cookie + readable CSRF cookie + CSRF header check on mutating requests
- Login rate limiting
- Generic invalid-credential responses
- Server-side RBAC (`platform_admin`, `tenant_admin`, `recruiter`, `viewer`)
- Tenant-scoped repository queries
- PostgreSQL RLS policies scaffolded on `tenants` and `tenant_memberships` (owner bypass remains for local app role unless `FORCE` is enabled later)
- Private local blob uploads via short-lived SAS to Azurite
- No password hashes in API responses

## Not claimed

- Production malware scanning
- Managed identity against Azure
- Hardened public HTTPS deployment
- Full FORCE RLS with a non-owner DB role
