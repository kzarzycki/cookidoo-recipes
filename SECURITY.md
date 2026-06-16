# Security

This project uses a Cookidoo session owned by the operator. Cookidoo has no public API for these workflows, so the implementation uses browser-session cookies and internal endpoints that may change.

## Credential Handling

- The project does not store a Cookidoo password.
- `cookidoo login` reads the password interactively and stores only the resulting cookie jar.
- Cookie jars are written with `0600` permissions.
- Cookie files, browser exports, live request captures, and `work/` outputs are ignored by git.
- Write tools default to dry run and require a confirmation token for the exact reviewed payload.

## Reporting Issues

Open a private security advisory or contact the maintainer directly for:

- Credential leakage.
- Cookie permission bypasses.
- Unintended Cookidoo write operations.
- Logs or exceptions that expose tokens, cookies, passwords, or private recipe data.

Do not attach real cookies, passwords, browser exports, or live network captures to an issue.
