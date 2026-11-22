import sys

from .bootstrap import run
from .secrets import ConfigError, normalise_environment


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("backup", "restore"):
        from .ops.__main__ import main as ops_main
        ops_main(sys.argv[1:])
        return
    normalise_environment()  # blank settings (as Docker Compose passes them) mean "not set"
    try:
        run()
    except ConfigError as e:
        sys.exit(f"Configuration error: {e}")


if __name__ == "__main__":
    main()
