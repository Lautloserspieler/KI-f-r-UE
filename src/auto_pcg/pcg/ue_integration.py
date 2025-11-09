"""Helpers to import Auto-PCG Graphs into Unreal via command line."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def run_unreal_import(
    editor_exe: Path,
    uproject: Path,
    graph_path: Path,
    script_path: Path,
    asset_folder: str,
    asset_name: Optional[str] = None,
    map_path: Optional[str] = None,
    spawn: bool = True,
) -> None:
    def _fmt_path(value: Path) -> str:
        # Unreal tolerates forward slashes even on Windows and they avoid \u escaping issues
        return str(Path(value).resolve()).replace("\\", "/")

    script_args = [
        f"--graph-json={_fmt_path(graph_path)}",
        f"--asset-folder={asset_folder}",
    ]
    if asset_name:
        script_args.append(f"--asset-name={asset_name}")
    if spawn:
        script_args.append("--spawn")
    if map_path:
        script_args.append(f"--spawn-map={map_path}")
    cmd = [
        str(editor_exe),
        str(uproject),
        "-run=pythonscript",
        f"-script={_fmt_path(script_path)}",
        "--",
        *script_args,
    ]
    subprocess.run(cmd, check=True)
