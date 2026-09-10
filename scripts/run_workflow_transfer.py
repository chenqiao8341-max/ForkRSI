import argparse
import asyncio
from pathlib import Path

from forkmem.workflows.benchmark import transfer

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument(
    "--config", type=Path, default=Path("configs/experiments/v2/transfer.yaml")
)
parser.add_argument("--resume", action="store_true")
args = parser.parse_args()
print(asyncio.run(transfer(args.source, args.config, args.output, resume=args.resume)))
