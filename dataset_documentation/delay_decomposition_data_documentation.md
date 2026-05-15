# 5G-LENA Delay Components as extracted using script `create_delay_decomposition_data.py`

The script first filters data traffic where possible: `msg_type == DATA` and `lcid >= 3`. This is done to separate data from control. 

## Output CSV Columns

These csv files contain one row per UL PDCP data packet with a valid packet id. The base row is keyed by `(rnti, lcid, pkt_id)` so packets from different logical channels are identifiable.

| Column | Unit | Metric |
|---|---:|---|
| `rnti` | count | UE RNTI for the packet. |
| `lcid` | count | Logical channel ID identifying the radio bearer for the packet. |
| `pkt_id` | count | Packet id used to align packet records across trace layers. |
| `pkt_size_bytes` | bytes | Packet size at receiver-side PDCP. |
| `pdcp_rx_time_us` | us | Time when receiver-side PDCP receives the packet. |
| `ran_delay_ms` | ms | RAN delay. Sender-PDCP to receiver-PDCP delay. |
| `pre_hol_wait_ms` | ms | Queue wait before the packet becomes head-of-line. |
| `hol_wait_ms` | ms | Head-of-line wait before grant/dequeue for the first RLC segment of the packet. |
| `queueing_delay_ms` | ms | Combined RLC queueing delay for the first RLC segment of the packet, computed as `pre_hol_wait_ms + hol_wait_ms` |
| `frame_alignment_delay_ms` | ms | Delay from UE-side PDCP TX time to the next matched UE scheduling request. |
| `scheduling_delay_ms` | ms | Delay from the matched UE scheduling request to the first RLC segment transmission for the packet. |
| `tx_retx_delay_ms` | ms | Transmission plus retransmission delay of the RLC segment of this packet with the largest delay. |
| `link_delay_ms` | ms | Delay from first grant/dequeue to final receiver-side RLC receive event for the packet. |
| `delay_residual_ms` | ms | Difference between the RAN delay and the components expected to explain it, computed as `ran_delay_ms - (queueing_delay_ms + link_delay_ms)`. |
| `segmentation_delay_ms` | ms | Delay due to RLC segmentation of the packet. It is defined as the extra link delay not explained by transmission plus retransmission delay of the RLC segment with the largest delay. |
| `reordering_delay_ms` | ms | Delay after all receiver-side RLC components for a packet are seen, until receiver-side PDCP receives the packet. This delay captures RLC waiting for reordering/window logic before pushing up the segments into the PDCP. |
| `rlc_segments_per_pkt` | count | Number of distinct RLC sequence numbers associated with the packet. |

Refer to raw_ns3_data_documentation.md for information about the source logs. 
