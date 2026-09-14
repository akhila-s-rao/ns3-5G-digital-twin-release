# Change Report: Configurable Maximum Uplink MCS

## Summary

Added a scheduler attribute, `MaxUlMcs`, that limits the MCS used for new uplink data grants
without disabling adaptive UL AMC. The bootstrap-grant MCS behavior remains independent: a
zero-estimate SR bootstrap uses the lower of the general UL cap and the bootstrap cap.

The first implementation applied `MaxUlMcs` only while constructing the final UL DCI. That
correctly limited the transmitted MCS but allowed resource allocation and scheduler metrics to use
the uncapped AMC result. This report documents both the feature and the correction of that
implementation regression.

## Motivation

The existing scheduler supported either adaptive UL AMC or a completely fixed UL MCS. Benchmark
experiments also need adaptive channel response while preventing the selected UL MCS from exceeding
a configured value, for example MCS 20.

`MaxUlMcs` provides that behavior:

- AMC can continue selecting a lower MCS when channel conditions require it.
- Values above the configured maximum are capped.
- The option affects UL only; DL MCS selection is unchanged.
- Fixed UL MCS values are also constrained by the maximum.

## Configuration

### Scheduler attribute

`NrMacSchedulerNs3` exposes:

```text
MaxUlMcs = -1   general scheduler default; limit disabled
MaxUlMcs >= 0   maximum UL MCS index
```

The digital-twin simulation scripts use `NrEesmCcT2` and validate the profile value in the range
0 through 27. A value of 27 is effectively equivalent to disabling the cap because that
configuration does not select an UL MCS above 27.

For example, the equivalent internal parameter combinations are:

```text
fixUlMcs=0, maxUlMcs=20
```

keeps adaptive UL AMC and caps its result at 20, while:

```text
fixUlMcs=27, maxUlMcs=20
```

requests fixed MCS 27 but schedules at MCS 20 because the maximum still applies.

Both Expeca simulation profiles set `maxUlMcs` to 20 in their C++ scenario setup. It is not exposed
as a command-line campaign parameter.

## Implementation

### One stored scheduling MCS per UE

`m_ulMcs` remains the single per-UE MCS consumed by resource sizing, scheduler metrics, UE ordering,
allocation reshaping, and DCI creation. There is no separate raw-versus-capped scheduling field.

The cap policy is centralized in `NrMacSchedulerNs3::GetCappedUlMcs()`. The stored per-UE value is
normalized whenever code can replace it:

1. When a UE is registered and receives `StartingMcsUl`.
2. After adaptive UL CQI processing updates `m_ulMcs`.
3. When UL CQI expires and restores `StartingMcsUl`.
4. When `MaxUlMcs` is lowered while UEs already exist.

All scheduler implementations therefore read the capped `m_ulMcs` directly. This covers OFDMA and
TDMA RR, PF, QoS, MR, Random, and AI variants that share the base scheduler state.

### Bootstrap composition

`GetEffectiveUlMcs()` starts with the persistent general cap. For a pending zero-estimate SR
bootstrap, it then applies:

```text
min(general-capped MCS, bootstrap MCS limit)
```

The bootstrap cap is temporary and applies only to the bootstrap DCI. It does not replace the
UE's persistent adaptive scheduling MCS.

## Regression in the Initial Implementation

### Original behavior

The first implementation called `GetEffectiveUlMcs()` only in `CreateUlDci()`. This produced a
capped final DCI, but `NrMacSchedulerUeInfo::UpdateUlMetric()` still calculated provisional TBS
from the uncapped `m_ulMcs`.

The allocation sequence could therefore be:

1. AMC selected MCS 27.
2. Resource allocation calculated TBS at MCS 27 and stopped when that provisional TBS covered the
   gNB's BSR-derived queue requirement.
3. DCI creation reduced the MCS to 20 and recalculated a smaller actual TBS using the resources
   already selected.
4. The resulting grant no longer covered the queue requirement used to size it.

The same inconsistency also inflated PF/QoS current and potential throughput metrics and could
affect multi-UE ordering. TDMA schedulers could stop allocating symbols too early for the same
reason.

### Observed benchmark symptom

In benchmark run `a5` (1200-byte delay probes, 50 ms interval, no background load), the gNB
received a 1038-byte quantized BSR estimate after the bootstrap transmission.

Before correction:

```text
allocator calculation: MCS 27, 10 PRBs, provisional TBS 1326 bytes
actual DCI:            MCS 20, 10 PRBs, actual TBS 955 bytes
RLC components:        179 + 945 + 84 bytes
```

The remaining 84 bytes required a third RLC transmission opportunity. Typical segmentation delay
increased from approximately 5.001 ms to 7.501 ms.

The neighboring 1400-byte experiment did not show the same increase because its 1446-byte BSR
estimate exceeded the provisional 10-PRB TBS. The allocator selected 15 PRBs before the cap was
applied, and the resulting MCS-20 TBS happened to be large enough to finish that packet in two
segments. This produced a non-monotonic packet-size artifact.

### Corrected behavior

The persistent per-UE `m_ulMcs` is now capped before allocation and metric calculation. For the
same `a5` conditions:

```text
allocation and DCI MCS: 20
allocated resources:    15 PRBs
actual TBS:              1434 bytes
RLC components:          179 + 1029 bytes
```

Resource allocation, scheduler accounting, and the transmitted DCI now use the same MCS.

## Files Changed

Core scheduler and tests:

- `contrib/nr/model/nr-mac-scheduler-ns3.h`
- `contrib/nr/model/nr-mac-scheduler-ns3.cc`
- `contrib/nr/test/nr-test-sched.cc`

Digital-twin configuration and reporting:

- `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network-user.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/delay-benchmarking.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/delay-benchmarking.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/delay-benchmarking-user.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/run-parallel-benchmarking-sims.py`
- `contrib/nr/examples/5G-LENA-digital-twin-script/run-parallel-bursty-traffic-sims.py`

Both simulation programs record `max_ul_mcs` in `sim_info.txt`.

## Verification

- Completed an optimized ns-3 build after the correction.
- `nr-test-sched` passes for TDMA RR, TDMA PF, OFDMA RR, and OFDMA PF.
- Tests verify disabled and enabled cap behavior, capped initialization of new UEs, lowering the cap
  for existing UEs, and capped CQI-expiry fallback.
- A short adaptive `a5` reproduction with `MaxUlMcs=20` produced MCS 20, 15 PRBs, TBS 1434 bytes,
  and two RLC components per normal packet.
- A fixed-MCS reproduction with `fixUlMcs=27` and `MaxUlMcs=20` produced the same correctly sized
  MCS-20 allocation.
- An adaptive control run with `MaxUlMcs=27` preserved MCS 27, 10 PRBs, TBS 1326 bytes, and two RLC
  components.

## Dataset Impact

Simulation data generated by the initial DCI-only implementation with an active cap can contain
under-sized grants, additional RLC segments, inflated segmentation delay, and altered PF scheduling
behavior. The effect occurs when the uncapped AMC MCS is above `MaxUlMcs` and the provisional TBS
crosses a resource-allocation threshold that the capped TBS does not.

Those effects are simulation behavior recorded accurately by the raw logs; they cannot be repaired
by rerunning the parsing or delay-decomposition scripts. Benchmark simulation data generated with
`maxUlMcs=20` before this correction must be regenerated for corrected scheduling results.

Runs using `maxUlMcs=27` with `NrEesmCcT2` are not affected by this particular cap mismatch because
the general cap does not reduce the selected UL MCS.
