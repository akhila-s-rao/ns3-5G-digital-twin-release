# 5G-LENA Digital Twin (ns-3 NR / 5G-LENA)

This folder contains the ns-3 NR (5G-LENA) simulation scripts and analysis tools
used to generate datasets across scenarios and study network behavior.

## What’s in this folder

### Core simulations
- `cellular-network.cc/.h` and `cellular-network-user.cc`  
  Main simulation and CLI entry point for the digital‑twin scenario.

### Batch runners for large simulation campaigns
- `run_parallel_sims.py`  
  Batch runner for `cellular-network`. Create a list of various input parameters to setup multiple parallel simulations. 

### Analysis & visualization
- `create_parsed_logs.py`  
  Aggregates raw trace logs into parsed outputs.
- `visualize_raw_data.py`  
  Generates per‑RNTI plots (histograms/CDFs/time series).


### Documentation & reports
- `logging_documentation.txt`  
  Log/trace documentation and column definitions.
- `bug_report_*.md`, `beamid-harq-rr-segv-report.md`, `harq-retx-bug-report.md`  
  Reports of the bug fixes to the current ns-3 and 5G-LENA code to enable running these simulations.
  If you want to fix these in your existing ns-3/5G-LENA then use the description in the report to make the changes. 
  You could also alternatively get the ns-3/5G-LENA installation along with the VR-app used for traffic generation here <Yet to add link to my updated verison of ns-3/5G-LENA/VR-app code>.   
- `rlc_tx_queue_sojourn_trace_report.md`  
  Tracing extensions to the existing 5G-LENA trace sources fo rincreased visibility. 

## Getting started

1. Build ns‑3 with the NR module as usual.
2. Apply bug fixes and tracing extensions to ns-3 and 5G-LENA
3. Run:
   - `cellular-network-user.cc` (digital‑twin scenario), or
3. Use the Python scripts in this folder to parse or visualize the logs.
