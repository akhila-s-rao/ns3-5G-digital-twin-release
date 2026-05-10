# 5G-LENA Delay Components as extracted using script `create_delay_decomposition_data.py`

The script first filters data traffic where possible: `msg_type == DATA` and `lcid >= 3`. This is done to separate data from control. 

## Source logs

The delay decomposition CSV is built from:

- `NrUlPdcpRxStats.txt`
- `NrUlPdcpTxStats.txt`
- `NrUlRlcRxComponentStats.txt`
- `NrUlRlcTxComponentStats.txt`
- `RlcTxQueueSojournTrace.txt`
- `RlcHolGrantWaitTrace.txt`
- `UePhyCtrlTxTrace.txt`

## Output CSV Columns

These csv files contain one row per UL PDCP data packet with a valid packet id. The base row is keyed by `(rnti, pkt_id)`.

| Column | Unit | Metric | Source logs |
|---|---:|---|---|
| `rnti` | count | UE RNTI for the packet. | `NrUlPdcpRxStats.txt` |
| `pkt_id` | count | Packet id used to align packet records across trace layers. | Obtained from all the delay decomposition source logs. |
| `pkt_size_bytes` | bytes | Packet size at receiver-side PDCP. | `NrUlPdcpRxStats.txt` |
| `pdcp_rx_time_us` | us | Time when receiver-side PDCP receives the packet. | `NrUlPdcpRxStats.txt` |
| `ran_delay_ms` | ms | RAN delay. Sender-PDCP to receiver-PDCP delay. | `NrUlPdcpRxStats.txt` |
| `pre_hol_wait_ms` | ms | Queue wait before the packet becomes head-of-line. | `RlcTxQueueSojournTrace.txt` |
| `hol_wait_ms` | ms | Head-of-line wait before grant/dequeue for the first RLC segment of the packet. | `RlcHolGrantWaitTrace.txt` |
| `queueing_delay_ms` | ms | Combined RLC queueing delay for the first RLC segment of the packet, computed as `pre_hol_wait_ms + hol_wait_ms` | `RlcTxQueueSojournTrace.txt`, `RlcHolGrantWaitTrace.txt` |
| `frame_alignment_delay_ms` | ms | Delay from packet arrival at UE-side PDCP to the scheduling request opportunity. | `NrUlPdcpTxStats.txt`, `UePhyCtrlTxTrace.txt` |
| `scheduling_delay_ms` | ms | Delay from scheduling request to first RLC segment transmission for the packet. | `UePhyCtrlTxTrace.txt`, `NrUlRlcTxComponentStats.txt` |
| `tx_retx_delay_ms` | ms | Transmission plus retransmission delay of the RLC segment with the largest delay. | `NrUlRlcRxComponentStats.txt` |
| `link_delay_ms` | ms | Delay from first grant/dequeue to final receiver-side RLC receive event for the packet. | `RlcHolGrantWaitTrace.txt`, `NrUlRlcRxComponentStats.txt` |
| `delay_residual_ms` | ms | Difference between the RAN delay and the components expected to explain it, computed as `ran_delay_ms - (queueing_delay_ms + link_delay_ms)`. | Derived from RAN delay, queueing delay, and link delay. |
| `segmentation_delay_ms` | ms | Delay due to RLC segmentation of the packet. It is defined as the extra link delay not explained by transmission plus retransmission delay of the RLC segment with the largest delay. | link delay - (transmission + retransmission delay). |
| `reordering_delay_ms` | ms | Delay after all receiver-side RLC components for a packet are seen, until receiver-side PDCP receives the packet. This delay captures RLC waiting for reordering/window logic before pushing up the segments into the PDCP.  | `NrUlRlcRxComponentStats.txt`, `NrUlPdcpRxStats.txt` |
| `rlc_segments_per_pkt` | count | Number of distinct RLC sequence numbers associated with the packet. | `NrUlRlcTxComponentStats.txt` |

Refer to raw_ns3_data_documentation.md for information about the source logs. 
