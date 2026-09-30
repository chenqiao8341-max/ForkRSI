"""CLI for the persistent research campaign."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from forkmem.rsi.campaign import run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("search", "freeze", "final"))
    parser.add_argument("--root", type=Path, default=Path("runs/forkrsi/campaign-v1"))
    parser.add_argument("--source", type=Path, default=Path("runs/forkrsi/source-v1"))
    parser.add_argument(
        "--protocol", type=Path, default=Path("configs/forkrsi/protocol-v1.json")
    )
    args = parser.parse_args()
    asyncio.run(run(args.root, args.source, args.protocol, args.phase))


if __name__ == "__main__":
    main()
