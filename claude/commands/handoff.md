# Handoff

The one context-saving habit: run `/handoff` before a mid-task `/clear` or
before quitting for the day. Breadcrumbs digest every cleared session
automatically, but the digest keeps only each turn's closing message — this
command puts the full picture into that slot deliberately.

Write a concise handoff for the next agent. Include:

- Current goal and status.
- Important decisions already made.
- Files changed or likely next.
- Exact verification commands already run.
- The next concrete action.

Save it under `~/dotfiles/claude/handoffs/` (create the directory if needed)
with an ISO-timestamp filename, then print the handoff body in full.

Printing it matters: the printed body becomes this turn's closing message, so
the breadcrumb digest keeps it verbatim and a same-terminal `/clear` restart
is pointed at it automatically. The saved file covers what breadcrumbs cannot:
quitting instead of clearing, resuming days later, or a different terminal.
