"""adapted from pipgrip: https://github.com/ddelange/pipgrip"""
import sys

PY36 = sys.version_info >= (3, 6)

if not PY36:
    from collections import OrderedDict
else:
    OrderedDict = dict
