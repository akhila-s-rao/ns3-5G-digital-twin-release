# Bug Report: NR UE SR/BSR State Machine Can Stall With Pending UL Data

## Summary
In long NR simulations, some UEs stop receiving UL data grants while they still have UL data queued. The UE continues sending SRS, but SR/BSR signaling stops and the gNB observes BSR = 0. This results in a permanent UL scheduling stall for those UEs even though RLC HOL indicates a large backlog.

## Environment
- ns-3 NR module (contrib/nr)
- Scenario: `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.cc`
- `UseIdealRrc = true`

## Symptoms (from run04_seed13 logs)
- `RlcHolDelayTrace.txt`: `tx_queue_bytes` remains high (e.g., ~204 KB) for LCID 4 after the stall time.
- `NrUlPdcpTxStats.txt`: PDCP continues to send UL data for affected RNTIs after the stall time.
- `NrUlPdcpRxStats.txt`, `NrUlRlcTxStats.txt`, `UlRxTbTrace.txt`: stop earlier for affected RNTIs (no UL data delivered).
- `GnbBsrTrace.txt`: last BSR entries show `queue_bytes = 0` for all LCGs at the stall time.
- `UeMacCtrlTxTrace.txt`: SR/BSR messages stop after the stall time.
- `UeMacStateTrace.txt`: last entries show `sr_state=ACTIVE` with non-zero buffer bytes, then no further state transitions.

## Root Cause
Two related issues contribute to the stall:
1) **UE MAC SR/BSR re-trigger is gated by UL DCI/HARQ state.**  
   `NrUeMac::DoTransmitBufferStatusReport()` only transitions to `TO_SEND` when:
   - the SR/BSR state is `INACTIVE`, or
   - the BSR timer has expired **and** certain HARQ/DCI conditions are met.

   When the UE is already `ACTIVE` and no UL data DCI arrives, the state machine never re-triggers SR. The UE therefore stops sending SR/BSR even though RLC continues to report non-zero buffers. Since the gNB only sees BSR=0, it stops granting UL data.

2) **RLC UM/AM periodic BSR timer is only re-armed after a UL TX opportunity.**  
   In `NrRlcUm` and `NrRlcAm`, the periodic BSR timer is scheduled when a PDU is transmitted. If UL grants stop right after the buffer drains, the timer never re-arms. When new data later arrives, there is no periodic BSR firing to announce the buffer again.

Control channel errors are not modeled for DCI in the NR code (`NrSpectrumPhy::EndRxCtrl()` has no error model), so this is not due to DCI loss.

## Fix Implemented (core change)
Two changes are applied to align with 3GPP TS 38.321 BSR triggering behavior (periodic BSR while buffered data exists):
1) **UE MAC:** Re-trigger SR/BSR when the BSR timer expires **and** there is still pending data, regardless of HARQ/DCI state.
2) **RLC UM/AM:** Re-arm the periodic BSR timer whenever the TX buffer is non-empty after PDCP enqueues data (not only after a UL TX opportunity).

### Patch 1 (UE MAC)
- File: `contrib/nr/model/nr-ue-mac.cc`
- Function: `NrUeMac::DoTransmitBufferStatusReport`

Old condition:
```
if (m_srState == INACTIVE ||
    (params.expBsrTimer && m_srState == ACTIVE && m_ulDci->m_harqProcess > 0 && m_ulDci->m_rv == 3) ||
    (params.expBsrTimer && m_srState == ACTIVE && m_ulDci->m_harqProcess == 0))
{
    ...
    m_srState = TO_SEND;
}
```

New condition:
```
const bool hasData = (GetTotalBufSize() > 0);
if (m_srState == INACTIVE ||
    (params.expBsrTimer && m_srState == ACTIVE && hasData))
{
    ...
    m_srState = TO_SEND;
}
```

### Patch 2 (RLC UM/AM)
- Files:
  - `contrib/nr/model/nr-rlc-um.cc`
  - `contrib/nr/model/nr-rlc-am.cc`
- Function: `DoTransmitPdcpPdu`

UM snippet (updated to start-only-if-not-running):
```
DoTransmitBufferStatusReport();
if (!m_txBuffer.empty() && !m_bsrTimer.IsPending())
{
    // codex added: start periodic BSR timer only if it is not already running.
    m_bsrTimer = Simulator::Schedule(MilliSeconds(10), &NrRlcUm::ExpireBsrTimer, this);
}
```

AM snippet (updated to start-only-if-not-running):
```
DoTransmitBufferStatusReport();
if ((m_txonBufferSize + m_txedBufferSize + m_retxBufferSize > 0) && !m_bsrTimer.IsPending())
{
    // codex added: start periodic BSR timer only if it is not already running.
    m_bsrTimer = Simulator::Schedule(m_bsrTimerValue, &NrRlcAm::ExpireBsrTimer, this);
}
```

Follow-up details and references are tracked in:
`contrib/nr/examples/5G-LENA-digital-twin-script/bug_report_nr_rlc_um_bsr_timer_restart_starvation.md`.

## Rationale
- 3GPP TS 38.321 specifies periodic BSR triggering while the UE has buffered data.
- The previous HARQ/DCI gating can prevent SR retransmission indefinitely if a grant is never received.
- Re-arming the periodic BSR timer on buffer non-empty prevents the deadlock when UL grants stop.

## Expected Outcome
With these changes, the UE re-sends SR/BSR when data remains buffered and the periodic timer is running, preventing the long-term UL scheduling stall.

## Notes
- The changes are minimal and do not alter scheduler or PHY error modeling behavior.
- The fix only affects SR/BSR triggering logic and periodic BSR timer behavior in RLC.
