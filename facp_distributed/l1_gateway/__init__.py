"""L1 Gateway Layer for Distributed FACP System"""
# V138 FIX (MEDIUM-3): request_normalizer.py was imported here but never
# existed in the repository, breaking the entire import chain and causing
# collection errors in facp_distributed/tests/test_distributed_system.py.
# Make the import optional so the rest of the package can still load.
from .client_interface import ClientInterface
from .gateway import L1Gateway

try:
    from .request_normalizer import RequestNormalizer
except ImportError:
    # request_normalizer.py is referenced but not yet implemented.
    # Define a stub so downstream `from .request_normalizer import X` works.
    class RequestNormalizer:  # type: ignore[no-redef]
        """Stub — request_normalizer.py is not yet implemented."""
        def __init__(self, *args, **kwargs):
            raise NotImplementedError(
                "request_normalizer.py is not yet implemented."
            )

__all__ = ['ClientInterface', 'L1Gateway', 'RequestNormalizer']
