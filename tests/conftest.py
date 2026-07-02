"""Register the integration as an importable package without HA installed.

The parser/alerts modules are HA-free by design; this shim lets tests import
them via ``at_rail_closures.parser`` etc. so their relative imports work,
without executing ``__init__.py`` (which needs Home Assistant).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_PKG_DIR = Path(__file__).parents[1] / "custom_components" / "at_rail_closures"

package = types.ModuleType("at_rail_closures")
package.__path__ = [str(_PKG_DIR)]
sys.modules.setdefault("at_rail_closures", package)
