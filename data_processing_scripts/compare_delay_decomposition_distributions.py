#!/usr/bin/env python3
import argparse
from pathlib import Path
import re

import pandas as pd
import os
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib.pyplot as plt
import numpy as np

FONT_SIZE = 12
LABEL_FONT_SIZE = 14
ANNOTATION_FONT_SIZE = 16
TITLE_FONT_SIZE = LABEL_FONT_SIZE * 2
EXPECA_CSV_REQUIRED_COLUMNS = {
    "End to End Delay",
    "Scheduling delay",
    "Transmission delay",
    "Retransmission delay",
    "Queuing delay",
    "Ran delay",
    "Frame alignment delay",
    "segmentation delay",
    "No of RLC attempts",
}
LENA_CSV_REQUIRED_COLUMNS = {
    "ran_delay_ms",
    "queueing_delay_ms",
    "frame_alignment_delay_ms",
    "scheduling_delay_ms",
    "tx_retx_delay_ms",
    "delay_residual_ms",
    "segmentation_delay_ms",
    "rlc_segments_per_pkt",
}
BENCHMARK_TITLE_BY_RUN: dict[int, str] = {
    1: "pkt_size=20B | inter_pkt=50ms | bg=none",
    2: "pkt_size=50B | inter_pkt=50ms | bg=none",
    3: "pkt_size=100B | inter_pkt=50ms | bg=none",
    4: "pkt_size=200B | inter_pkt=50ms | bg=none",
    5: "pkt_size=500B | inter_pkt=50ms | bg=none",
    6: "pkt_size=1000B | inter_pkt=50ms | bg=none",
    7: "pkt_size=1500B | inter_pkt=50ms | bg=none",
    8: "pkt_size=2000B | inter_pkt=50ms | bg=none",
    9: "pkt_size=100B | inter_pkt=10ms | bg=none",
    10: "pkt_size=100B | inter_pkt=15ms | bg=none",
    11: "pkt_size=100B | inter_pkt=20ms | bg=none",
    12: "pkt_size=100B | inter_pkt=25ms | bg=none",
    13: "pkt_size=100B | inter_pkt=100ms | bg=none",
    14: "pkt_size=100B | inter_pkt=50ms | bg=udp(cbrLoad=0.0001)",
    15: "pkt_size=100B | inter_pkt=50ms | bg=udp(cbrLoad=2.5)",
    16: "pkt_size=100B | inter_pkt=50ms | bg=udp(cbrLoad=5)",
    17: "pkt_size=100B | inter_pkt=50ms | bg=udp(cbrLoad=7.5)",
    18: "pkt_size=100B | inter_pkt=50ms | bg=udp(cbrLoad=10)",
}

def empty_series() -> pd.Series:
    return pd.Series(dtype=float)

def format_annotation_value(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"

def plot_hist(values, bins, xlabel, ax):
    values = values.dropna()
    if values.shape[0] == 0:
        ax.set_visible(False)
        return
    vmin = float(values.min())
    vmed = float(values.median())
    vmax = float(values.max())
    ax.hist(values, bins=bins, edgecolor="black", alpha=0.85, density=True)
    ax.set_xlabel(xlabel, fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel("")
    ax.text(
        0.98, 0.98,
        f"min: {format_annotation_value(vmin)}\n"
        f"med: {format_annotation_value(vmed)}\n"
        f"max: {format_annotation_value(vmax)}",
        ha="right", va="top", transform=ax.transAxes,
        fontsize=ANNOTATION_FONT_SIZE,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, edgecolor="none"),
    )

def plot_cdf(values, xlabel, ax, ylabel="CDF"):
    values = values.dropna()
    if values.shape[0] == 0:
        ax.set_visible(False)
        return
    vmin = float(values.min())
    vmed = float(values.median())
    vmax = float(values.max())
    values = np.sort(values.to_numpy())
    y = np.linspace(0.0, 1.0, num=values.size, endpoint=True)
    ax.plot(values, y, linewidth=0.9)
    ax.set_xlabel(xlabel, fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel(ylabel, fontsize=LABEL_FONT_SIZE)
    ax.text(
        0.98, 0.98,
        f"min: {format_annotation_value(vmin)}\n"
        f"med: {format_annotation_value(vmed)}\n"
        f"max: {format_annotation_value(vmax)}",
        ha="right", va="top", transform=ax.transAxes,
        fontsize=ANNOTATION_FONT_SIZE,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, edgecolor="none"),
    )

def plot_series_by_index(series: pd.Series, ax, label, x_label="Packet index"):
    series = pd.to_numeric(series, errors="coerce").dropna()
    if series.empty:
        ax.set_visible(False)
        return
    vmin = float(series.min())
    vmed = float(series.median())
    vmax = float(series.max())
    ax.plot(np.arange(series.size), series.to_numpy(), linewidth=0.8)
    ax.set_xlabel(x_label, fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel(label, fontsize=LABEL_FONT_SIZE)
    ax.text(
        0.98, 0.98,
        f"min: {format_annotation_value(vmin)}\n"
        f"med: {format_annotation_value(vmed)}\n"
        f"max: {format_annotation_value(vmax)}",
        ha="right", va="top", transform=ax.transAxes,
        fontsize=ANNOTATION_FONT_SIZE,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, edgecolor="none"),
    )

def expeca_csv_has_required_columns(csv_path: Path) -> bool:
    try:
        cols = set(pd.read_csv(csv_path, nrows=0).columns)
    except Exception:
        return False
    return EXPECA_CSV_REQUIRED_COLUMNS.issubset(cols)


def find_expeca_csv_runs(base_dir: Path) -> list[Path]:
    """Find ExPeCA CSV runs under a directory tree."""
    csv_files = sorted(p for p in base_dir.rglob("*.csv") if p.is_file())
    return [p for p in csv_files if expeca_csv_has_required_columns(p)]


def lena_csv_has_required_columns(csv_path: Path) -> bool:
    try:
        cols = set(pd.read_csv(csv_path, nrows=0).columns)
    except Exception:
        return False
    return LENA_CSV_REQUIRED_COLUMNS.issubset(cols)


def find_lena_delay_decomposition_csv_runs(base_dir: Path) -> list[Path]:
    """Find generated 5G-LENA delay decomposition CSVs under a directory tree."""
    csv_files = sorted(p for p in base_dir.rglob("*.csv") if p.is_file())
    return [p for p in csv_files if lena_csv_has_required_columns(p)]


def extract_run_number(name: str) -> int | None:
    m = re.search(r"0*(\d+)", name)
    if m:
        return int(m.group(1))
    return None


def index_paths_by_run_number(paths: list[Path], label: str) -> dict[int, Path]:
    out: dict[int, Path] = {}
    for path in sorted(paths):
        run_no = extract_run_number(path.stem if path.is_file() else path.name)
        if run_no is None:
            print(f"WARN: could not infer run number for {label} path: {path}")
            continue
        if run_no in out:
            print(f"WARN: duplicate {label} run number {run_no}, keeping first: {out[run_no]}, skipping {path}")
            continue
        out[run_no] = path
    return out


def load_expeca_csv_metrics(csv_path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        print(f"WARN: failed reading ExPeCA CSV {csv_path}: {exc}")
        return None
    missing = EXPECA_CSV_REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        print(f"WARN: skipping {csv_path}, missing columns: {sorted(missing)}")
        return None

    rename_map = {
        "Packet SN": "packet_sn",
        "Packet ID": "packet_id",
        "Packet Length": "packet_length",
        "No of RLC attempts": "rlc_attempts",
        "mcs": "mcs",
        "Max No of MAC attempts": "max_mac_attempts",
        "segmentation delay": "segmentation_delay_ms",
        "segmentation_delay": "segmentation_delay_ms",
        "Retransmission delay": "retransmission_delay_ms",
        "retransmission_delay": "retransmission_delay_ms",
        "Transmission delay": "transmission_delay_ms",
        "transmission_delay": "transmission_delay_ms",
        "End to End Delay": "ul_end_to_end_delay_ms",
        "e2e_delay": "ul_end_to_end_delay_ms",
        "Frame alignment delay": "frame_alignment_delay_ms",
        "Scheduling delay": "scheduling_delay_ms",
        "Ran delay": "ran_delay_ms",
        "ran_delay": "ran_delay_ms",
        "Queuing delay": "queueing_delay_ms",
        "queuing_delay": "queueing_delay_ms",
    }
    df = df.rename(columns=rename_map)
    for col in rename_map.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Match naming used for 5G-LENA-side plots in this script.
    df["tx_retx_delay_ms"] = (
        df.get("transmission_delay_ms", pd.Series(dtype=float)).fillna(0.0)
        + df.get("retransmission_delay_ms", pd.Series(dtype=float)).fillna(0.0)
    )
    df["delay_residual_ms"] = df["ul_end_to_end_delay_ms"] - (
        df["queueing_delay_ms"]
        + df["transmission_delay_ms"]
        + df["retransmission_delay_ms"]
        + df["segmentation_delay_ms"]
    )
    return df


def build_expeca_compare_metric_items(df: pd.DataFrame) -> list[tuple[pd.Series, str]]:
    items = [
        (df["ul_end_to_end_delay_ms"], "Uplink end-to-end delay (ms)"),
        (df["queueing_delay_ms"], "Queueing delay (ms)"),
        (df["frame_alignment_delay_ms"], "Frame alignment delay (ms)"),
        (df["scheduling_delay_ms"], "Scheduling delay (ms)"),
        # Re-enable this if HOL grant wait delay should be plotted again.
        # (empty_series(), "HOL grant wait delay (ms)"),
        (df["tx_retx_delay_ms"], "tx + retx delay (ms)"),
    ]
    # Re-enable this if reordering delay should be plotted again.
    # items.append((empty_series(), "Reordering delay (ms)"))
    items.extend([
        (df["delay_residual_ms"], "Delay residual (ms)"),
        (df["segmentation_delay_ms"], "Segmentation delay (ms)"),
        (df["rlc_attempts"], "RLC segments per packet"),
    ])
    return items


def load_lena_delay_decomposition_csv_metrics(csv_path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        print(f"WARN: failed reading 5G-LENA delay decomposition CSV {csv_path}: {exc}")
        return None
    missing = LENA_CSV_REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        print(f"WARN: skipping {csv_path}, missing columns: {sorted(missing)}")
        return None
    if "rnti" in df.columns:
        df["rnti"] = pd.to_numeric(df["rnti"], errors="coerce")
        rnti_counts = df["rnti"].dropna().value_counts()
        if not rnti_counts.empty:
            selected_rnti = rnti_counts.sort_values(kind="stable").index[0]
            df = df[df["rnti"] == selected_rnti].copy()
            print(
                f"INFO: {csv_path.name}: keeping rnti={format_annotation_value(float(selected_rnti))} "
                f"with {rnti_counts[selected_rnti]} rows"
            )
    for col in LENA_CSV_REQUIRED_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_lena_compare_metric_items(df: pd.DataFrame) -> list[tuple[pd.Series, str]]:
    return [
        (df["ran_delay_ms"], "RAN delay (ms)"),
        (df["queueing_delay_ms"], "Queueing delay (ms)"),
        (df["frame_alignment_delay_ms"], "Frame alignment delay (ms)"),
        (df["scheduling_delay_ms"], "Scheduling delay (ms)"),
        # Re-enable this if HOL grant wait delay should be plotted again.
        # (df["hol_wait_ms"], "HOL grant wait delay (ms)"),
        (df["tx_retx_delay_ms"], "tx + retx delay (ms)"),
        # Re-enable this if reordering delay should be plotted again.
        # (df["reordering_delay_ms"], "Reordering delay (ms)"),
        (df["delay_residual_ms"], "Delay residual (ms)"),
        (df["segmentation_delay_ms"], "Segmentation delay (ms)"),
        (df["rlc_segments_per_pkt"], "RLC segments per packet"),
    ]


def plot_compare_pair(run_no: int,
                      expeca_csv: Path,
                      lena_csv: Path,
                      output_root: Path) -> None:
    expeca_df = load_expeca_csv_metrics(expeca_csv)
    if expeca_df is None or expeca_df.empty:
        print(f"WARN: skipping run{run_no:02d}, unusable ExPeCA CSV: {expeca_csv}")
        return
    lena_df = load_lena_delay_decomposition_csv_metrics(lena_csv)
    if lena_df is None or lena_df.empty:
        print(f"WARN: skipping run{run_no:02d}, unusable 5G-LENA delay decomposition CSV: {lena_csv}")
        return

    output_root.mkdir(parents=True, exist_ok=True)
    expeca_items = build_expeca_compare_metric_items(expeca_df)
    lena_items = build_lena_compare_metric_items(lena_df)

    run_label = f"run{run_no:02d}"
    benchmark_desc = BENCHMARK_TITLE_BY_RUN.get(run_no)
    compare_label = f"{run_label} | {benchmark_desc}" if benchmark_desc else run_label

    cols = len(expeca_items)
    fig, axes = plt.subplots(2, cols, figsize=(cols * 5.5, 2 * 4.7))
    for col, ((ex_series, label1), (lena_series, label2)) in enumerate(zip(expeca_items, lena_items)):
        plot_hist(ex_series, bins=50, xlabel=label1, ax=axes[0, col])
        plot_hist(lena_series, bins=50, xlabel=label2, ax=axes[1, col])
    fig.text(0.01, 0.74, "ExPeCA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.text(0.01, 0.28, "5G-LENA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.suptitle(f"{compare_label} | Histograms", fontsize=TITLE_FONT_SIZE, y=0.995)
    fig.tight_layout(rect=[0.03, 0, 1, 0.95])
    fig.savefig(output_root / f"{run_label}_histograms.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, cols, figsize=(cols * 5.5, 2 * 4.7))
    for col, ((ex_series, label1), (lena_series, label2)) in enumerate(zip(expeca_items, lena_items)):
        plot_cdf(ex_series, xlabel=label1, ax=axes[0, col])
        plot_cdf(lena_series, xlabel=label2, ax=axes[1, col])
    fig.text(0.01, 0.74, "ExPeCA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.text(0.01, 0.28, "5G-LENA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.suptitle(f"{compare_label} | CDFs", fontsize=TITLE_FONT_SIZE, y=0.995)
    fig.tight_layout(rect=[0.03, 0, 1, 0.95])
    fig.savefig(output_root / f"{run_label}_cdf.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, cols, figsize=(cols * 5.5, 2 * 4.7))
    for col, ((ex_series, ex_label), (lena_series, lena_label)) in enumerate(zip(expeca_items, lena_items)):
        plot_series_by_index(ex_series, axes[0, col], ex_label)
        plot_series_by_index(lena_series, axes[1, col], lena_label)
    fig.text(0.01, 0.74, "ExPeCA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.text(0.01, 0.28, "5G-LENA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.suptitle(f"{compare_label} | Series", fontsize=TITLE_FONT_SIZE, y=0.995)
    fig.tight_layout(rect=[0.03, 0, 1, 0.95])
    fig.savefig(output_root / f"{run_label}_series.png", dpi=150)
    plt.close(fig)

    print(f"Wrote comparison plots for {run_label} to {output_root}")

def main():
    parser = argparse.ArgumentParser(
        description="Compare ExPeCA and generated 5G-LENA delay decomposition CSV distributions"
    )
    parser.add_argument(
        "--expeca-dir",
        required=True,
        help="Directory containing ExPeCA run folder(s) or ExPeCA delayDecom*.csv files.",
    )
    parser.add_argument(
        "--lena-csv-dir",
        required=True,
        help="Directory containing generated 5G-LENA delay decomposition CSV file(s).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where comparison plots should be written.",
    )
    args = parser.parse_args()

    expeca_dir = Path(args.expeca_dir).resolve()
    lena_csv_dir = Path(args.lena_csv_dir).resolve()
    plt.rcParams.update({"font.size": FONT_SIZE})
    csv_runs = find_expeca_csv_runs(expeca_dir)
    lena_runs = find_lena_delay_decomposition_csv_runs(lena_csv_dir)
    if not csv_runs:
        print(f"WARN: no ExPeCA CSV runs found under {expeca_dir}")
        return 0
    if not lena_runs:
        print(f"WARN: no 5G-LENA delay decomposition CSVs found under {lena_csv_dir}")
        return 0

    expeca_by_run = index_paths_by_run_number(csv_runs, "ExPeCA CSV")
    lena_by_run = index_paths_by_run_number(lena_runs, "5G-LENA delay decomposition CSV")
    common_runs = sorted(set(expeca_by_run).intersection(lena_by_run))

    missing_expeca = sorted(set(lena_by_run).difference(expeca_by_run))
    missing_lena = sorted(set(expeca_by_run).difference(lena_by_run))
    if missing_expeca:
        print(f"WARN: missing ExPeCA CSV for runs: {missing_expeca}")
    if missing_lena:
        print(f"WARN: missing 5G-LENA delay decomposition CSVs for runs: {missing_lena}")
    if not common_runs:
        print("WARN: no common run numbers found between ExPeCA and 5G-LENA inputs")
        return 0

    output_root = Path(args.output_dir).resolve()
    print(f"Writing comparison plots under: {output_root}")
    for run_no in common_runs:
        if run_no == 13:
            print("WARN: skipping run13")
            continue
        plot_compare_pair(
            run_no,
            expeca_by_run[run_no],
            lena_by_run[run_no],
            output_root,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
