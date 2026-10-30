"""toylib: a hand-written fixture library with planted ground truth.

Trusted code (written by us, not by a model), so its tests may run with the
local backend as well as in Docker (CLAUDE.md §2.5).
"""

from toylib.core import LIMIT, STRICT_DEFAULT, at_least, clamp, safe_div

__version__ = "0.1.0"
__all__ = ["LIMIT", "STRICT_DEFAULT", "at_least", "clamp", "safe_div"]
