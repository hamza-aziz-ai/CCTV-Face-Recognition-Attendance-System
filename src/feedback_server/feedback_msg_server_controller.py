"""
This module is created to start a server that listens for publishing feedback messages to a Kafka Stream.

Original Author: Anubhav Patrick
Modified by: Hamza Aziz
Date: 2 September 2023
"""

import json
# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
import os
import socket
import sys
import threading
from feedback_message_kafka_publisher import create_kafka_producer, feedback_message_publisher

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)
from parameters import FEEDBACK_PORT
from custom_logging import feedback_server_logger


def handle_client(client_socket):
    """
    This function handles the client connection and receives the data from the client.
    Parameters:
        client_socket: Client socket object
    """
    # Create a Kafka producer instance
    kafka_producer = create_kafka_producer()

    data = client_socket.recv(1048576)
    # print(data)
    if data:
        client_socket.send("OK".encode('utf-8'))  # Send acknowledgment
        client_socket.close()
        data = json.loads(data)
        result = data['results']

        # print(result)

        # Publish the data to Kafka
        feedback_message_publisher(formatted_result=result, producer=kafka_producer)


def main():
    """
    This function starts a server that listens for publishing feedback messages to a Kafka Stream.
    """
    server_ip = '0.0.0.0'  # to accept connections from all the IPs
    server_port = FEEDBACK_PORT

    # Create a socket server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((server_ip, server_port))
    server.listen(5)

    feedback_server_logger.info(f"Server listening on {server_ip}:{server_port}")

    while True:
        client_socket, addr = server.accept()
        # print(f"Accepted connection from {addr}")
        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.start()


if __name__ == "__main__":
    main()
