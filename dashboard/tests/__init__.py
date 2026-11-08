"""Support repository-root discovery and the existing test fixture imports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
