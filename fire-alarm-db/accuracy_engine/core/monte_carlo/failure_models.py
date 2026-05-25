import random

DETECTOR_FAILURE_RATE = 0.03
CABLE_FAILURE_RATE = 0.02
POWER_FAILURE_RATE = 0.01
EXIT_BLOCKAGE_RATE = 0.05


def detector_failed() -> bool:
    return random.random() < DETECTOR_FAILURE_RATE


def cable_failed() -> bool:
    return random.random() < CABLE_FAILURE_RATE


def power_failed() -> bool:
    return random.random() < POWER_FAILURE_RATE


def exit_blocked() -> bool:
    return random.random() < EXIT_BLOCKAGE_RATE