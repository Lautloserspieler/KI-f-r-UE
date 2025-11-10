"""Allows `python -m auto_pcg.gui`."""

from .control_panel import launch_control_panel


def main() -> None:
    launch_control_panel()


if __name__ == "__main__":
    main()
