from pathlib import Path
import runpy

PARENT_SERVER = Path(__file__).resolve().parent.parent / "server.py"
runpy.run_path(str(PARENT_SERVER), run_name="__main__")
