import socket
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
    endpoint = request_path_splitted[0]
    match endpoint:
        case "/api/videoinfo":
            if len(request_path_splitted) <= 1:
                answer = "HTTP/1.1 400 Client error\r\n\r\nNo parameters was sent!\r\n"\
                    "You must to send the 'video_id' parameter!"
                client.send(answer.encode())
                return

            queue_dict = parse_qs(request_path_splitted[1])
            if not ("video_id" in queue_dict):
                answer = "HTTP/1.1 400 Client error\r\n\r\nThe 'video_id' parameter is required!"
                client.send(answer.encode())
                return

            video_id = queue_dict["video_id"][0]
            video_info = get_video_info(video_id)
            if not video_info:
                answer = "HTTP/1.1 404 Not found\r\n\r\nCan't find video info!"
                client.send(answer.encode())
                return

            body = json.dumps(video_info)
            headers = f"Content-Type: application/json\r\nContent-Length: {len(body.encode())}"
            answer = f"HTTP/1.1 200 OK\r\n{headers}\r\n\r\n{body}"
            client.send(answer.encode())
        case "/api/nparam":
            if len(request_path_splitted) <= 1:
                answer = "HTTP/1.1 400 Client error\r\n\r\nNo parameters was sent!\r\n"\
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
        case _:
            msg = "Valid endpoint list:\r\nGET /api/videoinfo\r\nGET /api/nparam"
            answer = f"HTTP/1.1 400 Client error\r\n\r\n{msg}"
            client.send(answer.encode())


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
        print("GET /api/videoinfo?video_id=<youtube_video_id>")
        print("GET /api/nparam?n=<encrypted_n_parameter_value>&player_url=<youtube_video_player_url>")
        while True:
            client, client_addr = server.accept()
            print(f"Client {client_addr} is connected")
            process_client(client)
            client.close()
            print(f"Client {client_addr} is disconnected")
    except Exception as ex:
        print(ex)
