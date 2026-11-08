"""Version of the plugin under test (read from the source, without importing the package)."""
import re
from pathlib import Path

_INIT = Path(__file__).resolve().parents[1] / "plugins/vmodel/validator/vmodel_validator/__init__.py"
VERSION = re.search(r'VERSION = "([^"]+)"', _INIT.read_text(encoding="utf-8")).group(1)
