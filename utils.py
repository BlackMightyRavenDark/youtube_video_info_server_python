from ytdl.jsinterp import JSInterpreter
import re
import traceback
import urllib.request


def download_string(url):
    response = urllib.request.urlopen(url)
    data = response.read()
    return data.decode()


def extract_n_function_name(player_code):
    pattern = r'''(?x)
            (?:\(\s*(?P<b>[a-z])\s*=\s*String\s*\.\s*fromCharCode\s*\(\s*110\s*\)\s*,(?P<c>[a-z])\s*=\s*[a-z]\s*)?
            \.\s*get\s*\(\s*(?(b)(?P=b)|"n")(?:\s*\)){2}\s*&&\s*\(\s*(?(c)(?P=c)|b)\s*=\s*
            (?P<nfunc>[a-zA-Z_$][\w$]*)(?:\s*\[(?P<idx>\d+)\])?\s*\(\s*[\w$]+\s*\)
        '''
    match = re.search(pattern, player_code)
    func_name = match.group(3)
    idx = match.group(4)
    if not idx:
        return func_name

    pattern = r'var {0}\s*=\s*(\[.+?\])\s*[,;]'.format(re.escape(func_name))
    match = re.search(pattern, player_code)
    func_name = match.group(1)[1:][:-1]
    return func_name


def extract_n_function_from_code(jsi, func_code):
    func = jsi.extract_function_from_code(*func_code)

    def decrypt_n_param(encrypted_n_param):
        try:
            ret = func([encrypted_n_param])
        except JSInterpreter.Exception:
            raise
        except Exception as e:
            raise JSInterpreter.Exception(traceback.format_exc(), cause=e)

        if ret.startswith('enhanced_except_'):
            raise JSInterpreter.Exception('Signature function returned an exception')
        return ret

    return decrypt_n_param
