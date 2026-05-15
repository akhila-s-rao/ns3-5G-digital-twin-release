# Parsed Uplink Columns

This documents the columns produced by `create_parsed_uplink_data.py` when run with `--direction UL` (the default). 
Parsed CSVs are written to `--output-dir` as `parsed_data_from_<run-dir-name>.csv`.

Metrics are resampled into fixed windows of `--window-ms` milliseconds, default `100`, from 0 to `--sim-duration`. For each time window a per-UE list of metrics are reported along with some metrics that provide the overall view of the cell at that time. This is to capture not only the metrics that are reported per UE, but also aggregate the overall demands from other UEs that share the same cell and hence the same resources.   

The metrics reported are for uplink access and filtered for the DATA radio bearers only. i.e. lcid >= 3.

All columns in the CSV files are described below. 

## Index Columns (3 columns)

| Column name | Unit | Meaning |
|---|---:|---|
| `time_us` | us | Beginning of the aggregation window. |
| `rnti` | id | UE RNTI |
| `cell_id` | id | connected Cell ID for the RNTI. |

## RAN Feature Columns
# Per-RNTI (per-UE) (11 columns)

| Column name | Unit | Window aggregation logic | Meaning | Impute empty window with |
|---|---:|---|---|---|
| `ue_buffer_bytes` | bytes | max | UE buffer size reported by BSR. | ffill |
| `ue_bsr_level` | index | median | BSR level index reported by BSR. | ffill |
| `ue_mac_num_retx` | count | max | HARQ retransmission state observed for the UE. | ffill |
| `ue_mac_mcs` | index | median | UL MCS index. | ffill |
| `ue_scheduled_tb_bytes` | bytes | sum | Transport block bytes scheduled for the UE in UL grants. | zero |
| `ue_scheduled_prbs` | PRBs | sum | Physical resource blocks allocated to the UE in UL grants. | zero |
| `ue_pdcp_pdu_bytes` | bytes | sum | UL PDCP PDU bytes received at gNB PDCP. | zero |
| `ue_rlc_pdu_bytes` | bytes | sum | UL RLC PDU bytes received at gNB RLC. | zero |
| `ue_sinr_db` | dB | median | UL SINR for TB decoding at gNB PHY. | ffill |
| `ue_cqi` | index | median | UL CQI reported/used for the TB. | ffill |
| `ue_tbler` | ratio | mean | UL TB error-rate estimate for TB decoding. | ffill |

# Cell-overall (5 columns)
| Column name | Unit | Window aggregation logic | Meaning | Impute empty window with |
|---|---:|---|---|---|
| `cell_rlc_pdu_bytes` | bytes | sum over cell | UL RLC PDU bytes received at gNB RLC across UEs connected to the cell. | zero |
| `cell_pdcp_pdu_bytes` | bytes | sum over cell | UL PDCP PDU bytes received at gNB PDCP across UEs connected to the cell. | zero |
| `cell_scheduled_prbs` | PRBs | sum over cell | UL PRBs allocated across UEs connected to the cell. | zero |
| `cell_scheduled_tb_bytes` | bytes | sum over cell | UL transport block bytes scheduled across UEs connected to the cell. | zero |
| `cell_buffer_bytes` | bytes | max over cell | Reported UL buffer size across UEs connected to the cell. | ffill |

## Application performance Columns (5 columns)
| Column name | Unit | Window aggregation logic | Meaning | Impute empty window with |
|---|---:|---|---|---|
| `ul_probe_rx_bytes` | bytes | sum per RNTI | UL delay probe packet bytes received by UDP server. | zero |
| `ul_probe_delay_us` | us | max per RNTI | UL delay over delay probe packets. | ffill |
| `ul_vr_fragment_bytes` | bytes | sum per RNTI | Estimated VR fragment bytes received by the VR server. | zero |
| `ul_vr_fragment_delay_us` | us | max per RNTI | UL delay of VR fragments. | ffill |
| `ul_vr_burst_bytes` | bytes | sum per RNTI | Received VR burst sizes. | zero |
