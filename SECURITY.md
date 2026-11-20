# Security Policy

<!-- Created by Redfox using Claude -->

## Supported versions

Only the latest release of AI Command Centre receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository
(<https://github.com/RafaDevpt/ai-command-centre/security/advisories/new>).

Include the version, how it is deployed (Compose, reverse proxy, Tailscale…),
the steps to reproduce and the expected impact. Every report receives an answer
within 7 days; fixes are released as a new patch version and credited in the
CHANGELOG unless the reporter prefers otherwise.

## Scope

In scope: authentication and sessions, CSRF, authorisation between projects
and conversations, the approval flow, container isolation, the Codex bridge and
the Claude Code runner, and anything that could leak credentials or secrets.

Out of scope: deployments exposed directly to the Internet against the
documentation, and vulnerabilities in Ollama, Codex or Claude Code themselves
(report those to their vendors).

The security design is described in [docs/SECURITY.md](docs/SECURITY.md).
