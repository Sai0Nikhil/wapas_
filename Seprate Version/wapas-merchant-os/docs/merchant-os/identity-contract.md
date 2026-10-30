# Merchant identity and authorization — implemented behavior

Updated: 2026-10-29. This page describes current code and covered tests; it is not a production security certification.

## Identity records

- `User` is the person-level login identity. Passwords are stored as salted scrypt hashes.
- `MerchantMembership` binds a user to a merchant and store with role `OWNER` or `STAFF`. If more than one active membership exists, login requires a membership choice from the list returned after password verification.
- `AuthSession` stores a hash of a random bearer token and binds it to one membership and expiry. The browser receives the session value in an HttpOnly cookie.
- The CSRF cookie is paired with a server-validated session-bound value. Console writes require the CSRF header and same-origin checks; logout also verifies the CSRF pair.

## Tenant and role behavior

- Middleware resolves `merchant_id`, `store_id`, user, and role from the authenticated membership. Request bodies do not choose the tenant. Domain and ORM queries scope tenant-bearing rows; services also include store predicates where required.
- Public storefront routes resolve a store by slug. Customer order status additionally requires the order token. Public routes do not return the merchant console or Khata data.
- Owners can use the merchant console, including Khata and Sound Mode.
- Staff access is allowed for catalogue, stock, Counter bills, order routes, and read-only Sarkar asks. Staff cannot access Khata, Sound Mode, or confirm a Sarkar stock receipt.
- Recovery console APIs are owner-only under the current role boundary. Existing provider callbacks and public checkout routes remain available for their payment lifecycle.

## Bootstrap and runtime modes

- `WAPAS_ENV` defaults to `production`; `development` must be selected explicitly for the local HTTP walkthrough. Development mode does not bypass sign-in. Do not expose a development instance publicly; no remote-development security review has been performed.
- The first owner is provisioned by `python -m app.auth_cli create-owner` against the explicitly selected database. The password is entered interactively; no default owner password is seeded.
- The `test` middleware exception is limited to FastAPI's `testclient` with no forwarded-proxy headers. Test writes also require the test console header. Fixtures must use temporary databases.
- The old `ADMIN_TOKEN` setting remains readable for compatibility but does not authenticate console requests.

## Verification covered

Tests exercise login, membership selection, session expiry/revocation, CSRF and same-origin failures, role access, tenant scoping, and unauthorized requests. They do not establish a production deployment review, password recovery process, operational account lifecycle, external audit export, or security certification. See [security review](security-review.md) and [verification matrix](verification-matrix.md).
