#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from expeca_data_cleaning import clean_expeca_data


QUANTILES = [0.5, 0.8, 0.9, 0.99]
HARQ_RETX_INTERVAL_MS = 7.5
MAX_HARQ_RETRIES = 3
EXPECA_CLEANING_LABELS = (
    ("missing_mac_attempts_rows_dropped", "Rows dropped for missing MAC-attempt count"),
    ("missing_rlc_attempts_rows_dropped", "Rows dropped for missing RLC-attempt count"),
    (
        "mac_attempts_below_rlc_rows_dropped",
        "Rows dropped because MAC attempts were below RLC attempts",
    ),
    ("negative_ran_rows_dropped", "Rows dropped for negative RAN delay"),
    (
        "scheduling_above_queueing_set_to_nan",
        "Scheduling-delay values set to NaN because they exceeded queueing delay",
    ),
    ("negative_Queuing delay_set_to_nan", "Negative queueing-delay values set to NaN"),
    (
        "negative_Transmission delay_set_to_nan",
        "Negative transmission-delay values set to NaN",
    ),
    (
        "negative_Retransmission delay_set_to_nan",
        "Negative retransmission-delay values set to NaN",
    ),
    (
        "negative_segmentation delay_set_to_nan",
        "Negative multi-segment segmentation-delay values set to NaN",
    ),
    (
        "one_segment_segmentation_set_to_zero",
        "One-segment segmentation-delay values set to zero",
    ),
)


def run_sort_key(run: str) -> tuple[str, int]:
    match = re.match(r"([a-z]+)(\d+)", run)
    return (match.group(1), int(match.group(2))) if match else (run, 0)


def find_runs(directory: Path, dataset: str) -> dict[str, Path]:
    runs = {}
    if dataset == "sim":
        pattern = re.compile(r"^([ace]\d+)_5Glena_delay_decomposition$")
    else:
        pattern = re.compile(r"^([ac]\d+)_|^(e[1-7]_1)_")
    for path in sorted(directory.glob("*.csv")):
        match = pattern.match(path.stem)
        if match:
            runs[next(group for group in match.groups() if group)] = path
    return runs


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce")


def split_queueing_by_sr(
    queueing: pd.Series,
    frame_alignment: pd.Series,
    scheduling: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    has_matching_sr = (
        np.isfinite(frame_alignment) & np.isfinite(scheduling)
    )
    return queueing.where(has_matching_sr), queueing.where(~has_matching_sr)


def retry_stratified_tx_metrics(
    tx_retx: pd.Series,
    retry_delay: pd.Series,
) -> list[tuple[str, pd.Series]]:
    retry_count = (retry_delay / HARQ_RETX_INTERVAL_MS).round()
    labels = ["tx delay (no retx)"] + [
        f"tx + {count} retx delay" for count in range(1, MAX_HARQ_RETRIES + 1)
    ]
    return [
        (label, tx_retx.where(retry_count == count))
        for count, label in enumerate(labels)
    ]


def segmentation_metrics(
    delay: pd.Series,
    segment_count: pd.Series,
    counts: list[int],
) -> list[tuple[str, pd.Series]]:
    return [
        (f"segmentation delay ({count} segments)", delay.where(segment_count == count))
        for count in counts
    ]


def load_run(
    path: Path,
    dataset: str,
) -> tuple[pd.DataFrame, int, int, dict[str, int]]:
    frame = pd.read_csv(path)
    original_rows = len(frame)
    cleaning_counts = {}
    if dataset == "expeca":
        frame, cleaning_counts = clean_expeca_data(frame, return_counts=True)
    ran_column = "ran_delay_ms" if dataset == "sim" else "Ran delay"
    ran_delay = numeric(frame, ran_column)
    valid = ran_delay.notna() & np.isfinite(ran_delay) & (ran_delay >= 0)
    dropped_rows = original_rows - int(valid.sum())
    return frame.loc[valid].copy(), original_rows, dropped_rows, cleaning_counts


def sim_metrics(
    frame: pd.DataFrame,
    segment_counts: list[int],
) -> list[tuple[str, pd.Series]]:
    frame_alignment = numeric(frame, "frame_alignment_delay_ms")
    scheduling = numeric(frame, "scheduling_delay_ms")
    sr_queueing, non_sr_queueing = split_queueing_by_sr(
        numeric(frame, "queueing_delay_ms"), frame_alignment, scheduling
    )
    tx_retx = numeric(frame, "tx_retx_delay_ms")
    segmentation = numeric(frame, "segmentation_delay_ms")
    segment_count = numeric(frame, "rlc_segments_per_pkt")
    remaining_columns = [
        ("delay residual", "delay_residual_ms"),
        ("pre_hol_wait_ms", "pre_hol_wait_ms"),
        ("hol_wait_ms", "hol_wait_ms"),
        ("link_delay_ms", "link_delay_ms"),
        ("reordering_delay_ms", "reordering_delay_ms"),
    ]
    return [
        ("ran delay", numeric(frame, "ran_delay_ms")),
        ("frame alignment delay", frame_alignment),
        ("scheduling delay", scheduling),
        ("sr_queuing_delay", sr_queueing),
        ("non_sr_queuing_delay", non_sr_queueing),
        ("tx+retx delay", tx_retx),
        *retry_stratified_tx_metrics(tx_retx, tx_retx),
        ("segmentation delay", segmentation),
        *segmentation_metrics(segmentation, segment_count, segment_counts),
        *[
            (label, numeric(frame, column))
            for label, column in remaining_columns
        ],
    ]


def expeca_metrics(
    frame: pd.DataFrame,
    segment_counts: list[int],
) -> list[tuple[str, pd.Series]]:
    transmission = numeric(frame, "Transmission delay")
    retransmission = numeric(frame, "Retransmission delay")
    tx_retx = transmission + retransmission
    segmentation = numeric(frame, "segmentation delay")
    segment_count = numeric(frame, "No of RLC attempts")
    frame_alignment = numeric(frame, "Frame alignment delay")
    scheduling = numeric(frame, "Scheduling delay")
    sr_queueing, non_sr_queueing = split_queueing_by_sr(
        numeric(frame, "Queuing delay"), frame_alignment, scheduling
    )
    return [
        ("ran delay", numeric(frame, "Ran delay")),
        ("frame alignment delay", frame_alignment),
        ("scheduling delay", scheduling),
        ("sr_queuing_delay", sr_queueing),
        ("non_sr_queuing_delay", non_sr_queueing),
        ("tx+retx delay", tx_retx),
        *retry_stratified_tx_metrics(tx_retx, retransmission),
        ("segmentation delay", segmentation),
        *segmentation_metrics(segmentation, segment_count, segment_counts),
        ("delay residual", numeric(frame, "Delay Difference (E2E - Sum)")),
        ("End to End Delay", numeric(frame, "End to End Delay")),
        ("Sum of Component Delays", numeric(frame, "Sum of Component Delays")),
        (
            "Application-RAN Time Difference",
            numeric(frame, "Application-RAN Time Difference"),
        ),
    ]


def statistics_line(run: str, values: pd.Series) -> str:
    values = values.replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return f"{run:<12}" + "".join(f"{'nan':>22}" for _ in range(6))
    quantiles = values.quantile(QUANTILES).to_numpy(dtype=float)
    numbers = [values.min(), values.max(), *quantiles]
    return f"{run:<12}" + "".join(
        f"{value:>22.6f}" for value in numbers
    )


def write_summary(
    directory: Path,
    dataset: str,
    output_path: Path,
) -> tuple[Path, dict[str, int]]:
    run_paths = find_runs(directory, dataset)
    loaded = {}
    dropped = {}
    original = {}
    cleaning_totals = {}
    cleaning_files = {}
    threshold_counts = {25: {}, 50: {}}
    ran_p99 = {}
    harq_retx_ratios = {}
    harq_retx_counts = {}
    mac_attempt_counts = {}
    harq_retx_packet_counts = {}
    rlc_retx_packet_counts = {}
    four_plus_initial_segment_packet_counts = {}
    median_ul_cqi = {}
    additional_backlog_packet_counts = {}
    ran_column = "ran_delay_ms" if dataset == "sim" else "Ran delay"
    for run in sorted(run_paths, key=run_sort_key):
        frame, original_rows, dropped_rows, cleaning_counts = load_run(
            run_paths[run], dataset
        )
        loaded[run] = frame
        original[run] = original_rows
        dropped[run] = dropped_rows
        ran_delay = numeric(frame, ran_column)
        ran_p99[run] = ran_delay.quantile(0.99)
        for threshold in threshold_counts:
            threshold_counts[threshold][run] = int((ran_delay >= threshold).sum())
        if dataset == "expeca":
            mac_attempts = numeric(frame, "MAC attempts (total)")
            rlc_attempts = numeric(frame, "No of RLC attempts")
            rlc_retransmissions = numeric(frame, "No of RLC retransmissions")
            harq_retx_counts[run] = float((mac_attempts - rlc_attempts).sum())
            mac_attempt_counts[run] = float(mac_attempts.sum())
            harq_retx_packet_counts[run] = int((mac_attempts > rlc_attempts).sum())
            harq_retx_ratios[run] = (
                harq_retx_counts[run] / mac_attempt_counts[run]
                if mac_attempt_counts[run]
                else float("nan")
            )
            rlc_retx_packet_counts[run] = int((rlc_retransmissions > 0).sum())
            four_plus_initial_segment_packet_counts[run] = int(
                ((rlc_attempts - rlc_retransmissions) > 3).sum()
            )
            median_ul_cqi[run] = numeric(frame, "Ul CQI (Avg)").median()
            expected_packet_bytes = numeric(frame, "Packet Length") + 3
            additional_backlog_packet_counts[run] = int(
                (numeric(frame, "RLC queue (UE)") > expected_packet_bytes).sum()
            )
        for name, count in cleaning_counts.items():
            cleaning_totals[name] = cleaning_totals.get(name, 0) + count
            if count:
                cleaning_files.setdefault(name, []).append(run)

    if dataset == "sim":
        title = "BENCHMARKING DELAY DECOMPOSITION SUMMARY"
        formula_text = """
Delay decomposition formulas

ran_delay_ms = queueing_delay_ms + tx_retx_delay_ms + segmentation_delay_ms + reordering_delay_ms

link_delay_ms = tx_retx_delay_ms + segmentation_delay_ms

pre_hol_wait_ms + hol_wait_ms ends at the actual DCI/RLC-dequeue timestamp

For packets with a matched initial SR:
scheduling_delay_ms = pre_hol_wait_ms + hol_wait_ms (subject to timestamp precision)
frame_alignment_delay_ms is contained within scheduling_delay_ms
scheduling_delay_ms is contained within queueing_delay_ms
queueing_delay_ms - scheduling_delay_ms = initial DCI-to-virtual-dequeue delay

The EXPECA-aligned virtual dequeue is one millisecond before first PUSCH, clamped
to the actual DCI/RLC-dequeue time when the DCI-to-PUSCH interval is shorter.

delay_residual_ms = ran_delay_ms - (queueing_delay_ms + tx_retx_delay_ms + segmentation_delay_ms + reordering_delay_ms)
"""
        segment_column = "rlc_segments_per_pkt"
        metric_builder = sim_metrics
    else:
        title = "EXPECA BENCHMARKING DELAY DECOMPOSITION SUMMARY"
        formula_text = ""
        segment_column = "No of RLC attempts"
        metric_builder = expeca_metrics

    segment_counts = sorted(
        {
            int(value)
            for frame in loaded.values()
            for value in numeric(frame, segment_column).dropna().unique()
            if value >= 2 and float(value).is_integer()
        }
    )

    lines = [
        title,
        "=" * len(title),
        "",
        f"Source: {directory.resolve()}",
        f"Runs: {len(loaded)}",
        "Delay unit: milliseconds (ms)",
    ]
    if formula_text:
        lines.extend(formula_text.strip("\n").splitlines())
    if dataset == "expeca":
        lines.extend(["", "Cleaning applied before statistics", "----------------------------------"])
        for key, label in EXPECA_CLEANING_LABELS:
            count = cleaning_totals.get(key, 0)
            lines.append(f"{label}: {count}")
            if count:
                lines.append(f"  Runs: {', '.join(cleaning_files[key])}")
    lines.extend(["", "Invalid-row filtering", "---------------------"])
    lines.append("Rows with non-finite or negative RAN delay are excluded from every statistic.")
    lines.append(
        "SR queuing groups use finite frame-alignment and scheduling delays as the "
        "matching-SR indicator."
    )
    lines.append(
        "Retry-stratified TX groups use 7.5 ms HARQ-cycle bands and include at most "
        "three retransmissions."
    )
    lines.append("Segmentation groups include each observed segment count from two upward.")
    if dataset == "expeca":
        lines.append(
            "HARQ retx / MAC tx is the percentage of MAC transmission attempts that were HARQ retransmissions."
        )
        lines.append(
            "Pkts with HARQ retx and Pkts with RLC retx are percentages of packets with at least one corresponding retransmission."
        )
        lines.append(
            "Additional backlog means RLC queue (UE) exceeded Packet Length + 3 RLC bytes; all other packets are not-observed/unknown."
        )
    lines.append(f"Dropped rows: {sum(dropped.values())}")
    rows_header = (
        "run             rows    dropped   ran>=25ms (%)"
        "   Pkts RAN >50 ms   RAN delay p99"
    )
    if dataset == "expeca":
        rows_header += (
            "   Median UL CQI   Pkts with HARQ retx"
            "   Pkts with RLC retx   initial-segs>3"
            "   Additional backlog   HARQ retx / MAC tx"
        )
    lines.extend(["", "Rows per run", "------------", rows_header])
    for run, frame in loaded.items():
        row = (
            f"{run:<12}{len(frame):>10}{dropped[run]:>11}"
            f"{threshold_counts[25][run] / len(frame):>16.2%}"
            f"{threshold_counts[50][run] / len(frame):>16.2%}"
            f"{ran_p99[run]:>15.2f}"
        )
        if dataset == "expeca":
            row += (
                f"{median_ul_cqi[run]:>16.1f}"
                f"{harq_retx_packet_counts[run] / len(frame):>24.2%}"
                f"{rlc_retx_packet_counts[run] / len(frame):>20.2%}"
                f"{four_plus_initial_segment_packet_counts[run] / len(frame):>17.2%}"
                f"{additional_backlog_packet_counts[run] / len(frame):>33.2%}"
                f"{harq_retx_ratios[run]:>19.2%}"
            )
        lines.append(row)
    total_rows = sum(map(len, loaded.values()))
    total_row = (
        f"{'TOTAL':<12}{total_rows:>10}{sum(dropped.values()):>11}"
        f"{sum(threshold_counts[25].values()) / total_rows:>16.2%}"
        f"{sum(threshold_counts[50].values()) / total_rows:>16.2%}"
        f"{pd.concat([numeric(frame, ran_column) for frame in loaded.values()]).quantile(0.99):>15.2f}"
    )
    if dataset == "expeca":
        total_mac_attempts = sum(mac_attempt_counts.values())
        total_harq_retx_ratio = (
            sum(harq_retx_counts.values()) / total_mac_attempts
            if total_mac_attempts
            else float("nan")
        )
        total_row += (
            f"{pd.concat([numeric(frame, 'Ul CQI (Avg)') for frame in loaded.values()]).median():>16.1f}"
            f"{sum(harq_retx_packet_counts.values()) / total_rows:>24.2%}"
            f"{sum(rlc_retx_packet_counts.values()) / total_rows:>20.2%}"
            f"{sum(four_plus_initial_segment_packet_counts.values()) / total_rows:>17.2%}"
            f"{sum(additional_backlog_packet_counts.values()) / total_rows:>33.2%}"
            f"{total_harq_retx_ratio:>19.2%}"
        )
    lines.append(total_row)

    metric_names = [
        label
        for label, _ in metric_builder(next(iter(loaded.values())), segment_counts)
    ]
    for metric_index, metric_name in enumerate(metric_names):
        lines.extend(
            [
                "",
                metric_name,
                "-" * len(metric_name),
                (
                    "run                             min_ms"
                    "                max_ms             median_ms"
                    "                p80_ms                p90_ms"
                    "                p99_ms"
                ),
            ]
        )
        for run, frame in loaded.items():
            values = metric_builder(frame, segment_counts)[metric_index][1]
            lines.append(statistics_line(run, values))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")
    return output_path, dropped


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize benchmark delay decomposition CSVs.")
    parser.add_argument(
        "--sim-dir",
        type=Path,
        required=True,
        help="Directory containing simulation delay-decomposition CSVs.",
    )
    parser.add_argument(
        "--expeca-dir",
        type=Path,
        required=True,
        help="Directory containing Expeca delay-decomposition CSVs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where both summary text files should be written.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    inputs = [
        (
            "sim",
            args.sim_dir,
            output_dir / "sim_delay_decomposition_summary.txt",
        ),
        (
            "expeca",
            args.expeca_dir,
            output_dir / "expeca_delay_decomposition_summary.txt",
        ),
    ]
    for dataset, directory, output in inputs:
        output_path, dropped = write_summary(
            directory.resolve(),
            dataset,
            output.resolve(),
        )
        print(f"Wrote {output_path}")
        for run, count in dropped.items():
            if count:
                print(f"  {dataset} {run}: dropped {count}")
        print(f"  {dataset} total dropped: {sum(dropped.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
