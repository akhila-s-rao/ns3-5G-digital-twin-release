#!/usr/bin/env python3
import argparse
import ast
import json
import os
import pickle
import re
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, TypedDict

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
    match_rlc_components_to_pusch,
)


BASE_FONT_SIZE = 19
TICK_FONT_SIZE = 18
LABEL_FONT_SIZE = 20
TITLE_FONT_SIZE = 21
FIGURE_TITLE_FONT_SIZE = 25
LEGEND_FONT_SIZE = 19

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
MIN_QUANTILE_BAR_SAMPLES = 30
TBLER_WINDOW_SECONDS = 0.1
# Increment when raw-metric extraction logic changes incompatibly.
RAW_METRIC_CACHE_VERSION = 1

SIM_RAW_METRIC_FILES = (
    "NrUlPdcpRxStats.txt",
    "delay_trace.txt",
    "UlRxTbComponentTrace.txt",
    "NrUlMacStats.txt",
    "UlRxTbTrace.txt",
    "NrUlRlcTxComponentStats.txt",
    "NrUlRlcRxComponentStats.txt",
)

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
SIM_HARQ_RETRANSMISSIONS_COLUMN = "harq_retransmissions_per_pkt"
SIM_RLC_RETRANSMISSIONS_COLUMN = "rlc_retransmissions_per_pkt"
EXPECA_SEGMENTS_COLUMN = "No of RLC attempts"
EXPECA_RLC_RETRANSMISSIONS_COLUMN = "No of RLC retransmissions"
EXPECA_MAC_ATTEMPTS_COLUMN = "MAC attempts (total)"
FRESH_BACKLOG_COLUMN = "fresh_backlog"
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
POOLED_ALLOCATION_METRICS = [
    metric for metric in TB_METRICS if metric[0] in {"mcs", "prbs", "symbols", "tbs"}
]
BACKLOG_METRICS = [
    ("ran_delay", "RAN delay", "Delay (ms)"),
    ("queueing_delay", "Queuing delay", "Delay (ms)"),
    ("tx_retx_delay", "Tx + retransmission delay", "Delay (ms)"),
    ("segmentation_delay", "Segmentation delay", "Delay (ms)"),
    ("initial_segments", "Initial RLC segments", "Segments per packet"),
    (
        "prbs_per_allocation",
        "Mean PRBs per MAC allocation",
        "PRBs per allocation",
    ),
]


class RawMetricBundle(TypedDict):
    tb_metrics: dict[str, np.ndarray]
    initial_tb_series: pd.DataFrame
    rnti: str
    segment_attempt_delays: pd.DataFrame


class SimRawMetricBundle(RawMetricBundle):
    no_harq_packet_keys: pd.DataFrame


class RawMetricCache:
    """Persistent cache for expensive raw-trace metrics."""

    def __init__(self, directory: Path, rebuild: bool = False) -> None:
        self.directory = directory
        self.rebuild = rebuild
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _dependency_signature(paths: list[Path]) -> list[tuple[str, int, int]]:
        signature = []
        for path in paths:
            resolved = path.resolve()
            stat = resolved.stat()
            signature.append((str(resolved), stat.st_size, stat.st_mtime_ns))
        return signature

    def get_or_build(
        self,
        dataset: str,
        run: str,
        dependencies: list[Path],
        builder: Callable[[], RawMetricBundle],
    ) -> RawMetricBundle:
        cache_path = self.directory / f"{dataset}_{run}.pkl"
        signature = self._dependency_signature(dependencies)
        if cache_path.exists() and not self.rebuild:
            try:
                with cache_path.open("rb") as source:
                    cached = pickle.load(source)
                if (
                    cached.get("version") == RAW_METRIC_CACHE_VERSION
                    and cached.get("dependencies") == signature
                ):
                    print(f"Raw metric cache hit: {dataset} {run}")
                    return cached["metrics"]
            except (OSError, EOFError, pickle.UnpicklingError, AttributeError):
                pass

        print(f"Building raw metric cache: {dataset} {run}")
        metrics = builder()
        payload = {
            "version": RAW_METRIC_CACHE_VERSION,
            "dependencies": signature,
            "metrics": metrics,
        }
        temporary_path = cache_path.with_suffix(f".tmp-{os.getpid()}")
        try:
            with temporary_path.open("wb") as destination:
                pickle.dump(payload, destination, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temporary_path, cache_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return metrics


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
    packet_keys = packet_keys.loc[
        pd.to_numeric(packet_keys["pkt_id"], errors="coerce").ne(1)
    ]

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


def load_expeca_delay_probe_tb_metrics(
    packets: list[dict[str, object]],
) -> dict[str, np.ndarray]:
    attempts = {}
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


def load_sim_initial_tb_series(run_dir: Path) -> tuple[pd.DataFrame, str]:
    probe_rntis = pd.to_numeric(
        pd.read_csv(run_dir / "delay_trace.txt", sep="\t", usecols=["rnti"])[
            "rnti"
        ],
        errors="coerce",
    ).dropna().unique()
    if len(probe_rntis) != 1:
        raise ValueError(
            f"Expected one delay-probe RNTI in {run_dir}, found {probe_rntis.tolist()}"
        )

    columns = [
        "time_us", "frame", "subframe", "slot", "rnti", "tb_size", "mcs",
        "rv", "corrupt",
    ]
    attempts = pd.read_csv(run_dir / "UlRxTbTrace.txt", sep="\t", usecols=columns)
    for column in ["time_us", "rnti", "mcs", "rv", "corrupt"]:
        attempts[column] = pd.to_numeric(attempts[column], errors="coerce")
    attempts = attempts.dropna(subset=["time_us", "rnti", "mcs", "rv", "corrupt"])
    attempts = attempts.loc[attempts["rnti"].eq(probe_rntis[0])]
    attempts = attempts.drop_duplicates(
        ["time_us", "frame", "subframe", "slot", "rnti", "tb_size", "mcs", "rv"]
    )
    attempts = attempts.loc[attempts["rv"].eq(0)].sort_values("time_us")
    if attempts.empty:
        raise ValueError(f"No initial TBs found for delay-probe RNTI in {run_dir}")

    attempts = attempts[["time_us", "mcs", "corrupt"]].copy()
    attempts["elapsed_s"] = (
        attempts["time_us"] - attempts["time_us"].min()
    ) / 1_000_000.0
    attempts["failed"] = attempts["corrupt"].ne(0)
    return attempts, str(int(probe_rntis[0]))


def load_expeca_initial_tb_series(
    packets: list[dict[str, object]],
    json_path: Path,
) -> tuple[pd.DataFrame, str]:
    probe_rntis = {
        attempt.get("rnti")
        for packet in packets
        if packet.get("app.sn") is not None
        for rlc_attempt in packet.get("rlc.attempts", [])
        for attempt in rlc_attempt.get("mac.attempts", [])
        if attempt.get("rnti") is not None
    }
    if len(probe_rntis) != 1:
        raise ValueError(
            f"Expected one delay-probe RNTI in {json_path}, found {sorted(probe_rntis)}"
        )
    probe_rnti = next(iter(probe_rntis))

    attempts = {}
    for packet in packets:
        for rlc_attempt in packet.get("rlc.attempts", []):
            for attempt in rlc_attempt.get("mac.attempts", []):
                if attempt.get("rnti") != probe_rnti:
                    continue
                key = (
                    attempt.get("rnti"), attempt.get("frame"), attempt.get("slot"),
                    attempt.get("id"), attempt.get("hqpid"), attempt.get("hqround"),
                    attempt.get("phy.in_t"),
                )
                attempts[key] = attempt

    frame = pd.DataFrame(attempts.values())
    for column in ["phy.in_t", "mcs", "hqround"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["phy.in_t", "mcs", "hqround", "acked"])
    frame = frame.loc[frame["hqround"].eq(0)].sort_values("phy.in_t")
    if frame.empty:
        raise ValueError(f"No initial TBs found for delay-probe RNTI in {json_path}")

    frame = frame[["phy.in_t", "mcs", "acked"]].copy()
    frame["elapsed_s"] = frame["phy.in_t"] - frame["phy.in_t"].min()
    frame["failed"] = ~frame["acked"].astype(bool)
    return frame, str(probe_rnti)


def window_initial_tbler(attempts: pd.DataFrame) -> pd.DataFrame:
    window = np.floor(attempts["elapsed_s"] / TBLER_WINDOW_SECONDS).astype(int)
    result = attempts.assign(window=window).groupby("window")["failed"].mean()
    result = result.reindex(range(int(window.max()) + 1))
    return pd.DataFrame(
        {
            "time_s": (result.index.to_numpy() + 0.5) * TBLER_WINDOW_SECONDS,
            "tbler": result.to_numpy(),
        }
    )


def plot_initial_tbler_mcs_time_series(
    run: str,
    sim_attempts: pd.DataFrame,
    sim_rnti: str,
    expeca_attempts: pd.DataFrame,
    expeca_rnti: str,
    output_dir: Path,
) -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    for axis, attempts, rnti, system in [
        (axes[0], sim_attempts, sim_rnti, "5G-LENA"),
        (axes[1], expeca_attempts, expeca_rnti, "ExPeCA"),
    ]:
        tbler = window_initial_tbler(attempts)
        mcs_axis = axis.twinx()
        axis.step(
            tbler["time_s"],
            100.0 * tbler["tbler"],
            where="mid",
            color="#C43C39",
            linewidth=1.4,
            label="Initial TBLER (100 ms)",
        )
        mcs_axis.plot(
            attempts["elapsed_s"],
            attempts["mcs"],
            linestyle="none",
            marker=".",
            markersize=2.5,
            alpha=0.55,
            color="#2878B5",
            rasterized=True,
            label="Initial-TB MCS",
        )
        axis.set_title(f"{system} (delay-probe RNTI {rnti})")
        axis.set_xlabel("Elapsed time (s)")
        axis.set_ylabel("Initial TBLER (%)", color="#C43C39")
        mcs_axis.set_ylabel("UL MCS", color="#2878B5")
        axis.tick_params(axis="y", colors="#C43C39")
        mcs_axis.tick_params(axis="y", colors="#2878B5")
        axis.set_ylim(0, 100)
        mcs_axis.set_ylim(0, 28)
        axis.grid(color="#D9D9D9", linewidth=0.7)
        axis.set_axisbelow(True)
        handles = [*axis.get_lines(), *mcs_axis.get_lines()]
        axis.legend(handles, [line.get_label() for line in handles], loc="upper right")

    fig.suptitle(f"Initial TBLER and UL MCS: {run}", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.97), h_pad=2.5)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run}_initial_tbler_mcs_time_series.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_initial_tbler_mcs_histograms(
    run_prefix: str,
    runs: list[str],
    initial_tb_series: dict[str, dict[str, pd.DataFrame]],
    output_dir: Path,
) -> Path:
    column_specs = [
        ("sim", "mcs", "5G-LENA MCS", np.arange(-0.5, 29.5, 1), "UL MCS"),
        ("expeca", "mcs", "ExPeCA MCS", np.arange(-0.5, 29.5, 1), "UL MCS"),
        (
            "sim", "tbler", "5G-LENA initial TBLER", np.linspace(0, 100, 21),
            "Initial TBLER (%)",
        ),
        (
            "expeca", "tbler", "ExPeCA initial TBLER", np.linspace(0, 100, 21),
            "Initial TBLER (%)",
        ),
    ]
    colors = {"sim": "#2878B5", "expeca": "#E07A2D"}
    fig, axes = plt.subplots(
        len(runs), 4, figsize=(23, 3.4 * len(runs) + 1.5), squeeze=False
    )
    for row, run in enumerate(runs):
        for column, (dataset, metric, title, bins, xlabel) in enumerate(column_specs):
            axis = axes[row, column]
            attempts = initial_tb_series[run][dataset]
            values = (
                attempts["mcs"].dropna().to_numpy()
                if metric == "mcs"
                else 100.0
                * window_initial_tbler(attempts)["tbler"].dropna().to_numpy()
            )
            axis.hist(
                values,
                bins=bins,
                weights=np.full(len(values), 100.0 / len(values)),
                color=colors[dataset],
                edgecolor="white",
                linewidth=0.5,
            )
            if row == 0:
                axis.set_title(title)
            if row == len(runs) - 1:
                axis.set_xlabel(xlabel)
            axis.set_ylabel(
                f"{run}\nPercentage (%)" if column == 0 else "Percentage (%)"
            )
            axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
            axis.set_axisbelow(True)
            if metric == "mcs":
                axis.set_xlim(-0.5, 28.5)
                axis.set_xticks([0, 5, 10, 15, 20, 25, 28])
            else:
                axis.set_xlim(0, 100)

        for left, right in ((0, 1), (2, 3)):
            upper = max(axes[row, left].get_ylim()[1], axes[row, right].get_ylim()[1])
            axes[row, left].set_ylim(0, upper)
            axes[row, right].set_ylim(0, upper)

    fig.suptitle(
        f"Initial-TB MCS and 100 ms initial-TBLER: {run_prefix.upper()} runs",
        y=0.998,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985), h_pad=1.5, w_pad=1.4)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (
        f"{run_prefix}_runs_initial_tbler_mcs_histograms.png"
    )
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def load_sim_segment_attempt_delays(
    run_dir: Path,
    packet_csv: Path,
) -> pd.DataFrame:
    packets = pd.read_csv(packet_csv, usecols=[*PACKET_KEYS, "backlog"])
    fresh_backlog = pd.to_numeric(packets["backlog"], errors="coerce")
    packets = packets.loc[fresh_backlog.eq(0)]
    for column in PACKET_KEYS:
        packets[column] = pd.to_numeric(packets[column], errors="coerce")
    packets = packets[PACKET_KEYS].drop_duplicates()

    rlc_tx = pd.read_csv(run_dir / "NrUlRlcTxComponentStats.txt", sep="\t")
    rlc_rx = pd.read_csv(run_dir / "NrUlRlcRxComponentStats.txt", sep="\t")
    tb_attempts = pd.read_csv(
        run_dir / "UlRxTbComponentTrace.txt",
        sep="\t",
        usecols=[*PACKET_KEYS, "time_us", "rv"],
    )
    grants = pd.read_csv(run_dir / "NrUlMacStats.txt", sep="\t")
    for frame in (rlc_tx, rlc_rx, tb_attempts):
        for column in [*PACKET_KEYS, "time_us"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame.dropna(subset=[*PACKET_KEYS, "time_us"], inplace=True)
    rlc_tx = rlc_tx.merge(packets, on=PACKET_KEYS, how="inner")
    rlc_rx = rlc_rx.merge(packets, on=PACKET_KEYS, how="inner")
    tb_attempts = tb_attempts.merge(packets, on=PACKET_KEYS, how="inner")

    matched_tx = match_rlc_components_to_pusch(rlc_tx, grants)
    if matched_tx is None or matched_tx.empty:
        return pd.DataFrame(columns=["harq_attempts", "delay_ms"])

    terminal_attempts = (
        tb_attempts.groupby([*PACKET_KEYS, "time_us"], as_index=False)["rv"]
        .max()
        .rename(columns={"time_us": "rx_time_us"})
    )
    segments = rlc_rx[
        [*PACKET_KEYS, "rlc_sn", "time_us", "delay_us"]
    ].rename(columns={"time_us": "rx_time_us"})
    segments = segments.merge(
        matched_tx[
            [*PACKET_KEYS, "rlc_sn", "rlc_tx_time_us", "virtual_dequeue_time_us"]
        ],
        on=[*PACKET_KEYS, "rlc_sn"],
        how="inner",
    ).merge(
        terminal_attempts,
        on=[*PACKET_KEYS, "rx_time_us"],
        how="inner",
    )
    segments["harq_attempts"] = pd.to_numeric(segments["rv"], errors="coerce") + 1
    segments["delay_ms"] = (
        pd.to_numeric(segments["delay_us"], errors="coerce")
        - (
            pd.to_numeric(segments["virtual_dequeue_time_us"], errors="coerce")
            - pd.to_numeric(segments["rlc_tx_time_us"], errors="coerce")
        )
    ) / 1000.0
    return segments[["harq_attempts", "delay_ms"]].dropna()


def load_expeca_segment_attempt_delays(
    json_packets: list[dict[str, object]],
    packet_csv: Path,
) -> pd.DataFrame:
    packet_frame = clean_expeca_data(pd.read_csv(packet_csv))
    fresh_backlog = pd.to_numeric(
        packet_frame[FRESH_BACKLOG_COLUMN], errors="coerce"
    )
    packet_frame = packet_frame.loc[fresh_backlog.eq(0)]
    packet_keys = set(zip(packet_frame["Packet SN"], packet_frame["Packet ID"]))

    rows = []
    for packet in json_packets:
        if (packet.get("sn"), packet.get("id")) not in packet_keys:
            continue
        for segment in packet.get("rlc.attempts", []):
            mac_in = segment.get("mac.in_t")
            mac_out = segment.get("mac.out_t")
            attempts = segment.get("mac.attempts", [])
            if mac_in is None or mac_out is None or not attempts:
                continue
            rows.append(
                {
                    "harq_attempts": len(attempts),
                    "delay_ms": 1000.0 * (mac_out - mac_in),
                }
            )
    return pd.DataFrame(rows, columns=["harq_attempts", "delay_ms"])


def required_columns(dataset: str) -> list[str]:
    if dataset == "sim":
        return [
            *SIM_COLUMNS.values(),
            SIM_PACKET_SIZE_COLUMN,
            SIM_SEGMENTS_COLUMN,
            SIM_HARQ_RETRANSMISSIONS_COLUMN,
            SIM_RLC_RETRANSMISSIONS_COLUMN,
            "backlog",
        ]
    return [
        *EXPECA_COLUMNS.values(),
        EXPECA_TX_COLUMN,
        EXPECA_RETX_COLUMN,
        EXPECA_PACKET_SIZE_COLUMN,
        EXPECA_SEGMENTS_COLUMN,
        EXPECA_MAC_ATTEMPTS_COLUMN,
        FRESH_BACKLOG_COLUMN,
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


def remove_sim_startup_packet(
    run: str,
    csv_path: Path,
    output_dir: Path,
) -> Path:
    frame = pd.read_csv(csv_path)
    packet_ids = pd.to_numeric(frame["pkt_id"], errors="coerce")
    filtered = frame.loc[packet_ids.ne(1)]
    output_path = output_dir / f"{run}_sim_without_startup.csv"
    filtered.to_csv(output_path, index=False)
    print(f"Filtered {run}: removed {len(frame) - len(filtered)} simulation pkt_id=1 row(s)")
    return output_path


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


def load_sim_histogram_values(csv_path: Path) -> dict[str, np.ndarray]:
    frame = pd.read_csv(
        csv_path,
        usecols=[
            SIM_COLUMNS["ran_delay"],
            SIM_SEGMENTS_COLUMN,
            SIM_HARQ_RETRANSMISSIONS_COLUMN,
            SIM_RLC_RETRANSMISSIONS_COLUMN,
        ],
    )
    frame = filter_valid_delay_rows(frame, "sim")
    return {
        "initial_segments": numeric_values(frame, SIM_SEGMENTS_COLUMN),
        "mac_retransmissions": numeric_values(
            frame, SIM_HARQ_RETRANSMISSIONS_COLUMN
        ),
        "rlc_retransmissions": numeric_values(
            frame, SIM_RLC_RETRANSMISSIONS_COLUMN
        ),
    }


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
        fontsize=14,
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
                ha="right", va="top", transform=axis.transAxes, fontsize=14,
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


def plot_pooled_allocation_histograms(
    sim_values: dict[str, np.ndarray],
    expeca_values: dict[str, np.ndarray],
    output_dir: Path,
) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    for axis, (metric, title, xlabel, discrete) in zip(
        axes.flat, POOLED_ALLOCATION_METRICS
    ):
        simulation = sim_values[metric]
        expeca = expeca_values[metric]
        combined = np.concatenate([simulation, expeca])
        minimum, maximum = float(combined.min()), float(combined.max())
        if discrete and maximum - minimum <= 40:
            bins = np.arange(np.floor(minimum) - 0.5, np.ceil(maximum) + 1.5)
        elif minimum == maximum:
            bins = np.array([minimum - 0.5, maximum + 0.5])
        else:
            bins = np.linspace(minimum, maximum, 31)

        axis.hist(
            [simulation, expeca],
            bins=bins,
            weights=[
                np.full(simulation.size, 100.0 / simulation.size),
                np.full(expeca.size, 100.0 / expeca.size),
            ],
            label=["Simulation", "ExPeCA"],
            color=["#2878B5", "#E07A2D"],
            edgecolor="white",
            linewidth=0.5,
        )
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel("Allocations (%)")
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
        axis.set_axisbelow(True)

    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.94),
        ncol=2,
        frameon=False,
    )
    fig.suptitle("UL allocation metrics across all runs", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.9), h_pad=2.5, w_pad=2.5)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "all_runs_ul_allocation_metric_histograms.png"
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
    sim_histograms: dict[str, np.ndarray],
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
            fontsize=14,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=2),
        )

    plot_histogram(
        axes[2, 0],
        expeca_histograms["initial_segments"],
        "Initial RLC segments",
        "Segments per packet",
        discrete=True,
        simulation_values=sim_histograms["initial_segments"],
    )
    plot_histogram(
        axes[2, 1],
        expeca_histograms["mac_retransmissions"],
        "MAC retransmissions",
        "Retransmissions per packet",
        discrete=True,
        simulation_values=sim_histograms["mac_retransmissions"],
    )
    plot_histogram(
        axes[2, 2],
        expeca_histograms["rlc_retransmissions"],
        "RLC retransmissions",
        "Retransmissions per packet",
        discrete=True,
        simulation_values=sim_histograms["rlc_retransmissions"],
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
                pd.to_numeric(
                    sim[SIM_HARQ_RETRANSMISSIONS_COLUMN], errors="coerce"
                ),
                expeca_mac_attempts - expeca_rlc_attempts,
            ),
            (
                "RLC retransmissions",
                "Retransmissions",
                pd.to_numeric(
                    sim[SIM_RLC_RETRANSMISSIONS_COLUMN], errors="coerce"
                ),
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
    attempts = attempts.loc[attempts["pkt_id"].ne(1)]
    retry_free = attempts.groupby(PACKET_KEYS, as_index=False)["rv"].max()
    return retry_free.loc[retry_free["rv"] == 0, PACKET_KEYS]


def sim_raw_metric_dependencies(
    run_dir: Path,
    sim_csv: Path,
    expeca_csv: Path,
) -> list[Path]:
    return [
        sim_csv,
        expeca_csv,
        *(run_dir / filename for filename in SIM_RAW_METRIC_FILES),
    ]


def expeca_raw_metric_dependencies(
    json_path: Path,
    sim_csv: Path,
    expeca_csv: Path,
) -> list[Path]:
    return [json_path, sim_csv, expeca_csv]


def build_sim_raw_metric_bundle(
    run_dir: Path,
    balanced_packet_csv: Path,
) -> SimRawMetricBundle:
    initial_tb_series, rnti = load_sim_initial_tb_series(run_dir)
    return {
        "tb_metrics": load_sim_delay_probe_tb_metrics(run_dir),
        "initial_tb_series": initial_tb_series,
        "rnti": rnti,
        "segment_attempt_delays": load_sim_segment_attempt_delays(
            run_dir, balanced_packet_csv
        ),
        "no_harq_packet_keys": load_sim_no_harq_packet_keys(run_dir),
    }


def build_expeca_raw_metric_bundle(
    json_path: Path,
    balanced_packet_csv: Path,
) -> RawMetricBundle:
    with json_path.open() as source:
        packets = json.load(source)
    initial_tb_series, rnti = load_expeca_initial_tb_series(packets, json_path)
    return {
        "tb_metrics": load_expeca_delay_probe_tb_metrics(packets),
        "initial_tb_series": initial_tb_series,
        "rnti": rnti,
        "segment_attempt_delays": load_expeca_segment_attempt_delays(
            packets, balanced_packet_csv
        ),
    }


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


def load_backlog_metric_frame(
    csv_path: Path,
    dataset: str,
    no_harq_retx: bool = True,
) -> pd.DataFrame:
    if dataset == "sim":
        source = pd.read_csv(csv_path)
        harq_retransmissions = pd.to_numeric(
            source[SIM_HARQ_RETRANSMISSIONS_COLUMN], errors="coerce"
        )
        if no_harq_retx:
            source = source.loc[harq_retransmissions.eq(0)]
        frame = pd.DataFrame(
            {
                "ran_delay": source[SIM_COLUMNS["ran_delay"]],
                "frame_alignment_delay": source[
                    SIM_COLUMNS["frame_alignment_delay"]
                ],
                "scheduling_delay": source[SIM_COLUMNS["scheduling_delay"]],
                "queueing_delay": source[SIM_COLUMNS["queueing_delay"]],
                "tx_retx_delay": source[SIM_COLUMNS["tx_retx_delay"]],
                "segmentation_delay": source[SIM_COLUMNS["segmentation_delay"]],
                "initial_segments": source[SIM_SEGMENTS_COLUMN],
                "harq_retransmissions": source[
                    SIM_HARQ_RETRANSMISSIONS_COLUMN
                ],
                "prbs_per_allocation": (
                    source["resource_block_size_total"]
                    / (
                        source[SIM_SEGMENTS_COLUMN]
                        + source[SIM_HARQ_RETRANSMISSIONS_COLUMN]
                        + source[SIM_RLC_RETRANSMISSIONS_COLUMN]
                    )
                ),
                FRESH_BACKLOG_COLUMN: source["backlog"],
            }
        )
    else:
        source = clean_expeca_data(pd.read_csv(csv_path))
        mac_attempts = pd.to_numeric(
            source[EXPECA_MAC_ATTEMPTS_COLUMN], errors="coerce"
        )
        rlc_attempts = pd.to_numeric(
            source[EXPECA_SEGMENTS_COLUMN], errors="coerce"
        )
        if no_harq_retx:
            source = source.loc[mac_attempts.eq(rlc_attempts)]
        frame = pd.DataFrame(
            {
                "ran_delay": source[EXPECA_COLUMNS["ran_delay"]],
                "frame_alignment_delay": source[
                    EXPECA_COLUMNS["frame_alignment_delay"]
                ],
                "scheduling_delay": source[EXPECA_COLUMNS["scheduling_delay"]],
                "queueing_delay": source[EXPECA_COLUMNS["queueing_delay"]],
                "tx_retx_delay": (
                    source[EXPECA_TX_COLUMN] + source[EXPECA_RETX_COLUMN]
                ),
                "segmentation_delay": source[EXPECA_COLUMNS["segmentation_delay"]],
                "initial_segments": (
                    source[EXPECA_SEGMENTS_COLUMN]
                    - source[EXPECA_RLC_RETRANSMISSIONS_COLUMN]
                ),
                "harq_retransmissions": (
                    source[EXPECA_MAC_ATTEMPTS_COLUMN]
                    - source[EXPECA_SEGMENTS_COLUMN]
                ),
                "prbs_per_allocation": (
                    source["Resource block size (total)"]
                    / source[EXPECA_MAC_ATTEMPTS_COLUMN]
                ),
                FRESH_BACKLOG_COLUMN: source[FRESH_BACKLOG_COLUMN],
            }
        )

    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame.loc[
        frame["ran_delay"].ge(0) & frame[FRESH_BACKLOG_COLUMN].notna()
    ]


def plot_backlog_metric_bars(
    common_runs: list[str],
    sim_runs: dict[str, Path],
    expeca_runs: dict[str, Path],
    output_dir: Path,
) -> Path:
    frames = {
        "Simulation": pd.concat(
            [load_backlog_metric_frame(sim_runs[run], "sim") for run in common_runs],
            ignore_index=True,
        ),
        "ExPeCA": pd.concat(
            [
                load_backlog_metric_frame(expeca_runs[run], "expeca")
                for run in common_runs
            ],
            ignore_index=True,
        ),
    }

    sim = frames["Simulation"]
    expeca = frames["ExPeCA"]
    cohorts = [
        ("Simulation: no fresh backlog", sim, 0, "#8AB8D8"),
        ("Simulation: fresh backlog", sim, 1, "#2878B5"),
        ("ExPeCA: no fresh backlog", expeca, 0, "#F2B179"),
        ("ExPeCA: fresh backlog", expeca, 1, "#E07A2D"),
    ]
    x = np.arange(2)
    width = 0.19
    fig, axes = plt.subplots(2, 3, figsize=(20, 11))
    for axis, (metric, title, ylabel) in zip(axes.flat, BACKLOG_METRICS):
        for index, (label, frame, state, color) in enumerate(cohorts):
            values = frame.loc[
                frame[FRESH_BACKLOG_COLUMN].eq(state), metric
            ].dropna()
            statistics = values.quantile([0.5, 0.95]).to_numpy(dtype=float)
            axis.bar(
                x + (index - 1.5) * width,
                statistics,
                width,
                label=label,
                color=color,
                edgecolor="white",
                linewidth=0.5,
            )
        axis.set_title(title)
        axis.set_xticks(x, ["Median", "P95"])
        axis.set_ylabel(ylabel)
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
        axis.set_axisbelow(True)
        axis.margins(y=0.12)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.94),
        ncol=4,
        frameon=False,
    )
    fig.suptitle("No-HARQ packet metrics by fresh RLC backlog state", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.88), h_pad=2.5, w_pad=2.5)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "all_runs_no_harq_backlog_median_p95.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_quantile_comparison(
    axis,
    categories: list[str],
    sim_groups: list[pd.Series],
    expeca_groups: list[pd.Series],
    title: str,
    ylabel: str,
) -> None:
    x = np.arange(len(categories))
    width = 0.18
    offsets = np.array([-1.7, -0.7, 0.7, 1.7]) * width
    series = [
        ("Simulation median", sim_groups, 0.5, "#8AB8D8", None),
        ("ExPeCA median", expeca_groups, 0.5, "#F2B179", None),
        ("Simulation P95", sim_groups, 0.95, "#2878B5", "///"),
        ("ExPeCA P95", expeca_groups, 0.95, "#E07A2D", "///"),
    ]
    for index, (label, groups, quantile, color, hatch) in enumerate(series):
        valid_groups = [group.dropna() for group in groups]
        values = [
            group.quantile(quantile)
            if len(group) >= MIN_QUANTILE_BAR_SAMPLES
            else np.nan
            for group in valid_groups
        ]
        axis.bar(
            x + offsets[index],
            values,
            width,
            label=label,
            color=color,
            hatch=hatch,
            edgecolor="white",
            linewidth=0.5,
        )
    axis.set_title(title)
    axis.set_xticks(x, categories)
    axis.set_ylabel(ylabel)
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.margins(y=0.12)


def remove_unsupported_groups(
    categories: list[int],
    sim_groups: list[pd.Series],
    expeca_groups: list[pd.Series],
) -> tuple[list[int], list[pd.Series], list[pd.Series]]:
    supported = [
        index
        for index, (sim, expeca) in enumerate(zip(sim_groups, expeca_groups))
        if max(sim.notna().sum(), expeca.notna().sum()) >= MIN_QUANTILE_BAR_SAMPLES
    ]
    return (
        [categories[index] for index in supported],
        [sim_groups[index] for index in supported],
        [expeca_groups[index] for index in supported],
    )


def plot_filtered_delay_comparison(
    common_runs: list[str],
    sim_runs: dict[str, Path],
    expeca_runs: dict[str, Path],
    sim_raw_metrics: dict[str, SimRawMetricBundle],
    expeca_raw_metrics: dict[str, RawMetricBundle],
    output_dir: Path,
) -> Path:
    sim = pd.concat(
        [
            load_backlog_metric_frame(
                sim_runs[run], "sim", no_harq_retx=False
            )
            for run in common_runs
        ],
        ignore_index=True,
    )
    expeca = pd.concat(
        [
            load_backlog_metric_frame(
                expeca_runs[run], "expeca", no_harq_retx=False
            )
            for run in common_runs
        ],
        ignore_index=True,
    )
    sim_no_backlog = sim.loc[sim[FRESH_BACKLOG_COLUMN].eq(0)]
    expeca_no_backlog = expeca.loc[expeca[FRESH_BACKLOG_COLUMN].eq(0)]
    sim_baseline = sim_no_backlog.loc[sim_no_backlog["harq_retransmissions"].eq(0)]
    expeca_baseline = expeca_no_backlog.loc[
        expeca_no_backlog["harq_retransmissions"].eq(0)
    ]
    sim_segment_attempts = pd.concat(
        [
            sim_raw_metrics[run]["segment_attempt_delays"]
            for run in common_runs
        ],
        ignore_index=True,
    )
    expeca_segment_attempts = pd.concat(
        [
            expeca_raw_metrics[run]["segment_attempt_delays"]
            for run in common_runs
        ],
        ignore_index=True,
    )

    fig = plt.figure(figsize=(20, 12))
    grid = fig.add_gridspec(2, 2, hspace=0.4, wspace=0.25)
    baseline_axis = fig.add_subplot(grid[0, :])
    segmentation_axis = fig.add_subplot(grid[1, 0])
    harq_axis = fig.add_subplot(grid[1, 1])

    baseline_metrics = [
        ("ran_delay", "RAN"),
        ("frame_alignment_delay", "Frame\nalignment"),
        ("scheduling_delay", "Scheduling"),
        ("queueing_delay", "Queuing"),
        ("tx_retx_delay", "Tx"),
        ("segmentation_delay", "Segmentation"),
    ]
    plot_quantile_comparison(
        baseline_axis,
        [label for _, label in baseline_metrics],
        [sim_baseline[metric] for metric, _ in baseline_metrics],
        [expeca_baseline[metric] for metric, _ in baseline_metrics],
        "Delay components: no fresh backlog and no HARQ retransmissions",
        "Delay (ms)",
    )

    segment_counts = list(range(1, 7))
    sim_segment_groups = [
        sim_baseline.loc[
            sim_baseline["initial_segments"].eq(count),
            "segmentation_delay",
        ]
        for count in segment_counts
    ]
    expeca_segment_groups = [
        expeca_baseline.loc[
            expeca_baseline["initial_segments"].eq(count),
            "segmentation_delay",
        ]
        for count in segment_counts
    ]
    segment_counts, sim_segment_groups, expeca_segment_groups = (
        remove_unsupported_groups(
            segment_counts, sim_segment_groups, expeca_segment_groups
        )
    )
    plot_quantile_comparison(
        segmentation_axis,
        [str(count) for count in segment_counts],
        sim_segment_groups,
        expeca_segment_groups,
        "Segmentation delay by initial RLC segments\n"
        "(no fresh backlog, no HARQ retransmissions)",
        "Delay (ms)",
    )
    segmentation_axis.set_xlabel("Initial RLC segments per packet")

    harq_counts = [1, 2, 3, 4]
    sim_harq_groups = [
        sim_segment_attempts.loc[
            sim_segment_attempts["harq_attempts"].eq(count),
            "delay_ms",
        ]
        for count in harq_counts
    ]
    expeca_harq_groups = [
        expeca_segment_attempts.loc[
            expeca_segment_attempts["harq_attempts"].eq(count),
            "delay_ms",
        ]
        for count in harq_counts
    ]
    harq_counts, sim_harq_groups, expeca_harq_groups = remove_unsupported_groups(
        harq_counts, sim_harq_groups, expeca_harq_groups
    )
    plot_quantile_comparison(
        harq_axis,
        [str(count) for count in harq_counts],
        sim_harq_groups,
        expeca_harq_groups,
        "RLC-segment delay by consecutive HARQ attempts\n"
        "(no fresh backlog)",
        "Delay (ms)",
    )
    harq_axis.set_xlabel("HARQ attempts for the RLC segment")

    handles, labels = baseline_axis.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.94),
        ncol=4,
        frameon=False,
    )
    fig.suptitle(
        "Simulation and ExPeCA packet-delay comparison across all runs",
        y=0.995,
    )
    fig.text(
        0.98,
        0.02,
        f"Bars shown only for groups with at least {MIN_QUANTILE_BAR_SAMPLES} samples",
        ha="right",
        fontsize=14,
    )
    fig.subplots_adjust(top=0.84, bottom=0.14, left=0.07, right=0.98)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "all_runs_filtered_delay_median_p95.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


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
            SIM_HARQ_RETRANSMISSIONS_COLUMN,
            SIM_RLC_RETRANSMISSIONS_COLUMN,
        ]
        source = pd.read_csv(csv_path, usecols=columns)
        frame = pd.DataFrame(
            {
                "ran_delay": source[SIM_COLUMNS["ran_delay"]],
                "queueing_delay": source[SIM_COLUMNS["queueing_delay"]],
                "tx_retx_delay": source[SIM_COLUMNS["tx_retx_delay"]],
                "segmentation_delay": source[SIM_COLUMNS["segmentation_delay"]],
                "initial_segments": source[SIM_SEGMENTS_COLUMN],
                "mac_retransmissions": source[SIM_HARQ_RETRANSMISSIONS_COLUMN],
                "rlc_retransmissions": source[SIM_RLC_RETRANSMISSIONS_COLUMN],
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
                fontsize=14,
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


def plot_run_metric_heatmap(records: list[dict[str, object]], output_path: Path) -> Path:
    columns = [
        ("Inter-pkt - mean RAN", False),
        ("Pkts with HARQ retx", True),
        ("Pkts with RLC retx", True),
        ("Initial segs >3", True),
        ("Fresh backlog", True),
        ("Pkts RAN >25 ms", True),
        ("Pkts RAN >50 ms", True),
    ]
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
        "Pkts with\nHARQ retx",
        "Pkts with\nRLC retx",
        "Initial segs\n>3",
        "Fresh\nbacklog",
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
        "Fresh backlog",
        "Pkts RAN >25 ms",
        "Pkts RAN >50 ms",
    }
    for row in range(len(values)):
        for column, (name, _) in enumerate(columns):
            value = values.iloc[row][name]
            if name == "Inter-pkt - mean RAN":
                label = f"{value:.1f} ms"
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
                fontsize=15,
                fontweight="semibold",
            )

    colorbar = fig.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
    colorbar.set_ticks([])
    colorbar.set_label("Relative severity within each metric")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_expeca_run_metric_heatmap(
    runs: list[str],
    expeca_runs: dict[str, Path],
    run_configurations: dict[str, dict[str, object]],
    output_dir: Path,
) -> Path:
    records = []
    for run in runs:
        frame = filter_valid_delay_rows(
            clean_expeca_data(pd.read_csv(expeca_runs[run])), "expeca"
        )
        mac_attempts = pd.to_numeric(frame[EXPECA_MAC_ATTEMPTS_COLUMN], errors="coerce")
        rlc_attempts = pd.to_numeric(frame[EXPECA_SEGMENTS_COLUMN], errors="coerce")
        rlc_retransmissions = pd.to_numeric(
            frame[EXPECA_RLC_RETRANSMISSIONS_COLUMN], errors="coerce"
        )
        ran_delay = pd.to_numeric(frame[EXPECA_COLUMNS["ran_delay"]], errors="coerce")
        interval_ms = float(
            str(run_configurations[run]["delayInterval"]).removesuffix("ms")
        )
        records.append(
            {
                "Run": run,
                "Inter-pkt - mean RAN": interval_ms - ran_delay.mean(),
                "Pkts with HARQ retx": 100
                * ((mac_attempts - rlc_attempts) > 0).mean(),
                "Pkts with RLC retx": 100 * (rlc_retransmissions > 0).mean(),
                "Initial segs >3": 100
                * ((rlc_attempts - rlc_retransmissions) > 3).mean(),
                "Fresh backlog": 100
                * pd.to_numeric(
                    frame[FRESH_BACKLOG_COLUMN], errors="coerce"
                ).mean(),
                "Pkts RAN >25 ms": 100 * (ran_delay > 25).mean(),
                "Pkts RAN >50 ms": 100 * (ran_delay > 50).mean(),
            }
        )
    return plot_run_metric_heatmap(
        records, output_dir / "all_runs_expeca_metric_heatmap.png"
    )


def plot_sim_run_metric_heatmap(
    runs: list[str],
    sim_runs: dict[str, Path],
    run_configurations: dict[str, dict[str, object]],
    output_dir: Path,
) -> Path:
    records = []
    for run in runs:
        frame = filter_valid_delay_rows(pd.read_csv(sim_runs[run]), "sim")
        ran_delay = pd.to_numeric(frame[SIM_COLUMNS["ran_delay"]], errors="coerce")
        interval_ms = float(
            str(run_configurations[run]["delayInterval"]).removesuffix("ms")
        )
        records.append(
            {
                "Run": run,
                "Inter-pkt - mean RAN": interval_ms - ran_delay.mean(),
                "Pkts with HARQ retx": round(
                    100 * (frame[SIM_HARQ_RETRANSMISSIONS_COLUMN] > 0).mean(), 1
                ),
                "Pkts with RLC retx": round(
                    100 * (frame[SIM_RLC_RETRANSMISSIONS_COLUMN] > 0).mean(), 1
                ),
                "Initial segs >3": round(
                    100 * (frame[SIM_SEGMENTS_COLUMN] > 3).mean(), 1
                ),
                "Fresh backlog": round(
                    100
                    * pd.to_numeric(frame["backlog"], errors="coerce").mean(),
                    1,
                ),
                "Pkts RAN >25 ms": round(100 * (ran_delay > 25).mean(), 1),
                "Pkts RAN >50 ms": round(100 * (ran_delay > 50).mean(), 1),
            }
        )
    return plot_run_metric_heatmap(
        records, output_dir / "all_runs_sim_metric_heatmap.png"
    )


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
        "--cache-dir",
        type=Path,
        help=(
            "Directory for persistent raw-metric caches "
            "(default: OUTPUT_DIR/.raw_metric_cache)."
        ),
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="Recompute raw metrics even when a valid cache entry exists.",
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
    cache_dir = (
        args.cache_dir.resolve()
        if args.cache_dir is not None
        else output_dir / ".raw_metric_cache"
    )
    raw_metric_cache = RawMetricCache(cache_dir, rebuild=args.rebuild_cache)
    source_sim_runs = sim_runs.copy()
    source_expeca_runs = expeca_runs.copy()
    full_expeca_runs = expeca_runs.copy()
    balanced_csv_dir = TemporaryDirectory(prefix="balanced-delay-decomp-")
    balanced_root = Path(balanced_csv_dir.name)
    sim_runs = {
        run: remove_sim_startup_packet(run, sim_runs[run], balanced_root)
        for run in common_runs
    }
    full_sim_runs = sim_runs.copy()
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
    pooled_tb_values = {
        dataset: {metric: [] for metric, *_ in POOLED_ALLOCATION_METRICS}
        for dataset in ("sim", "expeca")
    }
    initial_tb_series: dict[str, dict[str, pd.DataFrame]] = {}
    sim_raw_metrics: dict[str, SimRawMetricBundle] = {}
    expeca_raw_metrics: dict[str, RawMetricBundle] = {}
    for run in common_runs:
        print(f"Processing {run}")
        cache_dependencies = [source_sim_runs[run], source_expeca_runs[run]]
        sim_raw_metrics[run] = raw_metric_cache.get_or_build(
            "sim",
            run,
            sim_raw_metric_dependencies(
                sim_raw_runs[run], *cache_dependencies
            ),
            lambda run=run: build_sim_raw_metric_bundle(
                sim_raw_runs[run], sim_runs[run]
            ),
        )
        expeca_raw_metrics[run] = raw_metric_cache.get_or_build(
            "expeca",
            run,
            expeca_raw_metric_dependencies(
                expeca_json_runs[run], *cache_dependencies
            ),
            lambda run=run: build_expeca_raw_metric_bundle(
                expeca_json_runs[run], expeca_runs[run]
            ),
        )
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
            load_sim_histogram_values(sim_runs[run]),
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
        sim_tb_metrics = sim_raw_metrics[run]["tb_metrics"]
        expeca_tb_metrics = expeca_raw_metrics[run]["tb_metrics"]
        for metric, *_ in POOLED_ALLOCATION_METRICS:
            pooled_tb_values["sim"][metric].append(sim_tb_metrics[metric])
            pooled_tb_values["expeca"][metric].append(expeca_tb_metrics[metric])
        output_path = plot_delay_probe_tb_histograms(
            run,
            sim_tb_metrics,
            expeca_tb_metrics,
            output_dir,
        )
        print(f"Wrote {output_path}")
        sim_initial_tbs = sim_raw_metrics[run]["initial_tb_series"]
        sim_rnti = sim_raw_metrics[run]["rnti"]
        expeca_initial_tbs = expeca_raw_metrics[run]["initial_tb_series"]
        expeca_rnti = expeca_raw_metrics[run]["rnti"]
        initial_tb_series[run] = {
            "sim": sim_initial_tbs,
            "expeca": expeca_initial_tbs,
        }
        output_path = plot_initial_tbler_mcs_time_series(
            run,
            sim_initial_tbs,
            sim_rnti,
            expeca_initial_tbs,
            expeca_rnti,
            output_dir,
        )
        print(f"Wrote {output_path}")

    for run_prefix in ("a", "c", "e"):
        class_runs = [run for run in common_runs if run.startswith(run_prefix)]
        if not class_runs:
            continue
        output_path = plot_initial_tbler_mcs_histograms(
            run_prefix,
            class_runs,
            initial_tb_series,
            output_dir,
        )
        print(f"Wrote {output_path}")

    pooled_tb_values = {
        dataset: {
            metric: np.concatenate(run_values)
            for metric, run_values in metrics.items()
        }
        for dataset, metrics in pooled_tb_values.items()
    }
    output_path = plot_pooled_allocation_histograms(
        pooled_tb_values["sim"], pooled_tb_values["expeca"], output_dir
    )
    print(f"Wrote {output_path}")

    output_path = plot_backlog_metric_bars(
        common_runs,
        sim_runs,
        expeca_runs,
        output_dir,
    )
    print(f"Wrote {output_path}")

    output_path = plot_filtered_delay_comparison(
        common_runs,
        sim_runs,
        expeca_runs,
        sim_raw_metrics,
        expeca_raw_metrics,
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
        quantile=0.95,
    )
    print(f"Wrote {output_path}")
    sim_no_harq_packet_keys = {
        run: sim_raw_metrics[run]["no_harq_packet_keys"]
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
    output_path = plot_sim_run_metric_heatmap(
        common_runs,
        sim_runs,
        run_configurations,
        output_dir,
    )
    print(f"Wrote {output_path}")
    balanced_csv_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
