# 5G-LENA Delay Components as extracted using script `distribution_compare.py`

The script first filters data traffic where possible: `msg_type == DATA` and `lcid >= 3`.

## Components

| Component | Unit | Meaning | Source logs |
|---|---:|---|---|
| UL end-to-end delay | ms | Full app-layer one-way UL delay observed at the UDP receiver. | `delay_trace.txt` |
| Queueing delay | ms | RLC waiting time before becoming HOL plus waiting as HOL before grant/dequeue. | `RlcTxQueueSojournTrace.txt`, `RlcHolGrantWaitTrace.txt` |
| Pre-HOL queue wait | ms | Time spent in RLC TX queue before the PDU/segment becomes HOL. | `RlcTxQueueSojournTrace.txt` |
| HOL grant wait | ms | Time from becoming HOL until dequeue for transmission. | `RlcHolGrantWaitTrace.txt` |
| Frame alignment delay | ms | Time from UE PDCP packet arrival to the scheduling request used for that packet. | `NrUlPdcpTxStats.txt`, `UePhyCtrlTxTrace.txt` |
| Scheduling delay | ms | Time from scheduling request to first RLC packet transmission. | `UePhyCtrlTxTrace.txt`, `NrUlRlcTxComponentStats.txt` |
| tx + retx delay | ms | RLC transmission plus retransmission delay observed at gNB RLC. | `NrUlRlcRxComponentStats.txt` |
| Link/RAN delay | ms | Time from first grant/dequeue to last RLC RX for the packet. Used to derive segmentation delay. | `RlcHolGrantWaitTrace.txt`, `NrUlRlcRxComponentStats.txt` |
| Segmentation delay | ms | Extra link/RAN time not accounted for by tx+retx delay, attributed to segmentation. | Derived from link delay and `NrUlRlcRxComponentStats.txt` |
| Reordering delay | ms | Time from final RLC RX for a packet to first PDCP RX. | `NrUlRlcRxComponentStats.txt`, `NrUlPdcpRxStats.txt` |

## Non-Delay Related Metric

| Metric | Unit | Meaning | Source logs |
|---|---:|---|---|
| RLC segments per packet | count | Number of RLC segments/components used for a packet. | `NrUlRlcTxComponentStats.txt` |

## Raw Log Field Notes

- `delay_trace.txt`: `delay_us` is one-way delay in microseconds.
- `NrUlRlcTxComponentStats.txt`: logs one row per `pkt_id` component in an RLC PDU at UE RLC TX.
- `NrUlRlcRxComponentStats.txt`: logs one row per `pkt_id` component in an RLC PDU at gNB RLC RX, including `delay_us`.
- `NrUlPdcpTxStats.txt`: records UE PDCP TX time for UL PDCP PDUs.
- `NrUlPdcpRxStats.txt`: records gNB PDCP RX time for UL PDCP PDUs.
- `RlcTxQueueSojournTrace.txt`: `pre_hol_wait_us` is RLC TX queue time before becoming HOL.
- `RlcHolGrantWaitTrace.txt`: `hol_grant_wait_us` is time from becoming HOL to dequeue.
- `UePhyCtrlTxTrace.txt`: includes `time_us`, `rnti`, and `msg_type`; `SR` is one possible control message string.
