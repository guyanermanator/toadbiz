import sys
from pathlib import Path

def _find_root(start_dir: Path) -> Path:
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / "game" / "map_world.py").is_file():
            return candidate
    return start_dir


ROOT_DIR = _find_root(Path(__file__).resolve().parent)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from game.app_server import main


if __name__ == "__main__":
    main()
