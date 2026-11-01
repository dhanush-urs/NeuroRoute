#!/usr/bin/env python3
"""
Wait for PostgreSQL database to be ready.
"""

import time
import socket
import sys


def wait_for_db(host: str = "postgres", port: int = 5432, max_attempts: int = 60, delay: float = 2.0) -> bool:
    """Wait for PostgreSQL database to be ready."""
    for i in range(max_attempts):
        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.close()
            print(f"Database is ready! (attempt {i+1}/{max_attempts})")
            return True
        except Exception:
            print(f"Waiting for database... (attempt {i+1}/{max_attempts})")
            time.sleep(delay)
    
    print(f"Database not ready after {max_attempts} attempts")
    return False


if __name__ == "__main__":
    success = wait_for_db()
    sys.exit(0 if success else 1)