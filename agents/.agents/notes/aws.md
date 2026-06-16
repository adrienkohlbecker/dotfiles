# AWS auth

The operator's real AWS account authenticates via `[profile default]` → `~/.local/bin/aws-credential-process`: a long-term IAM key plus a TOTP pulled from 1Password (`op item get --otp`) → `sts get-session-token` → a 12h STS session that aws-cli caches.

**MFA TOTP collision.** AWS rejects reusing the same 30s TOTP code across `GetSessionToken` calls. When the cached 12h session expires, a *burst* of concurrent/rapid commands each re-runs the credential process inside one TOTP window and all but one fail with `MultiFactorAuthentication failed with invalid MFA one time pass code`.

**Apply:** mint ONE session, then reuse its temp creds.
- Run a single `aws sts get-caller-identity` first to warm the cache (wait/retry if it errors), then run the rest sequentially; or capture the credential-process JSON and export `AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN` for the batch.
- The Go SDK (tofu's AWS provider) re-runs the credential process per `tofu` invocation, so back-to-back `plan` then `apply` can collide — space them ~35s (one fresh TOTP window).
- Exporting the real-account `AWS_*` session creds globally breaks the MinIO backend (it needs `[profile minio]`) — scope them to the batch, don't leak them into the whole shell.
