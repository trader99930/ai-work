import os
import json
import asyncio
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx

from model_manager import ModelManager

# Initialize Model Manager
manager = ModelManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start default model if configured
    default_model = manager.config.get("default_model")
    if default_model:
        print(f"[*] Starting default model: {default_model}")
        # Launch model loading in background so FastAPI can finish binding to port 8082 immediately
        asyncio.create_task(manager.start_model(default_model))
    yield
    # Shutdown: Stop llama-server cleanly
    print("[*] Stopping Llama server during shutdown...")
    manager.stop_server()

app = FastAPI(
    title="Local AI Workspace & Bridge",
    description="Local GGUF Model Workspace and OpenAI API Bridge on Port 8082",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for cross-origin tools and web apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# =========================================================================
# Web UI Root Endpoint
# =========================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Local AI Workspace is Starting...</h1><p>Static index not found.</p>")


# =========================================================================
# OpenAI Compatible API Endpoints
# =========================================================================

@app.get("/v1/models")
async def list_openai_models():
    """Returns detected models in OpenAI format."""
    scanned = manager.scan_models()
    model_entries = []
    
    for m in scanned:
        model_entries.append({
            "id": m["id"],
            "object": "model",
            "created": int(m["modified"]),
            "owned_by": "local-workspace",
            "permission": [],
            "root": m["filename"],
            "parent": None,
            "meta": {
                "display_name": m["display_name"],
                "filename": m["filename"],
                "size_human": m["size_human"],
                "quantization": m["quantization"],
                "is_active": m["is_active"]
            }
        })

    return {
        "object": "list",
        "data": model_entries
    }


@app.get("/v1/models/{model_id}")
async def get_openai_model(model_id: str):
    scanned = manager.scan_models()
    for m in scanned:
        if m["id"] == model_id or m["filename"] == model_id:
            return {
                "id": m["id"],
                "object": "model",
                "created": int(m["modified"]),
                "owned_by": "local-workspace",
                "permission": [],
                "meta": m
            }
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible Chat Completions endpoint.
    Supports both streaming (SSE) and standard JSON responses.
    Auto-switches model if requested model differs from currently loaded model.
    """
    body = await request.json()
    req_model = body.get("model", "")
    stream = body.get("stream", False)

    # If requested model is specified and different from active model, handle switch
    if req_model:
        target_path = manager.find_model_path(req_model)
        if target_path and manager.active_model_file != target_path.name:
            print(f"[*] Request requested model '{req_model}', switching from '{manager.active_model_file}'...")
            switched = await manager.start_model(target_path.name)
            if not switched:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to switch to model '{req_model}': {manager.error_message}"
                )

    # Ensure backend llama-server is ready
    if manager.status != "READY":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model server is {manager.status}. Error: {manager.error_message or 'Model still loading, please wait.'}"
        )

    target_url = f"http://{manager.llama_host}:{manager.llama_port}/v1/chat/completions"

    if stream:
        async def stream_generator():
            client = httpx.AsyncClient(timeout=120.0)
            try:
                async with client.stream(
                    "POST",
                    target_url,
                    json=body,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status_code != 200:
                        err_content = await response.aread()
                        yield f"data: {json.dumps({'error': err_content.decode('utf-8', errors='replace')})}\n\n"
                        return

                    async for chunk in response.aiter_raw():
                        yield chunk
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                await client.aclose()

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(
                    target_url,
                    json=body,
                    headers={"Content-Type": "application/json"}
                )
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Error communicating with backend llama-server: {str(e)}"
                )


@app.post("/v1/completions")
async def text_completions(request: Request):
    """OpenAI-compatible Text Completions endpoint."""
    body = await request.json()
    req_model = body.get("model", "")
    stream = body.get("stream", False)

    if req_model:
        target_path = manager.find_model_path(req_model)
        if target_path and manager.active_model_file != target_path.name:
            await manager.start_model(target_path.name)

    if manager.status != "READY":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model server is {manager.status}."
        )

    target_url = f"http://{manager.llama_host}:{manager.llama_port}/v1/completions"

    if stream:
        async def stream_generator():
            client = httpx.AsyncClient(timeout=120.0)
            try:
                async with client.stream(
                    "POST",
                    target_url,
                    json=body,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    async for chunk in response.aiter_raw():
                        yield chunk
            finally:
                await client.aclose()

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(target_url, json=body)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)


# =========================================================================
# Workspace & Model Management API
# =========================================================================

@app.get("/api/status")
async def get_status():
    """Returns status, memory, CPU, and active model info."""
    return manager.get_status()


@app.get("/api/models")
async def get_models():
    """Returns all detected GGUF models in /ai_workspace/models."""
    return {"models": manager.scan_models()}


@app.post("/api/models/load")
async def load_model(payload: Dict[str, Any]):
    """Loads or switches to the specified model."""
    model_name = payload.get("model")
    ctx = payload.get("context_size")
    if not model_name:
        raise HTTPException(status_code=400, detail="Missing 'model' field in request body.")

    success = await manager.start_model(model_name, ctx_size=ctx)
    if success:
        return {
            "success": True,
            "message": f"Successfully loaded model '{manager.active_model_file}'",
            "active_model": manager.active_model_file,
            "status": manager.status
        }
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load model: {manager.error_message}"
        )


@app.post("/api/models/unload")
async def unload_model():
    """Unloads active model to free RAM."""
    manager.stop_server()
    return {"success": True, "message": "Model unloaded and llama-server stopped."}


@app.get("/api/logs")
async def get_logs(lines: int = 60):
    """Returns recent log lines from llama-server."""
    return {"logs": manager.get_recent_logs(lines=lines)}


# Passthrough health check
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "workspace": "/ai_workspace",
        "model_status": manager.status,
        "active_model": manager.active_model_file
    }
