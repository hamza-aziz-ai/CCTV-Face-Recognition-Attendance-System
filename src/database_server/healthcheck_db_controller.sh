#!/bin/sh

# Healthy only when the controller's latest write to its database succeeded recently (GET /health), not merely when its
# port is open: a controller that cannot save attendance is not healthy
exec python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:20001/health', timeout=3)"
