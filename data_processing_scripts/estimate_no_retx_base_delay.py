#!/usr/bin/env python3
"""Estimate baseline packet delay from SR and TDD slot timing.

The model follows the local 5G-LENA scheduling timing:

* packet arrivals are uniformly distributed relative to the SR cycle;
* the SR is sent in an S, F, or UL slot and is available after that slot;
* UL data can be transmitted in F and UL slots;
* UL DCI must be sent in a DL, S, or F slot;
* scheduling occurs ``lookahead`` slots before the DCI;
* K2 is a minimum and is increased when its DCI would fall in a UL-only slot;
* the first segment carries the BSR, so all remaining segments can be scheduled
  after that first segment is received;
* one initial RLC segment completes per selected UL-data slot; and
* there is no contention, HARQ/RLC retransmission, or extra decode latency.

Results are analytical timing baselines, not predictions of queueing caused by
load, grant-size/MCS choices, or retransmissions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
import statistics


VALID_SLOT_TYPES = {"DL", "S", "F", "UL"}
UL_CONTROL_SLOT_TYPES = {"S", "F", "UL"}
UL_DATA_SLOT_TYPES = {"F", "UL"}
DL_CONTROL_SLOT_TYPES = {"DL", "S", "F"}
SYMBOLS_PER_SLOT = 14
DEFAULT_UL_CONTROL_SYMBOLS = 1


@dataclass(frozen=True)
class DelayEstimate:
    """Delay distribution over the SR phases in one combined TDD/SR cycle."""

    segments: int
    mean_slots: float
    minimum_slots: float
    maximum_slots: float
    mean_ms: float
    minimum_ms: float
    maximum_ms: float


def parse_tdd_pattern(pattern: str) -> tuple[str, ...]:
    slots = tuple(part.strip().upper() for part in pattern.split("|"))
    if not slots or any(slot not in VALID_SLOT_TYPES for slot in slots):
        raise ValueError(
            "TDD pattern must be a non-empty |-separated sequence of DL, S, F, and UL"
        )
    if not any(slot in UL_CONTROL_SLOT_TYPES for slot in slots):
        raise ValueError("TDD pattern has no slot capable of carrying an SR")
    if not any(slot in UL_DATA_SLOT_TYPES for slot in slots):
        raise ValueError("TDD pattern has no F or UL slot for UL data")
    if not any(slot in DL_CONTROL_SLOT_TYPES for slot in slots):
        raise ValueError("TDD pattern has no slot capable of carrying UL DCI")
    return slots


def _dci_and_generation_slots(
    target_slot: int,
    pattern: tuple[str, ...],
    k2_delay_slots: int,
    scheduler_lookahead_slots: int,
) -> tuple[int, int, int]:
    """Return absolute DCI slot, scheduler-generation slot, and effective K2."""
    effective_k2 = k2_delay_slots
    dci_slot = target_slot - effective_k2
    while pattern[dci_slot % len(pattern)] not in DL_CONTROL_SLOT_TYPES:
        effective_k2 += 1
        dci_slot = target_slot - effective_k2
    generation_slot = dci_slot - scheduler_lookahead_slots
    return dci_slot, generation_slot, effective_k2


def _eligible_ul_targets(
    pattern: tuple[str, ...],
    ready_slot: int,
    first_candidate_slot: int,
    count: int,
    k2_delay_slots: int,
    scheduler_lookahead_slots: int,
) -> list[int]:
    """Find UL-data slots whose scheduling instant is not before ``ready_slot``."""
    targets: list[int] = []
    candidate = first_candidate_slot
    scanned = 0
    scan_limit = max(10_000, count * len(pattern) * 100)

    while len(targets) < count:
        if pattern[candidate % len(pattern)] in UL_DATA_SLOT_TYPES:
            _, generation_slot, _ = _dci_and_generation_slots(
                candidate,
                pattern,
                k2_delay_slots,
                scheduler_lookahead_slots,
            )
            if generation_slot >= ready_slot:
                targets.append(candidate)
        candidate += 1
        scanned += 1
        if scanned > scan_limit:
            raise RuntimeError("could not find schedulable UL-data slots")
    return targets


def estimate_no_retx_base_delays(
    tdd_pattern: str,
    sr_periodicity_slots: int,
    sr_offset_slots: int,
    scheduler_lookahead_slots: int,
    k2_delay_slots: int,
    *,
    numerology: int = 1,
    maximum_segments: int = 3,
    ul_control_symbols: int = DEFAULT_UL_CONTROL_SYMBOLS,
) -> list[DelayEstimate]:
    """Estimate mean/min/max completion delay for one through N segments.

    The returned delay begins at packet arrival and ends when the final initial
    RLC segment reaches the end of its UL-data symbols.
    """
    pattern = parse_tdd_pattern(tdd_pattern)
    if sr_periodicity_slots <= 0:
        raise ValueError("SR periodicity must be positive")
    if not 0 <= sr_offset_slots < sr_periodicity_slots:
        raise ValueError("SR offset must be in [0, SR periodicity)")
    if scheduler_lookahead_slots < 0 or k2_delay_slots < 0:
        raise ValueError("scheduler lookahead and K2 must be non-negative")
    if numerology < 0:
        raise ValueError("numerology must be non-negative")
    if maximum_segments <= 0:
        raise ValueError("maximum_segments must be positive")
    if not 0 <= ul_control_symbols < SYMBOLS_PER_SLOT:
        raise ValueError("UL-control symbols must be in [0, 14)")

    combined_cycle = math.lcm(sr_periodicity_slots, len(pattern))
    sr_slots = list(range(sr_offset_slots, combined_cycle, sr_periodicity_slots))
    invalid_sr_slots = [
        slot
        for slot in sr_slots
        if pattern[slot % len(pattern)] not in UL_CONTROL_SLOT_TYPES
    ]
    if invalid_sr_slots:
        raise ValueError(
            "SR opportunities without UL control in combined cycle: "
            f"{invalid_sr_slots}"
        )

    completion_fraction = (SYMBOLS_PER_SLOT - ul_control_symbols) / SYMBOLS_PER_SLOT
    slot_duration_ms = 1.0 / (2**numerology)
    delays_by_segments = {segments: [] for segments in range(1, maximum_segments + 1)}

    for sr_slot in sr_slots:
        # The SR is received at the end of sr_slot, so the first scheduler
        # invocation that can use it is the start of sr_slot + 1.
        first_target = _eligible_ul_targets(
            pattern,
            ready_slot=sr_slot + 1,
            first_candidate_slot=sr_slot + 1,
            count=1,
            k2_delay_slots=k2_delay_slots,
            scheduler_lookahead_slots=scheduler_lookahead_slots,
        )[0]

        targets = [first_target]
        if maximum_segments > 1:
            # The first segment carries a BSR. From the next slot onward, the
            # scheduler knows the remaining buffer and may prepare consecutive
            # future UL opportunities.
            targets.extend(
                _eligible_ul_targets(
                    pattern,
                    ready_slot=first_target + 1,
                    first_candidate_slot=first_target + 1,
                    count=maximum_segments - 1,
                    k2_delay_slots=k2_delay_slots,
                    scheduler_lookahead_slots=scheduler_lookahead_slots,
                )
            )

        # Uniform arrivals see an average P/2 wait to the next SR-slot start.
        mean_arrival_to_sr_start = sr_periodicity_slots / 2.0
        for segments, final_target in enumerate(targets, start=1):
            delay_slots = (
                mean_arrival_to_sr_start
                + (final_target - sr_slot)
                + completion_fraction
            )
            delays_by_segments[segments].append(delay_slots)

    estimates: list[DelayEstimate] = []
    for segments, delays in delays_by_segments.items():
        mean_slots = statistics.fmean(delays)
        minimum_slots = min(delays)
        maximum_slots = max(delays)
        estimates.append(
            DelayEstimate(
                segments=segments,
                mean_slots=mean_slots,
                minimum_slots=minimum_slots,
                maximum_slots=maximum_slots,
                mean_ms=mean_slots * slot_duration_ms,
                minimum_ms=minimum_slots * slot_duration_ms,
                maximum_ms=maximum_slots * slot_duration_ms,
            )
        )
    return estimates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Estimate no-retransmission base delay from SR and TDD timing"
    )
    parser.add_argument("--tdd-pattern", required=True)
    parser.add_argument("--sr-periodicity-slots", required=True, type=int)
    parser.add_argument("--sr-offset-slots", required=True, type=int)
    parser.add_argument("--scheduler-lookahead-slots", required=True, type=int)
    parser.add_argument("--k2-delay-slots", required=True, type=int)
    parser.add_argument("--numerology", type=int, default=1)
    parser.add_argument("--maximum-segments", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    estimates = estimate_no_retx_base_delays(
        args.tdd_pattern,
        args.sr_periodicity_slots,
        args.sr_offset_slots,
        args.scheduler_lookahead_slots,
        args.k2_delay_slots,
        numerology=args.numerology,
        maximum_segments=args.maximum_segments,
    )

    print("segments  mean_slots  mean_ms  min_ms  max_ms")
    for estimate in estimates:
        print(
            f"{estimate.segments:>8}  {estimate.mean_slots:>10.3f}  "
            f"{estimate.mean_ms:>7.3f}  {estimate.minimum_ms:>6.3f}  "
            f"{estimate.maximum_ms:>6.3f}"
        )


if __name__ == "__main__":
    main()
