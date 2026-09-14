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

# Runs for expeca delay component distribution comparison as well as for benchmarking between testbeds and simulation
RUNS = [
     # vary pkt size
     {"name": "a1", "args": {"delayPacketSize": 50, "delayInterval": "50ms"}},
     {"name": "a2", "args": {"delayPacketSize": 100, "delayInterval": "50ms"}},
     {"name": "a3", "args": {"delayPacketSize": 200, "delayInterval": "50ms"}},
     {"name": "a4", "args": {"delayPacketSize": 1000, "delayInterval": "50ms"}},
     {"name": "a5", "args": {"delayPacketSize": 1200, "delayInterval": "50ms"}},
     {"name": "a6", "args": {"delayPacketSize": 1400, "delayInterval": "50ms"}},
     {"name": "a7", "args": {"delayPacketSize": 12, "delayInterval": "50ms"}},
     # vary sending rate
     {"name": "e1", "args": {"delayPacketSize": 100, "delayInterval": "10ms"}},
     {"name": "e2", "args": {"delayPacketSize": 100, "delayInterval": "15ms"}},
     {"name": "e3", "args": {"delayPacketSize": 100, "delayInterval": "20ms"}},
     {"name": "e4", "args": {"delayPacketSize": 100, "delayInterval": "25ms"}},
     {"name": "e5", "args": {"delayPacketSize": 100, "delayInterval": "50ms"}},
     {"name": "e6", "args": {"delayPacketSize": 100, "delayInterval": "75ms"}},
     {"name": "e7", "args": {"delayPacketSize": 100, "delayInterval": "100ms"}},
     # vary background load
     {"name": "c1", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 2.5}},
     {"name": "c2", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 5}},
     {"name": "c3", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 7.5}},
     {"name": "c4", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 10}},
     {"name": "c5", "args": {"delayPacketSize": 100, "delayInterval": "50ms", "loadType": "udp", "cbrLoad": 15}},
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
