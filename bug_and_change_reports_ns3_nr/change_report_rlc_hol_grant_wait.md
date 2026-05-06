# Change Report: RLC HOL-to-Grant Wait Trace

## Summary
- Added a new RLC trace source to report per-PDU/segment **HOL-to-grant wait** time (time from becoming HOL to dequeue for TX).
- Wired the new trace into both `cellular-network` and `delay-benchmarking` scripts and documented the new log.
- Added visualization support for the new metric in `visualize_raw_data.py`.

## Files Changed
- `contrib/nr/model/nr-rlc.h`
- `contrib/nr/model/nr-rlc.cc`
- `contrib/nr/model/nr-rlc-um.h`
- `contrib/nr/model/nr-rlc-um.cc`
- `contrib/nr/model/nr-rlc-am.h`
- `contrib/nr/model/nr-rlc-am.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/delay-benchmarking.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/logging_documentation.txt`
- `contrib/nr/examples/5G-LENA-digital-twin-script/visualize_raw_data.py`

## New Log
- `RlcHolGrantWaitTrace.txt` (columns: `time_us`, `cell_id`, `rnti`, `lcid`, `pdu_size`, `hol_grant_wait_us`)

## Notes
- HOL time is set when a PDU becomes the front of the TX buffer and **preserved** for partial reinsertions.
- The new metric is logged at dequeue time in the RLC `DoNotifyTxOpportunity` path.
