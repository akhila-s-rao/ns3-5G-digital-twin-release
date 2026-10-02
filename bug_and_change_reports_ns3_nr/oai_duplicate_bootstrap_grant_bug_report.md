# Duplicate Bootstrap Grants Before BSR Reception

## Problem

In the OAI gNB UL scheduler, a UE can be scheduled when it has known UL data, an active SR, or sufficient UL inactivity. This condition is implemented in `openairinterface5g-edaf/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c:1422`.

When the gNB still has no BSR-derived buffer estimate, `B` is computed from `estimated_ul_buffer - sched_ul_bytes` in `openairinterface5g-edaf/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c:1738`. If `B == 0` but scheduling is requested, the scheduler enters the no-data/SR bootstrap path in `openairinterface5g-edaf/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c:1755`.

That path allocates a small UL grant before the gNB has learned the UE buffer status. In `sched_5.json`, bootstrap grants are identifiable as `type: 2` entries with unknown buffer state (`buf: NaN`, `sched: NaN`), typically `5` PRBs, `MCS 9`, and `TBS 24`. 

## Minimal Patch

Add this guard at the start of the `if (B == 0 && do_sched)` block in `openairinterface5g-edaf/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c:1757`:

```c
if (sched_ctrl->estimated_ul_buffer == 0 && sched_ctrl->sched_ul_bytes > 0) {
  LOG_D(NR_MAC,
        "[UE %04x][%4d.%2d] skip duplicate bootstrap grant: sched_ul_bytes %d\n",
        UE->rnti, frame, slot, sched_ctrl->sched_ul_bytes);
  continue;
}
```

## Why This Fixes It

OAI increments `sched_ul_bytes` when it schedules an initial UL transmission in `/home/ubuntu/openairinterface5g-edaf/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c:2182`. It decrements that value when a UL PDU is received in `/home/ubuntu/openairinterface5g-edaf/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c:669`, and also releases it on failed HARQ abort in `/home/ubuntu/openairinterface5g-edaf/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c:489`.

The guard suppresses the specific duplicate-bootstrap state: the gNB still has no learned BSR estimate (`estimated_ul_buffer == 0`), but it has already issued an outstanding UL grant (`sched_ul_bytes > 0`). Once the first bootstrap grant is received or fails through HARQ handling, existing OAI accounting allows scheduling to continue.

This recommendation no longer depends on `sched_ctrl->SR` still being true. The trace evidence shows repeated pre-BSR bootstrap grants; the more direct condition is whether a prior no-buffer UL grant is already outstanding while the gNB still has no learned buffer estimate.
