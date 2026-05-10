#!/usr/bin/env python3
from pathlib import Path
import argparse
import os
import shlex
import subprocess
import time

# Simple settings you can edit.
MAX_PARALLEL = max(1, (os.cpu_count() or 1))

# Common CLI args shared by all runs.
COMMON_ARGS = {
    "digitalTwinScenario": "expeca",
    "channelScenario": "InH-OfficeOpen",
    "direction": "ul",
    "loadType": "none",
    "cbrLoad": 10,
    "delayPacketSize": 1400,
    "delayInterval": "100ms",
    "appGenerationTime": 1000,
    "progressInterval": "1s",
    "controlBearerQci": 80,
    "fixUlMcs": 0,
    "randomSeed": 3,
}

# Runs for expeca delay component distribution comparison 
# RUNS = [
#     # vary pkt size
#     {"name": "benchmark01", "args": {"delayPacketSize": 20, "delayInterval": "50ms", "randomSeed": 3}},
#     {"name": "benchmark02", "args": {"delayPacketSize": 50, "delayInterval": "50ms", "randomSeed": 3}},
#     {"name": "benchmark03", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "randomSeed": 3}},
#     {"name": "benchmark04", "args": {"delayPacketSize": 200, "delayInterval": "50ms", "randomSeed": 3}},
#     {"name": "benchmark05", "args": {"delayPacketSize": 500, "delayInterval": "50ms", "randomSeed": 3}},
#     {"name": "benchmark06", "args": {"delayPacketSize": 1000, "delayInterval": "50ms", "randomSeed": 3}},
#     {"name": "benchmark07", "args": {"delayPacketSize": 1500, "delayInterval": "50ms", "randomSeed": 3}},
#     {"name": "benchmark08", "args": {"delayPacketSize": 2000, "delayInterval": "50ms", "randomSeed": 3}},
#     # vary sending rate
#     {"name": "benchmark09", "args": {"delayPacketSize": 100, "delayInterval": "10ms", "randomSeed": 3}},
#     {"name": "benchmark10", "args": {"delayPacketSize": 100, "delayInterval": "15ms", "randomSeed": 3}},
#     {"name": "benchmark11", "args": {"delayPacketSize": 100, "delayInterval": "20ms", "randomSeed": 3}},
#     {"name": "benchmark12", "args": {"delayPacketSize": 100, "delayInterval": "25ms", "randomSeed": 3}},
#     {"name": "benchmark13", "args": {"delayPacketSize": 100, "delayInterval": "100ms", "randomSeed": 3}},
#     # with background load
#     {"name": "benchmark14", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 0.0001}},
#     {"name": "benchmark15", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 2.5}},
#     {"name": "benchmark16", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 5}},
#     {"name": "benchmark17", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 7.5}},
#     {"name": "benchmark18", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 10}},
# ]



# Runs for benchmarking
# Runs with no load
RUNS = [
    # Vary packet payload size, with fixed inter packet time range (50 B to 1400 B)
    # 50 B payload + headers is within a VOIP packet size range and fits into the first 1 PRB allocation by the Gnb for the UL BSR. This means we do not see ant RLC segmentation
    # 1400 B payload represents typical IP packets that wont get fragmented with a 1500 MTU at the IP layer.   
    {"name": "benchmark01", "args": {"delayPacketSize": 50, "delayInterval": "50ms"}},
    {"name": "benchmark02", "args": {"delayPacketSize": 100, "delayInterval": "50ms"}},
    {"name": "benchmark03", "args": {"delayPacketSize": 500, "delayInterval": "50ms"}},
    {"name": "benchmark04", "args": {"delayPacketSize": 1000, "delayInterval": "50ms"}},
    {"name": "benchmark05", "args": {"delayPacketSize": 1400, "delayInterval": "50ms"}},
    # Vary inter packet time, with fixed packet payload size range (20 ms to 100 ms)
    {"name": "benchmark06", "args": {"delayPacketSize": 1400, "delayInterval": "20ms"}},
    {"name": "benchmark07", "args": {"delayPacketSize": 1400, "delayInterval": "25ms"}},
    {"name": "benchmark08", "args": {"delayPacketSize": 1400, "delayInterval": "75ms"}},
    {"name": "benchmark09", "args": {"delayPacketSize": 1400, "delayInterval": "100ms"}},

    # Runs with UDP load
    #25 % UDP load

    {"name": "benchmark10", "args": {"delayPacketSize": 50, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 10}},
    {"name": "benchmark11", "args": {"delayPacketSize": 1400, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 10}},
    # Vary inter packet time, with fixed packet payload size range (20 ms to 100 ms)
    {"name": "benchmark12", "args": {"delayPacketSize": 1400, "delayInterval": "20ms", "loadType": "udp", "cbrLoad": 10}},
    {"name": "benchmark13", "args": {"delayPacketSize": 1400, "delayInterval": "100ms", "loadType": "udp", "cbrLoad": 10}},
    
    #50 % UDP load
    {"name": "benchmark14", "args": {"delayPacketSize": 50, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 20}},
    {"name": "benchmark15", "args": {"delayPacketSize": 1400, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 20}},
    # Vary inter packet time, with fixed packet payload size range (20 ms to 100 ms)
    {"name": "benchmark16", "args": {"delayPacketSize": 1400, "delayInterval": "20ms", "loadType": "udp", "cbrLoad": 20}},
    {"name": "benchmark17", "args": {"delayPacketSize": 1400, "delayInterval": "100ms", "loadType": "udp", "cbrLoad": 20}},

    #75 % UDP load
    {"name": "benchmark18", "args": {"delayPacketSize": 50, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 30}},
    {"name": "benchmark19", "args": {"delayPacketSize": 1400, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 30}},
    # Vary inter packet time, with fixed packet payload size range (20 ms to 100 ms)
    {"name": "benchmark20", "args": {"delayPacketSize": 1400, "delayInterval": "20ms", "loadType": "udp", "cbrLoad": 30}},
    {"name": "benchmark21", "args": {"delayPacketSize": 1400, "delayInterval": "100ms", "loadType": "udp", "cbrLoad": 30}},

    #Runs with TCP load
    {"name": "benchmark22", "args": {"delayPacketSize": 50, "delayInterval": "50ms", "loadType": "tcp"}},
    {"name": "benchmark23", "args": {"delayPacketSize": 1400, "delayInterval": "50ms", "loadType": "tcp"}},
    # Vary inter packet time, with fixed packet payload size range (20 ms to 100 ms)
    {"name": "benchmark24", "args": {"delayPacketSize": 1400, "delayInterval": "20ms", "loadType": "tcp"}},
    {"name": "benchmark25", "args": {"delayPacketSize": 1400, "delayInterval": "100ms", "loadType": "tcp"}},
]


def format_args(args):
    # Turn a dict into ["--key=value", ...] for ns-3.
    parts = []
    for key, value in args.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        parts.append(f"--{key}={value}")
    return parts


def build_run_spec(common, run_args):
    # Merge common args with per-run args.
    merged = dict(common)
    merged.update(run_args)
    return "delay-benchmarking-user " + " ".join(format_args(merged))


script_dir = Path(__file__).resolve().parent
ns3_root = script_dir.parents[3]
parser = argparse.ArgumentParser(description="Run delay benchmarking simulations in parallel")
parser.add_argument(
    "--output-dir",
    required=True,
    help="Directory where per-run simulation logs should be written.",
)
args = parser.parse_args()
output_base = Path(args.output_dir).resolve()

output_base.mkdir(parents=True, exist_ok=True)
run_specs = [(r["name"], build_run_spec(COMMON_ARGS, r["args"])) for r in RUNS]

running = []
idx = 0
failed = []

while idx < len(run_specs) or running:
    # Start new runs until MAX_PARALLEL is reached.
    while idx < len(run_specs) and len(running) < MAX_PARALLEL:
        name, spec = run_specs[idx]
        run_dir = output_base / name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run_cmd.txt").write_text(spec + "\n")
        cmd = [str(ns3_root / "./ns3"), "run", "--no-build", spec, f"--cwd={run_dir}"]
        print(f"Command for {name}: {shlex.join(cmd)}")
        stdout_f = (run_dir / "stdout.log").open("w")
        stderr_f = (run_dir / "stderr.log").open("w")
        start_time = time.perf_counter()
        proc = subprocess.Popen(cmd, cwd=ns3_root, stdout=stdout_f, stderr=stderr_f)
        running.append((proc, stdout_f, stderr_f, name, start_time))
        print(f"Started {name}")
        idx += 1
        time.sleep(1)

    # Check for completed runs and close logs.
    still_running = []
    for proc, stdout_f, stderr_f, name, start_time in running:
        if proc.poll() is None:
            still_running.append((proc, stdout_f, stderr_f, name, start_time))
        else:
            stdout_f.close()
            stderr_f.close()
            elapsed_s = time.perf_counter() - start_time
            print(f"Finished {name} in {elapsed_s:.1f}s")
            if proc.returncode != 0:
                failed.append(name)
                print(f"Failed run: {name}")
    running = still_running
    if running:
        time.sleep(1)

if failed:
    print("Failed runs:", ", ".join(failed))
