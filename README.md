# ns3 5G Digital Twin Release

This repository is a combined release tree built on top of ns-3 with local changes in core ns-3, `contrib/nr`, `contrib/vr-app`, and the digital-twin scripts under `contrib/nr/examples/5G-LENA-digital-twin-script`.

## Scope

This repo is intended for reproducibility and sharing of the full simulator setup.
It is not a clean fork of upstream ns-3 or upstream NR.

Main custom content includes:

- modified ns-3 core files under `src/`
- modified NR files under `contrib/nr/model/`
- VR application code under `contrib/vr-app/`
- digital-twin and benchmarking scripts under `contrib/nr/examples/5G-LENA-digital-twin-script/`

## Upstream bases

This release was assembled from:

- ns-3 dev base commit: `ea50b72ab79b1ec5912c66d5b384effa829f18bc`
- NR base commit: `f29ebd33450c49af934ea5dde8606f855c22c2a6`
- vr-app base commit: `1903d6f2bd2b96994da9d7e6479ed72d68f25bd3`

If you need clean upstreamable changes later, extract them from this repo into separate forks.

## Build

Example build:

```bash
./ns3 configure
./ns3 build
```

## Run

Example scripts live in:

```text
contrib/nr/examples/5G-LENA-digital-twin-script/
```

Common entry points include:

- `run_parallel_sims.py`
- `run-parallel-benchmarking.py`
- `distribution_compare.py`
- `visualize_raw_data.py`

Run them from the repo root or from the script directory, depending on the script.

## Notes

- build outputs and generated logs are not intended to be versioned
- if a script depends on local datasets or logs, provide those separately
- licensing for upstream components remains governed by their original licenses in this tree

