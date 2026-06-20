from pathlib import Path
import runpy

PARENT_SERVER = Path(__file__).resolve().parent.parent / "server.py"
if not PARENT_SERVER.is_file():
    raise RuntimeError(f"Expected parent server entrypoint at {PARENT_SERVER}")
runpy.run_path(str(PARENT_SERVER), run_name="__main__")
