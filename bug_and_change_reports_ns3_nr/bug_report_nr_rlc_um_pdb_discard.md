# Bug Report: NrRlcUm PDB Discard Does Not Enforce Drop (Pre-fix)

## Summary
`NrRlcUm::DoTransmitPdcpPdu` logs a discard when HOL > discard timer (PDB by default),
but the code continues to enqueue the PDCP SDU anyway. This means the Packet Delay
Budget (PDB) is **not actually enforced** even when `EnablePdcpDiscarding` is enabled
and `DiscardTimerMs` is 0.

## Evidence (code pointers)
- PDB is derived from the bearer QCI and passed into RLC when the DRB is created:
  - `contrib/nr/model/nr-gnb-rrc.cc:446-453` sets `rlc->SetPacketDelayBudgetMs(...)`.
- `EnablePdcpDiscarding` defaults to `true` and `DiscardTimerMs` defaults to `0`,
  which means **PDB is the discard timer**:
  - `contrib/nr/model/nr-rlc-um.cc:60-73`.
- When HOL exceeds the discard timer, a drop is logged and the drop trace is fired,
  **but the SDU is still enqueued**:
  - `contrib/nr/model/nr-rlc-um.cc:116-132` (pre-fix behavior).

## Impact
Even if a packet is declared discarded, it still enters the RLC TX buffer.
This inflates `m_txBufferSize`, contributes to BSR reports, and allows HOL to grow
far past the configured PDB threshold, contradicting the discard intent.

## Fix (implemented)
Return early after the drop is logged so the SDU is not enqueued:
- `contrib/nr/model/nr-rlc-um.cc:116-123` now includes:
  - `return; // codex added: enforce PDB by dropping instead of enqueueing`

## Expected behavior after fix
If `EnablePdcpDiscarding` is enabled and HOL > discard timer (PDB), the SDU is dropped
and **does not** enter the RLC TX buffer or affect subsequent BSR/queue behavior.
