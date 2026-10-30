#!/bin/sh

# Check the socket health: exit non-zero if nothing listens on the service port
exec python3 -c "import socket; socket.create_connection(('localhost', 20012), 1)"
