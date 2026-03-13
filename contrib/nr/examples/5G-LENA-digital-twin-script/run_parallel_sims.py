#!/usr/bin/env python3
from pathlib import Path
import os
import shlex
import subprocess
import time

# Simple settings you can edit.
MAX_PARALLEL = max(1, (os.cpu_count() or 1))
OUTPUT_BASE = Path(__file__).resolve().parent / "sim_campaign_logs"

# Common CLI args shared by all runs.
COMMON_ARGS = {
    "digitalTwinScenario": "expeca",
    "channelScenario": "InH-OfficeOpen",
    "numUes": 10,
    "numUesWithVrApp": 3,
    "vrTrafficType": "synthetic",
    "vrFrameRate": 30,
    "vrTargetDataRateMbps": 5,
    "vrAppProfile": "VirusPopper",
    "appGenerationTime": 1000,
    "progressInterval": "1s",
    "vrBearerQci": 80,
    "controlBearerQci": 80,
    "createRemMap": False,
    "randomSeed": 13,
}

RUNS = [
    {"name": "run01", "args": {"numUesWithVrApp": 3}},# default run
    {"name": "run02", "args": {"numUesWithVrApp": 2}},
    {"name": "run03", "args": {"numUesWithVrApp": 5}},
    {"name": "run04", "args": {"numUesWithVrApp": 6}},
    {"name": "run05", "args": {"channelScenario": "InH-OfficeMixed"}},
    {"name": "run06", "args": {"channelScenario": "UMi"}},
    {"name": "run07", "args": {"channelScenario": "UMa"}},
    {"name": "run08", "args": {"controlBearerQci": 69}},
    {"name": "run09", "args": {"controlBearerQci": 83}},
    {"name": "run10", "args": {"controlBearerQci": 5}},
    {"name": "run11", "args": {"vrAppProfile": "Minecraft"}},
    {"name": "run12", "args": {"vrAppProfile": "GoogleEarthVrCities"}},
    {"name": "run13", "args": {"vrAppProfile": "GoogleEarthVrTour"}},
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
    return "cellular-network-user " + " ".join(format_args(merged))


script_dir = Path(__file__).resolve().parent
ns3_root = script_dir.parents[3]

OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
run_specs = [(r["name"], build_run_spec(COMMON_ARGS, r["args"])) for r in RUNS]

running = []
idx = 0
failed = []

while idx < len(run_specs) or running:
    # Start new runs until MAX_PARALLEL is reached.
    while idx < len(run_specs) and len(running) < MAX_PARALLEL:
        name, spec = run_specs[idx]
        run_dir = OUTPUT_BASE / name
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
