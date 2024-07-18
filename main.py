import json
import socket
from urllib.parse import parse_qs
from utils import *


def process_client(client):
    received_string = client.recv(4096).decode()
    request_string_splitted = received_string.split("\r\n")[0].split(" ")
    request_method = request_string_splitted[0]
    if request_method != "GET":
        answer = "HTTP/1.1 405 Method not allowed\r\n\r\nOnly GET method is allowed!"
        client.send(answer.encode())
        return

    request_path_splitted = request_string_splitted[1].split("?")
    if len(request_path_splitted) <= 1:
        answer = "HTTP/1.1 400 Client error\r\n\r\nNo parameters was sent!"
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
        answer = "HTTP/1.1 500 Internal server error\r\n\r\n{0}".format(t)
        client.send(answer.encode())
        return
    func_name = extract_n_function_name(player_code)
    print("Function name: {0}".format(func_name))
    print("Decrypting given 'n'-parameter {0}...".format(n_param))
    jsi = JSInterpreter(player_code)
    func_code = jsi.extract_function_code(func_name)
    decryption_func = extract_n_function_from_code(jsi, func_code)
    n_param_decrypted = decryption_func(n_param)
    print("Decrypted 'n'-parameter: {0}".format(n_param_decrypted))

    json_answer = json.dumps({"n": n_param_decrypted, "functionName": func_name}).encode()
    headers = "Content-Type: application/json\r\nContent-Length: {0}".format(str(len(json_answer)))
    client.send("HTTP/1.1 200 OK\r\n{0}\r\n\r\n".format(headers).encode())
    client.send(json_answer)


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
        print("The server is started on port {0}".format(port))
        print("You can use it this way:")
        print("GET /api/nparam?n=<encrypted_n_parameter_value>&player_url=<youtube_video_player_url>")
        while True:
            client, client_addr = server.accept()
            print("Client {0} is connected".format(client_addr))
            process_client(client)
            client.close()
            print("Client {0} is disconnected".format(client_addr))
    except Exception as ex:
        print(ex)
