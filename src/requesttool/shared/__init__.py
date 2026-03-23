"""Shared, UI-free runtime modules reused by desktop and web stacks."""

from requesttool.shared.assertions import AssertionEngine
from requesttool.shared.reporting import ReportGenerator

__all__ = ["AssertionEngine", "ReportGenerator"]
