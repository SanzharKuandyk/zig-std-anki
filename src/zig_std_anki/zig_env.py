from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .models import ZigEnv


_FIELD_RE = re.compile(r'\.(zig_exe|std_dir|version)\s*=\s*"([^"]+)"')


def read_zig_env(zig_exe: str = "zig") -> ZigEnv:
    proc = subprocess.run(
        [zig_exe, "env"],
        check=True,
        capture_output=True,
        text=True,
    )
    fields = dict(_FIELD_RE.findall(proc.stdout))
    missing = {"zig_exe", "std_dir", "version"} - set(fields)
    if missing:
        raise RuntimeError(f"zig env missing fields: {', '.join(sorted(missing))}")
    return ZigEnv(
        zig_exe=fields["zig_exe"],
        std_dir=Path(fields["std_dir"]),
        version=fields["version"],
    )
