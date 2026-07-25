"""Research-grade adaptive finite-element building blocks.

Nothing in this package changes an ordinary solver default. Capabilities are
promoted only after their Task evidence has passed the repository review gates.
"""

from .global_two_level_r5 import (
    localize_global_two_level_correction,
    run_target_global_two_level_r5,
)

__all__ = [
    "localize_global_two_level_correction",
    "run_target_global_two_level_r5",
]
