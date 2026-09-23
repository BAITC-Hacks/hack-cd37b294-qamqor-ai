"""Live HTTP smoke: validates service health without faking an LLM call."""
import argparse
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=10) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["status"] == "ok"
        ready = client.get("/ready")
        assert ready.status_code in (200, 503)
        print(f"Live HTTP health: PASS; readiness HTTP {ready.status_code}")
        if ready.status_code == 503:
            print("API configuration missing; no LLM metrics claimed.")


if __name__ == "__main__":
    main()
