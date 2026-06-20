import sys
from pathlib import Path

BOOTSTRAP_DIR = Path(__file__).resolve().parent.parent
if str(BOOTSTRAP_DIR) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP_DIR))

from root_bootstrap import bootstrap_root

bootstrap_root(Path(__file__).resolve().parent)

from game.app_server import main


if __name__ == "__main__":
    main()
