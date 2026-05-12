# Parsed Uplink Columns

This documents the columns produced by `create_parsed_uplink_data.py` when run with `--direction UL` (the default). The script selects logs whose configured direction contains `UL`, including mixed `UL/DL` application traces, and filters mixed-direction traces to UL when a `direction` column exists. 

Rows are keyed by `time_us` window start and `rnti`; `cell_id` is mapped from raw logs when available.

Metrics are resampled into fixed windows of `--window-ms` milliseconds, default `100`, from 0 to `--sim-duration`.

Per-RNTI and cell-level features use descriptive output names. The tables below list the raw source log and raw metric for each output column. Cell-level features are only created for `packet_size`, `num_prbs`, `tb_size`, and `queue_bytes` from non-application traces.

Missing logs are skipped, so a parsed CSV only contains columns for raw log files present in that run directory.

Parsed CSVs are written to `--output-dir` as `parsed_data_from_<run-dir-name>.csv`.

## Index Columns (3 columns)

| Column name | Unit | Meaning |
|---|---:|---|
| `time_us` | us | Left edge of the aggregation window. |
| `rnti` | id | UE RNTI |
| `cell_id` | id | connected Cell ID for the RNTI. |

## RAN Feature Columns
# Per-RNTI (per-UE) (11 columns)

| Column name | Raw log | Raw metric | Unit | Window aggregation logic | Impute empty window with | Meaning |
|---|---|---|---:|---|---|---|
| `ue_buffer_bytes` | `GnbBsrTrace.txt` | `queue_bytes` | bytes | max per RNTI | ffill | UE buffer size reported by BSR. |
| `ue_bsr_level` | `GnbBsrTrace.txt` | `bsr_level` | index | median per RNTI | ffill | BSR level index reported by UE MAC. |
| `ue_mac_rv` | `NrUlMacStats.txt` | `rv` | index | max per RNTI | ffill | Redundancy version for DATA UL grants. |
| `ue_mac_mcs` | `NrUlMacStats.txt` | `mcs` | index | median per RNTI | ffill | MCS index for DATA UL allocations. |
| `ue_scheduled_tb_bytes` | `NrUlMacStats.txt` | `tb_size` | bytes | sum per RNTI | zero | UL transport block bytes scheduled for the RNTI. |
| `ue_scheduled_prbs` | `NrUlMacStats.txt` | `num_prbs` | PRBs | sum per RNTI | zero | UL PRBs allocated to the RNTI. |
| `ue_pdcp_pdu_bytes` | `NrUlPdcpRxStats.txt` | `packet_size` | bytes | sum per RNTI | zero | UL PDCP PDU bytes received at gNB PDCP. |
| `ul_rlc_pdu_bytes` | `NrUlRlcRxStats.txt` | `packet_size` | bytes | sum per RNTI | zero | UL RLC PDU bytes received at gNB RLC. |
| `ue_sinr_db` | `UlRxTbTrace.txt` | `sinr_db` | dB | median per RNTI | ffill | SINR for UL TB decoding at gNB PHY. |
| `ue_cqi` | `UlRxTbTrace.txt` | `cqi` | index | median per RNTI | ffill | CQI reported/used for the UL TB. |
| `ue_tbler` | `UlRxTbTrace.txt` | `tbler` | ratio | mean per RNTI | ffill | TB error-rate estimate for UL TB decoding. |

# Per-cell (5 columns)

| `cell_rlc_pdu_bytes` | `NrUlRlcRxStats.txt` | `packet_size` | bytes | sum over cell | zero | Total UL RLC PDU bytes received at gNB RLC. |
| `cell_pdcp_pdu_bytes` | `NrUlPdcpRxStats.txt` | `packet_size` | bytes | sum over cell | zero | Total UL PDCP PDU bytes received at gNB PDCP. |
| `cell_scheduled_prbs` | `NrUlMacStats.txt` | `num_prbs` | PRBs | sum over cell | zero | Total UL PRBs allocated in the window. |
| `cell_scheduled_tb_bytes` | `NrUlMacStats.txt` | `tb_size` | bytes | sum over cell | zero | Total UL transport block bytes scheduled in the window. |
| `cell_buffer_bytes` | `GnbBsrTrace.txt` | `queue_bytes` | bytes | max over cell | ffill | Overall max reported UL buffer size in the window. |

## Application performance Columns (6 columns)

| `ul_probe_rx_bytes` | `delay_trace.txt` | `pkt_size` | bytes | sum per RNTI | zero | UL app packet bytes received by UDP server. |
| `ul_probe_delay_us` | `delay_trace.txt` | `delay_us` | us | max per RNTI | ffill | Max one-way UL app delay in the window. |
| `ul_vr_fragment_burst_bytes` | `vrFragment_trace.txt` | `burst_size` | bytes | sum per RNTI | zero | Sum of burst-size values on received VR fragments. |
| `ul_vr_fragment_delay_us` | `vrFragment_trace.txt` | `delay_us` | us | max per RNTI | ffill | Max one-way VR fragment delay in the window. |
| `ul_vr_burst_bytes` | `vrBurst_trace.txt` | `burst_size` | bytes | sum per RNTI | zero | Sum of received VR burst sizes. |
| `ul_vr_burst_fragments` | `vrBurst_trace.txt` | `num_frags` | count | sum per RNTI | zero | Sum of fragment counts reported for received VR bursts. |


## Columns common between Expeca and 5G-SMARt testbeds
