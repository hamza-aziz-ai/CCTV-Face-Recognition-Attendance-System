from fastapi import FastAPI, Request
import json

test_app = FastAPI()

@test_app.post("/test-api")
async def receive_data(request: Request):
    """
    Endpoint to simulate an API that receives data.
    """
    try:
        data = await request.json()
        print(f"Received data: {json.dumps(data, indent=4)}")
        return {"status": "success", "message": "Data received successfully"}
    except Exception as e:
        print(f"Error receiving data: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(test_app, host="0.0.0.0", port=9000)
