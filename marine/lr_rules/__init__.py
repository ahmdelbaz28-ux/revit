"""marine/lr_rules — Lloyd's Register Rules for Fire Protection."""
from marine.lr_rules.fire_protection import (
    validate_detector_response_time,
    validate_fire_main_redundancy,
    validate_loop_capacity,
)

__all__ = [
    "validate_detector_response_time", "validate_fire_main_redundancy",
    "validate_loop_capacity",
]
