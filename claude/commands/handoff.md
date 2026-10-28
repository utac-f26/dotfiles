# Handoff

Run `/handoff` when you want to select the context a future session should
have. Breadcrumbs digest sessions automatically after `/clear` or quitting;
this command puts a deliberate summary into the final report they preserve.

Write a concise handoff for the next agent. Include:

- Current goal and status.
- Important decisions already made.
- Files changed or likely next.
- Exact verification commands already run.
- The next concrete action.

Save it under `~/dotfiles/claude/handoffs/` (create the directory if needed)
with an ISO-timestamp filename, then print the handoff body in full.

Printing it matters: the printed body becomes this turn's closing message, so
the breadcrumb digest keeps it verbatim. A `/clear` or recent startup can point
at that digest; begin your next message with `resume` to continue it. Startup
pointers cover only the last 24 hours. For a later resumption, name the saved
handoff explicitly; handoffs remain until you remove them.
