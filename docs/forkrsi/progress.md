# Progress

2026-09-30: Goal created; original target persisted; baseline copied with Git provenance; budget recorded. No experiment results yet. Missing raw historical corpus requires new collection. Container namespace support is an infrastructure obstacle under investigation.

Infrastructure: system Python3.10/Bubblewrap installed; native Bubblewrap fails due to prohibited namespaces. Explicit chroot-seccomp backend passes host isolation, read-only verifier, TCP/UDP and process-spawning probes; result at runs/forkrsi/sandbox-probe/result.json. C/I typed objects and append-only ledger implemented; tests pending Python3.13 environment install. Frozen local model service and rental budget check prepared. No new model experiment or RSI claim yet.

Python3.13 downloader PID 4152 confirmed live but on its third network retry. It remains running. An isolated system-site-packages Python3.12 runtime is being prepared in parallel to reuse the existing Torch installation and enable integration checks. This is an explicit runtime adaptation; project requires-python is unchanged, actual versions will be recorded, and Python3.13 validation remains planned. All experimental conditions will use the same recorded runtime. Inference output ceiling fixed to 8192 to support the original fork proposal max_tokens=6000.

- Python 3.13 official standalone download failed after three transport/extraction retries (bootstrap.log preserved); no incomplete archive is used. Independent Python 3.12.3 runtime installation remains live. This adaptation is infrastructure, not a relaxation of execution evidence or an experiment result.

## Current status, 2026-10-01

Python3.12 research runtime completed; exact dependency freeze and constraints saved. Original >=3.13 metadata/lock unchanged; Python3.13 validation unverified. Local frozen Qwen3.5-4B service ready, GPU resident ~8975MiB. Toy Action and Proposals requests parse first attempt; throughput ~16–21 tokens/sec, usage logged, no paid API.

Seccomp originally blocked asyncio socket pairs: eight original async tasks failed. It now allows Unix socket pairs and destination-free sends; external connect/listening/addressed UDP remains denied. Isolation probes pass again; original full suite73/73 and two added I1 consumption/source isolation tests2/2 pass. Strict mypy passes7 new/affected files.

All18 new tasks pass full witness verifier (146 nested cases). Archived partial-repair/falsified case replay matches4 branches: failure/success/failure/success. These are infrastructure results only.

C extraction/rendering, actual I-driven C/I proposals, append-only lineage, paired comparisons, independent selection, I reset and sealed final grid implemented. Protocol:4 development,2 selection,4 reset,8 final tasks; each arm3 C proposals (2 by I0,1 by actual I1),<=1500 cap,shared positive candidate IDs. Reset:2 proposals per I from C0. Final includes initial C controls.

Next: collect/audit new source episodes and branches, run search/reset, seal final. No model task-result or RSI improvement claim yet. Reproduction: docs/forkrsi/reproduce.md.
