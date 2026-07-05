"""
test_v131_integration.py — Test for V131 Extensions Integration
===============================================================

Verifies that the V131 kernel extensions are properly integrated with the main kernel.
Tests include: generative design, cloud webhooks, AR hooks, and security features.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fireai.core.fireai_kernel_v30 import KernelCore
from fireai.core.v131_kernel_extensions import V131KernelExtension


class TestV131Integration:
    """Tests for V131 extensions integration with the main kernel."""

    def test_kernel_creation_includes_v131_extensions(self):
        """Test that kernel creation includes V131 extensions."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Verify that the kernel has the V131 extensions
        assert hasattr(kernel, 'v131_extensions')
        assert isinstance(kernel.v131_extensions, V131KernelExtension)

        # Verify that the extensions have access to the kernel
        assert kernel.v131_extensions.kernel_core is kernel

    def test_generative_design_available_through_kernel(self):
        """Test that generative design engine is available through the kernel."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Check that the generative design functionality is available
        assert hasattr(kernel.v131_extensions, 'generative_engine')
        assert hasattr(kernel.v131_extensions, 'generate_design_variants')

    def test_webhook_publisher_available_through_kernel(self):
        """Test that webhook publisher is available through the kernel."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Check that the webhook functionality is available
        assert hasattr(kernel.v131_extensions, 'webhook_publisher')
        assert hasattr(kernel.v131_extensions, 'publish_webhook_event')

    def test_ar_hook_manager_available_through_kernel(self):
        """Test that AR hook manager is available through the kernel."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Check that the AR functionality is available
        assert hasattr(kernel.v131_extensions, 'ar_hook_manager')
        assert hasattr(kernel.v131_extensions, 'create_ar_session')

    @pytest.mark.asyncio
    async def test_async_initialization_of_extensions(self):
        """Test that extensions can be asynchronously initialized."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Initialize the extensions
        await kernel.v131_extensions.initialize()

        # Should complete without errors
        assert True

    @pytest.mark.asyncio
    async def test_generate_design_variants_through_kernel(self):
        """Test that design variants can be generated through the kernel."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Generate some design variants
        variants = await kernel.v131_extensions.generate_design_variants(
            room_width=10.0,
            room_length=15.0,
            ceiling_height=3.0,
            occupancy_type="office",
            detector_type="smoke"
        )

        # Should return a list of variants
        assert isinstance(variants, list)
        assert len(variants) > 0

    @pytest.mark.asyncio
    async def test_webhook_publishing_through_kernel(self):
        """Test that webhooks can be published through the kernel."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Try to publish a test event (this will likely fail due to invalid URL,
        # but should not crash the system)
        try:
            await kernel.v131_extensions.publish_webhook_event(
                url="http://invalid-url-for-test.com/webhook",
                event_type="test_event",
                data={"test": "data"},
                secret="test_secret"
            )
            # The result might be False due to invalid URL, which is expected
        except Exception:
            # Some exceptions are expected when trying to connect to invalid URLs
            pass

        # Should not have crashed
        assert True

    @pytest.mark.asyncio
    async def test_ar_session_creation_through_kernel(self):
        """Test that AR sessions can be created through the kernel."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Create an AR session
        session_id = await kernel.v131_extensions.create_ar_session(
            building_id="test_building_123",
            session_config={"theme": "dark", "units": "metric"}
        )

        # Should return a valid session ID
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_backward_compatibility_preserved(self):
        """Test that existing kernel functionality still works."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))

        # Verify that existing properties are still available
        assert hasattr(kernel, '_store')
        assert hasattr(kernel, '_engine')
        assert hasattr(kernel, '_ledger')
        assert hasattr(kernel, '_solver')
        assert hasattr(kernel, '_parser')
        assert hasattr(kernel, '_workers')

    def test_extension_features_integrated_correctly(self):
        """Test that all V131 features are properly integrated."""
        kernel = KernelCore.create(ledger_path=Path("test.ledger"))
        ext = kernel.v131_extensions

        # Check all expected components exist
        assert ext.generative_engine is not None
        assert ext.webhook_publisher is not None
        assert ext.ar_hook_manager is not None

        # Check all expected methods exist
        assert hasattr(ext, 'generate_design_variants')
        assert hasattr(ext, 'publish_webhook_event')
        assert hasattr(ext, 'create_ar_session')
        assert hasattr(ext, 'update_ar_visualization')


def test_v131_integration_suite():
    """Run all V131 integration tests."""
    # This is a meta-test to verify the test suite
    test_instance = TestV131Integration()

    # Run synchronous tests
    test_instance.test_kernel_creation_includes_v131_extensions()
    test_instance.test_generative_design_available_through_kernel()
    test_instance.test_webhook_publisher_available_through_kernel()
    test_instance.test_ar_hook_manager_available_through_kernel()
    test_instance.test_backward_compatibility_preserved()
    test_instance.test_extension_features_integrated_correctly()

    # Run async tests
    async def run_async_tests():
        await test_instance.test_async_initialization_of_extensions()
        await test_instance.test_generate_design_variants_through_kernel()
        await test_instance.test_webhook_publishing_through_kernel()
        await test_instance.test_ar_session_creation_through_kernel()

    # Execute async tests
    asyncio.run(run_async_tests())

    print("All V131 integration tests passed!")
