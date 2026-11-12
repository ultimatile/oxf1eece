"""Interactive fuzzy search, delegated to fzf."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable


class FzfNotFoundError(RuntimeError):
    """fzf is not installed or not on PATH."""


def fzf_select(rows: Iterable[str], *, preview_field: int) -> list[str]:
    """Show tab-separated `rows` in fzf; return the rows the user picked (empty if aborted).

    Fields before `preview_field` (1-based) are shown and searched; that field is shown
    in the preview pane.
    """
    fzf = shutil.which("fzf")
    if fzf is None:
        raise FzfNotFoundError(
            "fzf not found on PATH; install it or use `hexsieve list | <filter>`"
        )
    cmd = [
        fzf,
        "--multi",
        "--delimiter=\t",
        f"--with-nth=1..{preview_field - 1}",
        f"--preview=printf '%s\\n' {{{preview_field}}}",
        "--preview-window=down,3,wrap",
    ]
    proc = subprocess.run(
        cmd, input="".join(rows), stdout=subprocess.PIPE, encoding="utf-8", check=False
    )
    # fzf exits 1 when nothing matched and 130 when the user aborted; both mean "no pick".
    if proc.returncode not in (0, 1, 130):
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return proc.stdout.splitlines(keepends=True)
