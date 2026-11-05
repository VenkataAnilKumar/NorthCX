import sys

from .bootstrap import run
from .secrets import ConfigError, normalise_environment


def main() -> None:
    normalise_environment()  # blank settings (as Docker Compose passes them) mean "not set"
    try:
        run()
    except ConfigError as e:
        sys.exit(f"Configuration error: {e}")


if __name__ == "__main__":
    main()
