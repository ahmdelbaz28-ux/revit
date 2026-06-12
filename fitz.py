from pymupdf import *
import pymupdf as _pymupdf

# Re-export all symbols from pymupdf for backward compatibility
# PyMuPDF 1.23+ renamed the 'fitz' module to 'pymupdf'
# This compat module allows 'import fitz' to still work

# Provide fitz.Document for callers who use fitz.Document directly
Document = _pymupdf.Document

# Make sure fitz.open works exactly like pymupdf.open
open = _pymupdf.open
