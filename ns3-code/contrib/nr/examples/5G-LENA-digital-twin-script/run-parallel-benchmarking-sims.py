#!/usr/bin/env python3
from pathlib import Path
import argparse
import math
import os
import shlex
import subprocess
import time

# Simple settings you can edit.
MAX_PARALLEL = max(1, (os.cpu_count() or 1))

# Runtime controls that are neither traffic nor radio configuration.
EXECUTION_ARGS = {
    "appGenerationTime": 1000,
    "progressInterval": "1s",
    "randomSeed": 3,
}

# Traffic defaults shared by every traffic experiment. Individual TRAFFIC_RUNS
# entries may override only keys from this dictionary.
TRAFFIC_DEFAULTS = {
    "direction": "ul",
    "loadType": "none",
    "numBackgroundUes": 1,
    "totalBackgroundLoad": 10,
    "delayTrafficSource": "delay",
    "delayPktSize": 1400,
    "delayInterval": "100ms",
    "delayBurstPackets": 10,
}

# Default radio/configuration arguments passed to delay-benchmarking-user.
RADIO_DEFAULTS = {
    "digitalTwinScenario": "expeca",
    "channelScenario": "InH-OfficeOpen",
    "controlBearerQci": 80,
    "fixUlMcs": 0,
    "tddPattern":
        "DL|DL|DL|F|UL|DL|DL|DL|F|UL|DL|DL|DL|F|UL|DL|DL|DL|F|UL",
    "srPeriodicitySlots": 10,
    "srOffsetSlots": 3,
    "numRbPerRbg": 1,
    "bootstrapGrantPrbs": 5,
    "bootstrapMaxMcs": 9,
    "numerology": 1,
}

# Standard slot-based SR periodicities from 3GPP TS 38.331, indexed by
# numerology/SCS. Symbol-based SR periodicities are not represented by the
# slot-based benchmark arguments.
STANDARD_SR_PERIODICITIES_BY_NUMEROLOGY = {
    0: {1, 2, 4, 5, 8, 10, 16, 20, 40, 80},
    1: {1, 2, 4, 8, 10, 16, 20, 40, 80, 160},
    2: {1, 2, 4, 8, 16, 20, 40, 80, 160, 320},
    3: {1, 2, 4, 8, 16, 40, 80, 160, 320, 640},
}
UL_CONTROL_SLOT_TYPES = {"S", "F", "UL"}

# Every named configuration is run against every entry in RADIO_STUDY_RUNS. Values
# here override RADIO_DEFAULTS. Add configurations by copying an existing entry.
RADIO_CONFIGS = {
    #"baseline": {},

    "long_sr": {"srPeriodicitySlots": 20, "srOffsetSlots": 3,},

    "high_ul_tdd": {"tddPattern": "DL|DL|DL|DL|DL|DL|F|UL|UL|UL",
        "srPeriodicitySlots": 10, "srOffsetSlots": 6,}, # 4 UL/10 slots

    "moderate_ul_tdd": {"tddPattern": "DL|DL|DL|DL|DL|DL|DL|F|UL|UL",
        "srPeriodicitySlots": 10, "srOffsetSlots": 7,}, # 3 UL/10 slots

    "low_ul_tdd": {"tddPattern": "DL|DL|DL|DL|DL|DL|DL|DL|F|UL",
        "srPeriodicitySlots": 10, "srOffsetSlots": 8,}, # 2 UL/10 slots

    #"mixed_dl_tdd": {"tddPattern": "DL|F",
    #    "srPeriodicitySlots": 10, "srOffsetSlots": 1,},

    #"frequent_mixed_tdd": {"tddPattern": "DL|DL|F|UL",
    #    "srPeriodicitySlots": 20, "srOffsetSlots": 2,}, # 5 UL/10 slots

    "increase_bootstrap_grant_size_1": {"bootstrapGrantPrbs": 10,},
    "increase_bootstrap_grant_size_2": {"bootstrapGrantPrbs": 20,},

}
# for 2 grants k2=6slots
# long_sr:                         20.464 ms
# high_ul_tdd:                     17.964 ms
# moderate_ul_tdd:                 22.964 ms
# low_ul_tdd:                      22.964 ms
# mixed_dl_tdd:               16.964 ms
# frequent_mixed_tdd:              19.464 ms
# increase_bootstrap_grant_size_1: 17.964 ms
# increase_bootstrap_grant_size_2: 17.964 ms

# for 2 grants k2=2slots
# long_sr:                         15.464 ms
# high_ul_tdd:                     12.964 ms
# moderate_ul_tdd:                 12.964 ms
# low_ul_tdd:                      12.964 ms
# mixed_dl_tdd:                    12.964 ms
# frequent_mixed_tdd:              15.464 ms
# increase_bootstrap_grant_size_1: 12.964 ms
# increase_bootstrap_grant_size_2: 12.964 ms

# Packet-size sweep.
PACKET_SIZE_RUNS = [
    {"name": "a1", "args": {"delayPktSize": 50, "delayInterval": "50ms"}},
    {"name": "a2", "args": {"delayPktSize": 100, "delayInterval": "50ms"}},
    {"name": "a3", "args": {"delayPktSize": 200, "delayInterval": "50ms"}},
    {"name": "a4", "args": {"delayPktSize": 1000, "delayInterval": "50ms"}},
    {"name": "a5", "args": {"delayPktSize": 1200, "delayInterval": "50ms"}},
    {"name": "a6", "args": {"delayPktSize": 1400, "delayInterval": "50ms"}},
    {"name": "a7", "args": {"delayPktSize": 12, "delayInterval": "50ms"}},
]

# Inter-packet-interval sweep.
INTER_PACKET_TIME_RUNS = [
    {"name": "e1", "args": {"delayPktSize": 100, "delayInterval": "10ms"}},
    {"name": "e2", "args": {"delayPktSize": 100, "delayInterval": "15ms"}},
    {"name": "e3", "args": {"delayPktSize": 100, "delayInterval": "20ms"}},
    {"name": "e4", "args": {"delayPktSize": 100, "delayInterval": "25ms"}},
    {"name": "e5", "args": {"delayPktSize": 100, "delayInterval": "50ms"}},
    {"name": "e6", "args": {"delayPktSize": 100, "delayInterval": "75ms"}},
    {"name": "e7", "args": {"delayPktSize": 100, "delayInterval": "100ms"}},
    {"name": "e8", "args": {"delayPktSize": 100, "delayInterval": "7ms"}},
    {"name": "e9", "args": {"delayPktSize": 100, "delayInterval": "6ms"}},
    {"name": "e10", "args": {"delayPktSize": 100, "delayInterval": "5ms"}},
    {"name": "e11", "args": {"delayPktSize": 100, "delayInterval": "4ms"}},
    {"name": "e12", "args": {"delayPktSize": 100, "delayInterval": "3ms"}},
    {"name": "e13", "args": {"delayPktSize": 100, "delayInterval": "2ms"}},
    {"name": "e14", "args": {"delayPktSize": 100, "delayInterval": "1ms"}},
    {"name": "e15", "args": {"delayPktSize": 100, "delayInterval": "8ms"}},
    {"name": "e16", "args": {"delayPktSize": 100, "delayInterval": "9ms"}},
    {"name": "e17", "args": {"delayPktSize": 100, "delayInterval": "11ms"}},
]

# Aggregate background-load sweep. These runs remain available for traffic-only
# studies, but are not repeated for every radio configuration.
BACKGROUND_LOAD_RUNS = [
    {"name": "c1", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 2.5}},
    {"name": "c2", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 5}},
    {"name": "c3", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 7.5}},
    {"name": "c4", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 10}},
    {"name": "c5", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 15}},
    {"name": "c6", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 20}},
    {"name": "c7", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25}},
    {"name": "c8", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 30}},
]

# Validate every maintained traffic sweep, including sweeps not used by the
# current radio study.
ALL_TRAFFIC_RUNS = [
    *PACKET_SIZE_RUNS,
    *INTER_PACKET_TIME_RUNS,
    *BACKGROUND_LOAD_RUNS,
]

# Radio-configuration changes only need the packet-size and inter-packet-time
# sweeps. Add another named sweep here only when it is required by this study.
RADIO_STUDY_RUNS = [
    *PACKET_SIZE_RUNS,
    *INTER_PACKET_TIME_RUNS,
]

# Additional traffic runs that extend the benchmark experiments. Move enabled
# entries into the appropriate named sweep above.
# ADDITIONAL_TRAFFIC_RUNS = [
#     # vary #pkts in burst
#     {"name": "z1", "args": {"delayTrafficSource": "burst", "delayBurstPackets": 2, "delayPktSize": 1400, "delayInterval": "50ms"}},
#     {"name": "z2", "args": {"delayTrafficSource": "burst", "delayBurstPackets": 3, "delayPktSize": 1400, "delayInterval": "50ms"}},
#     {"name": "z3", "args": {"delayTrafficSource": "burst", "delayBurstPackets": 4, "delayPktSize": 1400, "delayInterval": "50ms"}},
#     {"name": "z4", "args": {"delayTrafficSource": "burst", "delayBurstPackets": 5, "delayPktSize": 1400, "delayInterval": "50ms"}},
#     {"name": "z5", "args": {"delayTrafficSource": "burst", "delayBurstPackets": 6, "delayPktSize": 1400, "delayInterval": "50ms"}},
#     {"name": "z6", "args": {"delayTrafficSource": "burst", "delayBurstPackets": 7, "delayPktSize": 1400, "delayInterval": "50ms"}},
#     {"name": "z7", "args": {"delayTrafficSource": "burst", "delayBurstPackets": 8, "delayPktSize": 1400, "delayInterval": "50ms"}},
#     # vary sending rate
#     {"name": "e8", "args": {"delayPktSize": 100, "delayInterval": "7ms"}},
#     {"name": "e9", "args": {"delayPktSize": 100, "delayInterval": "6ms"}},
#     {"name": "e10", "args": {"delayPktSize": 100, "delayInterval": "5ms"}},
#     {"name": "e11", "args": {"delayPktSize": 100, "delayInterval": "4ms"}},
#     {"name": "e12", "args": {"delayPktSize": 100, "delayInterval": "3ms"}},
#     {"name": "e13", "args": {"delayPktSize": 100, "delayInterval": "2ms"}},
#     {"name": "e14", "args": {"delayPktSize": 100, "delayInterval": "1ms"}},
#     {"name": "e15", "args": {"delayPktSize": 100, "delayInterval": "8ms"}},
#     {"name": "e16", "args": {"delayPktSize": 100, "delayInterval": "9ms"}},
#     {"name": "e17", "args": {"delayPktSize": 100, "delayInterval": "11ms"}},
#     # vary background load
#     {"name": "c6", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 20}},
#     {"name": "c7", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25}},
#     {"name": "c8", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 30}},
#     # vary number of UEs in background with fixed total load at 25 Mbps
#     {"name": "x1", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 2}},
#     {"name": "x2", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 3}},
#     {"name": "x3", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 4}},
#     {"name": "x4", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 5}},
#     {"name": "x5", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 6}},
#     {"name": "x6", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 7}},
#     {"name": "x7", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 8}},
#     {"name": "x8", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 9}},
#     {"name": "x9", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 10}},
#     {"name": "x10", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 20}},
#     {"name": "x11", "args": {"delayPktSize": 100, "delayInterval": "50ms", "loadType": "udp", "totalBackgroundLoad": 25, "numBackgroundUes": 30}},
# ]


def format_args(args):
    # Turn a dict into ["--key=value", ...] for ns-3.
    parts = []
    for key, value in args.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        parts.append(f"--{key}={value}")
    return parts


def validate_simple_name(name, kind):
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError(f"invalid {kind} name: {name!r}")



def validate_sr_configuration(config_name, radio_args):
    numerology = radio_args["numerology"]
    periodicity = radio_args["srPeriodicitySlots"]
    offset = radio_args["srOffsetSlots"]
    pattern_string = radio_args["tddPattern"]
    pattern = pattern_string.split("|")

    standard_periodicities = STANDARD_SR_PERIODICITIES_BY_NUMEROLOGY.get(numerology)
    if standard_periodicities is None:
        raise ValueError(
            f"radio configuration {config_name!r} uses numerology {numerology}, "
            "for which no standard SR-periodicity table is configured"
        )
    if periodicity not in standard_periodicities:
        raise ValueError(
            f"radio configuration {config_name!r} uses non-standard SR periodicity "
            f"{periodicity} for numerology {numerology}; allowed slot periods are "
            f"{sorted(standard_periodicities)}"
        )
    if offset >= periodicity:
        raise ValueError(
            f"radio configuration {config_name!r} has SR offset {offset}, which must "
            f"be smaller than periodicity {periodicity}"
        )
    valid_slot_types = {"DL", "S", "F", "UL"}
    if not pattern or any(slot_type not in valid_slot_types for slot_type in pattern):
        raise ValueError(
            f"radio configuration {config_name!r} has an invalid TDD pattern: "
            f"{pattern_string!r}"
        )

    cycle_length = math.lcm(periodicity, len(pattern))
    invalid_opportunities = [
        slot
        for slot in range(offset, cycle_length, periodicity)
        if pattern[slot % len(pattern)] not in UL_CONTROL_SLOT_TYPES
    ]
    if invalid_opportunities:
        raise ValueError(
            f"radio configuration {config_name!r} has SR opportunities in slots "
            f"{invalid_opportunities} without UL control over the {cycle_length}-slot "
            "combined SR/TDD cycle"
        )


def validate_matrix():
    argument_groups = {
        "execution": set(EXECUTION_ARGS),
        "traffic": set(TRAFFIC_DEFAULTS),
        "radio": set(RADIO_DEFAULTS),
    }
    group_names = list(argument_groups)
    for index, first_name in enumerate(group_names):
        for second_name in group_names[index + 1:]:
            overlap = argument_groups[first_name] & argument_groups[second_name]
            if overlap:
                raise ValueError(
                    f"{first_name} and {second_name} arguments overlap: {sorted(overlap)}"
                )

    for config_name, overrides in RADIO_CONFIGS.items():
        validate_simple_name(config_name, "radio configuration")
        unknown = set(overrides) - argument_groups["radio"]
        if unknown:
            raise ValueError(
                f"radio configuration {config_name!r} contains non-radio keys: "
                f"{sorted(unknown)}"
            )
        validate_sr_configuration(config_name, {**RADIO_DEFAULTS, **overrides})

    seen_runs = set()
    for run in ALL_TRAFFIC_RUNS:
        run_name = run["name"]
        validate_simple_name(run_name, "traffic run")
        if run_name in seen_runs:
            raise ValueError(f"duplicate traffic run name: {run_name}")
        seen_runs.add(run_name)
        unknown = set(run["args"]) - argument_groups["traffic"]
        if unknown:
            raise ValueError(
                f"traffic run {run_name!r} contains non-traffic keys: {sorted(unknown)}"
            )


def build_run_spec(traffic_args, radio_args):
    merged = {
        **EXECUTION_ARGS,
        **TRAFFIC_DEFAULTS,
        **traffic_args,
        **RADIO_DEFAULTS,
        **radio_args,
    }
    return "delay-benchmarking-user " + " ".join(format_args(merged))


def build_run_specs():
    validate_matrix()
    specs = []
    for config_name, radio_args in RADIO_CONFIGS.items():
        for traffic_run in RADIO_STUDY_RUNS:
            run_name = traffic_run["name"]
            label = f"{config_name}/{run_name}"
            relative_output = Path(config_name) / run_name
            spec = build_run_spec(traffic_run["args"], radio_args)
            specs.append((label, relative_output, spec))
    return specs


script_dir = Path(__file__).resolve().parent
ns3_root = script_dir.parents[3]
parser = argparse.ArgumentParser(description="Run delay benchmarking simulations in parallel")
parser.add_argument(
    "--output-dir",
    required=True,
    help="Directory where configuration/run simulation logs should be written.",
)
args = parser.parse_args()
output_base = Path(args.output_dir).resolve()

output_base.mkdir(parents=True, exist_ok=True)
run_specs = build_run_specs()
print(
    f"Prepared {len(run_specs)} runs: {len(RADIO_CONFIGS)} radio configurations "
    f"x {len(RADIO_STUDY_RUNS)} radio-study traffic experiments"
)

running = []
idx = 0
failed = []

while idx < len(run_specs) or running:
    # Start new runs until MAX_PARALLEL is reached.
    while idx < len(run_specs) and len(running) < MAX_PARALLEL:
        label, relative_output, spec = run_specs[idx]
        run_dir = output_base / relative_output
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run_cmd.txt").write_text(spec + "\n")
        cmd = [str(ns3_root / "./ns3"), "run", "--no-build", spec, f"--cwd={run_dir}"]
        print(f"Command for {label}: {shlex.join(cmd)}")
        stdout_f = (run_dir / "stdout.log").open("w")
        stderr_f = (run_dir / "stderr.log").open("w")
        start_time = time.perf_counter()
        proc = subprocess.Popen(cmd, cwd=ns3_root, stdout=stdout_f, stderr=stderr_f)
        running.append((proc, stdout_f, stderr_f, label, start_time))
        print(f"Started {label}")
        idx += 1
        time.sleep(1)

    # Check for completed runs and close logs.
    still_running = []
    for proc, stdout_f, stderr_f, label, start_time in running:
        if proc.poll() is None:
            still_running.append((proc, stdout_f, stderr_f, label, start_time))
        else:
            stdout_f.close()
            stderr_f.close()
            elapsed_s = time.perf_counter() - start_time
            print(f"Finished {label} in {elapsed_s:.1f}s")
            if proc.returncode != 0:
                failed.append(label)
                print(f"Failed run: {label}")
    running = still_running
    if running:
        time.sleep(1)

if failed:
    print("Failed runs:", ", ".join(failed))
    raise SystemExit(1)
