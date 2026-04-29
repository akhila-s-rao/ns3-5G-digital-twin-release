#!/usr/bin/env python3
"""Summarize delivery rates and delay percentiles from ns-3 digital-twin traces."""

import argparse
from pathlib import Path

import pandas as pd

PERCENTILES = [0.05, 0.50, 0.95]


def load(path: Path, cols) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path, sep="\t", usecols=cols)
    if "delay" in df:
        df["delay"] = df["delay"].astype(float) / 1e6
    return df


def summarize(df: pd.DataFrame, group_cols, label: str):
    if df.empty:
        print(f"{label}: no data\n")
        return
    grouped = df.groupby(group_cols)
    stats = pd.DataFrame({
        "delivered": grouped["seqNum"].nunique(),
        "expected": grouped["seqNum"].max() + 1,
    })
    percentiles = grouped["delay"].quantile(PERCENTILES).unstack(-1)
    stats = stats.join(percentiles).reset_index()
    print(label + ":")
    for _, row in stats.iterrows():
        ident = ", ".join(f"{col}={row[col]}" for col in group_cols)
        rate = row["delivered"] / row["expected"] if row["expected"] else 0.0
        p5, p50, p95 = (row.get(p, float("nan")) for p in PERCENTILES)
        print(
            f"  {ident}: delivery={rate:.4f} "
            f"(delivered={int(row['delivered'])}/{int(row['expected'])}), "
            f"p5={p5:.6f}s p50={p50:.6f}s p95={p95:.6f}s"
        )
    print()


def summarize_vr(df: pd.DataFrame):
    if df.empty:
        print("VR fragments: no data")
        return
    per_burst = df.groupby(["ueId", "burstSeqNum"])
    delivered = per_burst["fragSeqNum"].nunique().groupby("ueId").sum()
    expected = per_burst["numFragsInBurst"].max().groupby("ueId").sum()
    delays = df.groupby("ueId")["delay"].quantile(PERCENTILES).unstack(-1)
    print("VR fragments:")
    for ue in delivered.index:
        exp = expected.get(ue, 0)
        deliv = delivered.get(ue, 0)
        rate = deliv / exp if exp else 0.0
        p5, p50, p95 = (delays.loc[ue].get(p, float("nan")) for p in PERCENTILES)
        print(
            f"  UE {ue}: delivery={rate:.4f} "
            f"(delivered={deliv}/{exp}), "
            f"p5={p5:.6f}s p50={p50:.6f}s p95={p95:.6f}s"
        )


def main():
    parser = argparse.ArgumentParser(description="Trace statistics helper")
    parser.add_argument(
        "--trace-dir",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "traceFiles",
        help="Directory containing delay_trace.txt, rtt_trace.txt, vrFragment_trace.txt",
    )
    args = parser.parse_args()

    delay_df = load(args.trace_dir / "delay_trace.txt", ["dir", "ueId", "seqNum", "delay"])
    rtt_df = load(args.trace_dir / "rtt_trace.txt", ["ueId", "seqNum", "delay"])
    vr_df = load(
        args.trace_dir / "vrFragment_trace.txt",
        ["ueId", "burstSeqNum", "numFragsInBurst", "fragSeqNum", "delay"],
    )

    summarize(delay_df, ["dir", "ueId"], "Delay probes")
    summarize(rtt_df, ["ueId"], "RTT echoes")
    summarize_vr(vr_df)


if __name__ == "__main__":
    main()
