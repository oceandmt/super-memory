# Security Policy

## Reporting vulnerabilities

Please do not report security vulnerabilities through public GitHub issues.

Report privately to the maintainers using the repository's configured private vulnerability reporting channel, or another maintainer-approved private contact path.

## Sensitive data policy

Super Memory is memory infrastructure. Treat the following as sensitive and do not commit them:

- SQLite memory databases containing real user or agent memory
- API keys, OAuth tokens, SSH keys, cookies, and session files
- Private OpenClaw config or workspace paths
- Personal chat transcripts or private documents
- Production deployment hostnames, IPs, usernames, or key paths

## Supported versions

Until the project reaches a stable release, security fixes target the latest `main` branch.
