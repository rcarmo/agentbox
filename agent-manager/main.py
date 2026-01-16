#!/usr/bin/env python3
"""Main entry point for toadbox-manager."""

import sys
from pathlib import Path

# Add src to path for development
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from toadbox_manager import main

def main_entry():
    main()

if __name__ == "__main__":
    main_entry()
