# 5G-LENA Delay Components as extracted using script `delay_decomposition.py`

The script first filters data traffic where possible: `msg_type == DATA` and `lcid >= 3`. This is done to separate data from control. 

## Output CSV columns

`sim_campaign_logs/benchmarking_traffic/delay_decomposition_data/benchmarkNN_5Glena_delay_decomposition.csv` contains one row per selected UL delay-probe packet where data is available.

| Column | Unit | Meaning / derivation | Source logs |
|---|---:|---|---|
| `rnti` | count | UE RNTI selected for the delay-probe flow. | Joined from delay decomposition source logs. |
| `pkt_id` | count | Per-node packet id used to join packet records across trace files. | Joined from delay decomposition source logs. |
| `pkt_uid` | count | ns-3 packet UID from the app delay trace, when available. | `delay_trace.txt` |
| `pkt_size_bytes` | bytes | Application packet size from the app delay trace, when available. | `delay_trace.txt` |
| `app_tx_time_us` | us | Application transmit time, derived as `app_rx_time_us - delay_us`. | `delay_trace.txt` |
| `app_rx_time_us` | us | Application receive time at the UL UDP receiver. | `delay_trace.txt` |
| `ul_end_to_end_delay_ms` | ms | Full app-layer one-way UL delay, derived as `delay_us / 1000`. | `delay_trace.txt` |
| `pre_hol_wait_ms` | ms | RLC wait before the PDU/segment becomes HOL, derived as `pre_hol_wait_us / 1000`. | `RlcTxQueueSojournTrace.txt` |
| `hol_wait_ms` | ms | HOL wait before grant/dequeue, derived as `hol_grant_wait_us / 1000`. | `RlcHolGrantWaitTrace.txt` |
| `queueing_delay_ms` | ms | Combined RLC queueing delay, derived as `pre_hol_wait_ms + hol_wait_ms`. | `RlcTxQueueSojournTrace.txt`, `RlcHolGrantWaitTrace.txt` |
| `frame_alignment_delay_ms` | ms | Delay from UE PDCP TX to scheduling request, derived as `(sr_time_us - pdcp_tx_time_us) / 1000`; the SR is matched to the latest packet PDCP TX since the previous SR for the same UE. | `NrUlPdcpTxStats.txt`, `UePhyCtrlTxTrace.txt` |
| `scheduling_delay_ms` | ms | Delay from scheduling request to first RLC packet TX, derived as `(first_pkt_tx_time_us - sr_time_us) / 1000`; first packet TX is matched to the latest fresh SR for the same UE. | `UePhyCtrlTxTrace.txt`, `NrUlRlcTxComponentStats.txt` |
| `tx_retx_delay_ms` | ms | MAC/PHY transmission plus retransmission delay observed at gNB RLC, derived as the maximum per-packet RLC RX component `delay_us / 1000`. | `NrUlRlcRxComponentStats.txt` |
| `link_delay_ms` | ms | Delay from first grant/dequeue to final RLC RX for the packet, derived as `(last_rlc_rx_time_us - first_grant_time_us) / 1000`. | `RlcHolGrantWaitTrace.txt`, `NrUlRlcRxComponentStats.txt` |
| `segmentation_delay_ms` | ms | Extra link/RAN time not explained by tx + retx delay, derived as `link_delay_ms - tx_retx_delay_ms`. | Derived from link delay and `NrUlRlcRxComponentStats.txt` |
| `reordering_delay_ms` | ms | Delay from final RLC RX to first PDCP RX, derived as `(pdcp_rx_time_us - last_rlc_rx_time_us) / 1000`. | `NrUlRlcRxComponentStats.txt`, `NrUlPdcpRxStats.txt` |
| `rlc_segments_per_pkt` | count | Number of unique RLC sequence numbers used by the packet. | `NrUlRlcTxComponentStats.txt` |


Refer to raw_ns3_data_documentation.md for information about the source logs. 
