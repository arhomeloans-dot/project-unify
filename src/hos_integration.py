"""
HOS Integration Layer — Project Unify Daemon Client

Provides a simple interface for the three-agent pipeline (Scribe, AssistantLibrarian, 
Archivist) to submit documents for routing and get results.

Usage from any agent:
    from hos_integration import route_document
    
    result = route_document(
        doc_id="uuid-12345",
        task_type="classify",  # classify, reconcile, extract_entities, summarize, judicial
        content="Document text here..."
    )
    
    # Result contains:
    {
        "doc_id": "uuid-12345",
        "actual_tier": "tier1_local",  # or tier2_kimi, tier2_glm, tier3_claude
        "latency_ms": 24290.1,
        "cost_usd": 0.0,
        "confidence": 0.75,
        "success": true,
        "result_snippet": "..."
    }
"""

import requests
import json
import logging
from typing import Dict, Any, Optional

# Daemon connection
DAEMON_URL = "http://localhost:11435"
TIMEOUT = 60  # seconds to wait for daemon response

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hos_integration")


class DaemonConnectionError(Exception):
    """Raised when daemon is unreachable"""
    pass


class RoutingError(Exception):
    """Raised when routing fails"""
    pass


def route_document(
    doc_id: str,
    task_type: str,
    content: str,
    retries: int = 1
) -> Dict[str, Any]:
    """
    Submit a document for three-tier routing.
    
    Args:
        doc_id: Unique document identifier (UUID or internal ID)
        task_type: One of: classify, summarize, extract_entities, reconcile, judicial
        content: Document text to process
        retries: Number of retry attempts if daemon is busy
    
    Returns:
        Dictionary with routing decision, latency, cost, confidence, and result
    
    Raises:
        DaemonConnectionError: If daemon is unreachable
        RoutingError: If routing fails
    """
    
    payload = {
        "doc_id": doc_id,
        "task_type": task_type,
        "content": content
    }
    
    for attempt in range(retries):
        try:
            logger.info(f"Routing {doc_id} | task={task_type} | attempt={attempt+1}/{retries}")
            
            response = requests.post(
                f"{DAEMON_URL}/infer",
                json=payload,
                timeout=TIMEOUT
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"  ✓ Routed to {result['actual_tier']} | latency={result['latency_ms']:.1f}ms | cost=${result['cost_usd']:.6f}")
                return result
            
            elif response.status_code == 400:
                raise RoutingError(f"Bad request: {response.json()}")
            
            elif response.status_code == 500:
                error = response.json().get("error", "Unknown error")
                logger.warning(f"  Routing failed: {error}")
                if attempt < retries - 1:
                    logger.info(f"  Retrying...")
                    continue
                raise RoutingError(f"Daemon error: {error}")
            
            else:
                raise RoutingError(f"Unexpected status {response.status_code}")
        
        except requests.exceptions.ConnectionError as e:
            if attempt < retries - 1:
                logger.warning(f"  Daemon unreachable, retrying...")
                continue
            raise DaemonConnectionError(
                f"Cannot connect to daemon at {DAEMON_URL}. "
                f"Ensure project_unify_daemon.py is running."
            ) from e
        
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                logger.warning(f"  Daemon timeout, retrying...")
                continue
            raise DaemonConnectionError(f"Daemon timed out after {TIMEOUT}s")
    
    raise RoutingError("All retry attempts exhausted")


def get_metrics() -> Dict[str, Any]:
    """Fetch current routing metrics from daemon"""
    try:
        response = requests.get(f"{DAEMON_URL}/metrics", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            raise DaemonConnectionError(f"Failed to fetch metrics: {response.status_code}")
    except requests.exceptions.RequestException as e:
        raise DaemonConnectionError(f"Cannot reach daemon metrics: {e}")


def is_daemon_healthy() -> bool:
    """Quick health check - returns True if daemon is running"""
    try:
        response = requests.get(f"{DAEMON_URL}/health", timeout=2)
        return response.status_code == 200
    except:
        return False


# Example usage from agents
if __name__ == "__main__":
    print("HOS Integration Layer — Test\n")
    
    # Check if daemon is running
    if not is_daemon_healthy():
        print("ERROR: Daemon is not running at http://localhost:11435")
        print("Start it with: python project_unify_daemon.py")
        exit(1)
    
    print("✓ Daemon is healthy\n")
    
    # Example: Scribe classification task
    try:
        result = route_document(
            doc_id="scribe_doc_001",
            task_type="classify",
            content="Quick document classification"
        )
        print(f"Scribe result: {json.dumps(result, indent=2)}\n")
    except (DaemonConnectionError, RoutingError) as e:
        print(f"Error: {e}\n")
    
    # Example: Archivist high-confidence verification
    try:
        result = route_document(
            doc_id="archivist_doc_001",
            task_type="judicial",
            content="High-stakes document verification for archive integrity"
        )
        print(f"Archivist result: {json.dumps(result, indent=2)}\n")
    except (DaemonConnectionError, RoutingError) as e:
        print(f"Error: {e}\n")
    
    # Get current metrics
    try:
        metrics = get_metrics()
        print(f"Current metrics:\n{json.dumps(metrics, indent=2)}")
    except DaemonConnectionError as e:
        print(f"Metrics error: {e}")
