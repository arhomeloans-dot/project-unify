"""
Project Unify — Production Daemon (Three-Tier Cost-Optimized Router)

Runs 24/7 as a service. Applications connect to this daemon (default port 11435)
instead of calling Ollama/APIs directly. The daemon:

1. Routes requests based on document complexity (0.0-1.0 scale)
2. Implements automatic timeout-based failover between tiers
3. Logs all decisions, latency, errors, and costs
4. Maintains real-time metrics for Orion dashboard

Tier Structure:
  Complexity < 0.80 → Tier 1: Local Ollama (timeout: 60s)
  Complexity 0.80-0.95 → Tier 2: Kimi-K3 / GLM (timeout: 30s)
  Complexity >= 0.95 → Tier 3: Claude API (timeout: 10s)

Auto-failover: If a tier times out, automatically escalate to the next tier.
"""

import requests
import json
import os
import logging
import time
import threading
from typing import Dict, Tuple, Any
from datetime import datetime, timezone
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse

# Configuration
DAEMON_HOST = "0.0.0.0"
DAEMON_PORT = 11435  # Applications connect here

OLLAMA_PROXY_URL = "http://127.0.0.1:11434"
HUGGINGFACE_API_URL = "https://router.huggingface.co/v1/chat/completions"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

HUGGINGFACE_TOKEN = os.environ.get("HF_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

KIMI_K3_MODEL = "moonshotai/Kimi-K3"
GLM_5_2_MODEL = "zai-org/GLM-5.2"
CLAUDE_MODEL = "claude-3-5-haiku-20241022"

# Routing thresholds (adjustable)
COMPLEXITY_THRESHOLD_T2 = 0.80
COMPLEXITY_THRESHOLD_T3 = 0.95

# Per-tier timeouts (in seconds) — EXTENDED FOR LONGER GENERATIONS
TIMEOUT_CONFIG = {
    "tier1_local": {"connect": 3, "read": 90},   # Local Ollama - Gemma2:9b
    "tier2_llama": {"connect": 3, "read": 120},   # Local Ollama - Llama3.1 (extended for reasoning)
    "tier3_kimi": {"connect": 10, "read": 60},    # HuggingFace Kimi-K3
    "tier3_glm": {"connect": 10, "read": 60}      # HuggingFace GLM 5.2
}

# Setup logging
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project_unify_daemon.log")
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def log(msg: str, level: str = "INFO"):
    """Log to file and console"""
    if level == "ERROR":
        logging.error(msg)
        print(f"[ERROR] {msg}", flush=True)
    elif level == "WARN":
        logging.warning(msg)
        print(f"[WARN] {msg}", flush=True)
    else:
        logging.info(msg)
        print(f"[INFO] {msg}", flush=True)


class ProjectUnifyRouter:
    def __init__(self):
        self.metrics = {
            "total_requests": 0,
            "routing_breakdown": {"tier1_local": 0, "tier2_llama": 0, "tier3_kimi": 0, "tier3_glm": 0},
            "failover_events": 0,
            "performance": {"avg_latency_ms": 0, "errors": 0, "timeouts": 0},
            "cost": {"total_usd": 0.0, "breakdown": {}}
        }
        self.latencies = []
        self.lock = threading.Lock()

    def estimate_complexity(self, task_type: str, content_length: int) -> float:
        """Estimate complexity (0.0-1.0) from task type and content length"""
        task_weights = {
            "classify": 0.3,
            "summarize": 0.3,
            "extract_entities": 0.4,
            "reconcile": 0.7,
            "judicial": 0.99
        }
        base_score = task_weights.get(task_type, 0.5)
        length_factor = min(content_length / 1000, 0.3)
        return min(base_score + length_factor, 1.0)

    def decide_initial_routing(self, complexity: float) -> str:
        """Determine initial tier based on complexity"""
        if complexity < COMPLEXITY_THRESHOLD_T2:
            return "tier1_local"
        elif complexity < COMPLEXITY_THRESHOLD_T3:
            return "tier2_llama"
        else:
            return "tier3_kimi"

    def _infer_tier1_local(self, prompt: str, timeout: Tuple[int, int]) -> Tuple[str, float, float, int, str]:
        """Tier 1: Local Ollama via proxy"""
        try:
            start = time.time()
            response = requests.post(
                f"{OLLAMA_PROXY_URL}/api/generate",
                json={"model": "gemma2:9b", "prompt": prompt, "stream": False},
                timeout=timeout
            )
            latency = (time.time() - start) * 1000
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                return result, latency, 0.0, 200, "success"
            else:
                return "", latency, 0.0, response.status_code, "http_error"
        except requests.exceptions.Timeout:
            latency = (time.time() - start) * 1000
            return "", latency, 0.0, 504, "timeout"
        except Exception as e:
            return "", 0, 0.0, 500, f"exception: {str(e)[:50]}"


    def _infer_tier2_llama(self, prompt: str, timeout: Tuple[int, int]) -> Tuple[str, float, float, int, str]:
        """Tier 2: Local Llama3.1 via Ollama proxy"""
        try:
            start = time.time()
            response = requests.post(
                f"{OLLAMA_PROXY_URL}/api/generate",
                json={"model": "llama3.1:latest", "prompt": prompt, "stream": False},
                timeout=timeout
            )
            latency = (time.time() - start) * 1000
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                return result, latency, 0.0, 200, "success"
            else:
                return "", latency, 0.0, response.status_code, "http_error"
        except requests.exceptions.Timeout:
            latency = (time.time() - start) * 1000
            return "", latency, 0.0, 504, "timeout"
        except Exception as e:
            latency = (time.time() - start) * 1000
            return "", latency, 0.0, 500, str(e)


    def _infer_hf_router(self, model: str, prompt: str, timeout: Tuple[int, int]):
        """Shared HuggingFace Inference Providers call (OpenAI-compatible schema)"""
        start = time.time()
        try:
            headers = {
                "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512
            }
            response = requests.post(
                HUGGINGFACE_API_URL,
                headers=headers,
                json=payload,
                timeout=timeout
            )
            latency = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "")
                    return text, latency, 0.00015, 200, "success"
                return "", latency, 0.0, 502, "empty_choices"

            return "", latency, 0.0, response.status_code, f"http_error: {response.text[:120]}"

        except requests.exceptions.Timeout:
            return "", (time.time() - start) * 1000, 0.0, 504, "timeout"
        except Exception as e:
            return "", (time.time() - start) * 1000, 0.0, 500, f"exception: {str(e)[:80]}"

    def _infer_tier2_kimi(self, prompt: str, timeout: Tuple[int, int]) -> Tuple[str, float, float, int, str]:
        """Tier 3a: Kimi-K3 via HF Inference Providers router"""
        return self._infer_hf_router(KIMI_K3_MODEL, prompt, timeout)

    def _infer_tier2_glm(self, prompt: str, timeout: Tuple[int, int]) -> Tuple[str, float, float, int, str]:
        """Tier 3b: GLM 5.2 via HF Inference Providers router"""
        return self._infer_hf_router(GLM_5_2_MODEL, prompt, timeout)

    def _infer_tier3_claude(self, prompt: str, timeout: Tuple[int, int]) -> Tuple[str, float, float, int, str]:
        """Tier 3: Claude 3.5 Haiku via Anthropic API"""
        try:
            start = time.time()
            headers = {
                "Authorization": f"Bearer {ANTHROPIC_API_KEY}",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": CLAUDE_MODEL,
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}]
            }
            response = requests.post(
                ANTHROPIC_API_URL,
                headers=headers,
                json=payload,
                timeout=timeout
            )
            latency = (time.time() - start) * 1000
            
            if response.status_code == 200:
                result = response.json()
                text = result.get("content", [{}])[0].get("text", "")
                return text, latency, 0.00102, 200, "success"
            return "", latency, 0.0, response.status_code, "http_error"
        except requests.exceptions.Timeout:
            latency = (time.time() - start) * 1000
            return "", latency, 0.0, 504, "timeout"
        except Exception as e:
            return "", 0, 0.0, 500, f"exception: {str(e)[:50]}"

    def process_request(self, doc_id: str, task_type: str, content: str) -> Dict[str, Any]:
        """
        Process document with automatic failover on timeout.
        Returns complete request record with tier, latency, cost, success status.
        """
        with self.lock:
            self.metrics["total_requests"] += 1
        
        complexity = self.estimate_complexity(task_type, len(content))
        initial_tier = self.decide_initial_routing(complexity)
        actual_tier = initial_tier
        
        result = ""
        latency = 0
        cost = 0
        status = 500
        confidence = 0.0
        failover_chain = [initial_tier]
        
        log(f"Request {doc_id} | task={task_type} | complexity={complexity:.3f} | initial_tier={initial_tier}")
        
        # Tier 1: Local Ollama
        if actual_tier == "tier1_local":
            timeout = (TIMEOUT_CONFIG["tier1_local"]["connect"], TIMEOUT_CONFIG["tier1_local"]["read"])
            result, latency, cost, status, reason = self._infer_tier1_local(content, timeout)
            confidence = 0.75 if status == 200 else 0.0
            
            # Failover if timeout
            if status == 504:
                log(f"  Tier 1 timeout ({latency:.0f}ms), failing over to Tier 2...", "WARN")
                with self.lock:
                    self.metrics["failover_events"] += 1
                    self.metrics["performance"]["timeouts"] += 1
                actual_tier = "tier2_llama"
                failover_chain.append("tier2_llama")
        
        # Tier 2: Local Llama3.1
        if actual_tier == "tier2_llama":
            timeout = (TIMEOUT_CONFIG["tier2_llama"]["connect"], TIMEOUT_CONFIG["tier2_llama"]["read"])
            result, latency, cost, status, reason = self._infer_tier2_llama(content, timeout)
            confidence = 0.85 if status == 200 else 0.0
            
            # Failover if timeout
            if status == 504:
                log(f"  Tier 2 timeout ({latency:.0f}ms), escalating to Tier 3...", "WARN")
                with self.lock:
                    self.metrics["failover_events"] += 1
                    self.metrics["performance"]["timeouts"] += 1
                actual_tier = "tier3_kimi"
                failover_chain.append("tier3_kimi")
            # If Tier 2 fails, try Tier 3
            elif status != 200:
                log(f"  Tier 2 (Llama) failed ({reason}), escalating to Tier 3...", "WARN")
                with self.lock:
                    self.metrics["failover_events"] += 1
                actual_tier = "tier3_kimi"
                failover_chain.append("tier3_kimi")
        
        # Tier 3a: Kimi-K3
        if actual_tier == "tier3_kimi":
            timeout = (TIMEOUT_CONFIG["tier3_kimi"]["connect"], TIMEOUT_CONFIG["tier3_kimi"]["read"])
            result, latency, cost, status, reason = self._infer_tier2_kimi(content, timeout)
            confidence = 0.90 if status == 200 else 0.0
            
            # Failover if timeout
            if status == 504:
                log(f"  Tier 3 (Kimi) timeout ({latency:.0f}ms), trying GLM...", "WARN")
                with self.lock:
                    self.metrics["failover_events"] += 1
                    self.metrics["performance"]["timeouts"] += 1
                actual_tier = "tier3_glm"
                failover_chain.append("tier3_glm")
            # If Kimi fails for other reasons, try GLM
            elif status != 200:
                log(f"  Tier 3 (Kimi) failed ({reason}), trying GLM...", "WARN")
                with self.lock:
                    self.metrics["failover_events"] += 1
                actual_tier = "tier3_glm"
                failover_chain.append("tier3_glm")
        
        # Tier 3b: GLM 5.2
        if actual_tier == "tier3_glm":
            timeout = (TIMEOUT_CONFIG["tier3_glm"]["connect"], TIMEOUT_CONFIG["tier3_glm"]["read"])
            result, latency, cost, status, reason = self._infer_tier2_glm(content, timeout)
            confidence = 0.88 if status == 200 else 0.0
            
            if status != 200:
                log(f"  Tier 3 (GLM) failed ({reason}), no more tiers to escalate", "ERROR")
                with self.lock:
                    self.metrics["performance"]["errors"] += 1

        # Update metrics
        with self.lock:
            self.metrics["routing_breakdown"][actual_tier] += 1
            self.metrics["cost"]["total_usd"] += cost
            if actual_tier not in self.metrics["cost"]["breakdown"]:
                self.metrics["cost"]["breakdown"][actual_tier] = 0.0
            self.metrics["cost"]["breakdown"][actual_tier] += cost
            
            if latency > 0:
                self.latencies.append(latency)
                self.metrics["performance"]["avg_latency_ms"] = sum(self.latencies) / len(self.latencies)
        
        # Build response
        request_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "doc_id": doc_id,
            "task_type": task_type,
            "complexity": complexity,
            "initial_tier": initial_tier,
            "actual_tier": actual_tier,
            "failover_chain": failover_chain,
            "latency_ms": latency,
            "cost_usd": cost,
            "confidence": confidence,
            "http_status": status,
            "success": status == 200,
            "result_snippet": result[:100] if result else "(empty)"
        }
        
        log(f"  Result: tier={actual_tier} | latency={latency:.1f}ms | cost=${cost:.6f} | confidence={confidence:.2f} | status={status} | failover={'->'.join(failover_chain)}")
        
        return request_record

    def get_metrics(self) -> Dict[str, Any]:
        """Return current metrics snapshot"""
        with self.lock:
            return {
                "total_requests": self.metrics["total_requests"],
                "routing_breakdown": self.metrics["routing_breakdown"].copy(),
                "failover_events": self.metrics["failover_events"],
                "performance": {
                    "avg_latency_ms": round(self.metrics["performance"]["avg_latency_ms"], 2),
                    "errors": self.metrics["performance"]["errors"],
                    "timeouts": self.metrics["performance"]["timeouts"]
                },
                "cost": {
                    "total_usd": round(self.metrics["cost"]["total_usd"], 6),
                    "breakdown": {k: round(v, 6) for k, v in self.metrics["cost"]["breakdown"].items()}
                }
            }


# Global router instance
router = ProjectUnifyRouter()


class DaemonRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the daemon"""
    
    def do_POST(self):
        """Handle POST /infer requests"""
        if self.path == "/infer":
            self._handle_infer()
        elif self.path == "/metrics":
            self._handle_metrics()
        else:
            self._send_json(404, {"error": "Not found"})
    
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """Handle GET /metrics requests"""
        if self.path == "/metrics":
            self._handle_metrics()
        elif self.path == "/health":
            self._handle_health()
        else:
            self._send_json(404, {"error": "Not found"})
    
    def _handle_infer(self):
        """POST /infer - Process document through router"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b""
            request_data = json.loads(body) if body else {}
            
            doc_id = request_data.get("doc_id", "unknown")
            task_type = request_data.get("task_type", "classify")
            content = request_data.get("content", "")
            
            if not content:
                self._send_json(400, {"error": "content is required"})
                return
            
            result = router.process_request(doc_id, task_type, content)
            self._send_json(200, result)
        
        except Exception as e:
            log(f"Infer error: {str(e)}", "ERROR")
            self._send_json(500, {"error": str(e)[:100]})
    
    def _handle_metrics(self):
        """GET /metrics - Return current metrics"""
        metrics = router.get_metrics()
        self._send_json(200, metrics)
    
    def _handle_health(self):
        """GET /health - Health check"""
        self._send_json(200, {"status": "healthy", "uptime_requests": router.metrics["total_requests"]})
    
    def handle_one_request(self):
        """Never let a dropped client connection kill the worker"""
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def _send_json(self, status_code: int, data: Dict):
        """Send JSON response"""
        try:
            self._send_json_inner(status_code, data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send_json_inner(self, status_code: int, data: Dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        """Suppress HTTP logging"""
        pass


def start_daemon():
    """Start the daemon service"""
    log("="*90)
    log("Project Unify Daemon — Starting")
    log("="*90)
    log(f"Listening on {DAEMON_HOST}:{DAEMON_PORT}")
    log("Tier 1 Gemma2:9b 90s | Tier 2 Llama3.1 120s | Tier 3 HuggingFace 30s")
    log("POST /infer - Process document (doc_id, task_type, content)")
    log("GET /metrics - View current metrics")
    log("GET /health - Health check")
    log("="*90)
    
    server = ThreadingHTTPServer((DAEMON_HOST, DAEMON_PORT), DaemonRequestHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Daemon shutting down...")
        final_metrics = router.get_metrics()
        log(f"Final metrics: {json.dumps(final_metrics, indent=2)}")
        server.shutdown()


if __name__ == "__main__":
    start_daemon()
