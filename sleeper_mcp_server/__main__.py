"""Entry point for the Sleeper MCP server."""

import logging
import sys


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )
    from .server import mcp
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
