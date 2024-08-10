import socket
import time
from utils import *


def read_client(client):
    buffer_size = 1024
    buffer = client.recv(buffer_size)
    request_string, headers, stream = parse_first_content_chunk(buffer)
    content_length = int(headers["Content-Length"]) if "Content-Length" in headers else 0
    if content_length > stream.getbuffer().nbytes:
        remaining = content_length - stream.getbuffer().nbytes
        while remaining > 0:
            want_read = remaining if remaining < buffer_size else buffer_size
            tmp = client.recv(want_read)
            if not tmp:
                break
            stream.write(tmp)
            remaining -= len(tmp)
    return request_string, headers, stream


def process_client(client, client_addr):
    request_string, headers, stream = read_client(client)
    if not request_string:
        print(f"Can't read client {client_addr}")
        return
    request_string_splitted = request_string.split(" ")
    request_method = request_string_splitted[0]
    if request_method != "GET" and request_method != "POST":
        answer = "HTTP/1.1 405 Method not allowed\r\n\r\nOnly GET or POST methods are allowed!"
        client.send(answer.encode())
        return

    body = None
    if request_method == "POST" and stream:
        body = stream.getbuffer().tobytes().decode()

    request_path = request_string_splitted[1]
    request_path_splitted = request_path.split("?")
    endpoint_path = request_path_splitted[0]
    match endpoint_path:
        case "/api/videoinfo":
            process_video_info_request(client, client_addr, request_method, request_path_splitted)
        case "/api/nparam":
            process_nparam_request(client, request_method, request_path_splitted)
        case "/api/cipher":
            process_cipher_request(client, request_method, request_path_splitted)
        case "/api/streamingdata":
            process_urls_decrypt_request(client, request_method, body)
        case _:
            msg = "Valid endpoint list:\r\nGET /api/videoinfo\r\nGET /api/nparam\r\nGET /api/cipher"
            answer = f"HTTP/1.1 400 Client error\r\n\r\n{msg}"
            client.send(answer.encode())


def process_video_info_request(client, client_addr, request_method, request_path_splitted):
    if request_method != "GET":
        client.send(b"HTTP/1.1 405 Method not allowed\r\n\r\nPlease use GET method with this endpoint!")
        return
    if len(request_path_splitted) <= 1:
        answer = "HTTP/1.1 400 Client error\r\n\r\nNo parameters was sent!\r\n" \
                 "You must to send the 'video_id' parameter!"
        client.send(answer.encode())
        return
    queue_dict = parse_qs(request_path_splitted[1])
    if not ("video_id" in queue_dict):
        answer = "HTTP/1.1 400 Client error\r\n\r\nThe 'video_id' parameter is required!"
        client.send(answer.encode())
        return

    video_id = queue_dict["video_id"][0]
    print(f"Client {client_addr} is requested video {video_id}")

    use_api_first = True
    if "use_api_first" in queue_dict:
        value = queue_dict["use_api_first"][0]
        if value != "true" and value != "false":
            answer = "HTTP/1.1 400 Client error\r\n\r\n" \
                     "The 'use_api_first' parameter value must be 'true' or 'false' lowercased!"
            client.send(answer.encode())
            return
        if value == "false":
            use_api_first = False

    video_info = get_video_info(video_id, use_api_first)
    if not video_info:
        answer = "HTTP/1.1 404 Not found\r\n\r\nCan't find video info!"
        client.send(answer.encode())
        return

    body = json.dumps(video_info)
    headers = f"Content-Type: application/json\r\nContent-Length: {len(body.encode())}"
    answer = f"HTTP/1.1 200 OK\r\n{headers}\r\n\r\n{body}"
    client.send(answer.encode())


def process_nparam_request(client, request_method, request_path_splitted):
    if request_method != "GET":
        client.send(b"HTTP/1.1 405 Method not allowed\r\n\r\nPlease use GET method with this endpoint!")
        return
    if len(request_path_splitted) <= 1:
        answer = "HTTP/1.1 400 Client error\r\n\r\nNo parameters was sent!\r\n" \
                 "Required parameters are: 'n', 'player_url'"
        client.send(answer.encode())
        return
    queue_dict = parse_qs(request_path_splitted[1])
    if not ("n" in queue_dict):
        answer = "HTTP/1.1 400 Client error\r\n\r\nThe 'n' parameter is required!"
        client.send(answer.encode())
        return

    if not ("player_url" in queue_dict):
        answer = "HTTP/1.1 400 Client error\r\n\r\nThe 'player_url' parameter is required!"
        client.send(answer.encode())
        return

    n_param = queue_dict["n"][0]
    player_url = queue_dict["player_url"][0]
    print("Downloading player...")
    player_code = download_string(player_url.replace(" ", "%20"))
    if not player_code:
        t = "Unable to download player!"
        print(t)
        answer = f"HTTP/1.1 500 Internal server error\r\n\r\n{t}"
        client.send(answer.encode())
        return
    func_name = extract_n_function_name(player_code)
    if not func_name:
        t = "Unable to extract the 'n'-parameter decryption function name!"
        print(t)
        answer = f"HTTP/1.1 500 Internal server error\r\n\r\n{t}"
        client.send(answer.encode())
        return

    print(f"Function name: {func_name}")
    print(f"Decrypting given 'n'-parameter {n_param}...")
    jsi = JSInterpreter(player_code)
    func_code = jsi.extract_function_code(func_name)
    decryption_func = extract_n_function_from_code(jsi, func_code)
    n_param_decrypted = decryption_func(n_param)
    print(f"Decrypted 'n'-parameter: {n_param_decrypted}")

    json_answer = json.dumps({"n": n_param_decrypted, "functionName": func_name}).encode()
    headers = f"Content-Type: application/json\r\nContent-Length: {str(len(json_answer))}"
    client.send(f"HTTP/1.1 200 OK\r\n{headers}\r\n\r\n".encode())
    client.send(json_answer)


def process_cipher_request(client, request_method, request_path_splitted):
    if request_method != "GET":
        client.send(b"HTTP/1.1 405 Method not allowed\r\n\r\nPlease use GET method with this endpoint!")
        return
    if len(request_path_splitted) <= 1:
        answer = "HTTP/1.1 400 Client error\r\n\r\nNo parameters was sent!\r\n" \
                 "Required parameters are: 'cipher', 'player_url'"
        client.send(answer.encode())
        return
    queue_dict = parse_qs(request_path_splitted[1])
    if not ("cipher" in queue_dict):
        answer = "HTTP/1.1 400 Client error\r\n\r\nThe 'cipher' parameter is required!"
        client.send(answer.encode())
        return

    if not ("player_url" in queue_dict):
        answer = "HTTP/1.1 400 Client error\r\n\r\nThe 'player_url' parameter is required!"
        client.send(answer.encode())
        return

    player_url = queue_dict["player_url"][0].replace(" ", "%20")
    player_code = download_string(player_url)
    if not player_code:
        t = f"Unable to download player code!\r\n{player_url}"
        print(t)
        answer = f"HTTP/1.1 500 Internal server error\r\n\r\n{t}"
        client.send(answer.encode())
        return

    encrypted_cipher = queue_dict["cipher"][0]
    decrypted_cipher = decrypt_cipher(encrypted_cipher, player_code)
    if not decrypted_cipher:
        t = "Unable to decrypt Cipher!"
        print(t)
        answer = f"HTTP/1.1 500 Internal server error\r\n\r\n{t}"
        client.send(answer.encode())
        return

    json_answer = json.dumps({"encryptedCipher": encrypted_cipher, "decryptedCipher": decrypted_cipher}).encode()
    headers = f"Content-Type: application/json\r\nContent-Length: {str(len(json_answer))}"
    client.send(f"HTTP/1.1 200 OK\r\n{headers}\r\n\r\n".encode())
    client.send(json_answer)


def process_urls_decrypt_request(client, request_method, body):
    if request_method != "POST":
        client.send(b"HTTP/1.1 405 Method not allowed\r\n\r\nPlease use POST method with this endpoint!")
        return
    json_body = try_loads_json(body)
    if json_body is None:
        client.send(b"HTTP/1.1 500 Internal server error\r\n\r\nCan't parse JSON!")
        return
    if not json_body:
        client.send(b"HTTP/1.1 400 Client error\r\n\r\nJSON object is empty!")
        return
    player_url = json_body.get("playerUrl")
    if not player_url:
        client.send(b"HTTP/1.1 400 Client error\r\n\r\nYou must send player URL!")
        return
    streaming_data = json_body.get("streamingData")
    if not streaming_data:
        client.send(b"HTTP/1.1 400 Client error\r\n\r\nYou must send streaming data!")
        return
    streaming_data_json = try_loads_json(streaming_data)
    if streaming_data_json is None:
        client.send(b"HTTP/1.1 500 Internal server error\r\n\r\nCan't parse streaming data!")
        return
    player_code = download_string(player_url)
    if not player_code:
        answer = f"HTTP/1.1 500 Internal server error\r\n\r\nUnable to download a player code!\r\n{player_url}"
        client.send(answer.encode())
    fix_download_urls(streaming_data_json, player_code)
    client.send(f"HTTP/1.1 200 OK\r\n\r\n{json.dumps(streaming_data_json)}".encode())


if __name__ == '__main__':
    try:
        port = 0

        # noinspection PyBroadException
        try:
            port = int(input("Enter a server port number (leave it empty for 5556):"))
        except Exception:
            port = 5556

        server = socket.socket()
        server.bind(('', port))
        server.listen()
        print(f"The server is started on port {port}")
        print("You can use it this way:")
        print_help()
        while True:
            client, client_addr = server.accept()
            print(f"Client {client_addr} is connected")
            time.sleep(1)
            process_client(client, client_addr)
            client.close()
            print(f"Client {client_addr} is disconnected")
    except Exception as ex:
        print(ex)
