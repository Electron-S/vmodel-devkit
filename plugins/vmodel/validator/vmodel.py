"""VModel DevKit validator entry point.

Run as:  python vmodel.py <command> [...]
The bin/vmodel wrapper locates a Python 3.11+ interpreter and calls this file.
"""
import os
import sys

# Never write __pycache__ into the (pinned, hashed) validator directory, and never *read* bytecode from it either:
# a hand-made .pyc next to a core module would otherwise change behaviour without changing the core hash.
sys.dont_write_bytecode = True
import tempfile  # noqa: E402

sys.pycache_prefix = os.path.join(tempfile.gettempdir(), "vmodel-no-pyc-%d" % os.getpid())

if sys.version_info < (3, 11):
    sys.stderr.write("vmodel: Python 3.11 or newer is required (found %d.%d)\n" % sys.version_info[:2])
    sys.exit(2)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vmodel_validator.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
