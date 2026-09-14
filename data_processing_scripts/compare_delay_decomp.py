#!/usr/bin/env python3
import argparse
import ast
import json
import os
import re
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from expeca_data_cleaning import clean_expeca_data
from create_delay_decomposition_data import (
    PACKET_KEYS,
    build_pdcp_packet_table,
    filter_data_only,
    match_delay_probe_packet_keys,
)


BASE_FONT_SIZE = 17
TICK_FONT_SIZE = 16
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

REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_SCRIPT = (
    REPO_ROOT
    / "ns3-code/contrib/nr/examples/5G-LENA-digital-twin-script/"
    "run-parallel-benchmarking-sims.py"
)
QUANTILES = [0.5, 0.8, 0.9, 0.99]
QUANTILE_LABELS = ["Median", "P80", "P90", "P99"]
LARGE_CSV_BYTES = 256 * 1024 * 1024
CSV_CHUNK_ROWS = 500_000
RAN_TAIL_THRESHOLD_MS = 25.0
RAN_EXTREME_THRESHOLD_MS = 50.0
TB_GRANT_MATCH_TOLERANCE_US = 1_000

METRICS = [
    ("ran_delay", "RAN delay"),
    ("frame_alignment_delay", "Frame alignment delay"),
    ("scheduling_delay", "Scheduling delay"),
    ("queueing_delay", "Queuing delay"),
    ("tx_retx_delay", "Tx + retransmission delay"),
    ("segmentation_delay", "Segmentation delay"),
]

SIM_COLUMNS = {
    "ran_delay": "ran_delay_ms",
    "frame_alignment_delay": "frame_alignment_delay_ms",
    "scheduling_delay": "scheduling_delay_ms",
    "queueing_delay": "queueing_delay_ms",
    "tx_retx_delay": "tx_retx_delay_ms",
    "segmentation_delay": "segmentation_delay_ms",
}

EXPECA_COLUMNS = {
    "ran_delay": "Ran delay",
    "frame_alignment_delay": "Frame alignment delay",
    "scheduling_delay": "Scheduling delay",
    "queueing_delay": "Queuing delay",
    "segmentation_delay": "segmentation delay",
}
EXPECA_TX_COLUMN = "Transmission delay"
EXPECA_RETX_COLUMN = "Retransmission delay"
SIM_PACKET_SIZE_COLUMN = "pkt_size_bytes"
EXPECA_PACKET_SIZE_COLUMN = "Packet Length"
SIM_SEGMENTS_COLUMN = "rlc_segments_per_pkt"
EXPECA_SEGMENTS_COLUMN = "No of RLC attempts"
EXPECA_RLC_RETRANSMISSIONS_COLUMN = "No of RLC retransmissions"
EXPECA_MAC_ATTEMPTS_COLUMN = "MAC attempts (total)"
EXPECA_UL_CQI_COLUMN = "Ul CQI (Avg)"
TAIL_COMPONENTS = [
    ("queueing_delay", "Queuing", "#2878B5"),
    ("tx_retx_delay", "Tx + retransmission", "#E07A2D"),
    ("segmentation_delay", "Segmentation", "#3A923A"),
]
COUNT_DELAY_METRICS = [
    ("ran_delay", "RAN delay", "#222222"),
    *TAIL_COMPONENTS,
]
TB_METRICS = [
    ("sinr", "UL SINR", "SINR (dB)", False),
    ("cqi", "UL CQI", "UL CQI", True),
    ("mcs", "UL MCS", "MCS", True),
    ("prbs", "Allocated PRBs", "PRBs", False),
    ("symbols", "Allocated symbols", "Symbols", True),
    ("tbs", "Transport block size", "TBS (bytes)", False),
]


def run_sort_key(run: str) -> tuple[str, int]:
    match = re.fullmatch(r"([a-z]+)(\d+)", run)
    if match is None:
        return run, 0
    return match.group(1), int(match.group(2))


def load_run_configurations() -> dict[str, dict[str, object]]:
    tree = ast.parse(CAMPAIGN_SCRIPT.read_text(), filename=str(CAMPAIGN_SCRIPT))
    assignments = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in {"COMMON_ARGS", "RUNS"}:
            assignments[target.id] = ast.literal_eval(node.value)

    if not {"COMMON_ARGS", "RUNS"}.issubset(assignments):
        raise ValueError(f"Could not read COMMON_ARGS and RUNS from {CAMPAIGN_SCRIPT}")

    configurations = {}
    for run in assignments["RUNS"]:
        configuration = dict(assignments["COMMON_ARGS"])
        configuration.update(run["args"])
        configurations[run["name"]] = configuration
    return configurations


def format_interval(value: object) -> str:
    return re.sub(r"(?<=\d)(ms|s)$", r" \1", str(value))


def format_background_load(configuration: dict[str, object]) -> str:
    load_type = str(configuration.get("loadType", "none")).lower()
    if load_type == "none":
        return "none"
    load_mbps = float(configuration["cbrLoad"])
    return f"{load_type.upper()} {load_mbps:g} Mbps"


def find_sim_runs(directory: Path) -> dict[str, Path]:
    runs = {}
    pattern = re.compile(r"^([ace]\d+)_5Glena_delay_decomposition$")
    for path in sorted(directory.glob("*.csv")):
        match = pattern.fullmatch(path.stem)
        if match:
            runs[match.group(1)] = path
    return runs


def find_expeca_runs(directory: Path) -> dict[str, Path]:
    runs = {}
    direct_pattern = re.compile(r"^([ac]\d+)_")
    e_pattern = re.compile(r"^(e[1-7])_1_")
    for path in sorted(directory.glob("*.csv")):
        match = direct_pattern.match(path.name) or e_pattern.match(path.name)
        if match:
            runs[match.group(1)] = path
    return runs


def find_sim_raw_runs(directory: Path) -> dict[str, Path]:
    return {
        path.name: path
        for path in directory.iterdir()
        if path.is_dir() and re.fullmatch(r"[ace]\d+", path.name)
    }


def find_expeca_json_runs(directory: Path) -> dict[str, Path]:
    runs = {}
    direct_pattern = re.compile(r"^([ac]\d+)_")
    e_pattern = re.compile(r"^(e[1-7])_1_")
    for path in sorted(directory.glob("*.json")):
        match = direct_pattern.match(path.name) or e_pattern.match(path.name)
        if match:
            runs[match.group(1)] = path
    return runs


def numeric_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(frame[column], errors="coerce").dropna().to_numpy()


def load_sim_delay_probe_tb_metrics(run_dir: Path) -> dict[str, np.ndarray]:
    pdcp = pd.read_csv(
        run_dir / "NrUlPdcpRxStats.txt",
        sep="\t",
        usecols=["time_us", "rnti", "lcid", "pkt_id", "packet_size", "delay_us"],
    )
    delay_trace = pd.read_csv(run_dir / "delay_trace.txt", sep="\t")
    packet_keys, _ = match_delay_probe_packet_keys(
        build_pdcp_packet_table(pdcp), delay_trace
    )

    columns = [
        "time_us", "frame", "subframe", "slot", "sym_start", "num_symbols",
        "cell_id", "bwp_id", "rnti", "lcid", "pkt_id", "tb_size", "mcs",
        "rv", "sinr_db",
    ]
    attempts = pd.read_csv(
        run_dir / "UlRxTbComponentTrace.txt", sep="\t", usecols=columns
    ).merge(packet_keys, on=["rnti", "lcid", "pkt_id"], how="inner")
    tb_key = [
        "time_us", "frame", "subframe", "slot", "sym_start", "num_symbols",
        "cell_id", "bwp_id", "rnti", "tb_size", "mcs", "rv",
    ]
    attempts = attempts.drop_duplicates(tb_key)
    attempts["time_us"] = pd.to_numeric(
        attempts["time_us"], errors="coerce"
    ).astype(float)

    grants = pd.read_csv(
        run_dir / "NrUlMacStats.txt",
        sep="\t",
        usecols=[
            "time_us", "rnti", "send_start_time_delta_us", "num_prbs", "msg_type"
        ],
    )
    grants = grants[grants["msg_type"].astype(str).str.upper() == "DATA"].copy()
    for column in ["time_us", "rnti", "send_start_time_delta_us", "num_prbs"]:
        grants[column] = pd.to_numeric(grants[column], errors="coerce")
    grants = grants.dropna()
    grants["pusch_tx_time_us"] = grants["time_us"] + grants["send_start_time_delta_us"]
    matched = pd.merge_asof(
        attempts.sort_values("time_us"),
        grants[["rnti", "pusch_tx_time_us", "num_prbs"]].sort_values(
            "pusch_tx_time_us"
        ),
        left_on="time_us",
        right_on="pusch_tx_time_us",
        by="rnti",
        direction="backward",
        tolerance=TB_GRANT_MATCH_TOLERANCE_US,
    )
    return {
        "sinr": numeric_values(attempts, "sinr_db"),
        "cqi": np.array([]),
        "mcs": numeric_values(attempts, "mcs"),
        "prbs": numeric_values(matched, "num_prbs"),
        "symbols": numeric_values(attempts, "num_symbols"),
        "tbs": numeric_values(attempts, "tb_size"),
    }


def load_expeca_delay_probe_tb_metrics(json_path: Path) -> dict[str, np.ndarray]:
    attempts = {}
    with json_path.open() as source:
        packets = json.load(source)
    for packet in packets:
        if packet.get("app.sn") is None:
            continue
        for rlc_attempt in packet.get("rlc.attempts", []):
            for attempt in rlc_attempt.get("mac.attempts", []):
                key = (
                    attempt.get("rnti"), attempt.get("frame"), attempt.get("slot"),
                    attempt.get("id"), attempt.get("hqpid"), attempt.get("hqround"),
                    attempt.get("phy.in_t"),
                )
                attempts[key] = attempt

    frame = pd.DataFrame(attempts.values())
    if frame.empty:
        return {metric: np.array([]) for metric, *_ in TB_METRICS}
    ul_cqi = pd.to_numeric(frame["ul_cqi"], errors="coerce").where(
        pd.to_numeric(frame["ul_cqi"], errors="coerce") != 255
    )
    return {
        "sinr": (ul_cqi * 0.5 - 64.0).dropna().to_numpy(),
        "cqi": ul_cqi.dropna().to_numpy(),
        "mcs": numeric_values(frame, "mcs"),
        "prbs": numeric_values(frame, "rbs"),
        "symbols": numeric_values(frame, "symbols"),
        "tbs": numeric_values(frame, "len"),
    }


def required_columns(dataset: str) -> list[str]:
    if dataset == "sim":
        return [
            *SIM_COLUMNS.values(),
            SIM_PACKET_SIZE_COLUMN,
            SIM_SEGMENTS_COLUMN,
        ]
    return [
        *EXPECA_COLUMNS.values(),
        EXPECA_TX_COLUMN,
        EXPECA_RETX_COLUMN,
        EXPECA_PACKET_SIZE_COLUMN,
        EXPECA_SEGMENTS_COLUMN,
        EXPECA_MAC_ATTEMPTS_COLUMN,
    ]


def metric_series(frame: pd.DataFrame, dataset: str) -> dict[str, pd.Series]:
    if dataset == "sim":
        return {
            metric: pd.to_numeric(frame[column], errors="coerce")
            for metric, column in SIM_COLUMNS.items()
        }

    values = {
        metric: pd.to_numeric(frame[column], errors="coerce")
        for metric, column in EXPECA_COLUMNS.items()
    }
    values["tx_retx_delay"] = (
        pd.to_numeric(frame[EXPECA_TX_COLUMN], errors="coerce")
        + pd.to_numeric(frame[EXPECA_RETX_COLUMN], errors="coerce")
    )
    return values


def valid_delay_mask(frame: pd.DataFrame, dataset: str) -> pd.Series:
    column = SIM_COLUMNS["ran_delay"] if dataset == "sim" else EXPECA_COLUMNS["ran_delay"]
    ran_delay = pd.to_numeric(frame[column], errors="coerce")
    return ran_delay.notna() & np.isfinite(ran_delay) & (ran_delay >= 0)


def filter_valid_delay_rows(frame: pd.DataFrame, dataset: str) -> pd.DataFrame:
    return frame.loc[valid_delay_mask(frame, dataset)].copy()


def count_invalid_delay_rows(csv_path: Path, dataset: str) -> tuple[int, int]:
    column = SIM_COLUMNS["ran_delay"] if dataset == "sim" else EXPECA_COLUMNS["ran_delay"]
    values = pd.read_csv(csv_path, usecols=[column])
    valid = valid_delay_mask(values, dataset)
    return len(values), int((~valid).sum())


def validate_columns(csv_path: Path, dataset: str) -> None:
    columns = set(pd.read_csv(csv_path, nrows=0).columns)
    missing = sorted(set(required_columns(dataset)).difference(columns))
    if missing:
        raise ValueError(f"{csv_path} is missing required columns: {missing}")


def balance_run_samples(
    run: str,
    sim_csv: Path,
    expeca_csv: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    sim = filter_valid_delay_rows(pd.read_csv(sim_csv), "sim")
    expeca = filter_valid_delay_rows(
        clean_expeca_data(pd.read_csv(expeca_csv)), "expeca"
    )
    sample_count = min(len(sim), len(expeca))
    if sample_count == 0:
        raise ValueError(f"{run} has no usable samples in one or both datasets")

    sim_output = output_dir / f"{run}_sim.csv"
    expeca_output = output_dir / f"{run}_expeca.csv"
    sim.iloc[:sample_count].to_csv(sim_output, index=False)
    expeca.iloc[:sample_count].to_csv(expeca_output, index=False)
    print(
        f"Balanced {run}: sim={len(sim):,}, ExPeCA={len(expeca):,}, "
        f"using first {sample_count:,} samples"
    )
    return sim_output, expeca_output


def packet_size_values(frame: pd.DataFrame, dataset: str) -> pd.Series:
    column = (
        SIM_PACKET_SIZE_COLUMN
        if dataset == "sim"
        else EXPECA_PACKET_SIZE_COLUMN
    )
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def dominant_packet_size(values: pd.Series) -> float:
    if values.empty:
        return float("nan")
    return float(values.mode().iloc[0])


def segment_values(frame: pd.DataFrame, dataset: str) -> pd.Series:
    column = SIM_SEGMENTS_COLUMN if dataset == "sim" else EXPECA_SEGMENTS_COLUMN
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def calculate_in_memory(
    csv_path: Path,
    dataset: str,
) -> tuple[dict[str, np.ndarray], dict[str, tuple[float, float]], float, float]:
    frame = pd.read_csv(csv_path, usecols=required_columns(dataset))
    if dataset == "expeca":
        frame = clean_expeca_data(frame)
    frame = filter_valid_delay_rows(frame, dataset)
    values_by_metric = {
        metric: series.dropna()
        for metric, series in metric_series(frame, dataset).items()
    }
    statistics = {
        metric: values.quantile(QUANTILES).to_numpy(dtype=float)
        for metric, values in values_by_metric.items()
    }
    extrema = {
        metric: (float(values.min()), float(values.max()))
        if not values.empty
        else (float("nan"), float("nan"))
        for metric, values in values_by_metric.items()
    }
    segments = segment_values(frame, dataset)
    median_segments = float(segments.median()) if not segments.empty else float("nan")
    return (
        statistics,
        extrema,
        dominant_packet_size(packet_size_values(frame, dataset)),
        median_segments,
    )


def calculate_chunked(
    csv_path: Path,
    dataset: str,
) -> tuple[dict[str, np.ndarray], dict[str, tuple[float, float]], float, float]:
    metric_names = [metric for metric, _ in METRICS]
    counts = {metric: 0 for metric in metric_names}
    packet_size_counts = Counter()

    with TemporaryDirectory(prefix="delay-decomp-quantiles-") as temp_dir:
        temp_paths = {
            metric: Path(temp_dir) / f"{metric}.bin" for metric in metric_names
        }
        handles = {
            metric: path.open("wb") for metric, path in temp_paths.items()
        }
        segments_path = Path(temp_dir) / "segments.bin"
        segments_handle = segments_path.open("wb")
        segments_count = 0
        try:
            for frame in pd.read_csv(
                csv_path,
                usecols=required_columns(dataset),
                chunksize=CSV_CHUNK_ROWS,
            ):
                if dataset == "expeca":
                    frame = clean_expeca_data(frame)
                frame = filter_valid_delay_rows(frame, dataset)
                for metric, series in metric_series(frame, dataset).items():
                    values = series.dropna().to_numpy(dtype=np.float64)
                    values.tofile(handles[metric])
                    counts[metric] += values.size
                packet_size_counts.update(packet_size_values(frame, dataset))
                segments = segment_values(frame, dataset).to_numpy(dtype=np.float64)
                segments.tofile(segments_handle)
                segments_count += segments.size
        finally:
            for handle in handles.values():
                handle.close()
            segments_handle.close()

        statistics = {}
        extrema = {}
        for metric in metric_names:
            if counts[metric] == 0:
                statistics[metric] = np.full(len(QUANTILES), np.nan)
                extrema[metric] = (float("nan"), float("nan"))
                continue
            values = np.memmap(
                temp_paths[metric],
                dtype=np.float64,
                mode="r+",
                shape=(counts[metric],),
            )
            extrema[metric] = (float(values.min()), float(values.max()))
            statistics[metric] = np.quantile(
                values,
                QUANTILES,
                overwrite_input=True,
            )
            del values
        packet_size = (
            float(packet_size_counts.most_common(1)[0][0])
            if packet_size_counts
            else float("nan")
        )
        if segments_count:
            segments = np.memmap(
                segments_path,
                dtype=np.float64,
                mode="r+",
                shape=(segments_count,),
            )
            median_segments = float(
                np.quantile(segments, 0.5, overwrite_input=True)
            )
            del segments
        else:
            median_segments = float("nan")
        return statistics, extrema, packet_size, median_segments


def calculate_statistics(
    csv_path: Path,
    dataset: str,
) -> tuple[dict[str, np.ndarray], dict[str, tuple[float, float]], float, float]:
    validate_columns(csv_path, dataset)
    if csv_path.stat().st_size >= LARGE_CSV_BYTES:
        print(f"INFO: processing large CSV in chunks: {csv_path}")
        return calculate_chunked(csv_path, dataset)
    return calculate_in_memory(csv_path, dataset)


def load_expeca_histogram_values(csv_path: Path) -> dict[str, np.ndarray]:
    columns = list(
        dict.fromkeys(
            required_columns("expeca")
            + [EXPECA_MAC_ATTEMPTS_COLUMN, EXPECA_RLC_RETRANSMISSIONS_COLUMN]
        )
    )
    frame = pd.read_csv(csv_path, usecols=columns)
    frame = filter_valid_delay_rows(clean_expeca_data(frame), "expeca")
    rlc_attempts = pd.to_numeric(frame[EXPECA_SEGMENTS_COLUMN], errors="coerce")
    rlc_retransmissions = pd.to_numeric(
        frame[EXPECA_RLC_RETRANSMISSIONS_COLUMN], errors="coerce"
    )
    mac_attempts = pd.to_numeric(frame[EXPECA_MAC_ATTEMPTS_COLUMN], errors="coerce")
    return {
        "initial_segments": (rlc_attempts - rlc_retransmissions).dropna().to_numpy(),
        "mac_retransmissions": (mac_attempts - rlc_attempts).dropna().to_numpy(),
        "rlc_retransmissions": rlc_retransmissions.dropna().to_numpy(),
    }


def load_sim_segment_histogram_values(csv_path: Path) -> np.ndarray:
    frame = pd.read_csv(
        csv_path,
        usecols=[SIM_COLUMNS["ran_delay"], SIM_SEGMENTS_COLUMN],
    )
    frame = filter_valid_delay_rows(frame, "sim")
    return numeric_values(frame, SIM_SEGMENTS_COLUMN)


def plot_histogram(
    axis,
    values: np.ndarray,
    title: str,
    xlabel: str,
    discrete: bool,
    simulation_values: np.ndarray | None = None,
) -> None:
    available = [values]
    if simulation_values is not None and simulation_values.size:
        available.insert(0, simulation_values)
    combined = np.concatenate(available) if available else np.array([])
    if combined.size == 0:
        axis.set_visible(False)
        return
    bins = (
        np.arange(np.floor(combined.min()) - 0.5, np.ceil(combined.max()) + 1.5)
        if discrete
        else 20
    )
    if simulation_values is not None and simulation_values.size:
        axis.hist(
            [simulation_values, values],
            bins=bins,
            color=["#2878B5", "#E07A2D"],
            label=["Simulation", "ExPeCA"],
            edgecolor="white",
            linewidth=0.6,
        )
        axis.legend()
        range_text = (
            f"Sim min/max: {format_range((float(simulation_values.min()), float(simulation_values.max())))}\n"
            f"ExPeCA min/max: {format_range((float(values.min()), float(values.max())))}"
        )
    else:
        axis.hist(values, bins=bins, color="#E07A2D", edgecolor="white", linewidth=0.6)
        range_text = f"min/max: {format_range((float(values.min()), float(values.max())))}"
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel("Packets")
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.text(
        0.98,
        0.03,
        range_text,
        ha="right",
        va="bottom",
        transform=axis.transAxes,
        fontsize=12,
        bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=2),
    )


def plot_delay_probe_tb_histograms(
    run: str,
    sim_values: dict[str, np.ndarray],
    expeca_values: dict[str, np.ndarray],
    output_dir: Path,
) -> Path:
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    for axis, (metric, title, xlabel, discrete) in zip(axes.flat, TB_METRICS):
        available = [
            (label, values, color)
            for label, values, color in (
                ("Simulation", sim_values[metric], "#2878B5"),
                ("ExPeCA", expeca_values[metric], "#E07A2D"),
            )
            if values.size
        ]
        combined = np.concatenate([values for _, values, _ in available])
        if not combined.size:
            axis.set_visible(False)
            continue
        minimum, maximum = float(combined.min()), float(combined.max())
        if discrete and maximum - minimum <= 40:
            bins = np.arange(np.floor(minimum) - 0.5, np.ceil(maximum) + 1.5)
        elif minimum == maximum:
            bins = np.array([minimum - 0.5, maximum + 0.5])
        else:
            bins = np.linspace(minimum, maximum, 31)
        axis.hist(
            [values for _, values, _ in available],
            bins=bins,
            weights=[np.full(values.size, 100.0 / values.size) for _, values, _ in available],
            label=[label for label, _, _ in available],
            color=[color for _, _, color in available],
            edgecolor="white",
            linewidth=0.5,
        )
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.tick_params(axis="y", left=False, labelleft=False)
        axis.spines["left"].set_visible(False)
        if metric == "cqi":
            axis.text(
                0.98, 0.96, "Simulation: unavailable",
                ha="right", va="top", transform=axis.transAxes, fontsize=12,
            )

    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.93),
               ncol=2, frameon=False)
    fig.suptitle(f"MAC level metrics: {run}", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run}_delay_probe_tb_metric_histograms.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def format_packet_size(value: float) -> str:
    if np.isnan(value):
        return "N/A"
    if value.is_integer():
        return f"{int(value)} B"
    return f"{value:g} B"


def format_count(value: float) -> str:
    if np.isnan(value):
        return "N/A"
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def format_range(extrema: tuple[float, float]) -> str:
    minimum, maximum = extrema
    if not np.isfinite(minimum) or not np.isfinite(maximum):
        return "N/A"
    return f"{minimum:.2f}/{maximum:.2f}"


def format_percentage(count: int, total: int) -> str:
    percentage = 100.0 * count / total
    return "<0.01%" if count and percentage < 0.01 else f"{percentage:.2f}%"


def plot_run(
    run: str,
    sim_statistics: dict[str, np.ndarray],
    expeca_statistics: dict[str, np.ndarray],
    sim_extrema: dict[str, tuple[float, float]],
    expeca_extrema: dict[str, tuple[float, float]],
    sim_packet_size: float,
    expeca_packet_size: float,
    sim_median_segments: float,
    expeca_median_segments: float,
    sim_segment_histogram: np.ndarray,
    expeca_histograms: dict[str, np.ndarray],
    run_configuration: dict[str, object],
    output_dir: Path,
) -> Path:
    fig, axes = plt.subplots(3, 3, figsize=(15, 12.4))
    x = np.arange(len(QUANTILE_LABELS))
    width = 0.36

    for axis, (metric, title) in zip(axes.flat[:6], METRICS):
        axis.bar(
            x - width / 2,
            sim_statistics[metric],
            width,
            label="Simulation",
            color="#2878B5",
        )
        axis.bar(
            x + width / 2,
            expeca_statistics[metric],
            width,
            label="ExPeCA",
            color="#E07A2D",
        )
        axis.set_title(title)
        axis.set_xticks(x, QUANTILE_LABELS)
        axis.set_ylabel("Delay (ms)")
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
        axis.set_axisbelow(True)
        axis.text(
            0.98,
            0.03,
            f"Sim min/max: {format_range(sim_extrema[metric])}\n"
            f"ExPeCA min/max: {format_range(expeca_extrema[metric])}",
            ha="right",
            va="bottom",
            transform=axis.transAxes,
            fontsize=12,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=2),
        )

    plot_histogram(
        axes[2, 0],
        expeca_histograms["initial_segments"],
        "Initial RLC segments",
        "Segments per packet",
        discrete=True,
        simulation_values=sim_segment_histogram,
    )
    plot_histogram(
        axes[2, 1],
        expeca_histograms["mac_retransmissions"],
        "MAC retransmissions (ExPeCA)",
        "Retransmissions per packet",
        discrete=True,
    )
    plot_histogram(
        axes[2, 2],
        expeca_histograms["rlc_retransmissions"],
        "RLC retransmissions (ExPeCA)",
        "Retransmissions per packet",
        discrete=True,
    )

    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.85),
        ncol=2,
        frameon=False,
        fontsize=LEGEND_FONT_SIZE,
    )
    fig.suptitle(
        f"Delay decomposition comparison: {run}",
        fontsize=FIGURE_TITLE_FONT_SIZE,
        y=0.995,
    )
    fig.text(
        0.5,
        0.955,
        (
            "Inter-packet interval: "
            f"{format_interval(run_configuration['delayInterval'])}"
            " | Background load: "
            f"{format_background_load(run_configuration)}"
            "\n"
            f"Packet size - Simulation (PDCP): {format_packet_size(sim_packet_size)}"
            f" | ExPeCA (Packet Length): {format_packet_size(expeca_packet_size)}"
            "\n"
            f"Median segments - Simulation: {format_count(sim_median_segments)}"
            f" | ExPeCA: {format_count(expeca_median_segments)}"
        ),
        ha="center",
        va="top",
        fontsize=BASE_FONT_SIZE,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.82))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run}_delay_decomposition_comparison.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_run_time_series(
    run: str,
    sim_csv: Path,
    expeca_csv: Path,
    output_dir: Path,
) -> Path:
    sim_columns = required_columns("sim")
    sim = pd.read_csv(sim_csv, usecols=sim_columns)
    sim = filter_valid_delay_rows(sim, "sim")

    expeca_columns = list(
        dict.fromkeys(
            required_columns("expeca")
            + [EXPECA_RLC_RETRANSMISSIONS_COLUMN]
        )
    )
    expeca = pd.read_csv(expeca_csv, usecols=expeca_columns)
    expeca = filter_valid_delay_rows(clean_expeca_data(expeca), "expeca")

    sim_delays = metric_series(sim, "sim")
    expeca_delays = metric_series(expeca, "expeca")
    expeca_rlc_attempts = pd.to_numeric(
        expeca[EXPECA_SEGMENTS_COLUMN], errors="coerce"
    )
    expeca_rlc_retransmissions = pd.to_numeric(
        expeca[EXPECA_RLC_RETRANSMISSIONS_COLUMN], errors="coerce"
    )
    expeca_mac_attempts = pd.to_numeric(
        expeca[EXPECA_MAC_ATTEMPTS_COLUMN], errors="coerce"
    )
    sim_order = np.arange(1, len(sim) + 1)
    expeca_order = np.arange(1, len(expeca) + 1)

    rows = [
        (title, "Delay (ms)", sim_delays[metric], expeca_delays[metric])
        for metric, title in METRICS
    ]
    rows.extend(
        [
            (
                "Initial RLC segments",
                "Segments",
                pd.to_numeric(sim[SIM_SEGMENTS_COLUMN], errors="coerce"),
                expeca_rlc_attempts - expeca_rlc_retransmissions,
            ),
            (
                "MAC retransmissions",
                "Retransmissions",
                None,
                expeca_mac_attempts - expeca_rlc_attempts,
            ),
            (
                "RLC retransmissions",
                "Retransmissions",
                None,
                expeca_rlc_retransmissions,
            ),
        ]
    )

    fig, axes = plt.subplots(len(rows), 2, figsize=(16, 37))
    for row, (title, ylabel, sim_values, expeca_values) in enumerate(rows):
        for axis, values, order, color in [
            (axes[row, 0], sim_values, sim_order, "#2878B5"),
            (axes[row, 1], expeca_values, expeca_order, "#E07A2D"),
        ]:
            axis.set_title(title)
            axis.set_ylabel(ylabel)
            axis.set_xlabel("Packet order within run")
            if values is None:
                axis.text(
                    0.5,
                    0.5,
                    "Not available",
                    ha="center",
                    va="center",
                    transform=axis.transAxes,
                )
                axis.set_xticks([])
                axis.set_yticks([])
                continue
            axis.plot(order, values, color=color, linewidth=0.6, alpha=0.75)
            axis.grid(color="#D9D9D9", linewidth=0.7)
            axis.set_axisbelow(True)

    fig.suptitle(f"Per-packet metric time series: {run}", y=0.995)
    fig.text(
        0.29,
        0.976,
        "Simulation",
        ha="center",
        va="center",
        fontsize=TITLE_FONT_SIZE,
        fontweight="bold",
    )
    fig.text(
        0.73,
        0.976,
        "ExPeCA",
        ha="center",
        va="center",
        fontsize=TITLE_FONT_SIZE,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.965), h_pad=2.5, w_pad=3)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run}_metric_time_series.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def load_sim_no_harq_packet_keys(run_dir: Path) -> pd.DataFrame:
    attempts = pd.read_csv(
        run_dir / "UlRxTbComponentTrace.txt",
        sep="\t",
        usecols=[*PACKET_KEYS, "rv"],
    )
    attempts = filter_data_only(attempts)
    for column in [*PACKET_KEYS, "rv"]:
        attempts[column] = pd.to_numeric(attempts[column], errors="coerce")
    attempts = attempts.dropna()
    retry_free = attempts.groupby(PACKET_KEYS, as_index=False)["rv"].max()
    return retry_free.loc[retry_free["rv"] == 0, PACKET_KEYS]


def load_component_frame(
    csv_path: Path,
    dataset: str,
    no_harq_retx: bool = False,
    sim_no_harq_packet_keys: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if dataset == "sim":
        columns = {
            "ran_delay": "ran_delay_ms",
            "queueing_delay": "queueing_delay_ms",
            "tx_retx_delay": "tx_retx_delay_ms",
            "segmentation_delay": "segmentation_delay_ms",
        }
        source_columns = list(columns.values())
        if no_harq_retx:
            source_columns.extend(PACKET_KEYS)
        frame = pd.read_csv(csv_path, usecols=source_columns).rename(
            columns={source: target for target, source in columns.items()}
        )
        if no_harq_retx:
            if sim_no_harq_packet_keys is None:
                raise ValueError("simulation no-HARQ filtering requires packet keys")
            frame = frame.merge(sim_no_harq_packet_keys, on=PACKET_KEYS, how="inner")
    else:
        source_columns = [
            "Ran delay",
            "Scheduling delay",
            "Queuing delay",
            EXPECA_TX_COLUMN,
            EXPECA_RETX_COLUMN,
            "segmentation delay",
            EXPECA_SEGMENTS_COLUMN,
            EXPECA_MAC_ATTEMPTS_COLUMN,
        ]
        source = pd.read_csv(csv_path, usecols=source_columns)
        source = clean_expeca_data(source)
        if no_harq_retx:
            mac_attempts = pd.to_numeric(
                source[EXPECA_MAC_ATTEMPTS_COLUMN], errors="coerce"
            )
            rlc_attempts = pd.to_numeric(
                source[EXPECA_SEGMENTS_COLUMN], errors="coerce"
            )
            source = source.loc[mac_attempts == rlc_attempts]
        frame = pd.DataFrame(
            {
                "ran_delay": source["Ran delay"],
                "queueing_delay": source["Queuing delay"],
                "tx_retx_delay": (
                    source[EXPECA_TX_COLUMN] + source[EXPECA_RETX_COLUMN]
                ),
                "segmentation_delay": source["segmentation delay"],
            }
        )

    frame = frame[["ran_delay", *(component for component, _, _ in TAIL_COMPONENTS)]]
    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame[frame["ran_delay"] >= 0].dropna()


def component_statistics(
    frame: pd.DataFrame,
    quantile: float | None = None,
) -> dict[str, float]:
    statistics = frame.mean() if quantile is None else frame.quantile(quantile)
    columns = ["ran_delay", *(component for component, _, _ in TAIL_COMPONENTS)]
    return {column: float(statistics[column]) for column in columns}


def plot_component_sweeps(
    common_runs: list[str],
    sim_runs: dict[str, Path],
    expeca_runs: dict[str, Path],
    run_configurations: dict[str, dict[str, object]],
    output_dir: Path,
    quantile: float | None = None,
    no_harq_retx: bool = False,
    sim_no_harq_packet_keys: dict[str, pd.DataFrame] | None = None,
) -> Path:
    sweep_specs = [
        {
            "runs": [f"a{index}" for index in range(1, 8)],
            "x_value": lambda config: float(config["delayPacketSize"]),
            "x_label": "Packet size (B)",
            "x_tick_label": lambda config: f"{config['delayPacketSize']}",
            "title": "Packet-size sweep",
        },
        {
            "runs": [f"e{index}" for index in range(1, 8)],
            "x_value": lambda config: -float(
                re.fullmatch(r"([0-9.]+)ms", str(config["delayInterval"])).group(1)
            ),
            "x_label": "Inter-packet interval (ms)",
            "x_tick_label": lambda config: re.fullmatch(
                r"([0-9.]+)ms", str(config["delayInterval"])
            ).group(1),
            "title": "Inter-packet-interval sweep",
        },
        {
            "runs": [f"c{index}" for index in range(1, 6)],
            "x_value": lambda config: float(config["cbrLoad"]),
            "x_label": "Background UDP load (Mbps)",
            "x_tick_label": lambda config: f"{float(config['cbrLoad']):g}",
            "title": "Background-load sweep",
        },
    ]
    selected_runs = set(common_runs)
    run_component_statistics = {}
    for run in common_runs:
        sim_frame = load_component_frame(
            sim_runs[run],
            "sim",
            no_harq_retx,
            None if sim_no_harq_packet_keys is None else sim_no_harq_packet_keys[run],
        )
        expeca_frame = load_component_frame(
            expeca_runs[run], "expeca", no_harq_retx
        )
        if no_harq_retx:
            sim_count = len(sim_frame)
            expeca_count = len(expeca_frame)
            sample_count = min(sim_count, expeca_count)
            if sample_count == 0:
                raise ValueError(
                    f"{run} has no retry-free packets in one or both datasets"
                )
            sim_frame = sim_frame.iloc[:sample_count]
            expeca_frame = expeca_frame.iloc[:sample_count]
            print(
                f"No-HARQ {run}: sim={sim_count:,}, ExPeCA={expeca_count:,}, "
                f"using first {sample_count:,} samples"
            )
        run_component_statistics[run] = {
            "sim": component_statistics(sim_frame, quantile),
            "expeca": component_statistics(expeca_frame, quantile),
        }
    statistic_label = "Mean" if quantile is None else f"P{quantile * 100:g}"

    fig, axes = plt.subplots(2, 3, figsize=(19, 11.5))
    for row, (dataset, dataset_label) in enumerate(
        [("sim", "Simulation"), ("expeca", "ExPeCA")]
    ):
        for column, spec in enumerate(sweep_specs):
            axis = axes[row, column]
            runs = [run for run in spec["runs"] if run in selected_runs]
            runs.sort(key=lambda run: spec["x_value"](run_configurations[run]))
            if not runs:
                axis.set_visible(False)
                continue

            x = np.arange(len(runs))
            markers = ["o", "s", "^"]
            for (component, label, color), marker in zip(TAIL_COMPONENTS, markers):
                values = np.array(
                    [
                        run_component_statistics[run][dataset][component]
                        for run in runs
                    ]
                )
                axis.plot(
                    x,
                    values,
                    color=color,
                    marker=marker,
                    linewidth=2,
                    markersize=7,
                    label=label,
                )
            axis.plot(
                x,
                [run_component_statistics[run][dataset]["ran_delay"] for run in runs],
                color="#222222",
                marker="D",
                linewidth=3,
                markersize=7,
                label="RAN delay",
            )

            labels = [
                spec["x_tick_label"](run_configurations[run]) for run in runs
            ]
            axis.set_xticks(x, labels)
            axis.set_xlabel(spec["x_label"], labelpad=9)
            axis.set_ylabel(f"{statistic_label} delay (ms)")
            axis.set_title(spec["title"], fontsize=TITLE_FONT_SIZE, pad=12)
            axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
            axis.set_axisbelow(True)
            axis.margins(y=0.08)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.95),
        ncol=len(handles),
        frameon=False,
        fontsize=LEGEND_FONT_SIZE,
    )
    packet_cohort = (
        "packets without HARQ retransmissions"
        if no_harq_retx
        else "all valid packets"
    )
    figure_title = fig.suptitle(
        f"{statistic_label} RAN delay and delay components among {packet_cohort}",
        fontsize=FIGURE_TITLE_FONT_SIZE,
        y=0.995,
    )
    figure_title.set_in_layout(False)
    fig.tight_layout(rect=(0, 0, 1, 0.84), h_pad=4)
    fig.text(
        0.5,
        0.86,
        "Simulation",
        ha="center",
        va="center",
        fontsize=TITLE_FONT_SIZE,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.425,
        "ExPeCA",
        ha="center",
        va="center",
        fontsize=TITLE_FONT_SIZE,
        fontweight="bold",
    )
    figure_title.set_in_layout(True)

    output_dir.mkdir(parents=True, exist_ok=True)
    cohort_suffix = "_no_harq_retx" if no_harq_retx else ""
    statistic_suffix = "" if quantile is None else f"_p{quantile * 100:g}"
    filename = f"all_packet_component{cohort_suffix}{statistic_suffix}_comparison.png"
    output_path = output_dir / filename
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def load_delay_count_frame(csv_path: Path, dataset: str) -> pd.DataFrame:
    if dataset == "sim":
        columns = [
            SIM_COLUMNS["ran_delay"],
            SIM_COLUMNS["queueing_delay"],
            SIM_COLUMNS["tx_retx_delay"],
            SIM_COLUMNS["segmentation_delay"],
            SIM_SEGMENTS_COLUMN,
        ]
        source = pd.read_csv(csv_path, usecols=columns)
        frame = pd.DataFrame(
            {
                "ran_delay": source[SIM_COLUMNS["ran_delay"]],
                "queueing_delay": source[SIM_COLUMNS["queueing_delay"]],
                "tx_retx_delay": source[SIM_COLUMNS["tx_retx_delay"]],
                "segmentation_delay": source[SIM_COLUMNS["segmentation_delay"]],
                "initial_segments": source[SIM_SEGMENTS_COLUMN],
            }
        )
    else:
        columns = [
            "Ran delay",
            "Scheduling delay",
            "Queuing delay",
            EXPECA_TX_COLUMN,
            EXPECA_RETX_COLUMN,
            "segmentation delay",
            EXPECA_SEGMENTS_COLUMN,
            EXPECA_MAC_ATTEMPTS_COLUMN,
            EXPECA_RLC_RETRANSMISSIONS_COLUMN,
        ]
        source = clean_expeca_data(pd.read_csv(csv_path, usecols=columns))
        rlc_attempts = pd.to_numeric(source[EXPECA_SEGMENTS_COLUMN], errors="coerce")
        rlc_retransmissions = pd.to_numeric(
            source[EXPECA_RLC_RETRANSMISSIONS_COLUMN], errors="coerce"
        )
        frame = pd.DataFrame(
            {
                "ran_delay": source["Ran delay"],
                "queueing_delay": source["Queuing delay"],
                "tx_retx_delay": (
                    pd.to_numeric(source[EXPECA_TX_COLUMN], errors="coerce")
                    + pd.to_numeric(source[EXPECA_RETX_COLUMN], errors="coerce")
                ),
                "segmentation_delay": source["segmentation delay"],
                "initial_segments": rlc_attempts - rlc_retransmissions,
                "mac_retransmissions": (
                    pd.to_numeric(
                        source[EXPECA_MAC_ATTEMPTS_COLUMN], errors="coerce"
                    )
                    - rlc_attempts
                ),
                "rlc_retransmissions": rlc_retransmissions,
            }
        )

    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame[frame["ran_delay"] >= 0]


def plot_delay_by_count(
    axis,
    frame: pd.DataFrame,
    count_column: str,
    title: str,
    xlabel: str,
) -> None:
    if count_column not in frame:
        axis.text(
            0.5,
            0.5,
            "Not available",
            ha="center",
            va="center",
            transform=axis.transAxes,
        )
        axis.set_title(title)
        axis.set_xticks([])
        axis.set_yticks([])
        return

    valid = frame.loc[frame[count_column].notna() & (frame[count_column] >= 0)]
    grouped = valid.groupby(count_column)[
        [metric for metric, _, _ in COUNT_DELAY_METRICS]
    ].mean()
    for metric, label, color in COUNT_DELAY_METRICS:
        axis.plot(
            grouped.index,
            grouped[metric],
            color=color,
            marker="o",
            linewidth=2,
            markersize=7,
            label=label,
        )
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel("Mean delay (ms)")
    axis.set_xticks(grouped.index)
    axis.grid(color="#D9D9D9", linewidth=0.7)
    axis.set_axisbelow(True)


def plot_delay_by_packet_counts(
    common_runs: list[str],
    sim_runs: dict[str, Path],
    expeca_runs: dict[str, Path],
    output_dir: Path,
) -> Path:
    pooled = {
        "sim": pd.concat(
            [load_delay_count_frame(sim_runs[run], "sim") for run in common_runs],
            ignore_index=True,
        ),
        "expeca": pd.concat(
            [
                load_delay_count_frame(expeca_runs[run], "expeca")
                for run in common_runs
            ],
            ignore_index=True,
        ),
    }
    count_specs = [
        ("initial_segments", "Initial RLC segments", "Initial RLC segments per packet"),
        (
            "mac_retransmissions",
            "MAC retransmissions",
            "MAC retransmissions per packet",
        ),
        (
            "rlc_retransmissions",
            "RLC retransmissions",
            "RLC retransmissions per packet",
        ),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(19, 11.5))
    for row, dataset in enumerate(["sim", "expeca"]):
        for column, (count_column, title, xlabel) in enumerate(count_specs):
            plot_delay_by_count(
                axes[row, column],
                pooled[dataset],
                count_column,
                title,
                xlabel,
            )

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.95),
        ncol=len(handles),
        frameon=False,
        fontsize=LEGEND_FONT_SIZE,
    )
    fig.suptitle(
        "Mean delay by per-packet segment and retransmission counts",
        fontsize=FIGURE_TITLE_FONT_SIZE,
        y=0.995,
    )
    fig.text(
        0.5,
        0.86,
        "Simulation",
        ha="center",
        va="center",
        fontsize=TITLE_FONT_SIZE,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.425,
        "ExPeCA",
        ha="center",
        va="center",
        fontsize=TITLE_FONT_SIZE,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.84), h_pad=4, w_pad=3)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "all_runs_delay_by_packet_counts.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_delay_threshold_components(
    common_runs: list[str],
    sim_runs: dict[str, Path],
    expeca_runs: dict[str, Path],
    output_dir: Path,
) -> Path:
    pooled = {
        "Simulation": pd.concat(
            [load_component_frame(sim_runs[run], "sim") for run in common_runs],
            ignore_index=True,
        ),
        "ExPeCA": pd.concat(
            [load_component_frame(expeca_runs[run], "expeca") for run in common_runs],
            ignore_index=True,
        ),
    }
    cohorts = [
        (f"< {RAN_TAIL_THRESHOLD_MS:g} ms", lambda frame: frame["ran_delay"] < RAN_TAIL_THRESHOLD_MS),
        (f">= {RAN_TAIL_THRESHOLD_MS:g} ms", lambda frame: frame["ran_delay"] >= RAN_TAIL_THRESHOLD_MS),
        (
            f">= {RAN_EXTREME_THRESHOLD_MS:g} ms",
            lambda frame: frame["ran_delay"] >= RAN_EXTREME_THRESHOLD_MS,
        ),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5), sharey=True)
    for axis, (dataset, frame) in zip(axes, pooled.items()):
        x = np.arange(len(cohorts))
        cohort_frames = [frame.loc[selector(frame)] for _, selector in cohorts]
        markers = ["o", "s", "^"]
        component_values = []
        for (component, label, color), marker in zip(TAIL_COMPONENTS, markers):
            values = np.array(
                [float(cohort[component].mean()) for cohort in cohort_frames]
            )
            component_values.append(values)
            axis.plot(
                x,
                values,
                color=color,
                marker=marker,
                linewidth=2,
                markersize=7,
                label=label,
            )

        for index, cohort in enumerate(cohort_frames):
            annotation_height = max(values[index] for values in component_values)
            axis.annotate(
                f"n={len(cohort):,}\n{format_percentage(len(cohort), len(frame))}",
                (x[index], annotation_height),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=12,
            )
        axis.set_xticks(x, [label for label, _ in cohorts])
        axis.set_title(dataset)
        axis.set_xlabel("RAN delay cohort")
        axis.set_ylabel("Mean delay (ms)")
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
        axis.set_axisbelow(True)
        axis.margins(y=0.18)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.91),
        ncol=len(TAIL_COMPONENTS),
        frameon=False,
    )
    fig.suptitle(
        "Mean delay components of large RAN delays",
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.84), w_pad=3)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "all_runs_mean_delay_components_of_large_ran_delays.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_expeca_run_metric_heatmap(
    runs: list[str],
    expeca_runs: dict[str, Path],
    run_configurations: dict[str, dict[str, object]],
    output_dir: Path,
) -> Path:
    columns = [
        ("Inter-pkt - mean RAN", False),
        ("Mean UL CQI", False),
        ("Pkts with HARQ retx", True),
        ("Pkts with RLC retx", True),
        ("Initial segs >3", True),
        ("Additional backlog", True),
        ("Pkts RAN >25 ms", True),
        ("Pkts RAN >50 ms", True),
    ]
    records = []
    for run in runs:
        frame = filter_valid_delay_rows(
            clean_expeca_data(pd.read_csv(expeca_runs[run])), "expeca"
        )
        mac_attempts = pd.to_numeric(
            frame[EXPECA_MAC_ATTEMPTS_COLUMN], errors="coerce"
        )
        rlc_attempts = pd.to_numeric(
            frame[EXPECA_SEGMENTS_COLUMN], errors="coerce"
        )
        rlc_retransmissions = pd.to_numeric(
            frame[EXPECA_RLC_RETRANSMISSIONS_COLUMN], errors="coerce"
        )
        harq_retransmissions = mac_attempts - rlc_attempts
        ran_delay = pd.to_numeric(
            frame[EXPECA_COLUMNS["ran_delay"]], errors="coerce"
        )
        expected_packet_bytes = (
            pd.to_numeric(frame[EXPECA_PACKET_SIZE_COLUMN], errors="coerce") + 3
        )
        additional_backlog = (
            pd.to_numeric(frame["RLC queue (UE)"], errors="coerce")
            > expected_packet_bytes
        )
        interval_ms = float(
            str(run_configurations[run]["delayInterval"]).removesuffix("ms")
        )
        records.append(
            {
                "Run": run,
                "Inter-pkt - mean RAN": interval_ms - ran_delay.mean(),
                "Mean UL CQI": pd.to_numeric(
                    frame[EXPECA_UL_CQI_COLUMN], errors="coerce"
                ).mean(),
                "Pkts with HARQ retx": 100 * (harq_retransmissions > 0).mean(),
                "Pkts with RLC retx": 100 * (rlc_retransmissions > 0).mean(),
                "Initial segs >3": 100
                * ((rlc_attempts - rlc_retransmissions) > 3).mean(),
                "Additional backlog": 100 * additional_backlog.mean(),
                "Pkts RAN >25 ms": 100 * (ran_delay > 25).mean(),
                "Pkts RAN >50 ms": 100 * (ran_delay > 50).mean(),
            }
        )

    values = pd.DataFrame(records).sort_values(
        "Pkts RAN >25 ms", ascending=False
    ).set_index("Run")
    normalized = values.astype(float).copy()
    for name, higher_is_worse in columns:
        series = values[name].astype(float)
        spread = series.max() - series.min()
        scaled = (series - series.min()) / spread if spread else series * 0
        normalized[name] = scaled if higher_is_worse else 1 - scaled

    labels = [
        "Inter-pkt -\nmean RAN",
        "Mean UL\nCQI",
        "Pkts with\nHARQ retx",
        "Pkts with\nRLC retx",
        "Initial segs\n>3",
        "Additional\nbacklog",
        "Pkts RAN\n>25 ms",
        "Pkts RAN\n>50 ms",
    ]
    fig, axis = plt.subplots(figsize=(15.5, 11.5))
    image = axis.imshow(normalized.to_numpy(), cmap="YlOrRd", aspect="auto")
    axis.set_xticks(np.arange(len(labels)), labels=labels)
    axis.set_yticks(np.arange(len(values)), labels=values.index)
    axis.tick_params(axis="x", pad=10)
    axis.set_ylabel("Run")

    percent_columns = {
        "Pkts with HARQ retx",
        "Pkts with RLC retx",
        "Initial segs >3",
        "Additional backlog",
        "Pkts RAN >25 ms",
        "Pkts RAN >50 ms",
    }
    for row in range(len(values)):
        for column, (name, _) in enumerate(columns):
            value = values.iloc[row][name]
            if name == "Inter-pkt - mean RAN":
                label = f"{value:.1f} ms"
            elif name == "Mean UL CQI":
                label = f"{value:.1f}"
            elif name in percent_columns:
                label = f"{value:.1f}%"
            else:
                label = f"{value:.0f}"
            text_color = "white" if normalized.iloc[row, column] > 0.62 else "#222222"
            axis.text(
                column,
                row,
                label,
                ha="center",
                va="center",
                color=text_color,
                fontsize=13,
                fontweight="semibold",
            )

    colorbar = fig.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
    colorbar.set_ticks([])
    colorbar.set_label("Relative severity within each metric")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "all_runs_expeca_metric_heatmap.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare simulation and ExPeCA delay-decomposition quantiles with "
            "one six-panel bar chart per run."
        )
    )
    parser.add_argument(
        "--sim-dir",
        required=True,
        type=Path,
        help="Directory containing simulation delay-decomposition CSVs.",
    )
    parser.add_argument(
        "--expeca-dir",
        required=True,
        type=Path,
        help="Directory containing Expeca delay-decomposition CSVs.",
    )
    parser.add_argument(
        "--sim-raw-dir",
        required=True,
        type=Path,
        help="Directory containing per-run simulation raw trace directories.",
    )
    parser.add_argument(
        "--expeca-json-dir",
        required=True,
        type=Path,
        help="Directory containing Expeca raw JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where comparison figures should be written.",
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        help="Optional run names to plot, for example: --runs a1 c2 e4.",
    )
    args = parser.parse_args()

    sim_runs = find_sim_runs(args.sim_dir.resolve())
    expeca_runs = find_expeca_runs(args.expeca_dir.resolve())
    sim_raw_runs = find_sim_raw_runs(args.sim_raw_dir.resolve())
    expeca_json_runs = find_expeca_json_runs(args.expeca_json_dir.resolve())
    run_configurations = load_run_configurations()
    common_runs = sorted(
        set(sim_runs).intersection(expeca_runs),
        key=run_sort_key,
    )
    if args.runs:
        requested = set(args.runs)
        missing = sorted(requested.difference(common_runs), key=run_sort_key)
        if missing:
            parser.error(f"runs not found in both datasets: {', '.join(missing)}")
        common_runs = [run for run in common_runs if run in requested]
    if not common_runs:
        parser.error("no matching simulation and ExPeCA runs were found")
    missing_raw = [
        run for run in common_runs
        if run not in sim_raw_runs or run not in expeca_json_runs
    ]
    if missing_raw:
        parser.error(
            "runs missing simulation raw traces or Expeca JSON: "
            + ", ".join(missing_raw)
        )
    missing_configurations = [
        run for run in common_runs if run not in run_configurations
    ]
    if missing_configurations:
        parser.error(
            "runs missing from campaign configuration: "
            + ", ".join(missing_configurations)
        )

    output_dir = args.output_dir.resolve()
    full_sim_runs = sim_runs.copy()
    full_expeca_runs = expeca_runs.copy()
    balanced_csv_dir = TemporaryDirectory(prefix="balanced-delay-decomp-")
    balanced_root = Path(balanced_csv_dir.name)
    balanced_runs = {
        run: balance_run_samples(
            run,
            sim_runs[run],
            expeca_runs[run],
            balanced_root,
        )
        for run in common_runs
    }
    sim_runs = {run: paths[0] for run, paths in balanced_runs.items()}
    expeca_runs = {run: paths[1] for run, paths in balanced_runs.items()}

    print(f"Creating {len(common_runs)} per-run comparison figure(s)")
    for run in common_runs:
        print(f"Processing {run}")
        (
            sim_statistics,
            sim_extrema,
            sim_packet_size,
            sim_median_segments,
        ) = calculate_statistics(sim_runs[run], "sim")
        (
            expeca_statistics,
            expeca_extrema,
            expeca_packet_size,
            expeca_median_segments,
        ) = calculate_statistics(
            expeca_runs[run],
            "expeca",
        )
        expeca_histograms = load_expeca_histogram_values(expeca_runs[run])
        output_path = plot_run(
            run,
            sim_statistics,
            expeca_statistics,
            sim_extrema,
            expeca_extrema,
            sim_packet_size,
            expeca_packet_size,
            sim_median_segments,
            expeca_median_segments,
            load_sim_segment_histogram_values(sim_runs[run]),
            expeca_histograms,
            run_configurations[run],
            output_dir,
        )
        print(f"Wrote {output_path}")
        output_path = plot_run_time_series(
            run,
            sim_runs[run],
            expeca_runs[run],
            output_dir,
        )
        print(f"Wrote {output_path}")
        output_path = plot_delay_probe_tb_histograms(
            run,
            load_sim_delay_probe_tb_metrics(sim_raw_runs[run]),
            load_expeca_delay_probe_tb_metrics(expeca_json_runs[run]),
            output_dir,
        )
        print(f"Wrote {output_path}")

    output_path = plot_delay_threshold_components(
        common_runs,
        sim_runs,
        expeca_runs,
        output_dir,
    )
    print(f"Wrote {output_path}")
    output_path = plot_component_sweeps(
        common_runs,
        sim_runs,
        expeca_runs,
        run_configurations,
        output_dir,
    )
    print(f"Wrote {output_path}")
    output_path = plot_component_sweeps(
        common_runs,
        sim_runs,
        expeca_runs,
        run_configurations,
        output_dir,
        quantile=0.99,
    )
    print(f"Wrote {output_path}")
    sim_no_harq_packet_keys = {
        run: load_sim_no_harq_packet_keys(sim_raw_runs[run])
        for run in common_runs
    }
    output_path = plot_component_sweeps(
        common_runs,
        full_sim_runs,
        full_expeca_runs,
        run_configurations,
        output_dir,
        no_harq_retx=True,
        sim_no_harq_packet_keys=sim_no_harq_packet_keys,
    )
    print(f"Wrote {output_path}")
    output_path = plot_component_sweeps(
        common_runs,
        full_sim_runs,
        full_expeca_runs,
        run_configurations,
        output_dir,
        quantile=0.95,
        no_harq_retx=True,
        sim_no_harq_packet_keys=sim_no_harq_packet_keys,
    )
    print(f"Wrote {output_path}")
    output_path = plot_delay_by_packet_counts(
        common_runs,
        sim_runs,
        expeca_runs,
        output_dir,
    )
    print(f"Wrote {output_path}")
    output_path = plot_expeca_run_metric_heatmap(
        common_runs,
        expeca_runs,
        run_configurations,
        output_dir,
    )
    print(f"Wrote {output_path}")
    balanced_csv_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
