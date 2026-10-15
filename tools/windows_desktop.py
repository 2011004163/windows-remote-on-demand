#!/usr/bin/env python3
"""Convenience entrypoint; implementation is bundled with the portable Skill."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"skills/windows-remote-on-demand/scripts"))
from windows_desktop import main
if __name__ == "__main__":
    raise SystemExit(main())
