# Sign in to Codex with your UT ChatGPT account

Codex is OpenAI's coding agent, and `codex` is the CLI command used in this
course. ChatGPT is the account and workspace you use to sign in. UT provides
ChatGPT Edu to every student at no cost.

1. Go to `https://chatgpt.com/`.
2. Sign in with `yourEID@eid.utexas.edu`.
3. Continue through Microsoft login, UT authentication, and Duo MFA.
4. Confirm the account shows UT Austin.
5. In a terminal, run:

   ```bash
   codex login
   codex login status
   ```

`self-check` uses `codex login status`; it does not make a paid model call.
