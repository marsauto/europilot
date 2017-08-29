"""
europilot.compat
~~~~~~~~~~~~~~~~

This module handles compatibility issues between Python 2 and 3.

"""

import sys

_ver = sys.version_info
is_py2 = _ver[0] == 2
is_py3 = _ver[0] == 3

if is_py2:
    from Queue import Queue
elif is_py3:
    from queue import Queue
