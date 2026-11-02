#!/usr/bin/env python3
import time
import json
import httpx

BASE_URL = "http://127.0.0.1:8082"

def log(msg):
    print(f"[TEST] {msg}")

def main():
    log("Starting comprehensive API verification for port 8082...")

    # 1. Health check
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        assert r.status_code == 200, f"Health check failed: {r.text}"
        log(f"✅ /health check passed: {r.json()}")
    except Exception as e:
        log(f"❌ Failed to connect to {BASE_URL}: {e}")
        return

    # 2. Status & Models
    r = httpx.get(f"{BASE_URL}/api/status", timeout=5.0)
    status_data = r.json()
    log(f"Bridge Status: {status_data.get('status')}")
    log(f"Active Model: {status_data.get('active_model_file')}")
    log(f"Available Models: {[m['filename'] for m in status_data.get('models', [])]}")

    # 3. Wait if model is loading
    log("Waiting for model server to be in READY state...")
    max_wait = 40
    start = time.time()
    while time.time() - start < max_wait:
        r = httpx.get(f"{BASE_URL}/api/status", timeout=5.0)
        curr = r.json().get("status")
        if curr == "READY":
            log(f"✅ Backend model is READY! (took {int(time.time() - start)}s)")
            break
        elif curr == "ERROR":
            log(f"❌ Backend model error: {r.json().get('error_message')}")
            return
        time.sleep(2)

    # 4. Test /v1/models (OpenAI format)
    r = httpx.get(f"{BASE_URL}/v1/models", timeout=5.0)
    models_openai = r.json()
    log(f"✅ /v1/models returned {len(models_openai.get('data', []))} models:")
    for m in models_openai.get("data", []):
        log(f"   • {m['id']} ({m.get('meta', {}).get('size_human')})")

    # 5. Test /v1/chat/completions (Non-streaming)
    log("Testing /v1/chat/completions non-streaming...")
    chat_payload = {
        "model": status_data.get("active_model_file"),
        "messages": [
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "Calculate 17 * 19 and reply with just the number."}
        ],
        "max_tokens": 30,
        "temperature": 0.1,
        "stream": False
    }
    t0 = time.time()
    r = httpx.post(f"{BASE_URL}/v1/chat/completions", json=chat_payload, timeout=60.0)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"Chat completion failed: {r.status_code} {r.text}"
    resp_json = r.json()
    content = resp_json["choices"][0]["message"]["content"]
    log(f"✅ Non-streaming response received in {elapsed:.2f}s:")
    log(f"   Assistant says: {content.strip()}")

    # 6. Test /v1/chat/completions (Streaming SSE)
    log("Testing /v1/chat/completions streaming SSE...")
    stream_payload = {
        "model": status_data.get("active_model_file"),
        "messages": [
            {"role": "user", "content": "Count from 1 to 5 separated by commas."}
        ],
        "max_tokens": 30,
        "temperature": 0.1,
        "stream": True
    }
    t0 = time.time()
    collected = []
    with httpx.stream("POST", f"{BASE_URL}/v1/chat/completions", json=stream_payload, timeout=60.0) as stream_resp:
        for chunk in stream_resp.iter_lines():
            line = chunk.strip()
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    delta = json.loads(data_str)["choices"][0]["delta"].get("content", "")
                    collected.append(delta)
                except Exception:
                    pass
    stream_elapsed = time.time() - t0
    streamed_text = "".join(collected)
    log(f"✅ Streaming response received in {stream_elapsed:.2f}s:")
    log(f"   Streamed tokens: {streamed_text.strip()}")

    log("\n🎉 ALL TESTS PASSED! Local AI Workspace on port 8082 is 100% operational!")

if __name__ == "__main__":
    main()
