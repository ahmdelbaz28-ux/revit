"""FireAI Digital Twin Platform — Backend Package."""

try:
    with open("VERSION") as f:
        __version__ = f.read().strip()
except FileNotFoundError:
    __version__ = "0.0.0"
