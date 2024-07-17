from __future__ import unicode_literals
import calendar
import datetime
import json
import locale
import re
import socket
import sys
import traceback

from ytdl.compat import (
    compat_collections_abc,
    compat_basestring,
    compat_contextlib_suppress,
    compat_ctypes_WINFUNCTYPE,
    compat_datetime_timedelta_total_seconds,
    compat_str,
    compat_urllib_error,
)


NO_DEFAULT = object()
IDENTITY = lambda x: x

DATE_FORMATS = (
    '%d %B %Y',
    '%d %b %Y',
    '%B %d %Y',
    '%B %dst %Y',
    '%B %dnd %Y',
    '%B %drd %Y',
    '%B %dth %Y',
    '%b %d %Y',
    '%b %dst %Y',
    '%b %dnd %Y',
    '%b %drd %Y',
    '%b %dth %Y',
    '%b %dst %Y %I:%M',
    '%b %dnd %Y %I:%M',
    '%b %drd %Y %I:%M',
    '%b %dth %Y %I:%M',
    '%Y %m %d',
    '%Y-%m-%d',
    '%Y.%m.%d.',
    '%Y/%m/%d',
    '%Y/%m/%d %H:%M',
    '%Y/%m/%d %H:%M:%S',
    '%Y%m%d%H%M',
    '%Y%m%d%H%M%S',
    '%Y%m%d',
    '%Y-%m-%d %H:%M',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d %H:%M:%S:%f',
    '%d.%m.%Y %H:%M',
    '%d.%m.%Y %H.%M',
    '%Y-%m-%dT%H:%M:%SZ',
    '%Y-%m-%dT%H:%M:%S.%fZ',
    '%Y-%m-%dT%H:%M:%S.%f0Z',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%dT%H:%M:%S.%f',
    '%Y-%m-%dT%H:%M',
    '%b %d %Y at %H:%M',
    '%b %d %Y at %H:%M:%S',
    '%B %d %Y at %H:%M',
    '%B %d %Y at %H:%M:%S',
    '%H:%M %d-%b-%Y',
)


DATE_FORMATS_MONTH_FIRST = list(DATE_FORMATS)
DATE_FORMATS_MONTH_FIRST.extend([
    '%m-%d-%Y',
    '%m.%d.%Y',
    '%m/%d/%Y',
    '%m/%d/%y',
    '%m/%d/%Y %H:%M:%S',
])


def preferredencoding():
    """Get preferred encoding.

    Returns the best encoding scheme for the system, based on
    locale.getpreferredencoding() and some further tweaks.
    """
    try:
        pref = locale.getpreferredencoding()
        'TEST'.encode(pref)
    except Exception:
        pref = 'UTF-8'

    return pref


def bug_reports_message(before=';'):
    if ytdl_is_updateable():
        update_cmd = 'type  youtube-dl -U  to update'
    else:
        update_cmd = 'see  https://github.com/ytdl-org/youtube-dl/#user-content-installation  on how to update'

    msg = (
        'please report this issue on https://github.com/ytdl-org/youtube-dl/issues ,'
        ' using the appropriate issue template.'
        ' Make sure you are using the latest version; %s.'
        ' Be sure to call youtube-dl with the --verbose option and include the complete output.'
    ) % update_cmd

    before = (before or '').rstrip()
    if not before or before.endswith(('.', '!', '?')):
        msg = msg[0].title() + msg[1:]

    return (before + ' ' if before else '') + msg


class YoutubeDLError(Exception):
    """Base exception for YoutubeDL errors."""
    pass


class ExtractorError(YoutubeDLError):
    """Error during info extraction."""

    def __init__(self, msg, tb=None, expected=False, cause=None, video_id=None):
        """ tb, if given, is the original traceback (so that it can be printed out).
        If expected is set, this is a normal error message and most likely not a bug in youtube-dl.
        """
        self.orig_msg = msg
        if sys.exc_info()[0] in (compat_urllib_error.URLError, socket.timeout, UnavailableVideoError):
            expected = True
        if video_id is not None:
            msg = video_id + ': ' + msg
        if cause:
            msg += ' (caused by %r)' % cause
        if not expected:
            msg += bug_reports_message()
        super(ExtractorError, self).__init__(msg)

        self.traceback = tb
        self.exc_info = sys.exc_info()  # preserve original exception
        self.cause = cause
        self.video_id = video_id

    def format_traceback(self):
        if self.traceback is None:
            return None
        return ''.join(traceback.format_tb(self.traceback))


class UnsupportedError(ExtractorError):
    def __init__(self, url):
        super(UnsupportedError, self).__init__(
            'Unsupported URL: %s' % url, expected=True)
        self.url = url


class RegexNotFoundError(ExtractorError):
    """Error when a regex didn't match"""
    pass


class GeoRestrictedError(ExtractorError):
    """Geographic restriction Error exception.

    This exception may be thrown when a video is not available from your
    geographic location due to geographic restrictions imposed by a website.
    """
    def __init__(self, msg, countries=None):
        super(GeoRestrictedError, self).__init__(msg, expected=True)
        self.msg = msg
        self.countries = countries


class DownloadError(YoutubeDLError):
    """Download Error exception.

    This exception may be thrown by FileDownloader objects if they are not
    configured to continue on errors. They will contain the appropriate
    error message.
    """

    def __init__(self, msg, exc_info=None):
        """ exc_info, if given, is the original exception that caused the trouble (as returned by sys.exc_info()). """
        super(DownloadError, self).__init__(msg)
        self.exc_info = exc_info


class SameFileError(YoutubeDLError):
    """Same File exception.

    This exception will be thrown by FileDownloader objects if they detect
    multiple files would have to be downloaded to the same file on disk.
    """
    pass


class PostProcessingError(YoutubeDLError):
    """Post Processing exception.

    This exception may be raised by PostProcessor's .run() method to
    indicate an error in the postprocessing task.
    """

    def __init__(self, msg):
        super(PostProcessingError, self).__init__(msg)
        self.msg = msg


class MaxDownloadsReached(YoutubeDLError):
    """ --max-downloads limit has been reached. """
    pass


class UnavailableVideoError(YoutubeDLError):
    """Unavailable Format exception.

    This exception will be thrown when a video is requested
    in a format that is not available for that video.
    """
    pass


def extract_timezone(date_str):
    m = re.search(
        r'''(?x)
            ^.{8,}?                                              # >=8 char non-TZ prefix, if present
            (?P<tz>Z|                                            # just the UTC Z, or
                (?:(?<=.\b\d{4}|\b\d{2}:\d\d)|                   # preceded by 4 digits or hh:mm or
                   (?<!.\b[a-zA-Z]{3}|[a-zA-Z]{4}|..\b\d\d))     # not preceded by 3 alpha word or >= 4 alpha or 2 digits
                   [ ]?                                          # optional space
                (?P<sign>\+|-)                                   # +/-
                (?P<hours>[0-9]{2}):?(?P<minutes>[0-9]{2})       # hh[:]mm
            $)
        ''', date_str)
    if not m:
        m = re.search(r'\d{1,2}:\d{1,2}(?:\.\d+)?(?P<tz>\s*[A-Z]+)$', date_str)
        timezone = TIMEZONE_NAMES.get(m and m.group('tz').strip())
        if timezone is not None:
            date_str = date_str[:-len(m.group('tz'))]
        timezone = datetime.timedelta(hours=timezone or 0)
    else:
        date_str = date_str[:-len(m.group('tz'))]
        if not m.group('sign'):
            timezone = datetime.timedelta()
        else:
            sign = 1 if m.group('sign') == '+' else -1
            timezone = datetime.timedelta(
                hours=sign * int(m.group('hours')),
                minutes=sign * int(m.group('minutes')))
    return timezone, date_str


def date_formats(day_first=True):
    return DATE_FORMATS_DAY_FIRST if day_first else DATE_FORMATS_MONTH_FIRST


def unified_timestamp(date_str, day_first=True):
    if date_str is None:
        return None

    date_str = re.sub(r'\s+', ' ', re.sub(
        r'(?i)[,|]|(mon|tues?|wed(nes)?|thu(rs)?|fri|sat(ur)?)(day)?', '', date_str))

    pm_delta = 12 if re.search(r'(?i)PM', date_str) else 0
    timezone, date_str = extract_timezone(date_str)

    # Remove AM/PM + timezone
    date_str = re.sub(r'(?i)\s*(?:AM|PM)(?:\s+[A-Z]+)?', '', date_str)

    # Remove unrecognized timezones from ISO 8601 alike timestamps
    m = re.search(r'\d{1,2}:\d{1,2}(?:\.\d+)?(?P<tz>\s*[A-Z]+)$', date_str)
    if m:
        date_str = date_str[:-len(m.group('tz'))]

    # Python only supports microseconds, so remove nanoseconds
    m = re.search(r'^([0-9]{4,}-[0-9]{1,2}-[0-9]{1,2}T[0-9]{1,2}:[0-9]{1,2}:[0-9]{1,2}\.[0-9]{6})[0-9]+$', date_str)
    if m:
        date_str = m.group(1)

    for expression in date_formats(day_first):
        with compat_contextlib_suppress(ValueError):
            dt = datetime.datetime.strptime(date_str, expression) - timezone + datetime.timedelta(hours=pm_delta)
            return calendar.timegm(dt.timetuple())
    timetuple = email.utils.parsedate_tz(date_str)
    if timetuple:
        return calendar.timegm(timetuple) + pm_delta * 3600 - compat_datetime_timedelta_total_seconds(timezone)


def _windows_write_string(s, out):
    """ Returns True if the string was written using special methods,
    False if it has yet to be written out."""
    # Adapted from http://stackoverflow.com/a/3259271/35070

    import ctypes
    import ctypes.wintypes

    WIN_OUTPUT_IDS = {
        1: -11,
        2: -12,
    }

    try:
        fileno = out.fileno()
    except AttributeError:
        # If the output stream doesn't have a fileno, it's virtual
        return False
    except io.UnsupportedOperation:
        # Some strange Windows pseudo files?
        return False
    if fileno not in WIN_OUTPUT_IDS:
        return False

    GetStdHandle = compat_ctypes_WINFUNCTYPE(
        ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD)(
        ('GetStdHandle', ctypes.windll.kernel32))
    h = GetStdHandle(WIN_OUTPUT_IDS[fileno])

    WriteConsoleW = compat_ctypes_WINFUNCTYPE(
        ctypes.wintypes.BOOL, ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR,
        ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.wintypes.DWORD),
        ctypes.wintypes.LPVOID)(('WriteConsoleW', ctypes.windll.kernel32))
    written = ctypes.wintypes.DWORD(0)

    GetFileType = compat_ctypes_WINFUNCTYPE(ctypes.wintypes.DWORD, ctypes.wintypes.DWORD)(('GetFileType', ctypes.windll.kernel32))
    FILE_TYPE_CHAR = 0x0002
    FILE_TYPE_REMOTE = 0x8000
    GetConsoleMode = compat_ctypes_WINFUNCTYPE(
        ctypes.wintypes.BOOL, ctypes.wintypes.HANDLE,
        ctypes.POINTER(ctypes.wintypes.DWORD))(
        ('GetConsoleMode', ctypes.windll.kernel32))
    INVALID_HANDLE_VALUE = ctypes.wintypes.DWORD(-1).value

    def not_a_console(handle):
        if handle == INVALID_HANDLE_VALUE or handle is None:
            return True
        return ((GetFileType(handle) & ~FILE_TYPE_REMOTE) != FILE_TYPE_CHAR
                or GetConsoleMode(handle, ctypes.byref(ctypes.wintypes.DWORD())) == 0)

    if not_a_console(h):
        return False

    def next_nonbmp_pos(s):
        try:
            return next(i for i, c in enumerate(s) if ord(c) > 0xffff)
        except StopIteration:
            return len(s)

    while s:
        count = min(next_nonbmp_pos(s), 1024)

        ret = WriteConsoleW(
            h, s, count if count else 2, ctypes.byref(written), None)
        if ret == 0:
            raise OSError('Failed to write string')
        if not count:  # We just wrote a non-BMP character
            assert written.value == 2
            s = s[1:]
        else:
            assert written.value > 0
            s = s[written.value:]
    return True


def write_string(s, out=None, encoding=None):
    if out is None:
        out = sys.stderr
    assert isinstance(s, compat_str)

    if sys.platform == 'win32' and encoding is None and hasattr(out, 'fileno'):
        if _windows_write_string(s, out):
            return

    if ('b' in getattr(out, 'mode', '')
            or sys.version_info[0] < 3):  # Python 2 lies about mode of sys.stderr
        byt = s.encode(encoding or preferredencoding(), 'ignore')
        out.write(byt)
    elif hasattr(out, 'buffer'):
        enc = encoding or getattr(out, 'encoding', None) or preferredencoding()
        byt = s.encode(enc, 'ignore')
        out.buffer.write(byt)
    else:
        out.write(s)
    out.flush()


def remove_quotes(s):
    if s is None or len(s) < 2:
        return s
    for quote in ('"', "'", ):
        if s[0] == quote and s[-1] == quote:
            return s[1:-1]
    return s


def variadic(x, allowed_types=NO_DEFAULT):
    if isinstance(allowed_types, compat_collections_abc.Iterable):
        allowed_types = tuple(allowed_types)
    return x if is_iterable_like(x, blocked_types=allowed_types) else (x,)


def try_call(*funcs, **kwargs):

    # parameter defaults
    expected_type = kwargs.get('expected_type')
    fargs = kwargs.get('args', [])
    fkwargs = kwargs.get('kwargs', {})

    for f in funcs:
        try:
            val = f(*fargs, **fkwargs)
        except (AttributeError, KeyError, TypeError, IndexError, ZeroDivisionError):
            pass
        else:
            if expected_type is None or isinstance(val, expected_type):
                return val


def js_to_json(code, *args, **kwargs):
    # vars is a dict of (var, val) pairs to substitute
    vars = args[0] if len(args) > 0 else kwargs.get('vars', {})
    strict = kwargs.get('strict', False)

    STRING_QUOTES = '\'"`'
    STRING_RE = '|'.join(r'{0}(?:\\.|[^\\{0}])*{0}'.format(q) for q in STRING_QUOTES)
    COMMENT_RE = r'/\*(?:(?!\*/).)*?\*/|//[^\n]*\n'
    SKIP_RE = r'\s*(?:{comment})?\s*'.format(comment=COMMENT_RE)
    INTEGER_TABLE = (
        (r'(?s)^(0[xX][0-9a-fA-F]+){skip}:?$'.format(skip=SKIP_RE), 16),
        (r'(?s)^(0+[0-7]+){skip}:?$'.format(skip=SKIP_RE), 8),
        (r'(?s)^(\d+){skip}:?$'.format(skip=SKIP_RE), 10),
    )
    # compat candidate
    JSONDecodeError = json.JSONDecodeError if 'JSONDecodeError' in dir(json) else ValueError

    def process_escape(match):
        JSON_PASSTHROUGH_ESCAPES = r'"\bfnrtu'
        escape = match.group(1) or match.group(2)

        return ('\\' + escape if escape in JSON_PASSTHROUGH_ESCAPES
                else '\\u00' if escape == 'x'
                else '' if escape == '\n'
                else escape)

    def template_substitute(match):
        evaluated = js_to_json(match.group(1), vars, strict=strict)
        if evaluated[0] == '"':
            return json.loads(evaluated)
        return evaluated

    def fix_kv(m):
        v = m.group(0)
        if v in ('true', 'false', 'null'):
            return v
        elif v in ('undefined', 'void 0'):
            return 'null'
        elif v.startswith('/*') or v.startswith('//') or v == ',':
            return ''

        if v[0] in STRING_QUOTES:
            v = re.sub(r'(?s)\${([^}]+)}', template_substitute, v[1:-1]) if v[0] == '`' else v[1:-1]
            escaped = re.sub(r'(?s)(")|\\(.)', process_escape, v)
            return '"{0}"'.format(escaped)

        inv = IDENTITY
        im = re.split(r'^!+', v)
        if len(im) > 1 and not im[-1].endswith(':'):
            if (len(v) - len(im[1])) % 2 == 1:
                inv = lambda x: 'true' if x == 0 else 'false'
            else:
                inv = lambda x: 'false' if x == 0 else 'true'
        if not any(x for x in im):
            return
        v = im[-1]

        for regex, base in INTEGER_TABLE:
            im = re.match(regex, v)
            if im:
                i = int(im.group(1), base)
                return ('"%s":' if v.endswith(':') else '%s') % inv(i)

        if v in vars:
            try:
                if not strict:
                    json.loads(vars[v])
            except JSONDecodeError:
                return inv(json.dumps(vars[v]))
            else:
                return inv(vars[v])

        if not strict:
            v = try_call(inv, args=(v,), default=v)
            if v in ('true', 'false'):
                return v
            return '"{0}"'.format(v)

        raise ValueError('Unknown value: ' + v)

    def create_map(mobj):
        return json.dumps(dict(json.loads(js_to_json(mobj.group(1) or '[]', vars=vars))))

    code = re.sub(r'new Map\((\[.*?\])?\)', create_map, code)
    if not strict:
        code = re.sub(r'new Date\((".+")\)', r'\g<1>', code)
        code = re.sub(r'new \w+\((.*?)\)', lambda m: json.dumps(m.group(0)), code)
        code = re.sub(r'parseInt\([^\d]+(\d+)[^\d]+\)', r'\1', code)
        code = re.sub(r'\(function\([^)]*\)\s*\{[^}]*\}\s*\)\s*\(\s*(["\'][^)]*["\'])\s*\)', r'\1', code)

    return re.sub(r'''(?sx)
        {str_}|
        {comment}|
        ,(?={skip}[\]}}])|
        void\s0|
        !*(?:(?<!\d)[eE]|[a-df-zA-DF-Z_$])[.a-zA-Z_$0-9]*|
        (?:\b|!+)0(?:[xX][\da-fA-F]+|[0-7]+)(?:{skip}:)?|
        !+\d+(?:\.\d*)?(?:{skip}:)?|
        [0-9]+(?:{skip}:)|
        !+
        '''.format(comment=COMMENT_RE, skip=SKIP_RE, str_=STRING_RE), fix_kv, code)


def ytdl_is_updateable():
    """ Returns if youtube-dl can be updated with -U """
    from zipimport import zipimporter

    return isinstance(globals().get('__loader__'), zipimporter) or hasattr(sys, 'frozen')


def error_to_compat_str(err):
    return _decode_compat_str(str(err))


def error_to_compat_str(err):
    return _decode_compat_str(str(err))


# what it could have been
def _decode_compat_str(s, encoding=preferredencoding(), errors='strict', or_none=False):
    if not or_none:
        assert isinstance(s, compat_basestring)
    return (
        s if isinstance(s, compat_str)
        else compat_str(s, encoding, errors) if isinstance(s, compat_basestring)
        else None)


def is_iterable_like(x, allowed_types=compat_collections_abc.Iterable, blocked_types=NO_DEFAULT):
    if blocked_types is NO_DEFAULT:
        blocked_types = (compat_str, bytes, compat_collections_abc.Mapping)
    return isinstance(x, allowed_types) and not isinstance(x, blocked_types)
