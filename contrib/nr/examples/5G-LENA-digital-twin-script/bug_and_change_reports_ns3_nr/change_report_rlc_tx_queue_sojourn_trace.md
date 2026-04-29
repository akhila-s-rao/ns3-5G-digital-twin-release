RLC TX Queue Sojourn Trace (Codex Additions)
============================================

Goal
----
Add a per-PDU/segment log that reports how long each RLC PDU/segment spent
in the UE TX queue before it was dequeued for transmission. This helps
explain end-to-end probe delays that are not visible in HOL-only traces.

What Changed
------------
1) Added a new RLC trace source:
   - Name: TxQueueSojourn
   - Signature: (rnti, lcid, pdu_size_bytes, sojourn_ns)
   - Files:
     - contrib/nr/model/nr-rlc.h (new trace type + member)
     - contrib/nr/model/nr-rlc.cc (TypeId AddTraceSource)

2) Emitted the trace for every dequeued PDU/segment:
   - UM: contrib/nr/model/nr-rlc-um.cc
   - AM: contrib/nr/model/nr-rlc-am.cc
   The log fires when a PDU/segment becomes HOL (head of line). The
   pre‑HOL wait is (holSince - waitingSince).

3) Wired the trace into the cellular-network logging:
   - New log file: RlcTxQueueSojournTrace.txt
   - Header: time_us, cell_id, rnti, lcid, pdu_size, pre_hol_wait_us
   - Stream created in CreateTraceFiles()
   - Connected in ConnectPdcpRlcTracesUe()

New Log File
------------
RlcTxQueueSojournTrace.txt
Columns:
  time_us          - current simulation time when segment becomes HOL
  cell_id          - serving cell ID
  rnti             - UE RNTI
  lcid             - logical channel ID
  pdu_size         - PDU/segment size (bytes)
  pre_hol_wait_us  - time from enqueue to HOL (microseconds)

Notes
-----
- This is per PDU/segment, so a single PDCP SDU that is segmented can appear
  multiple times with the same enqueue timestamp.
- This does not replace HOL delay; it complements it by showing per-PDU
  queueing time before it becomes HOL.

Files Touched (for diff review)
-------------------------------
- contrib/nr/model/nr-rlc.h
- contrib/nr/model/nr-rlc.cc
- contrib/nr/model/nr-rlc-um.cc
- contrib/nr/model/nr-rlc-am.cc
- contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.h
