"""A backend writing a TextMate grammar, packaged for Visual Studio Code.

See `generator` for the design.
"""

from .generator import TextMateGenerator

__all__ = ["TextMateGenerator"]
