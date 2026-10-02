#!/usr/bin/env python3
"""Plot simulation delay components across the four benchmarking sweeps."""

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BASE_FONT_SIZE = 17
TICK_FONT_SIZE = 14
LABEL_FONT_SIZE = 18
TITLE_FONT_SIZE = 19
FIGURE_TITLE_FONT_SIZE = 23
LEGEND_FONT_SIZE = 17

plt.rcParams.update(
    {
        "font.size": BASE_FONT_SIZE,
        "axes.titlesize": TITLE_FONT_SIZE,
        "axes.labelsize": LABEL_FONT_SIZE,
        "xtick.labelsize": TICK_FONT_SIZE,
        "ytick.labelsize": TICK_FONT_SIZE,
        "legend.fontsize": LEGEND_FONT_SIZE,
        "figure.titlesize": FIGURE_TITLE_FONT_SIZE,
    }
)

COMPONENTS = [
    ("queueing_delay", "Queuing", "#2878B5", "o"),
    ("tx_retx_delay", "Tx + retransmission", "#E07A2D", "s"),
    ("segmentation_delay", "Segmentation", "#3A923A", "^"),
]
SOURCE_COLUMNS = {
    "ran_delay": "ran_delay_ms",
    "queueing_delay": "queueing_delay_ms",
    "tx_retx_delay": "tx_retx_delay_ms",
    "segmentation_delay": "segmentation_delay_ms",
}
INITIAL_SEGMENTS_SOURCE_COLUMN = "rlc_segments_per_pkt"
INITIAL_SEGMENTS_COLUMN = "initial_segments"
STATISTIC_COLUMNS = [*SOURCE_COLUMNS, INITIAL_SEGMENTS_COLUMN]


@dataclass(frozen=True)
class Sweep:
    runs: tuple[str, ...]
    x_label: str
    title: str
    x_value: Callable[[str], float]
    x_tick_label: Callable[[str], str]


PACKET_BYTES = {
    "a1": 50,
    "a2": 100,
    "a3": 200,
    "a4": 1000,
    "a5": 1200,
    "a6": 1400,
    "a7": 12,
    **{f"z{index}": 1400 * (index + 1) for index in range(1, 8)},
}
INTER_PACKET_MS = {
    "e1": 10,
    "e2": 15,
    "e3": 20,
    "e4": 25,
    "e5": 50,
    "e6": 75,
    "e7": 100,
    "e8": 7,
    "e9": 6,
    "e10": 5,
    "e11": 4,
    "e12": 3,
    "e13": 2,
    "e14": 1,
    "e15": 8,
    "e16": 9,
    "e17": 11,
}
BACKGROUND_LOAD_MBPS = {
    "c1": 2.5,
    "c2": 5,
    "c3": 7.5,
    "c4": 10,
    "c5": 15,
    "c6": 20,
    "c7": 25,
    "c8": 30,
}
BACKGROUND_UES = {
    **{f"x{index}": index + 1 for index in range(1, 10)},
    "x10": 20,
    "x11": 30,
}


def format_number(value: float) -> str:
    return f"{value:g}"


SWEEPS = [
    Sweep(
        runs=tuple(PACKET_BYTES),
        x_label="Packet size / burst payload (bytes)",
        title="Packet/burst sweep: completion delay and unique initial RLC PDUs",
        x_value=lambda run: PACKET_BYTES[run],
        x_tick_label=lambda run: format_number(PACKET_BYTES[run]),
    ),
    Sweep(
        runs=tuple(INTER_PACKET_MS),
        x_label="Inter-packet interval (ms)",
        title="Inter-packet-interval sweep",
        # Match the earlier comparison plot: lower offered load is on the left.
        x_value=lambda run: -INTER_PACKET_MS[run],
        x_tick_label=lambda run: format_number(INTER_PACKET_MS[run]),
    ),
    Sweep(
        runs=tuple(BACKGROUND_LOAD_MBPS),
        x_label="Total background UDP load (Mbps)",
        title="Background-load sweep",
        x_value=lambda run: BACKGROUND_LOAD_MBPS[run],
        x_tick_label=lambda run: format_number(BACKGROUND_LOAD_MBPS[run]),
    ),
    Sweep(
        runs=tuple(BACKGROUND_UES),
        x_label="Number of background UEs",
        title="Background-UE sweep (25 Mbps total)",
        x_value=lambda run: BACKGROUND_UES[run],
        x_tick_label=lambda run: format_number(BACKGROUND_UES[run]),
    ),
]


def run_sort_key(run: str) -> tuple[str, int]:
    match = re.fullmatch(r"([a-z]+)(\d+)", run)
    if match is None:
        return run, 0
    return match.group(1), int(match.group(2))


def find_sim_runs(directory: Path) -> dict[str, Path]:
    runs: dict[str, Path] = {}
    pattern = re.compile(r"^([acexyz]\d+)_5Glena_delay_decomposition$")
    for path in sorted(directory.glob("*.csv")):
        match = pattern.fullmatch(path.stem)
        if match:
            runs[match.group(1)] = path
    return runs


def load_burst_segment_counts(csv_path: Path) -> dict[str, pd.Series]:
    required_columns = {"run", "burst_id", "initial_rlc_segments"}
    frame = pd.read_csv(csv_path)
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"{csv_path} is missing columns: {sorted(missing_columns)}"
        )
    frame["burst_id"] = pd.to_numeric(frame["burst_id"], errors="coerce")
    frame["initial_rlc_segments"] = pd.to_numeric(
        frame["initial_rlc_segments"], errors="coerce"
    )
    frame = frame.dropna(subset=["run", "burst_id", "initial_rlc_segments"])
    frame["burst_id"] = frame["burst_id"].astype(int)
    if frame.duplicated(["run", "burst_id"]).any():
        raise ValueError(f"{csv_path} contains duplicate run/burst_id rows")
    if frame["initial_rlc_segments"].le(0).any():
        raise ValueError(f"{csv_path} contains non-positive segment counts")
    return {
        run: group.set_index("burst_id")["initial_rlc_segments"].sort_index()
        for run, group in frame.groupby("run")
    }


def load_component_frame(
    csv_path: Path,
    run: str,
    burst_segment_counts: pd.Series | None = None,
) -> pd.DataFrame:
    requested_columns = [
        *SOURCE_COLUMNS.values(),
        INITIAL_SEGMENTS_SOURCE_COLUMN,
        "pkt_id",
    ]
    frame = pd.read_csv(csv_path, usecols=requested_columns)
    frame["pkt_id"] = pd.to_numeric(frame["pkt_id"], errors="coerce")
    frame = frame.loc[frame["pkt_id"].gt(0) & frame["pkt_id"].ne(1)].copy()
    frame.rename(
        columns={
            **{source: target for target, source in SOURCE_COLUMNS.items()},
            INITIAL_SEGMENTS_SOURCE_COLUMN: INITIAL_SEGMENTS_COLUMN,
        },
        inplace=True,
    )
    metric_columns = STATISTIC_COLUMNS
    frame[metric_columns] = frame[metric_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.loc[frame["ran_delay"] >= 0].dropna(
        subset=["pkt_id", *metric_columns]
    )

    if not run.startswith("z"):
        return frame[metric_columns]

    burst_size = int(run[1:]) + 1
    frame["burst_id"] = (frame["pkt_id"].astype(int) - 1) // burst_size
    frame = frame.loc[frame["burst_id"] > 0]
    packets_per_burst = frame.groupby("burst_id")["pkt_id"].nunique()
    complete_burst_ids = packets_per_burst[packets_per_burst.eq(burst_size)].index
    complete = frame.loc[frame["burst_id"].isin(complete_burst_ids)]
    completion_indices = complete.groupby("burst_id")["ran_delay"].idxmax()
    completion_packets = complete.loc[
        completion_indices, ["burst_id", *SOURCE_COLUMNS]
    ].set_index("burst_id")
    if burst_segment_counts is None:
        raise ValueError(f"{run} has no burst-level initial-segment data")
    missing_bursts = completion_packets.index.difference(burst_segment_counts.index)
    if not missing_bursts.empty:
        raise ValueError(
            f"{run} is missing initial-segment counts for "
            f"{len(missing_bursts)} completed bursts"
        )
    completion_packets[INITIAL_SEGMENTS_COLUMN] = burst_segment_counts.reindex(
        completion_packets.index
    )
    completion_percent = 100.0 * len(complete_burst_ids) / len(packets_per_burst)
    print(
        f"Grouped {run}: {len(complete_burst_ids):,} completed bursts of "
        f"{len(packets_per_burst):,} observed ({completion_percent:.1f}%); "
        "using the last-delivered packet for delay and unique burst-level "
        "initial segments"
    )
    return completion_packets


def component_statistics(
    frame: pd.DataFrame,
    quantile: float | None = None,
) -> dict[str, float]:
    statistics = frame.mean() if quantile is None else frame.quantile(quantile)
    return {column: float(statistics[column]) for column in STATISTIC_COLUMNS}


def load_run_frames(
    sim_runs: dict[str, Path],
    burst_segments: dict[str, pd.Series],
) -> dict[str, pd.DataFrame]:
    required_runs = {run for sweep in SWEEPS for run in sweep.runs}
    missing_runs = sorted(required_runs.difference(sim_runs), key=run_sort_key)
    if missing_runs:
        raise ValueError(
            "missing simulation delay-decomposition CSVs for: "
            + ", ".join(missing_runs)
        )

    run_frames = {}
    for run in sorted(required_runs, key=run_sort_key):
        frame = load_component_frame(
            sim_runs[run], run, burst_segments.get(run)
        )
        if frame.empty:
            raise ValueError(f"{run} has no usable packets after filtering")
        run_frames[run] = frame
        observation_label = "completed bursts" if run.startswith("z") else "packets"
        print(f"Loaded {run}: {len(frame):,} {observation_label}")
    return run_frames

def plot_sweeps(
    run_frames: dict[str, pd.DataFrame],
    output_path: Path,
    percentile_range: bool = False,
) -> None:
    if percentile_range:
        run_statistics = {
            run: {
                quantile: component_statistics(frame, quantile)
                for quantile in (0.5, 0.95)
            }
            for run, frame in run_frames.items()
        }
        statistic_label = "Median"
    else:
        run_statistics = {
            run: {None: component_statistics(frame)}
            for run, frame in run_frames.items()
        }
        statistic_label = "Mean"

    fig, axes = plt.subplots(2, 2, figsize=(20, 12))
    segment_axis = None
    for axis, sweep in zip(axes.flat, SWEEPS):
        runs = sorted(sweep.runs, key=sweep.x_value)
        x = np.arange(len(runs))
        is_packet_sweep = sweep is SWEEPS[0]
        plot_specs = (
            [("ran_delay", "RAN delay", "#222222", "D")]
            if is_packet_sweep
            else [
                *COMPONENTS,
                ("ran_delay", "RAN delay", "#222222", "D"),
            ]
        )

        def draw_series(
            target_axis,
            component: str,
            label: str,
            color: str,
            marker: str,
            linewidth: float,
            linestyle: str = "-",
        ) -> None:
            center_quantile = 0.5 if percentile_range else None
            values = np.array(
                [run_statistics[run][center_quantile][component] for run in runs]
            )
            plot_kwargs = {
                "color": color,
                "marker": marker,
                "linewidth": linewidth,
                "linestyle": linestyle,
                "markersize": 7,
                "label": label,
            }
            if percentile_range:
                p95 = np.array(
                    [run_statistics[run][0.95][component] for run in runs]
                )
                target_axis.errorbar(
                    x,
                    values,
                    yerr=np.vstack((np.zeros_like(values), p95 - values)),
                    capsize=3,
                    elinewidth=1.2,
                    **plot_kwargs,
                )
            else:
                target_axis.plot(x, values, **plot_kwargs)

        for component, label, color, marker in plot_specs:
            draw_series(
                axis,
                component,
                label,
                color,
                marker,
                3 if component == "ran_delay" else 2,
            )

        if is_packet_sweep:
            segment_axis = axis.twinx()
            segment_color = "#7A3E9D"
            draw_series(
                segment_axis,
                INITIAL_SEGMENTS_COLUMN,
                "Unique initial RLC PDUs",
                segment_color,
                "P",
                2,
                "--",
            )
            segment_axis.set_ylabel(
                f"{statistic_label} unique initial RLC PDUs per packet/burst",
                color=segment_color,
            )
            segment_axis.tick_params(axis="y", colors=segment_color)
            segment_axis.margins(y=0.08)

        axis.set_xticks(x, [sweep.x_tick_label(run) for run in runs])
        axis.set_xlabel(sweep.x_label, labelpad=8)
        if is_packet_sweep:
            axis.set_ylabel(f"{statistic_label} event-completion delay (ms)")
        else:
            axis.set_ylabel(f"{statistic_label} delay (ms)")
        axis.set_title(sweep.title, pad=11)
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
        axis.set_axisbelow(True)
        axis.margins(y=0.08)
        axis.set_ylim(bottom=0)

        if is_packet_sweep:
            first_burst = runs.index("z1")
            axis.axvline(
                first_burst - 0.5,
                color="#888888",
                linestyle="--",
                linewidth=1,
            )
            axis.text(
                first_burst - 0.65,
                0.97,
                "single-packet events  |  completed bursts",
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=12,
                color="#555555",
            )

    legend_handles = []
    legend_labels = []
    legend_axes = [*axes.flat]
    if segment_axis is not None:
        legend_axes.append(segment_axis)
    for legend_axis in legend_axes:
        handles, labels = legend_axis.get_legend_handles_labels()
        for handle, label in zip(handles, labels):
            if label not in legend_labels:
                legend_handles.append(handle)
                legend_labels.append(label)
    fig.legend(
        legend_handles,
        legend_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.96),
        ncol=len(legend_handles),
        frameon=False,
    )
    title_suffix = " with P95 upper error bars" if percentile_range else ""
    figure_title = fig.suptitle(
        f"{statistic_label} simulation sweep metrics{title_suffix}",
        y=0.995,
    )
    figure_title.set_in_layout(False)
    fig.tight_layout(rect=(0, 0, 1, 0.9), h_pad=3.0, w_pad=3.0)
    figure_title.set_in_layout(True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot one simulation-only figure containing packet/burst-size, "
            "inter-packet-interval, background-load, and background-UE sweeps."
        )
    )
    parser.add_argument(
        "--sim-dir",
        required=True,
        type=Path,
        help="Directory containing simulation delay-decomposition CSVs.",
    )
    parser.add_argument(
        "--burst-segments-csv",
        type=Path,
        help=(
            "Burst-level unique initial RLC-segment CSV. Defaults to "
            "burst_initial_rlc_segments.csv inside --sim-dir."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help=(
            "Base output figure path. The script adds _mean and "
            "_median_p95 before the extension."
        ),
    )
    return parser.parse_args()


def statistic_output_path(base_path: Path, statistic: str) -> Path:
    return base_path.with_name(f"{base_path.stem}_{statistic}{base_path.suffix}")


def main() -> int:
    args = parse_args()
    sim_dir = args.sim_dir.resolve()
    if not sim_dir.is_dir():
        raise ValueError(f"simulation directory does not exist: {sim_dir}")
    burst_segments_path = (
        args.burst_segments_csv.resolve()
        if args.burst_segments_csv is not None
        else sim_dir / "burst_initial_rlc_segments.csv"
    )
    if not burst_segments_path.is_file():
        raise ValueError(
            f"burst-level segment CSV does not exist: {burst_segments_path}"
        )
    burst_segments = load_burst_segment_counts(burst_segments_path)
    run_frames = load_run_frames(find_sim_runs(sim_dir), burst_segments)
    base_output_path = args.output.resolve()
    for statistic, percentile_range in (
        ("mean", False),
        ("median_p95", True),
    ):
        output_path = statistic_output_path(base_output_path, statistic)
        plot_sweeps(run_frames, output_path, percentile_range)
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
