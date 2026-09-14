# Bug Report: Periodic BSR Recovery SRs Were Misclassified as Bootstrap Grants

## Summary

This change fixes a regression created by a previous UE grant-starvation bug fix.

The earlier fix successfully prevented a UE from remaining permanently stuck with buffered
uplink data. It did so by propagating an RLC periodic-BSR timer-expiry flag to UE MAC and
forcing an active UE to send another Scheduling Request (SR). However, the scheduler treated
every SR as if the gNB had no buffer information for that UE:

- it replaced each UL logical-channel-group estimate with 12 bytes;
- it classified the next grant as a bootstrap grant; and
- when bootstrap MCS limiting was enabled, it capped that grant at MCS 9.

Under congestion, an active UE can legitimately wait longer than the timer interval for its
next grant. The previous fix therefore generated repeated recovery SRs and repeatedly destroyed
valid positive gNB buffer estimates. This produced a large population of very small grants even
though the UE still had substantial data buffered.

## Regression Origin

### Original starvation problem

The scheduler subtracts assigned bytes from its UL buffer estimate when it creates a grant. A
SHORT_BSR is sent with new UL data, but that BSR is not retained in the UE HARQ buffer. If the
gNB did not receive an updated BSR, its estimate could reach zero while the UE MAC remained
`ACTIVE` with data still queued. New RLC reports did not request another SR from an active UE,
so the UE could stop receiving grants indefinitely.

### Previous fix

The previous fix added or extended the following path:

1. RLC UM/AM issued periodic local buffer-status reports.
2. `BufferStatusReportParameters` carried an `expBsrTimer` flag.
3. `NrUeMac::DoTransmitBufferStatusReport()` changed `ACTIVE` to `TO_SEND` whenever that flag
   was set and data remained.
4. The resulting SR entered the scheduler's ordinary SR bootstrap path.

That fixed the permanent stall, but it conflated two different cases:

- **Initial bootstrap SR:** the scheduler knows zero buffered bytes and needs a small grant to
  obtain a radio BSR.
- **Recovery SR:** the UE has waited too long for another grant, but the scheduler may already
  hold a valid positive buffer estimate.

The ExPeCA-style configuration uses one PRB per RBG for normal grants. A genuine initial
bootstrap SR is allocated exactly five PRBs, independently of the normal one-PRB scheduling
granularity, matching the corresponding OAI grant.

The scheduler then compounded the problem by unconditionally calling `UpdateInfo(12)` for all
UL LCGs of every SR UE. A recovery SR therefore replaced, rather than supplemented, the gNB's
existing estimate.

## Observed Effect

The bursty run-04 investigation found:

- 938,721 transmitted SRs;
- 689,400 per-UE SR intervals equal to 10 ms; and
- 273,053 UL grants with TBS 13 bytes and MCS 9.

The 10 ms concentration matches the RLC UM periodic timer used by the earlier fix. The issue is
most visible under congestion because active UEs commonly wait past that interval. In the
benchmark workload, buffers empty more often and most SRs are genuine zero-estimate bootstrap
requests, so the regression occurs less often.

## Corrected Design

### UE MAC owns grant-recovery timing

`NrUeMac` now has a configurable `RetxBsrTimer` with a default of 10 ms:

- new data arriving while the SR state is `INACTIVE` still requests an immediate SR;
- transmitting an SR starts the recovery timer;
- receiving and processing a new-data UL grant restarts it when data remains;
- an empty aggregate RLC buffer cancels it and returns the state to `INACTIVE`; and
- expiry requests another SR only when data remains and the UE is still `ACTIVE`.

Restarting the timer on each new-data grant means a continuously served UE does not emit
periodic recovery SRs. A UE that stops receiving grants still retries and therefore cannot
remain permanently starved.

### Periodic RLC reporting remains, but no longer controls SR

RLC UM/AM periodic buffer-status reporting is retained. The obsolete `expBsrTimer` field and
the direct RLC-expiry-to-SR decision are removed. RLC reports describe local queue state; UE
MAC now independently decides whether grant recovery is required.

The existing AM `BufferStatusReportTimer` attribute is preserved.

### Scheduler distinguishes bootstrap from recovery

For each SR, the scheduler now checks its existing aggregate UL LCG estimates:

- if all estimates are zero, it seeds 12 bytes and records a pending bootstrap;
- if any estimate is positive, it preserves every estimate and treats the SR as recovery;
- the bootstrap MCS cap applies only to pending zero-estimate bootstraps; and
- bootstrap state remains pending if DCI creation fails, then clears only when an UL DCI is
  successfully created or the UE is released.

This retains the original small-grant mechanism for a genuinely unknown queue without
corrupting information already known to the gNB.

### Dataset traces distinguish SR causes

The bursty and benchmarking scenarios now write `UeMacSrTriggerTrace.txt`. It records whether
each UE-MAC request is an `INITIAL` SR caused by new data in an idle buffer or a `RECOVERY` SR
caused by `RetxBsrTimer` expiry. The delay-decomposition script pairs this trigger with the
actual SR in `UePhyCtrlTxTrace.txt` and excludes recovery SRs from frame-alignment and
scheduling-delay calculations.

## Changed Files

- `contrib/nr/model/nr-ue-mac.{h,cc}`
  - adds and manages `RetxBsrTimer`;
  - removes the periodic-RLC-expiry SR trigger.
- `contrib/nr/model/nr-mac-scheduler-ns3.{h,cc}`
  - preserves positive UL estimates on recovery SR;
  - tracks zero-estimate bootstrap state until grant creation.
- `contrib/nr/model/nr-mac-sap.h`
  - removes the obsolete `expBsrTimer` cross-layer flag.
- `contrib/nr/model/nr-rlc-{um,am}.{h,cc}` and `contrib/nr/model/nr-rlc.cc`
  - retain periodic reports but stop propagating timer expiry as an SR command.
- `contrib/nr/examples/5G-LENA-digital-twin-script/{cellular-network,delay-benchmarking}.h`
  - write initial/recovery SR trigger classifications for dataset processing.
- `data_processing_scripts/create_delay_decomposition_data.py`
  - uses only classified initial SRs for SR-derived delay components.

## Regression Coverage

- `nr-ue-mac-retx-bsr`
  - checks immediate SR state on idle-buffer arrival;
  - checks that restarting the timer postpones recovery;
  - checks expiry with buffered data; and
  - checks cancellation and `INACTIVE` state when the buffer empties.
- `nr-test-sched`
  - checks that recovery SR preserves a positive estimate and does not apply the bootstrap cap;
  - checks zero-estimate seeding and MCS limiting;
  - checks repeated bootstrap SR state; and
  - checks cleanup on UE release.

## Dataset Implication

Existing simulation outputs are not modified by this code change. Runs generated with the
previous behavior retain its altered grant sizes, MCS choices, segmentation pattern, and
resulting delays. Any dataset intended to represent the corrected scheduler behavior must be
regenerated from the raw simulation stage; rerunning only the parsing or decomposition scripts
cannot reconstruct grants that were never scheduled correctly.

Older raw runs also lack `UeMacSrTriggerTrace.txt`. The corrected decomposition script omits
the two SR-derived columns for those runs instead of treating recovery SRs as initial SRs.
