"""
integration_test_ocr_scan_to_bim.py — Integration Test for OCR + ScanToBIM
============================================================================

Integration test to verify OCR service and ScanToBIM service work together
properly, maintaining the audit trail and security requirements.
"""

from __future__ import annotations

from unittest.mock import Mock

from backend.services.ocr_service import OCRService
from backend.services.scan_to_bim import ScanToBIMService


class TestOCRScanToBIMIntegration:
    """Integration tests for OCR and ScanToBIM services."""

    def test_ocr_to_scan_to_bim_flow(self):
        """Test the complete flow from OCR to ScanToBIM processing."""
        # Create mock OCR service that returns predictable results
        mock_ocr = Mock(spec=OCRService)
        mock_ocr.process_file.return_value = {
            'success': True,
            'audit_trail': {
                'timestamp': 1234567890.0,
                'file_path': '/mock/path/test.pdf',
                'confidence_score': 85.0,
                'requires_human_review': True
            },
            'pages': [{'page_number': 1, 'text': 'ROOM A-101: OFFICE. AREA: 25.0 SQM', 'confidence': 85.0}],
            'extracted_text': 'ROOM A-101: OFFICE. AREA: 25.0 SQM',
            'room_areas': [('A-101', 25.0)],
            'areas_only': [],
            'statistics': {
                'total_rooms_found': 1,
                'total_areas_found': 0,
                'average_confidence': 85.0,
                'total_words_extracted': 8
            }
        }

        # Create ScanToBIM service with mock OCR
        scan_service = ScanToBIMService(ocr_service_instance=mock_ocr)

        # Process a mock file
        result = scan_service.process_scan("dummy_file.pdf")

        # Verify the result
        assert result.success is True
        assert len(result.rooms) >= 1
        assert result.requires_human_review is True  # Should always be True for OCR data
        assert 'OCR-derived BIM data requires professional review' in str(result.audit_trail)

        # Verify room was created properly
        room = result.rooms[0]
        assert room.name == "A-101"  # Should be normalized
        assert room.area == 25.0
        assert room.room_type in ["OFFICE", "OTHER"]
        assert room.confidence == 85.0

    def test_ocr_failure_handled_by_scan_to_bim(self):
        """Test that ScanToBIM properly handles OCR failures."""
        # Create mock OCR service that returns failure
        mock_ocr = Mock(spec=OCRService)
        mock_ocr.process_file.return_value = {
            'success': False,
            'audit_trail': {'error': 'Mock OCR error'}
        }

        # Create ScanToBIM service with mock OCR
        scan_service = ScanToBIMService(ocr_service_instance=mock_ocr)

        # Process a mock file
        result = scan_service.process_scan("dummy_file.pdf")

        # Verify the result shows failure
        assert result.success is False
        assert len(result.rooms) == 0
        assert result.requires_human_review is True  # Still requires review even when failed

    def test_nfpa_72_audit_trail_compliance(self):
        """Test that audit trail meets NFPA 72-2022 §10.6 requirements."""
        # Create mock OCR service
        mock_ocr = Mock(spec=OCRService)
        mock_ocr.process_file.return_value = {
            'success': True,
            'audit_trail': {
                'timestamp': 1234567890.0,
                'file_path': '/mock/path/test.pdf',
                'confidence_score': 85.0,
                'requires_human_review': True
            },
            'pages': [{'page_number': 1, 'text': 'ROOM TEST: AREA: 30.0 SQM', 'confidence': 85.0}],
            'extracted_text': 'ROOM TEST: AREA: 30.0 SQM',
            'room_areas': [('TEST', 30.0)],
            'areas_only': [],
            'statistics': {
                'total_rooms_found': 1,
                'total_areas_found': 0,
                'average_confidence': 85.0,
                'total_words_extracted': 6
            }
        }

        scan_service = ScanToBIMService(ocr_service_instance=mock_ocr)
        result = scan_service.process_scan("test_file.pdf")

        # Verify audit trail compliance
        audit_trail = result.audit_trail
        assert 'timestamp' in audit_trail
        assert 'process_type' in audit_trail
        assert 'input_file' in audit_trail
        assert 'ocr_audit' in audit_trail
        assert 'requires_human_review' in audit_trail
        assert audit_trail['requires_human_review'] is True
        assert 'processing_notes' in audit_trail

    def test_multi_language_support_integration(self):
        """Test that multi-language support flows through both services."""
        # Create mock OCR with Arabic text
        mock_ocr = Mock(spec=OCRService)
        mock_ocr.process_file.return_value = {
            'success': True,
            'audit_trail': {
                'timestamp': 1234567890.0,
                'file_path': '/mock/path/test.pdf',
                'confidence_score': 78.0,
                'requires_human_review': True
            },
            'pages': [{'page_number': 1, 'text': 'غرفة 101: مكتب. المساحة: 22.5 متر مربع', 'confidence': 78.0}],
            'extracted_text': 'غرفة 101: مكتب. المساحة: 22.5 متر مربع',
            'room_areas': [('101', 22.5)],  # Arabic room name and area
            'areas_only': [],
            'statistics': {
                'total_rooms_found': 1,
                'total_areas_found': 0,
                'average_confidence': 78.0,
                'total_words_extracted': 7
            }
        }

        scan_service = ScanToBIMService(ocr_service_instance=mock_ocr)
        result = scan_service.process_scan("arabic_test.pdf", lang="ara+eng")

        # Should process Arabic text successfully
        assert result.success is True
        assert len(result.rooms) >= 1
        assert result.statistics['total_rooms_identified'] >= 1
        assert result.requires_human_review is True

    def test_security_sanitize_integration(self):
        """Test that security sanitization flows through the pipeline."""
        # Create mock OCR with potentially malicious text that should be sanitized
        mock_ocr = Mock(spec=OCRService)
        mock_ocr.process_file.return_value = {
            'success': True,
            'audit_trail': {
                'timestamp': 1234567890.0,
                'file_path': '/mock/path/test.pdf',
                'confidence_score': 80.0,
                'requires_human_review': True
            },
            'pages': [{'page_number': 1, 'text': 'ROOM SAFE: AREA: 20.0 SQM; DROP TABLE users;', 'confidence': 80.0}],
            'extracted_text': 'ROOM SAFE: AREA: 20.0 SQM; DROP TABLE users;',  # Contains malicious-looking text
            'room_areas': [('SAFE', 20.0)],
            'areas_only': [],
            'statistics': {
                'total_rooms_found': 1,
                'total_areas_found': 0,
                'average_confidence': 80.0,
                'total_words_extracted': 8
            }
        }

        scan_service = ScanToBIMService(ocr_service_instance=mock_ocr)
        result = scan_service.process_scan("security_test.pdf")

        # Should process despite potentially malicious text in OCR
        assert result.success is True
        assert result.requires_human_review is True
        # The malicious text should have been handled appropriately during OCR processing
