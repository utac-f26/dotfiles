# Windows setup

Use WSL first if your laptop allows it. WSL gives you a Linux environment that
matches the department-host workflow closely enough that one set of commands and
one `~/dotfiles` checkout can serve both places. Generate the graded
`.setup-receipt.json` from WSL or your CS department Linux home: `./setup` does
not run under MSYS2 or Git Bash, and says so if you try.

## MSYS2 as your native daily shell

If your files and tools must live on the Windows side, MSYS2 gives you bash +
git + pacman on native Windows. It is solid only when configured exactly right,
and every step below fails silently when skipped. The Windows setup reference
(deck 902) walks through the same recipe with the reasoning.

1. Install MSYS2 (msys2.org) and always open the "MSYS2 UCRT64" shell — not
   MSYS, not MINGW64, and never Git Bash. In that shell run `pacman -Syu` to
   update the base system; rerun it if it closes the shell partway.
2. Install the toolchain with pacman (Git Bash has no pacman and cannot do
   this):
   `pacman -S --needed git tmux curl mingw-w64-ucrt-x86_64-github-cli
   mingw-w64-ucrt-x86_64-ripgrep mingw-w64-ucrt-x86_64-jq`
3. One home for every tool: set `db_home: /c/Users/%U` in `/etc/nsswitch.conf`
   (the file is `C:\msys64\etc\nsswitch.conf`; edit it with any editor and
   open a new shell) so `$HOME = $USERPROFILE`. Do not create a second
   dotfiles home under the MSYS2 installation tree.
4. Real symlinks: turn on Developer Mode (Settings > System > For developers),
   then `setx MSYS winsymlinks:nativestrict`. Without both, `ln -s` silently
   copies the file and returns 0.
5. Keep agents on the same runtime:
   `setx CLAUDE_CODE_GIT_BASH_PATH C:\msys64\usr\bin\bash.exe` so Claude Code's
   Bash tool runs MSYS2's bash. Its default is Git Bash — a second msys runtime
   that silently drops `TMP`/`TEMP` for native tools spawned from scripts.

Verify in a freshly opened shell: `echo $MSYSTEM` prints `UCRT64`,
`cygpath -w ~` prints `C:\Users\<you>`, and
`touch t && ln -s t l && test -L l` succeeds. `setx` values reach only process
trees started after they were set, so a stale terminal fails checks a fresh one
passes.

Even with MSYS2 as your daily shell, the graded receipt still comes from WSL or
the department host.
