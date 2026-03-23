"""Entry point - auto-detects if terminal or GUI."""
import sys


def main():
    args = sys.argv[1:]
    # If --gui flag or no args in a graphical environment, launch GUI
    if "--gui" in args:
        from cursfig.gui import run_gui
        run_gui()
    elif not args or args == ["--help"]:
        # Default: CLI (shows help)
        from cursfig.cli import main as cli_main
        cli_main()
    else:
        from cursfig.cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
