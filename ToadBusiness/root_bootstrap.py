import sys
from pathlib import Path


def bootstrap_root(start_dir: Path) -> Path:
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / "game" / "map_world.py").is_file():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)
            return candidate
    raise RuntimeError(
        f"Could not locate project root from {start_dir} (missing game/map_world.py)"
    )
