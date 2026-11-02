import os
import sys
import time
import json
import signal
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
import httpx

class ModelManager:
    def __init__(self, config_path: str = "/ai_workspace/bridge/config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.models_dir = Path(self.config.get("models_dir", "/ai_workspace/models"))
        self.llama_bin = self.config.get("llama_bin", "/ai_workspace/llama.cpp/build/bin/llama-server")
        self.llama_host = self.config.get("llama_host", "127.0.0.1")
        self.llama_port = int(self.config.get("llama_port", 8085))
        self.threads = int(self.config.get("threads", 4))
        self.context_size = int(self.config.get("context_size", 2048))
        self.repeat_penalty = float(self.config.get("repeat_penalty", 1.1))

        self.process: Optional[subprocess.Popen] = None
        self.active_model_file: Optional[str] = None
        self.active_model_id: Optional[str] = None
        self.status: str = "STOPPED"  # STOPPED, STARTING, READY, ERROR
        self.error_message: Optional[str] = None
        self.start_time: Optional[float] = None
        self.log_file_path = "/ai_workspace/bridge/logs/llama.log"
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def scan_models(self) -> List[Dict[str, Any]]:
        """Scans the models directory and returns metadata for all valid GGUF models."""
        models = []
        if not self.models_dir.exists():
            return models

        for file_path in sorted(self.models_dir.glob("*.gguf")):
            try:
                stat = file_path.stat()
                size_bytes = stat.st_size
                # Only include full models (> 100MB), skipping tiny vocab files
                if size_bytes < 100 * 1024 * 1024:
                    continue

                filename = file_path.name
                # Derive friendly ID
                clean_id = filename.replace(".gguf", "")
                
                # Determine parameter size / quantization label
                quant = "Unknown"
                if "Q4_K_M" in filename:
                    quant = "Q4_K_M (4-bit Medium)"
                elif "Q8_0" in filename:
                    quant = "Q8_0 (8-bit)"
                elif "Q5_K_M" in filename:
                    quant = "Q5_K_M (5-bit Medium)"
                elif "F16" in filename:
                    quant = "F16"

                display_name = clean_id
                if "Hermes-3" in clean_id:
                    display_name = "Nous Hermes 3 (Llama 3.2 3B)"
                elif "Qwen2.5" in clean_id:
                    display_name = "Qwen 2.5 3B Instruct"

                is_active = (self.status == "READY" and self.active_model_file == filename)

                models.append({
                    "id": clean_id,
                    "filename": filename,
                    "display_name": display_name,
                    "path": str(file_path.resolve()),
                    "size_bytes": size_bytes,
                    "size_human": f"{size_bytes / (1024**3):.2f} GB",
                    "quantization": quant,
                    "is_active": is_active,
                    "modified": stat.st_mtime
                })
            except Exception as e:
                print(f"Error scanning model {file_path}: {e}", file=sys.stderr)

        return models

    def find_model_path(self, model_identifier: str) -> Optional[Path]:
        """Finds model path matching filename, stem, or alias."""
        models = self.scan_models()
        model_id_lower = model_identifier.lower().strip()
        
        for m in models:
            if (m["filename"].lower() == model_id_lower or
                m["id"].lower() == model_id_lower or
                model_id_lower in m["filename"].lower() or
                model_id_lower in m["display_name"].lower()):
                return Path(m["path"])
        return None

    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of the model server and system stats."""
        models = self.scan_models()
        mem = self._get_memory_info()
        uptime = time.time() - self.start_time if (self.start_time and self.status == "READY") else 0

        return {
            "status": self.status,
            "active_model_file": self.active_model_file,
            "active_model_id": self.active_model_id,
            "error_message": self.error_message,
            "uptime_seconds": int(uptime),
            "llama_endpoint": f"http://{self.llama_host}:{self.llama_port}",
            "models_count": len(models),
            "models": models,
            "system": {
                "memory": mem,
                "cpu_cores": os.cpu_count() or 1,
                "load_avg": self._get_load_avg()
            }
        }

    def _get_memory_info(self) -> Dict[str, Any]:
        mem_info = {"total_mb": 0, "available_mb": 0, "used_mb": 0, "used_percent": 0.0}
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            kvs = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = parts[1].strip().split()[0]
                    kvs[k] = int(v)
            total_kb = kvs.get("MemTotal", 0)
            avail_kb = kvs.get("MemAvailable", kvs.get("MemFree", 0))
            used_kb = total_kb - avail_kb
            total_mb = total_kb // 1024
            avail_mb = avail_kb // 1024
            used_mb = used_kb // 1024
            percent = (used_kb / total_kb * 100) if total_kb > 0 else 0.0
            mem_info = {
                "total_mb": total_mb,
                "available_mb": avail_mb,
                "used_mb": used_mb,
                "used_percent": round(percent, 1)
            }
        except Exception:
            pass
        return mem_info

    def _get_load_avg(self) -> List[float]:
        try:
            with open("/proc/loadavg", "r") as f:
                parts = f.read().strip().split()
                return [float(parts[0]), float(parts[1]), float(parts[2])]
        except Exception:
            return [0.0, 0.0, 0.0]

    def stop_server(self):
        """Terminates any running llama-server process."""
        self.status = "STOPPING"
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            except Exception as e:
                print(f"Error terminating process: {e}", file=sys.stderr)
            finally:
                self.process = None

        # Also cleanup any stray llama-server processes on the configured port
        try:
            subprocess.run(
                ["pkill", "-f", f"llama-server.*--port {self.llama_port}"],
                capture_output=True,
                check=False
            )
        except Exception:
            pass

        self.status = "STOPPED"
        self.active_model_file = None
        self.active_model_id = None
        self.start_time = None

    async def start_model(self, model_identifier: str, ctx_size: Optional[int] = None) -> bool:
        """Starts or switches the model to the specified identifier."""
        target_path = self.find_model_path(model_identifier)
        if not target_path or not target_path.exists():
            self.error_message = f"Model '{model_identifier}' not found in {self.models_dir}"
            self.status = "ERROR"
            return False

        # If already ready with this model, no-op
        if self.status == "READY" and self.active_model_file == target_path.name:
            return True

        self.stop_server()
        self.status = "STARTING"
        self.error_message = None
        self.active_model_file = target_path.name
        self.active_model_id = target_path.stem

        ctx = ctx_size or self.context_size
        cmd = [
            self.llama_bin,
            "-m", str(target_path),
            "-c", str(ctx),
            "-t", str(self.threads),
            "--host", self.llama_host,
            "--port", str(self.llama_port),
            "--repeat-penalty", str(self.repeat_penalty)
        ]

        try:
            log_f = open(self.log_file_path, "a", encoding="utf-8")
            log_f.write(f"\n--- Starting model {target_path.name} at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            log_f.write(f"Command: {' '.join(cmd)}\n")
            log_f.flush()

            self.process = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid
            )

            # Wait for health check
            health_url = f"http://{self.llama_host}:{self.llama_port}/health"
            max_wait = 35  # seconds
            start_wait = time.time()

            async with httpx.AsyncClient(timeout=3.0) as client:
                while time.time() - start_wait < max_wait:
                    # Check if process died
                    ret = self.process.poll()
                    if ret is not None:
                        self.status = "ERROR"
                        self.error_message = f"llama-server exited unexpectedly with return code {ret}."
                        return False

                    try:
                        resp = await client.get(health_url)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("status") == "ok":
                                self.status = "READY"
                                self.start_time = time.time()
                                return True
                    except Exception:
                        pass
                    await asyncio.sleep(1.0)

            # Timed out waiting
            self.status = "ERROR"
            self.error_message = f"Timed out waiting for model to load after {max_wait}s."
            self.stop_server()
            return False

        except Exception as e:
            self.status = "ERROR"
            self.error_message = str(e)
            return False

    def get_recent_logs(self, lines: int = 50) -> List[str]:
        if not os.path.exists(self.log_file_path):
            return []
        try:
            with open(self.log_file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.readlines()
                return [line.rstrip() for line in content[-lines:]]
        except Exception:
            return []
