import sys
from pathlib import Path

# Make cli/ importable as 'tavernbench'
sys.path.insert(0, str(Path(__file__).parent.parent / "cli"))
