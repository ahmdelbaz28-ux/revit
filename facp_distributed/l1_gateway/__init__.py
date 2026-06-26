"""L1 Gateway Layer for Distributed FACP System"""
# V139 FIX: RequestNormalizer is defined in client_interface.py (not a
# separate request_normalizer.py file). Import from the correct module.
# This eliminates the stub class I added in V138 — no more NotImplementedError.
from .client_interface import ClientInterface, RequestNormalizer
from .gateway import L1Gateway

__all__ = ['ClientInterface', 'L1Gateway', 'RequestNormalizer']
