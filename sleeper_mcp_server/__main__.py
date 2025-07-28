"""Main entry point for the Sleeper MCP server."""

import asyncio
import sys
from typing import Optional

from .server import main as server_main


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point for the Sleeper MCP server.
    
    Args:
        args: Command line arguments (defaults to sys.argv[1:])
        
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    if args is None:
        args = sys.argv[1:]
    
    try:
        # Run the MCP server
        asyncio.run(server_main())
        return 0
    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())