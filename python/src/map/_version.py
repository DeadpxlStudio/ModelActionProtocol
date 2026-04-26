"""Single source of version truth.

`__version__` is the implementation version (SemVer). `SPEC_VERSION` is the
MAP wire-format spec this implementation conforms to. They are deliberately
decoupled — bugfix releases can iterate the implementation without changing
the spec, and a new spec version forces a major implementation bump.
"""

__version__ = "0.1.0"
SPEC_VERSION = "0.1"
