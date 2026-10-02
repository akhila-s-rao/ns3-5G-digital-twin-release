#!/usr/bin/env python3
"""Create per-burst unique initial RLC-PDU counts from simulation traces."""

import argparse
import re
from pathlib import Path

import pandas as pd


TRACE_FILENAME = "NrUlRlcTxComponentStats.txt"
DELAY_SUFFIX = "_5Glena_delay_decomposition.csv"
OUTPUT_COLUMNS = [
    "run",
    "burst_id",
    "packets_per_burst",
    "packet_id_first",
    "packet_id_last",
    "initial_rlc_segments",
]


def run_sort_key(path: Path) -> int:
    match = re.fullmatch(r"z(\d+)", path.name)
    return int(match.group(1)) if match else 0


def complete_burst_ids(delay_path: Path, burst_size: int) -> pd.Index:
    frame = pd.read_csv(delay_path, usecols=["pkt_id", "ran_delay_ms"])
    frame["pkt_id"] = pd.to_numeric(frame["pkt_id"], errors="coerce")
    frame["ran_delay_ms"] = pd.to_numeric(
        frame["ran_delay_ms"], errors="coerce"
    )
    frame = frame.loc[
        frame["pkt_id"].gt(0)
        & frame["pkt_id"].ne(1)
        & frame["ran_delay_ms"].ge(0)
    ].dropna(subset=["pkt_id"])
    frame["burst_id"] = (frame["pkt_id"].astype(int) - 1) // burst_size
    frame = frame.loc[frame["burst_id"] > 0]
    packet_counts = frame.groupby("burst_id")["pkt_id"].nunique()
    return packet_counts[packet_counts.eq(burst_size)].index


def burst_segment_counts(
    run: str,
    trace_path: Path,
    complete_ids: pd.Index,
    burst_size: int,
) -> pd.DataFrame:
    trace_columns = ["rnti", "lcid", "rlc_sn", "pkt_id"]
    frame = pd.read_csv(trace_path, sep="\t", usecols=trace_columns)
    frame[trace_columns] = frame[trace_columns].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=trace_columns)
    frame = frame.loc[frame["pkt_id"].gt(0)].copy()
    frame["pkt_id"] = frame["pkt_id"].astype(int)
    frame["burst_id"] = (frame["pkt_id"] - 1) // burst_size
    frame = frame.loc[frame["burst_id"].isin(complete_ids)]

    # One RLC PDU can contain bytes from several application packets. Count its
    # sequence number once per burst, not once for every packet component row.
    initial_pdus = frame.drop_duplicates(
        ["burst_id", "rnti", "lcid", "rlc_sn"]
    )
    counts = initial_pdus.groupby("burst_id").size().rename(
        "initial_rlc_segments"
    )
    missing = complete_ids.difference(counts.index)
    if not missing.empty:
        raise ValueError(
            f"{run}: {len(missing)} completed bursts have no RLC component trace"
        )

    result = counts.reindex(complete_ids).reset_index()
    result.insert(0, "run", run)
    result["packets_per_burst"] = burst_size
    result["packet_id_first"] = result["burst_id"] * burst_size + 1
    result["packet_id_last"] = result["packet_id_first"] + burst_size - 1
    return result[OUTPUT_COLUMNS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create unique initial RLC-PDU counts for completed z bursts."
    )
    parser.add_argument(
        "--raw-dir",
        required=True,
        type=Path,
        help="Directory containing the raw per-run simulation directories.",
    )
    parser.add_argument(
        "--delay-dir",
        required=True,
        type=Path,
        help="Directory containing processed delay-decomposition CSVs.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output burst-level CSV path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dirs = sorted(
        [
            path
            for path in args.raw_dir.iterdir()
            if path.is_dir() and re.fullmatch(r"z\d+", path.name)
        ],
        key=run_sort_key,
    )
    if not run_dirs:
        raise ValueError(f"no z run directories found in {args.raw_dir}")

    results = []
    for run_dir in run_dirs:
        run = run_dir.name
        burst_size = int(run[1:]) + 1
        trace_path = run_dir / TRACE_FILENAME
        delay_path = args.delay_dir / f"{run}{DELAY_SUFFIX}"
        if not trace_path.is_file() or not delay_path.is_file():
            raise ValueError(f"missing input for {run}: {trace_path} or {delay_path}")
        complete_ids = complete_burst_ids(delay_path, burst_size)
        result = burst_segment_counts(
            run, trace_path, complete_ids, burst_size
        )
        results.append(result)
        mean_segments = result["initial_rlc_segments"].mean()
        print(
            f"Processed {run}: {len(result):,} completed bursts; "
            f"mean unique initial RLC segments={mean_segments:.3f}"
        )

    output = pd.concat(results, ignore_index=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(f"Wrote {len(output):,} rows to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
