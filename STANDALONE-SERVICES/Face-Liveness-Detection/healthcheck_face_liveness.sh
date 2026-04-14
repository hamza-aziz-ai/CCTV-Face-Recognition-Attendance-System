#!/bin/bash

# Check the socket health (replace with your specific socket check logic)
nc -z -w 1 localhost 6969

# Exit with status 0 if socket is healthy, non-zero otherwise
echo $?

