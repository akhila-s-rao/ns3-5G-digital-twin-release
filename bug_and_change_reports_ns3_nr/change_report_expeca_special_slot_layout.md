# Change Report: ExPeCA Special-Slot Layout in 5G-LENA

## Summary

The shared ExPeCA radio profile now models the OAI mixed special slot with a constrained 5G-LENA
flexible (`F`) slot. The resulting 14-symbol layout is:

```text
symbol 0       DL control
symbols 1-5    DL allocation
symbols 6-9    unused guard
symbols 10-12  UL allocation
symbol 13      UL control
```

This profile is used by both `cellular-network.cc` and `delay-benchmarking.cc`. No ExPeCA or OAI
code is changed.

## Problem

The previous 5G-LENA profile represented `DDDSU` using 5G-LENA's `S` slot type. That type means
DL control, DL data, and UL control; it cannot carry UL data. OAI's special slot instead contains
both DL and UL data regions separated by guard symbols. Consequently, OAI could transmit a
three-symbol PUSCH in each special slot while 5G-LENA had to wait for the following full UL slot.

5G-LENA's existing `F` type supports both data directions, but its data symbols are divided
dynamically. Replacing `S` with unrestricted `F` would therefore not reproduce OAI's fixed
five-DL/four-guard/three-UL partition.

## Implementation

`NrMacSchedulerNs3` now exposes two optional attributes:

```text
FSlotDlAllocationSymbols = 0  # unrestricted stock behavior
FSlotUlAllocationSymbols = 0  # unrestricted stock behavior
```

When nonzero, they cap the symbols available to the corresponding scheduler in an `F` slot. Their
zero defaults preserve existing 5G-LENA behavior. The shared ExPeCA profile sets them to five and
three respectively. UL allocation already proceeds backwards from the final UL-control symbol, so
the three-symbol limit places PUSCH on symbols 10 through 12. DL allocation begins after symbol 0,
so the five-symbol limit confines it to symbols 1 through 5. Symbols 6 through 9 receive no
allocation and form the guard interval.

The shared profile changes each repeated pattern unit from:

```text
DL|DL|DL|S|UL
```

to:

```text
DL|DL|DL|F|UL
```

Using `F` also makes the slot a valid target for UL scheduling and UL DCI generation. SR remains
on the final UL-control symbol of the flexible slot.

## SRS Alignment

OAI source and ExPeCA traces show that periodic SRS uses one symbol in full UL slots rather than
the three-symbol mixed slots:

- OAI configures one SRS symbol with `startPosition = 1`, which places it at symbol 12.
- A normal full-slot PUSCH uses symbols 0 through 12.
- A full UL slot containing SRS shortens PUSCH to symbols 0 through 11.
- A mixed-slot PUSCH continues to use symbols 10 through 12.

The ExPeCA JSON confirms this behavior. For example, run `a4` contains 12-symbol PUSCH allocations
at frame/slot `(0,4)`, `(4,4)`, `(8,4)`, and so on: an 80-absolute-slot cadence. OAI derives that
period as five slots per TDD period times `MAX_MOBILES_PER_GNB = 16`.

The 5G-LENA ExPeCA profile therefore sets:

```text
EnableSrsInFSlots = false
EnableSrsInUlSlots = true
NrMacSchedulerSrsDefault::StartingPeriodicity = 16 eligible UL opportunities
```

With one full UL opportunity per five absolute slots, 16 opportunities correspond to OAI's
80-slot SRS period. SRS continues to drive the configured realistic beamforming updates.

## Files Changed

- `contrib/nr/model/nr-mac-scheduler-ns3.h`
- `contrib/nr/model/nr-mac-scheduler-ns3.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/digital-twin-radio-profile.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/delay-benchmarking.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/delay-benchmarking.h`
- `contrib/nr/test/nr-lte-pattern-generation.cc`
- `dataset_documentation/README.md`
- `dataset_documentation/raw_ns3_data_documentation.md`

## Dataset Impact

New raw simulation data is required to observe the changed timing. Re-running only parsing or
delay-decomposition scripts cannot add the new special-slot PUSCH opportunities. Compared with the
previous profile, packets may be transmitted in the flexible slot rather than waiting for the next
full UL slot, changing queueing, scheduling, segmentation, transmission, and total RAN delay.

Each run records the TDD pattern, flexible-slot limits, and SRS controls in `sim_info.txt` so data
generated before and after this change can be distinguished.

## Verification

- Built the NR library, both digital-twin examples, and the NR test library in the configured
  optimized/release build.
- `nr-lte-pattern-generation` passes with the flexible slot represented as both a DL and UL
  scheduling target.
- `nr-test-sched` passes.
- A short uplink benchmark run produced 258 flexible-slot TB records with `sym_start=10` and
  `num_symbols=3`; its full-UL TB records used `sym_start=0` and `num_symbols=13`.
- A short downlink benchmark run produced 38 flexible-slot TB records with `sym_start=1` and
  `num_symbols=5`; full-DL records used 13 data symbols.
- All 51 SRS transmissions in the uplink smoke run occurred at TDD-pattern position 4, the full
  `UL` slot. Their steady-state interval was 40 ms, equal to 80 slots at numerology 1.
