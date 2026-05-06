# Bug Report: NR RLC UM/AM Periodic BSR Timer Can Be Indefinitely Postponed

## Summary
In `NrRlcUm` and `NrRlcAm`, periodic BSR timer handling could repeatedly restart the timer while data remained buffered. Under sustained arrivals, this can postpone timer expiry for a long time, delaying periodic `expBsrTimer` signaling and making UL grant recovery fragile.

## Affected code
- `contrib/nr/model/nr-rlc-um.cc`
- `contrib/nr/model/nr-rlc-am.cc`

## Root cause
The timer lifecycle used unconditional cancel-and-reschedule patterns:

1. After enqueue + BSR report in `DoTransmitPdcpPdu(...)`, the code could cancel and reschedule the timer.
2. In UM, TX-op path could also restart the timer again if buffer stayed non-empty.

If arrivals are frequent enough, expiry is repeatedly pushed out.

## Fix implemented
The periodic BSR timer is now started only if it is not already pending:

- In UM enqueue path: schedule only when `!m_txBuffer.empty() && !m_bsrTimer.IsPending()`.
- In UM TX-op path: same guard; no cancel/restart of an already running timer.
- In AM enqueue path: schedule only when `(m_txonBufferSize + m_txedBufferSize + m_retxBufferSize > 0) && !m_bsrTimer.IsPending()`.
- In AM TX-op path (status/retx/new-TX sends): same guard; no cancel/restart of an already running timer.
- In AM, `expBsrTimer` is now propagated in `BufferStatusReportParameters` to align with UE-MAC expiry-trigger logic.

This preserves one active periodic timer instance instead of repeatedly postponing expiry.

## Why this is standard-aligned
3GPP defines periodic BSR as a timer-expiry based trigger in MAC BSR procedure; it is not intended to be continuously postponed by each new enqueue event.

- 3GPP TS 38.321, clause 5.4.5 (BSR procedure): periodic BSR is triggered when `periodicBSR-Timer` expires.
- 3GPP TS 38.321 also defines regular/retransmission BSR triggers separately (new data and `retxBSR-Timer` paths), i.e., periodic timer behavior should remain periodic once running.

References:
- ETSI TS 138 321 (3GPP TS 38.321 v17.8.0), clause 5.4.5  
  https://www.etsi.org/deliver/etsi_ts/138300_138399/138321/17.08.00_60/ts_138321v170800p.pdf
- 3GPP portal entry for TS 38.321  
  https://portal.3gpp.org/desktopmodules/Specifications/SpecificationDetails.aspx?specificationId=3194

## Scope and interaction with previous fix
This change does **not** revert or weaken the prior UE-MAC SR/BSR state-machine fix. It addresses a separate RLC UM/AM timer lifecycle issue by preventing timer starvation through restart loops.

## Change marker
Code lines added/changed are tagged with `codex added` comments in `nr-rlc-um.cc` and `nr-rlc-am.cc`.
