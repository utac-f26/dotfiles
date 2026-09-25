# Windows setup

Use WSL first if your laptop allows it. WSL gives you a Linux environment that
matches the department-host workflow closely enough that one set of commands and
one `~/dotfiles` checkout can serve both places. Generate the graded
`.setup-receipt.json` from WSL or your CS department Linux home: `./setup` does
not run under MSYS2 or Git Bash, and says so if you try.

## Optional native Windows shell

This is a manual MSYS2 recipe for daily work on the Windows side. It does not
install an agent, configure its login, install SOPS, or produce a graded setup
receipt. Keep using WSL or the department host for the graded path.

1. [Install MSYS2](https://www.msys2.org/) in its default `C:\msys64`
   directory and open **MSYS2 UCRT64**. Run `pacman -Syu`; if the update closes
   the shell, reopen UCRT64 and run it again. The [MSYS2 environment guide](https://www.msys2.org/docs/environments/)
   identifies `MSYSTEM=UCRT64` and `/ucrt64/bin:/usr/bin` as its tool path.
2. In that UCRT64 shell, install the course-useful packages. The UCRT64 package
   names follow the [MSYS2 package index](https://packages.msys2.org/):

   ```bash
   pacman -S --needed git tmux curl \
       mingw-w64-ucrt-x86_64-github-cli \
       mingw-w64-ucrt-x86_64-ripgrep \
       mingw-w64-ucrt-x86_64-jq \
       mingw-w64-ucrt-x86_64-uv \
       mingw-w64-ucrt-x86_64-nodejs \
       mingw-w64-ucrt-x86_64-fd \
       mingw-w64-ucrt-x86_64-fzf \
       mingw-w64-ucrt-x86_64-age
   ```

3. Set `db_home: /c/Users/%U` in `/etc/nsswitch.conf` (the Windows file is
   `C:\msys64\etc\nsswitch.conf`). Open a new shell and check that
   `cygpath -w "$HOME"` names your Windows user profile. Keep one home; do not
   create another under the MSYS2 installation tree.
4. For real symlinks, turn on Developer Mode (Settings > System > For
   developers), then run `setx MSYS winsymlinks:nativestrict`. Open a new shell
   before testing symlinks.
5. Point Claude Code's Bash tool at this same runtime with
   `setx CLAUDE_CODE_GIT_BASH_PATH 'C:\msys64\usr\bin\bash.exe'`. Install and sign
   in to your chosen agents separately. Package installation alone does not
   provide them.

### Make native tools available to agent shells

An interactive UCRT64 login shell gets its path from MSYS2. A desktop-launched
agent and its nested `bash -c` processes may skip that login setup. Create
`$HOME/.bashenv` if absent, or merge this block into it if it exists. If you
already use `BASH_ENV` with another file, merge the block there and keep its
native Windows path. This file runs through
`BASH_ENV` in non-interactive Bash; it keeps the inherited path and restores
Windows variables that native children need. The temp path is your actual
Windows profile's `AppData\Local\Temp`, not an MSYS-only `/tmp` value.

```bash
# File named by BASH_ENV — source only from the MSYS2 bash in this recipe.
export MSYSTEM=UCRT64
if [ -x /usr/bin/cygpath ]; then
    PATH=${PATH:-/usr/bin}
    case $PATH in
        *';'*) PATH=$(/usr/bin/cygpath -up "$PATH") ;;
    esac
    USERPROFILE=$(/usr/bin/cygpath -w "$HOME")
    export USERPROFILE
    if [ -n "${APPDATA:-}" ]; then export APPDATA
    else export APPDATA="$USERPROFILE\\AppData\\Roaming"; fi
    if [ -n "${LOCALAPPDATA:-}" ]; then export LOCALAPPDATA
    else export LOCALAPPDATA="$USERPROFILE\\AppData\\Local"; fi
    export TEMP="$LOCALAPPDATA\\Temp" TMP="$LOCALAPPDATA\\Temp"
    case ${PATHEXT:-} in
        *.EXE*|*.exe*) export PATHEXT ;;
        *) export PATHEXT='.COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC' ;;
    esac
    case :$PATH: in *:/usr/bin:*) ;; *) PATH="/usr/bin:$PATH" ;; esac
    case :$PATH: in *:/ucrt64/bin:*) ;; *) PATH="/ucrt64/bin:$PATH" ;; esac
    native_home=$(/usr/bin/cygpath -u "$USERPROFILE")
    case :$PATH: in
        *:"$native_home/.local/bin":*) ;;
        *) PATH="$native_home/.local/bin:$PATH" ;;
    esac
    unset native_home
    export PATH
fi
```

In the Windows **Environment Variables** UI, edit your **user** variables:

- Add `C:\msys64\ucrt64\bin` to the existing user `Path`, ahead of
  `WindowsApps` if present. Do not replace the existing entries. This makes
  `uv` and the UCRT64 tools visible before Bash starts.
- Set `MSYSTEM` to `UCRT64`. Set `BASH_ENV` to the native path of the file you
  just created if it is not already set. Run `cygpath -m "$HOME/.bashenv"` in
  UCRT64 to get that value, for example `C:/Users/Ada/.bashenv`. Use a native
  path for the Windows setting and an MSYS path when sourcing inside Bash.

These user-environment values reach only newly started processes. Restart the
agent as well as its terminal after changing them. You do not need to replace
an existing `claude/settings.json` or any other JSON settings file.

In a fresh interactive UCRT64 shell, source the file and check the basics:

```bash
. "$(cygpath -u "$BASH_ENV")"
printf '%s\n' "$MSYSTEM" "$USERPROFILE" "$TEMP"
command -v uv node rg fd fzf age
touch t && ln -s t l && test -L l && rm t l
```

Then paste this probe into the agent's **Bash tool**, not an interactive
terminal. It checks one more nested Bash and a native, uv-managed CPython
child. The first run may download Python. A successful run prints `UCRT64`,
paths to each tool, and `native Python paths writable`:

```bash
bash -c '
    test "$MSYSTEM" = UCRT64 || exit 1
    printf "%s\n" "$MSYSTEM"
    for tool in uv node rg fd fzf age; do command -v "$tool" || exit 1; done
    uv run --no-project --managed-python --python 3.11 python - <<"PY"
import os
import shutil
import tempfile
from pathlib import Path

home = Path.home()
temp = Path(os.environ["TEMP"])
assert home == Path(os.environ["USERPROFILE"])
assert temp == Path(os.environ["TMP"])
for tool in ("uv", "node", "rg", "fd", "fzf", "age"):
    assert shutil.which(tool), tool
with tempfile.TemporaryDirectory(dir=home), tempfile.TemporaryDirectory(dir=temp):
    print("native Python paths writable")
PY
'
```

The Python probe deliberately requests a uv-managed interpreter, so it never
depends on `/usr/bin/python`. If the agent cannot find `uv`, check the new
process's Windows user `Path` first; if nested Bash loses home or temp, check
`BASH_ENV` and the six exported native variables above. The [MSYS2 path guide](https://www.msys2.org/docs/filesystem-paths/)
explains why Windows path values and Bash source paths need different forms.
