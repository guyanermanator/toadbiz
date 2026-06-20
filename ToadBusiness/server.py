import sys
from pathlib import Path

from root_bootstrap import bootstrap_root

bootstrap_root(Path(__file__).resolve().parent)

from game.app_server import main


if __name__ == "__main__":
    main()
