"""Face crops from this client's edge nodes (D-043): POST /v1/edge/faces, which the proxy serves as /api/v1/edge/faces.

Only a machine token with the edge_collector role may call it, and it forwards only to this client's own collector, which
has no route of its own. An older API without this route turns edge uploads away; it never exposes the collector.
"""
import requests
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import accounts
from custom_logging import api_logger
from parameters import DYNAMIC_FACE_DATA_COLLECTOR_LOCAL

router = APIRouter(prefix="/v1/edge")
COLLECTOR = f"{DYNAMIC_FACE_DATA_COLLECTOR_LOCAL}/faces"
MAX_BODY = 8 * 1024 * 1024  # one recognition batch of JPEG crops is tens of KB


@router.post("/faces")
async def faces(request: Request) -> Response:
    caller = await run_in_threadpool(accounts.identify, request)
    if caller is None:
        return JSONResponse({"error": "signed_out"}, status_code=401)
    if caller["role"] != "edge_collector":
        return JSONResponse({"error": "role_cannot_upload_faces"}, status_code=403)
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        return JSONResponse({"error": "too_large"}, status_code=413)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:  # a chunked upload has no length to check first
            return JSONResponse({"error": "too_large"}, status_code=413)
    try:
        answer = await run_in_threadpool(requests.post, COLLECTOR, data=bytes(body), timeout=30,
                                         headers={"Content-Type": "application/json"})
    except requests.RequestException as error:
        api_logger.error(f"Edge face crops from {caller['name']} not forwarded: {error}")
        return JSONResponse({"error": "collector_unavailable"}, status_code=503)
    # 200 all kept, 207 some not (with the failures), 422 malformed: the edge reads it as the collector said it
    return Response(answer.content, status_code=answer.status_code, media_type="application/json")
