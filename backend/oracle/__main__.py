"""Start the API server: python -m oracle [--port 8000] [--reload]"""

import argparse
import logging

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="oracle")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    uvicorn.run("oracle.api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
