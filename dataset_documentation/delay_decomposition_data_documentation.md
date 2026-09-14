# 5G-LENA Delay Components as extracted using script `create_delay_decomposition_data.py`

The script first filters identifiable data traffic where possible: `msg_type == DATA`,
`lcid >= 3`, and `pkt_id > 0`. This separates data from control and excludes zero-valued
sentinel IDs emitted when no packet-identification tag is available.

By default, the output includes every qualifying UL data packet, including background
traffic. Pass `--delay-probes-only` to retain only packets matched to UL receptions in
`delay_trace.txt`. Matching uses the same RNTI, the corresponding PDCP packet size, and the
nearest PDCP sender timestamp within 100 us, then verifies that the application reception
follows the receiver-side PDCP timestamp by no more than 100 us. This packet-level match
avoids including non-probe traffic merely because it uses the same UE or LCID. A run is
skipped with a warning if `delay_trace.txt` is unavailable; unmatched probe receptions are
omitted and reported in a warning. Probe packet keys are selected before packet-level delay
decomposition so non-probe PDCP, RLC, queue-sojourn, and HOL-wait rows do not undergo the
expensive grouping and joining steps. MAC and SR traces retain their complete timing context.

Runs are processed in parallel when multiple run directories are found. `--jobs` sets the
maximum number of worker processes and defaults to at most 4; use `--jobs=1` for sequential
processing.

## Output CSV Columns

These csv files contain one row per UL PDCP data packet with a valid positive packet id. The base row is keyed by `(rnti, lcid, pkt_id)` so packets from different logical channels are identifiable.

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
| `queueing_delay_ms` | ms | EXPECA-aligned interval from UE PDCP transmission/RLC enqueue to a virtual dequeue one millisecond before the scheduled PUSCH carrying the packet's first RLC component. If DCI processing occurs less than one millisecond before PUSCH, the virtual dequeue is clamped to the actual DCI/RLC-dequeue timestamp. |
| `frame_alignment_delay_ms` | ms | Interval from UE-side PDCP TX to the start of the eligible slot in which a strictly matched initial scheduling request is transmitted. This removes the intra-slot UL-control-symbol offset from the metric. |
| `scheduling_delay_ms` | ms | Interval from UE-side PDCP TX/RLC enqueue to UE reception and processing of the UL DCI for the packet's first RLC component, populated only when the packet has a strictly matched initial scheduling request. It includes `frame_alignment_delay_ms` but excludes the subsequent initial K2 wait. |
| `tx_retx_delay_ms` | ms | Interval from the EXPECA-aligned virtual dequeue to receiver-side RLC reception for the RLC segment of this packet with the largest delay. It includes the final one millisecond before the initial PUSCH and subsequent HARQ retransmission cycles. |
| `link_delay_ms` | ms | Delay from the packet's first EXPECA-aligned virtual dequeue to its final receiver-side RLC receive event. |
| `delay_residual_ms` | ms | Unexplained difference after subtracting queueing, link, and receiver-side reordering delay from RAN delay, computed as `ran_delay_ms - (queueing_delay_ms + link_delay_ms + reordering_delay_ms)`. |
| `segmentation_delay_ms` | ms | Delay due to RLC segmentation of the packet. It is defined as the extra link delay not explained by transmission plus retransmission delay of the RLC segment with the largest delay. |
| `reordering_delay_ms` | ms | Delay after all receiver-side RLC components for a packet are seen, until receiver-side PDCP receives the packet. This delay captures RLC waiting for reordering/window logic before pushing up the segments into the PDCP. |
| `rlc_segments_per_pkt` | count | Number of distinct RLC sequence numbers associated with the packet. |
| `transport_block_size_total_bytes` | bytes | Sum of scheduled transport-block sizes for the packet's initial (`RV=0`) RLC transmissions. HARQ retransmissions are excluded so that the same transport block is not counted repeatedly. |
| `resource_block_size_total` | PRBs | Sum of physical resource blocks allocated across all MAC attempts associated with the packet, including HARQ retransmissions. |

## Scheduling-request matching

`UePhyCtrlTxTrace.txt` supplies the actual SR transmission timestamp and its frame, subframe,
and slot. The parser derives the start of that slot and uses it as the frame-alignment
endpoint; the later PHY timestamp remains part of strict match validation.
`UeMacSrTriggerTrace.txt` identifies why UE MAC requested that SR. The script pairs an SR with
a trigger preceding the SR slot start for the same RNTI within 7 ms using chronological
one-to-one matching.
Matching is performed backwards in time so that two triggers pending before consecutive
UL-control opportunities retain their order and neither trigger is reused. Only triggers
marked `INITIAL` are retained for delay decomposition. `RECOVERY` SRs caused by
`NrUeMac::RetxBsrTimer` are excluded from both SR-derived columns.

The script derives both SR-based components from one shared packet-to-initial-SR match.
An initial SR trigger is attributed to the latest preceding PDCP packet for that UE, and the
match is retained only when
`PDCP TX <= initial SR trigger <= SR slot start <= SR transmission <= first RLC TX opportunity`.
For a retained match, `frame_alignment_delay_ms` is the initial portion of
`scheduling_delay_ms`. The remaining interval between `scheduling_delay_ms` and the directly
measured `queueing_delay_ms` is the initial DCI-to-virtual-dequeue interval, normally about
two milliseconds with the EXPECA profile. If no initial SR satisfies this ordering, both
SR-derived columns remain empty for that packet.

## RLC-to-PUSCH matching

`NrUlRlcTxComponentStats.txt` identifies the packet and RLC segment dequeued after an UL
grant. `NrUlMacStats.txt` supplies the grant timestamp and `send_start_time_delta_us`, from
which the scheduled PUSCH start is computed. Each RLC component is matched to the immediately
preceding DATA grant for the same RNTI within 100 us. Unmatched components are not assigned
PUSCH-based delay values and are reported in a warning. For EXPECA-aligned accounting, the
virtual dequeue is one millisecond before PUSCH, clamped to the actual DCI/RLC-dequeue time
when necessary. The DCI-to-virtual-dequeue part of K2 is included in queueing delay, while
the final virtual-dequeue-to-PUSCH part is included in `tx_retx_delay_ms`. HARQ
retransmission waits remain in `tx_retx_delay_ms`.

If `UeMacSrTriggerTrace.txt` is absent, as it is in datasets generated before the
SR/BSR recovery correction, the script prints a warning and omits
`frame_alignment_delay_ms` and `scheduling_delay_ms`. It does not fall back to treating every
SR as an initial request. All non-SR delay components can still be generated.

Refer to raw_ns3_data_documentation.md for information about the source logs. 
