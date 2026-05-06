MAC TB Delay Trace (UL/DL) - Change Report
==========================================

Summary
-------
Added a minimal-disruption MAC transport-block delay trace that measures the time from the first
MAC->PHY transmission attempt to successful PHY decoding (including HARQ retransmissions). The
measurement is logged separately for UL and DL in new trace files without changing the existing
RxTb trace formats.

What changed
------------
1) New packet tag to carry the first MAC->PHY TX time:
   - NrMacTxTimeTag (new files in contrib/nr/model/).

2) MAC layer stamps the tag on the first transmission only (preserved across retransmissions):
   - UE MAC: NrUeMac::DoTransmitPdu
   - gNB MAC: NrGnbMac::DoTransmitPdu

3) PHY emits a new trace source on successful TB decode:
   - NrSpectrumPhy trace source "MacTbDelay" fires at RX when TB is not corrupted.
   - The delay is computed from the tag and logged in cellular-network.

4) cellular-network adds new trace files:
   - DlMacTbDelayTrace.txt
   - UlMacTbDelayTrace.txt

5) Logging documentation updated with the new logs and columns.

New log formats
---------------
DlMacTbDelayTrace.txt (UE PHY; DL)
  time_us, cell_id, bwp_id, rnti, mac_tb_delay_us

UlMacTbDelayTrace.txt (gNB PHY; UL)
  time_us, cell_id, bwp_id, rnti, mac_tb_delay_us

Notes
-----
- The delay is only logged for successfully decoded TBs.
- The trace measures MAC->PHY delivery time including HARQ retransmissions, which makes it a
  MAC-level TB delay (not PDCP/RLC delay).
