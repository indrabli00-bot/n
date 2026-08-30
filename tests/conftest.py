"""Test harness: make the repository root importable for standalone pytest runs.

Without this, `pytest tests/test_phase2.py` cannot import product modules
(whop_webhook_phase2, database, ...) because pytest inserts tests/ — not the
repository root — into sys.path when tests/ has no __init__.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
