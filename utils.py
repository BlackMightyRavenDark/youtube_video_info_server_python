import io
from urllib.parse import parse_qs
from ytdl.jsinterp import JSInterpreter
import json
import re
import traceback
import urllib.request

YOUTUBE_URL = "https://youtube.com"
YOUTUBE_API_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"
YOUTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"


def download_string(url):
    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        return data.decode()
    except Exception as ex:
        print(ex)
        return None


def http_post(url, headers, body):
    try:
        body_bytes = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = len(body_bytes)
        request_obj = urllib.request.Request(url, method="POST", headers=headers)
        request = urllib.request.urlopen(request_obj, data=body_bytes)
        response = json.loads(request.read().decode())
        return response
    except Exception as ex:
        print(ex)
        return None


def download_video_web_page(video_id, bpctr):
    url = f"{YOUTUBE_URL}/watch?v={video_id}"
    if bpctr:
        url += "&bpctr=9999999999&has_verified=1"
    return download_string(url)


def get_video_info(video_id, use_api_first):
    microformat = None
    if use_api_first:
        url = f"{YOUTUBE_API_PLAYER_URL}?key={YOUTUBE_API_KEY}"
        body = generate_video_info_request_body(video_id, True)
        video_info = http_post(url, {}, body)
        if video_info:
            microformat = video_info.get("microformat")
            if is_family_safe(video_info):
                streaming_data_decoded = get_streaming_data_decoded(video_id)
                if streaming_data_decoded:
                    video_info["streamingData"] = streaming_data_decoded
                    return video_info
    web_page = download_video_web_page(video_id, False)
    video_info = extract_initial_player_response(web_page)
    if video_info:
        if not is_family_safe(video_info):
            web_page = download_video_web_page(video_id, True)
            player_url = extract_player_url_from_web_page(web_page)
            player_code = download_string(player_url)
            if player_code:
                sts = extract_signature_timestamp_from_player_code(player_code)
                body = {
                    "playbackContext": {
                        "contentPlaybackContext": {"html5Preference": "HTML5_PREF_WANTS", "signatureTimestamp": sts}},
                    "contentCheckOk": True,
                    "racyCheckOk": True,
                    "context": {
                        "client": {"clientName": "TVHTML5_SIMPLY_EMBEDDED_PLAYER", "clientVersion": "2.0", "hl": "en",
                                   "clientScreen": "EMBED"},
                        "thirdParty": {"embedUrl": "https://google.com"}
                    },
                    "videoId": video_id
                }
                headers = {
                    "X-YouTube-Client-Name": "85",
                    "X-YouTube-Client-Version": "2.0",
                    "Origin": "https://www.youtube.com"
                }

                response = http_post(YOUTUBE_API_PLAYER_URL, headers, body)
                if response:
                    video_info = response
        else:
            player_url = extract_player_url_from_web_page(web_page)
            player_code = download_string(player_url)
        if video_info:
            if microformat:
                video_info["microformat"] = microformat
            streaming_data = video_info.get("streamingData")
            if streaming_data:
                fix_download_urls(streaming_data, player_code)
            return video_info
    return None


def fix_download_urls(streaming_data, player_code):
    if streaming_data:
        adaptive_formats = streaming_data.get("adaptiveFormats")
        if adaptive_formats:
            func_name = extract_n_function_name(player_code)
            if not func_name:
                return
            jsi = JSInterpreter(player_code)
            func_code = jsi.extract_function_code(func_name)
            decryption_func = extract_n_function_from_code(jsi, func_code)

            dict_n_params = dict()
            dict_cipher = dict()
            for item in adaptive_formats:
                cipher_string = item.get("signatureCipher")
                if cipher_string:
                    cipher_signature_dict = parse_qs(cipher_string)
                    encrypted_cipher = cipher_signature_dict["s"][0]
                    encrypted_cipher_quoted = urllib.parse.quote_plus(encrypted_cipher)
                    if encrypted_cipher_quoted in dict_cipher:
                        decrypted_cipher = dict_cipher[encrypted_cipher_quoted]
                    else:
                        decrypted_cipher = decrypt_cipher(encrypted_cipher, player_code)
                        dict_cipher[encrypted_cipher_quoted] = decrypted_cipher
                    encrypted_url_splitted = cipher_signature_dict["url"][0].split("?")
                    url_dict = parse_qs(encrypted_url_splitted[1])
                    url_dict["sig"] = [decrypted_cipher]
                    if "n" in url_dict:
                        encrypted_n = url_dict["n"][0]
                        if encrypted_n in dict_n_params:
                            decrypted_n = dict_n_params[encrypted_n]
                        else:
                            decrypted_n = decryption_func(encrypted_n)
                            dict_n_params[encrypted_n] = decrypted_n
                        url_dict["n"] = [decrypted_n]
                    fixed_url = f"{encrypted_url_splitted[0]}?{"&".join(
                        f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value[0])}'
                        for key, value in url_dict.items())}"
                    item["url"] = fixed_url
                    continue

                url_splitted = item["url"].split("?")
                queue_string = parse_qs(url_splitted[1])
                if "n" in queue_string:
                    n_param = queue_string["n"][0]
                    if n_param in dict_n_params:
                        n_param_decrypted = dict_n_params[n_param]
                    else:
                        n_param_decrypted = decryption_func(n_param)
                        dict_n_params[n_param] = n_param_decrypted
                    queue_string["n"] = [n_param_decrypted]
                    fixed_url = f"{url_splitted[0]}?{"&".join(
                        f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value[0])}'
                        for key, value in queue_string.items())}"
                    item["url"] = fixed_url


def is_ciphered(streaming_data):
    formats = streaming_data.get("adaptiveFormats")
    if formats:
        return formats[0].get("signatureCipher") is not None
    return False


def extract_initial_player_response(web_page_code):
    pattern = "ytInitialPlayerResponse\\s*=\\s*({.+?})\\s*;\\s*(?:var\\s+meta|</script|\\n)"
    match = re.search(pattern, web_page_code)
    if match:
        return json.loads(match.group(1))
    return None


def is_family_safe(video_info):
    microformat = video_info.get("microformat")
    if microformat:
        player_microformat_renderer = microformat.get("playerMicroformatRenderer")
        if player_microformat_renderer:
            return player_microformat_renderer.get("isFamilySafe")
    return True


def get_streaming_data_decoded(video_id):
    url = f"{YOUTUBE_API_PLAYER_URL}?key={YOUTUBE_API_KEY}"
    body = generate_video_info_request_body(video_id, False)
    response = http_post(url, {}, body)
    data = response.get("streamingData") if response else None
    return data if data else response


def generate_video_info_request_body(video_id, get_with_encrypted_urls):
    if get_with_encrypted_urls:
        body = {
            "context": {
                "client": {
                    "hl": "en",
                    "gl": "US",
                    "clientName": "WEB",
                    "clientVersion": "2.20201021.03.00"
                }
            },
            "videoId": video_id}
        return body
    else:
        body = {
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": "ANDROID_TESTSUITE",
                    "clientVersion": "1.9",
                    "androidSdkVersion": 30,
                    "hl": "en",
                    "gl": "US",
                    "utcOffsetMinutes": 0
                }
            }
        }
        return body


def extract_player_url_from_web_page(web_page_code):
    pattern = r'"(?:PLAYER_JS_URL|jsUrl)"\s*:\s*"([^"]+)"'
    match = re.search(pattern, web_page_code)
    if match:
        return YOUTUBE_URL + match.group(1)
    return None


def extract_signature_timestamp_from_player_code(player_code):
    pattern = r"(?:signatureTimestamp|sts)\s*:\s*(?P<sts>[0-9]{5})"
    match = re.search(pattern, player_code)
    if match:
        return match.group(1)
    return None


def extract_n_function_name(player_code):
    pattern = r'''(?x)
                \((?:[\w$()\s]+,)*?\s*      # (
                (?P<b>[a-z])\s*=\s*         # b=
                (?:
                    (?:                     # expect ,c=a.get(b) (etc)
                        String\s*\.\s*fromCharCode\s*\(\s*110\s*\)|
                        "n+"\[\s*\+?s*[\w$.]+\s*]
                    )\s*(?:,[\w$()\s]+(?=,))*|
                       (?P<old>[\w$]+)      # a (old[er])
                   )\s*
                   (?(old)
                                            # b.get("n")
                       (?:\.\s*[\w$]+\s*|\[\s*[\w$]+\s*]\s*)*?
                       (?:\.\s*n|\[\s*"n"\s*]|\.\s*get\s*\(\s*"n"\s*\))
                       |                    # ,c=a.get(b)
                       ,\s*(?P<c>[a-z])\s*=\s*[a-z]\s*
                       (?:\.\s*[\w$]+\s*|\[\s*[\w$]+\s*]\s*)*?
                       (?:\[\s*(?P=b)\s*]|\.\s*get\s*\(\s*(?P=b)\s*\))
                   )
                                            # interstitial junk
                   \s*(?:\|\|\s*null\s*)?(?:\)\s*)?&&\s*(?:\(\s*)?
               (?(c)(?P=c)|(?P=b))\s*=\s*   # [c|b]=
                                            # nfunc|nfunc[idx]
                   (?P<nfunc>[a-zA-Z_$][\w$]*)(?:\s*\[(?P<idx>\d+)\])?\s*\(\s*[\w$]+\s*\)
        '''
    match = re.search(pattern, player_code)
    if not match:
        print("[n-param decryptor] Can't extract function name!")
        return None
    func_name = match.group(4)
    idx = match.group(5)
    if not idx:
        return func_name

    pattern = r"var {0}\s*=\s*(\[.+?\])\s*[,;]".format(func_name)
    match = re.search(pattern, player_code)
    if not match:
        print("[n-param decryptor] Can't find function name!")
        return None

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


def decrypt_cipher(encrypted_signature, player_code):
    patterns = (r'\b[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*encodeURIComponent\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                r'\b[a-zA-Z0-9]+\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*encodeURIComponent\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                r'\bm=(?P<sig>[a-zA-Z0-9$]{2,})\(decodeURIComponent\(h\.s\)\)',
                r'\bc&&\(c=(?P<sig>[a-zA-Z0-9$]{2,})\(decodeURIComponent\(c\)\)',
                r'(?:\b|[^a-zA-Z0-9$])(?P<sig>[a-zA-Z0-9$]{2,})\s*=\s*function\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(\s*""\s*\)(?:;[a-zA-Z0-9$]{2}\.[a-zA-Z0-9$]{2}\(a,\d+\))?',
                r'(?P<sig>[a-zA-Z0-9$]+)\s*=\s*function\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(\s*""\s*\)',
                # Obsolete patterns
                r'("|\')signature\1\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                r'\.sig\|\|(?P<sig>[a-zA-Z0-9$]+)\(',
                r'yt\.akamaized\.net/\)\s*\|\|\s*.*?\s*[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*(?:encodeURIComponent\s*\()?\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                r'\b[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                r'\b[a-zA-Z0-9]+\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                r'\bc\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(')
    func_name = search_patterns(patterns, player_code)
    if func_name:
        print(f"Decrypting Cipher signature '{encrypted_signature}'...")
        jsi = JSInterpreter(player_code)
        func = jsi.extract_function(func_name)
        compat_chr = chr
        t = ''.join(map(compat_chr, range(len(encrypted_signature))))
        numbers = [ord(c) for c in func([t])]
        decrypted_signature = ''.join([encrypted_signature[number] for number in numbers])
        return decrypted_signature
    return None


def search_patterns(patterns, text):
    for t in patterns:
        match = re.search(t, text)
        if match:
            return match.group(1)
    return None


def extract_body_from_received_string(received_string):
    splitted = received_string.split("\r\n\r\n")
    if len(splitted) > 1:
        return splitted[1]
    return None


def try_loads_json(json_string):
    try:
        j_dict = json.loads(json_string)
        return j_dict
    except Exception as ex:
        print(ex)
    return None


def parse_first_content_chunk(chunk_bytes):
    stream = io.BytesIO()
    chunk_length = len(chunk_bytes)
    headers_start = 0
    data_start = 0
    for i in range(0, chunk_length - 4):
        a = chr(chunk_bytes[i])
        if a == '\r':
            b = chr(chunk_bytes[i + 2])
            if b == '\r':
                data_start = i + 4
                break
            if headers_start == 0:
                headers_start = i + 2
    request_string = chunk_bytes[0:headers_start-2].decode("ANSI")
    headers_string = chunk_bytes[headers_start:data_start-1].decode("ANSI")
    headers_splitted = headers_string.split("\r\n")
    headers_dict = dict()
    for s in headers_splitted:
        s_splitted = s.split(":")
        if len(s_splitted) >= 2 and (s_splitted[0]):
            header_name = s_splitted[0].strip()
            if header_name:
                header_value = s_splitted[1].strip()
                headers_dict[header_name] = header_value
    if headers_start < data_start < chunk_length:
        stream.write(chunk_bytes[data_start:chunk_length])
    return request_string, headers_dict, stream


def print_help():
    print("GET /api/videoinfo?video_id=<youtube_video_id>&use_api_first=false")
    print("GET /api/nparam?n=<encrypted_n_parameter_value>&player_url=<youtube_video_player_url>")
    print("GET /api/cipher?cipher=<encrypted_cipher_signature_value>&player_url=<youtube_video_player_url>")
    print('''POST /api/streamingdata
{
    "playerUrl": "<youtube_video_player_url>",
    "streamingData", "<youtube_streaming_data>"
}''')
