"""Concurrent HTTP load test for Placement Copilot."""

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONCURRENCIES = (1, 10, 25)


def percentile(values, proportion):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(proportion * len(ordered)) - 1)
    return round(ordered[index], 3)


def send_request(api_url, path, question, api_key, timeout_seconds):
    url = api_url.rstrip("/") + path
    headers = {}
    data = None
    method = "GET"
    if path == "/ask":
        data = json.dumps({"question": question}).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    if api_key:
        headers["X-API-Key"] = api_key

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
            status_code = response.status
    except urllib.error.HTTPError as error:
        status_code = error.code
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = {}
    except (urllib.error.URLError, TimeoutError) as error:
        return {
            "status_code": None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": str(error),
        }

    return {
        "status_code": status_code,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "degraded": bool(body.get("degraded") or body.get("error")),
        "timings_ms": body.get("timings_ms"),
    }


def run_wave(api_url, path, question, api_key, timeout_seconds, concurrency, requests_per_client):
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                send_request,
                api_url,
                path,
                question,
                api_key,
                timeout_seconds,
            )
            for _ in range(concurrency * requests_per_client)
        ]
        outcomes = [future.result() for future in futures]
    elapsed_seconds = time.perf_counter() - started

    status_counts = Counter(
        str(outcome["status_code"]) if outcome["status_code"] is not None else "network_error"
        for outcome in outcomes
    )
    latencies = [outcome["elapsed_ms"] for outcome in outcomes]
    successful = sum(
        outcome["status_code"] is not None and outcome["status_code"] < 400
        for outcome in outcomes
    )
    degraded = sum(outcome.get("degraded", False) for outcome in outcomes)
    return {
        "concurrency": concurrency,
        "requests_per_client": requests_per_client,
        "requests": len(outcomes),
        "successful_http_responses": successful,
        "degraded_responses": degraded,
        "status_counts": dict(status_counts),
        "wall_time_seconds": round(elapsed_seconds, 3),
        "throughput_requests_per_second": round(len(outcomes) / elapsed_seconds, 3)
        if elapsed_seconds else None,
        "successful_throughput_per_second": round(successful / elapsed_seconds, 3)
        if elapsed_seconds else None,
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "per_request": outcomes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("LOADTEST_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("LOADTEST_API_KEY"))
    parser.add_argument("--path", choices=("/ask", "/health", "/ready"), default="/ask")
    parser.add_argument(
        "--question",
        default=os.getenv(
            "LOADTEST_QUESTION",
            "Which eligibility rules apply to quantum weather forecasting?",
        ),
    )
    parser.add_argument("--requests-per-client", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--name", default="current")
    args = parser.parse_args()
    if args.requests_per_client < 1:
        parser.error("--requests-per-client must be positive")

    results = [
        run_wave(
            args.api_url,
            args.path,
            args.question,
            args.api_key,
            args.timeout,
            concurrency,
            args.requests_per_client,
        )
        for concurrency in CONCURRENCIES
    ]
    report = {
        "name": args.name,
        "path": args.path,
        "question": args.question if args.path == "/ask" else None,
        "results": results,
    }
    output_path = BASE_DIR / f"loadtest_results_{args.name}.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("clients | requests | throughput req/s | p50 ms | p95 ms | degraded | statuses")
    for result in results:
        print(
            f"{result['concurrency']} | {result['requests']} | "
            f"{result['throughput_requests_per_second']} | "
            f"{result['latency_p50_ms']} | {result['latency_p95_ms']} | "
            f"{result['degraded_responses']} | {result['status_counts']}"
        )
    print("Saved:", output_path.name)


if __name__ == "__main__":
    main()
