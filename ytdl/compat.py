from __future__ import unicode_literals
from __future__ import division
import ctypes
import datetime
import itertools
import platform
import re
import sys

compat_str, compat_basestring, compat_chr = (str, (str, bytes), chr)


try:
    import collections.abc as compat_collections_abc
except ImportError:
    import collections as compat_collections_abc


try:
    import urllib.error as compat_urllib_error
except ImportError:  # Python 2
    import urllib2 as compat_urllib_error


try:
    from contextlib import suppress as compat_contextlib_suppress
except ImportError:
    class compat_contextlib_suppress(object):
        _exceptions = None

        def __init__(self, *exceptions):
            super(compat_contextlib_suppress, self).__init__()
            # TODO: [Base]ExceptionGroup (3.12+)
            self._exceptions = exceptions

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return exc_type is not None and issubclass(exc_type, self._exceptions or tuple())


# compat_map/filter() returning an iterator, supposedly the
# same versioning as for zip below
try:
    from future_builtins import map as compat_map
except ImportError:
    try:
        from itertools import imap as compat_map
    except ImportError:
        compat_map = map

try:
    from future_builtins import filter as compat_filter
except ImportError:
    try:
        from itertools import ifilter as compat_filter
    except ImportError:
        compat_filter = filter

try:
    from future_builtins import zip as compat_zip
except ImportError:  # not 2.6+ or is 3.x
    try:
        from itertools import izip as compat_zip  # < 2.5 or 3.x
    except ImportError:
        compat_zip = zip


# method renamed between Py2/3
try:
    from itertools import zip_longest as compat_itertools_zip_longest
except ImportError:
    from itertools import izip_longest as compat_itertools_zip_longest


# new class in collections
try:
    from collections import ChainMap as compat_collections_chain_map
    # Py3.3's ChainMap is deficient
    if sys.version_info < (3, 4):
        raise ImportError
except ImportError:
    # Py <= 3.3
    class compat_collections_chain_map(compat_collections_abc.MutableMapping):

        maps = [{}]

        def __init__(self, *maps):
            self.maps = list(maps) or [{}]

        def __getitem__(self, k):
            for m in self.maps:
                if k in m:
                    return m[k]
            raise KeyError(k)

        def __setitem__(self, k, v):
            self.maps[0].__setitem__(k, v)
            return

        def __contains__(self, k):
            return any((k in m) for m in self.maps)

        def __delitem(self, k):
            if k in self.maps[0]:
                del self.maps[0][k]
                return
            raise KeyError(k)

        def __delitem__(self, k):
            self.__delitem(k)

        def __iter__(self):
            return itertools.chain(*reversed(self.maps))

        def __len__(self):
            return len(iter(self))

        # to match Py3, don't del directly
        def pop(self, k, *args):
            if self.__contains__(k):
                off = self.__getitem__(k)
                self.__delitem(k)
                return off
            elif len(args) > 0:
                return args[0]
            raise KeyError(k)

        def new_child(self, m=None, **kwargs):
            m = m or {}
            m.update(kwargs)
            return compat_collections_chain_map(m, *self.maps)

        @property
        def parents(self):
            return compat_collections_chain_map(*(self.maps[1:]))


# Pythons disagree on the type of a pattern (RegexObject, _sre.SRE_Pattern, Pattern, ...?)
compat_re_Pattern = type(re.compile(''))
# and on the type of a match
compat_re_Match = type(re.match('a', 'a'))


if platform.python_implementation() == 'PyPy' and sys.pypy_version_info < (5, 4, 0):
    # PyPy2 prior to version 5.4.0 expects byte strings as Windows function
    # names, see the original PyPy issue [1] and the youtube-dl one [2].
    # 1. https://bitbucket.org/pypy/pypy/issues/2360/windows-ctypescdll-typeerror-function-name
    # 2. https://github.com/ytdl-org/youtube-dl/pull/4392
    def compat_ctypes_WINFUNCTYPE(*args, **kwargs):
        real = ctypes.WINFUNCTYPE(*args, **kwargs)

        def resf(tpl, *args, **kwargs):
            funcname, dll = tpl
            return real((str(funcname), dll), *args, **kwargs)

        return resf
else:
    def compat_ctypes_WINFUNCTYPE(*args, **kwargs):
        return ctypes.WINFUNCTYPE(*args, **kwargs)


# compat_datetime_timedelta_total_seconds
try:
    compat_datetime_timedelta_total_seconds = datetime.timedelta.total_seconds
except AttributeError:
    # Py 2.6
    def compat_datetime_timedelta_total_seconds(td):
        return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6

# optional decompression packages
# PyPi brotli package implements 'br' Content-Encoding
try:
    import brotli as compat_brotli
except ImportError:
    compat_brotli = None
# PyPi ncompress package implements 'compress' Content-Encoding
try:
    import ncompress as compat_ncompress
except ImportError:
    compat_ncompress = None

