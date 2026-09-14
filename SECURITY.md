# Security Policy

If you find a security vulnerability in this template, please **do not** open
a public issue.

Report it privately through GitHub: this repository's **Security** tab →
**Report a vulnerability**. That opens a private advisory visible only to
maintainers until a fix is ready.

## Scope

This is a backend template, not a hosted service, so there is no live
deployment to disclose against. Reports about the authentication, session,
or revocation logic in `apps/users` and `apps/realtime` — the parts of the
template most likely to have security-relevant bugs — are the most useful.

Issues that only reproduce with `DEBUG=True` or the insecure development
`SECRET_KEY` are expected: those are documented development-only defaults,
not vulnerabilities. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the
production hardening this template applies automatically when `DEBUG=False`.
