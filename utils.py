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
        headers["Content-Length"] = len(body)
        request_obj = urllib.request.Request(url, method="POST", headers=headers)
        request = urllib.request.urlopen(request_obj, data=body)
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


def get_video_info(video_id):
    url = f"{YOUTUBE_API_PLAYER_URL}?key={YOUTUBE_API_KEY}"
    body = generate_video_info_request_body(video_id, True)
    headers = {"Content-Type": "application/json"}
    video_info = http_post(url, headers, json.dumps(body).encode())
    microformat = None
    if video_info:
        microformat = video_info["microformat"]
        if is_family_safe(video_info):
            streaming_data_decoded = get_streaming_data_decoded(video_id)
            if streaming_data_decoded:
                video_info["streamingData"] = streaming_data_decoded
                return video_info
    web_page = download_video_web_page(video_id, False)
    video_info = extract_initial_player_response(web_page)
    if video_info and not is_family_safe(video_info):
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
                "Content-Type": "application/json",
                "X-YouTube-Client-Name": "85",
                "X-YouTube-Client-Version": "2.0",
                "Origin": "https://www.youtube.com"
            }

            data = json.dumps(body).encode()
            request_obj = urllib.request.Request(YOUTUBE_API_PLAYER_URL, method="POST", headers=headers)
            request = urllib.request.urlopen(request_obj, data=data)
            response = json.loads(request.read().decode())
            if microformat:
                response["microformat"] = microformat
            fix_download_urls(response, player_code)
            return response
    return None


def fix_download_urls(video_info, player_code):
    streaming_data = video_info["streamingData"]
    adaptive_formats = streaming_data["adaptiveFormats"]
    if adaptive_formats:
        func_name = extract_n_function_name(player_code)
        if not func_name:
            return
        jsi = JSInterpreter(player_code)
        func_code = jsi.extract_function_code(func_name)
        decryption_func = extract_n_function_from_code(jsi, func_code)

        dict_n_params = dict()
        for item in adaptive_formats:
            url_splitted = item["url"].split("?")
            queue_string = parse_qs(url_splitted[1])
            if "n" in queue_string:
                n_param = queue_string["n"][0]
                if n_param in dict_n_params:
                    n_param_decrypted = dict_n_params[n_param]
                else:
                    n_param_decrypted = decryption_func(n_param)
                    dict_n_params[n_param] = n_param_decrypted
                queue_string["n"][0] = n_param_decrypted
                fixed_url = f"{url_splitted[0]}?{"&".join(
                    f'{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(value[0])}'
                    for key, value in queue_string.items())}"
                item["url"] = fixed_url


def extract_initial_player_response(web_page_code):
    pattern = "ytInitialPlayerResponse\\s*=\\s*({.+?})\\s*;\\s*(?:var\\s+meta|</script|\\n)"
    match = re.search(pattern, web_page_code)
    if match:
        return json.loads(match.group(1))
    return None


def is_family_safe(video_info):
    return video_info["microformat"]["playerMicroformatRenderer"]["isFamilySafe"]


def get_streaming_data_decoded(video_id):
    url = f"{YOUTUBE_API_PLAYER_URL}?key={YOUTUBE_API_KEY}"
    body = generate_video_info_request_body(video_id, False)
    headers = {"Content-Type": "application/json"}
    data = http_post(url, headers, json.dumps(body).encode())
    return data


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
            (?:\(\s*(?P<b>[a-z])\s*=\s*String\s*\.\s*fromCharCode\s*\(\s*110\s*\)\s*,(?P<c>[a-z])\s*=\s*[a-z]\s*)?
            \.\s*get\s*\(\s*(?(b)(?P=b)|"n")(?:\s*\)){2}\s*&&\s*\(\s*(?(c)(?P=c)|b)\s*=\s*
            (?P<nfunc>[a-zA-Z_$][\w$]*)(?:\s*\[(?P<idx>\d+)\])?\s*\(\s*[\w$]+\s*\)
        '''
    match = re.search(pattern, player_code)
    if not match:
        print("Can't extract function name!")
        return None
    func_name = match.group(3)
    idx = match.group(4)
    if not idx:
        return func_name

    pattern = r"var {0}\s*=\s*(\[.+?\])\s*[,;]".format(func_name)
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
