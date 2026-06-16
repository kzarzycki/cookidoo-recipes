---
description: Log in to Cookidoo locally
allowed-tools: Bash
disable-model-invocation: true
---

Run the plugin login script in the local terminal:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/cookidoo-login
```

Do not ask the user to provide a Cookidoo password in chat. If the command reports that interactive login needs a terminal, show the exact terminal command from the script output and stop.
