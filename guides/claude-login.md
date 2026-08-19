# Sign in to Claude Code with UT Claude EDU

Claude Code is Anthropic's coding agent, and `claude` is the CLI command used
in this course. claude.ai is the account and workspace you use to sign in. UT
Claude EDU is centrally funded and available to every student.

1. Go to `https://claude.ai/`.
2. Sign in with `yourEID@eid.utexas.edu`.
3. Continue through Microsoft login, UT authentication, and Duo MFA.
4. Confirm that you entered the UT Austin workspace, not a personal account.
5. In a terminal, run:

   ```bash
   claude auth login
   claude auth status
   ```

`self-check` reads `claude auth status`; it does not make a paid model call.
