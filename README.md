# ns-3 5G Digital Twin Release

The objective of this codebase is to bring together various ns-3 components and create 5G simulation scripts that can be used to study network and user performance under various scenarios, and to generate datasets for training machine learning models for KPI prediction.

## What’s in this folder

This repository keeps the ns-3 source tree under `ns3-code/`, with dataset documentation and data-processing scripts kept outside the simulator tree.

The `ns3-code/` directory is a combined release tree built on top of ns-3 with local changes in core ns-3, `contrib/nr`, `contrib/vr-app`, and the custom digital-twin 5G simulation scripts under `ns3-code/contrib/nr/examples/5G-LENA-digital-twin-script/`.
This repo is intended for reproducibility and sharing of the full simulator setup.
It is not a clean fork of upstream ns-3 or upstream NR.

Main custom content includes:

- modified ns-3 core files under `ns3-code/src/`
- modified NR files under `ns3-code/contrib/nr/model/`
- VR application code under `ns3-code/contrib/vr-app/`
- custom 5G simulation setup scripts under `ns3-code/contrib/nr/examples/5G-LENA-digital-twin-script/`
- data-processing scripts under `data_processing_scripts/`
- dataset and trace documentation under `dataset_documentation/`

## Upstream bases

This release was assembled from:

- ns-3 dev base commit: `ea50b72ab79b1ec5912c66d5b384effa829f18bc`
- NR base commit: `f29ebd33450c49af934ea5dde8606f855c22c2a6`
- vr-app base commit: `1903d6f2bd2b96994da9d7e6479ed72d68f25bd3`

If you need clean upstreamable changes later, extract them from this repo into separate forks.
Some bugs in the main source code have been fixed. A few feature additions have also been made to improve the tracing and logging capability of the simulation. Bug reports and change reports for these are provided in `bug_and_change_reports_ns3_nr/`.

## Build

Build from inside the ns-3 source tree:

```bash
cd ns3-code
./ns3 configure -d optimized --enable-examples
./ns3 build
```

If you also want the ns-3 tests enabled, use:

```bash
cd ns3-code
./ns3 configure -d optimized --enable-examples --enable-tests
./ns3 build
```

## Run simulations to generate data

The custom scripts we have created to generate data live in:

```text
ns3-code/contrib/nr/examples/5G-LENA-digital-twin-script/
```

Scripts `cellular-network-user.cc` and `delay-benchmarking-user.cc` create the two main dataset-generation scenarios. The experiment setup, dataset links, and data-format documentation are collected in [dataset_documentation/README.md](dataset_documentation/README.md).

### Batch runners for large simulation campaigns
These scripts help setup a simulation campaign with multiple simulations in parallel over multiple parameter settings:

- `run-parallel-bursty-traffic-sims.py`
- `run-parallel-benchmarking-sims.py`

Both runners can be launched from any working directory. They locate the ns-3 tree from their own file path and require `--output-dir`; generated logs are written to the directory you choose rather than to a hardcoded campaign folder.

### Data analysis, visualization and processing scripts 
These scripts live in `data_processing_scripts/`.

- `compare_delay_decomposition_distributions.py`: compares ExPeCA delay-decomposition CSVs against generated 5G-LENA delay-decomposition CSVs and writes histogram, CDF, and packet-index series plots to `--output-dir`.
- `create_parsed_uplink_data.py`: aggregates raw ns-3 trace logs into aligned per-RNTI time-window CSVs for uplink feature/metric analysis.
- `create_delay_decomposition_data.py`: creates per-packet 5G-LENA delay-decomposition CSVs from raw 5G-LENA trace logs and writes them to `--output-dir`.
- `visualize_raw_data.py`: generates per-RNTI raw-trace histograms, CDFs, timeseries plots, and summary text inside each run directory.

## Datasets and Documentation

You can also download the datasets that we have generated along with its documentation.
Dataset access, experiment setup, and data-format documentation are here:

- [Dataset documentation](dataset_documentation/README.md)

## Notes

- build outputs and generated logs are not intended to be versioned
- if a script depends on local datasets or logs, provide those separately
- licensing for upstream components remains governed by their original licenses in this tree
