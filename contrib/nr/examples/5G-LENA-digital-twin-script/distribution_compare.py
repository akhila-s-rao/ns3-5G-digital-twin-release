#!/usr/bin/env python3
import argparse
from pathlib import Path
import re

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

FONT_SIZE = 12
LABEL_FONT_SIZE = 14
ANNOTATION_FONT_SIZE = 16
TITLE_FONT_SIZE = LABEL_FONT_SIZE * 2
DRB_LCID_MIN = 3  # SRB0/1/2 are reserved; DRB/data LCIDs start at 3.
KNOWN_LOGS = [
    "delay_trace.txt",
    "NrUlRlcRxComponentStats.txt",
    "NrUlRlcTxComponentStats.txt",
    "RlcTxQueueSojournTrace.txt",
    "RlcHolGrantWaitTrace.txt",
]
EXPECA_CSV_REQUIRED_COLUMNS = {
    "End to End Delay",
    "Scheduling delay",
    "Transmission delay",
    "Retransmission delay",
    "Queuing delay",
    "Ran delay",
    "segmentation delay",
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

def load_tsv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, sep=r"\s+")

def filter_data_only(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Filter to data traffic when possible using msg_type or LCID."""
    if df is None:
        return df
    if "msg_type" in df.columns:
        df = df[df["msg_type"].astype(str).str.upper() == "DATA"]
    if "lcid" in df.columns:
        df = df[df["lcid"] >= DRB_LCID_MIN]
    return df


def require_columns(df: pd.DataFrame, label: str, required_cols: set[str]) -> pd.DataFrame:
    missing = sorted(required_cols.difference(df.columns))
    if missing:
        raise ValueError(f"{label} missing columns: {missing}")
    return df


def require_optional_columns(df: pd.DataFrame | None,
                             label: str,
                             required_cols: set[str]) -> pd.DataFrame | None:
    if df is None:
        return None
    return require_columns(df, label, required_cols)


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

def plot_timeseries(df, time_col, value_col, ax, label):
    if df is None or time_col not in df.columns or value_col not in df.columns:
        ax.set_visible(False)
        return
    series = df[[time_col, value_col]].dropna()
    if series.empty:
        ax.set_visible(False)
        return
    series = series.sort_values(time_col)
    vmin = float(series[value_col].min())
    vmed = float(series[value_col].median())
    vmax = float(series[value_col].max())
    ax.plot(series[time_col] / 1e6, series[value_col], linewidth=0.8)
    ax.set_xlabel("Time (s)", fontsize=LABEL_FONT_SIZE)
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

def has_required_logs(run_dir: Path) -> bool:
    """Return True if the directory contains any known log file."""
    return any((run_dir / name).exists() for name in KNOWN_LOGS)


def infer_unique_delay_probe_rnti(df_delay: pd.DataFrame | None, input_dir: Path) -> int | None:
    if df_delay is None:
        return None
    ul_delay = df_delay[df_delay["direction"] == "UL"].copy()
    if ul_delay.empty:
        return None
    # In delay-benchmarking.cc, background load (if enabled) is installed only on ueId == 1,
    # while delay probes are installed on all UEs. Exclude ue_id==1 when load_trace exists.
    if (input_dir / "load_trace.txt").exists() and "ue_id" in ul_delay.columns:
        ul_delay = ul_delay[ul_delay["ue_id"] != 1]
    candidate_rntis = sorted(int(r) for r in ul_delay["rnti"].dropna().unique().tolist())
    if len(candidate_rntis) == 1:
        return candidate_rntis[0]
    return None

def find_run_dirs(base_dir: Path) -> list[Path]:
    """Find run directories to plot."""
    if has_required_logs(base_dir):
        return [base_dir]
    runs: list[Path] = []
    for entry in sorted(base_dir.iterdir()):
        if entry.is_dir() and has_required_logs(entry):
            runs.append(entry)
    return runs


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


def extract_run_number(name: str) -> int | None:
    m = re.search(r"(?i)(?:benchmark|delaycal)[^0-9]*0*(\d+)", name)
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
        "Retransmission delay": "retransmission_delay_ms",
        "Transmission delay": "transmission_delay_ms",
        "End to End Delay": "ul_end_to_end_delay_ms",
        "Frame alignment delay": "frame_alignment_delay_ms",
        "Scheduling delay": "scheduling_delay_ms",
        "Ran delay": "link_delay_ms",
        "Queuing delay": "queueing_delay_ms",
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
    return df


def load_lena_compare_metrics(input_dir: Path) -> dict | None:
    if not has_required_logs(input_dir):
        print(f"WARN: skipping {input_dir}, no known log files found")
        return None

    df_delay = filter_data_only(load_tsv(input_dir / "delay_trace.txt"))
    df_ul_rlc = filter_data_only(load_tsv(input_dir / "NrUlRlcRxComponentStats.txt"))
    df_ul_rlc_tx = filter_data_only(load_tsv(input_dir / "NrUlRlcTxComponentStats.txt"))
    df_ul_pdcp_tx = filter_data_only(load_tsv(input_dir / "NrUlPdcpTxStats.txt"))
    df_rlc_sojourn = filter_data_only(load_tsv(input_dir / "RlcTxQueueSojournTrace.txt"))
    df_rlc_hol_wait = filter_data_only(load_tsv(input_dir / "RlcHolGrantWaitTrace.txt"))
    df_ue_phy_ctrl = load_tsv(input_dir / "UePhyCtrlTxTrace.txt")

    try:
        df_delay = require_optional_columns(
            df_delay, "delay_trace.txt", {"time_us", "rnti", "direction", "delay_us"}
        )
        df_ul_rlc = require_optional_columns(
            df_ul_rlc, "NrUlRlcRxComponentStats.txt", {"time_us", "rnti", "pkt_id", "delay_us"}
        )
        df_ul_rlc_tx = require_optional_columns(
            df_ul_rlc_tx, "NrUlRlcTxComponentStats.txt", {"time_us", "rnti", "pkt_id", "rlc_sn"}
        )
        df_ul_pdcp_tx = require_optional_columns(
            df_ul_pdcp_tx, "NrUlPdcpTxStats.txt", {"time_us", "rnti", "pkt_id"}
        )
        df_rlc_sojourn = require_optional_columns(
            df_rlc_sojourn, "RlcTxQueueSojournTrace.txt", {"time_us", "rnti", "pkt_id", "pre_hol_wait_us"}
        )
        df_rlc_hol_wait = require_optional_columns(
            df_rlc_hol_wait, "RlcHolGrantWaitTrace.txt", {"time_us", "rnti", "pkt_id", "hol_grant_wait_us"}
        )
        df_ue_phy_ctrl = require_optional_columns(
            df_ue_phy_ctrl, "UePhyCtrlTxTrace.txt", {"time_us", "rnti", "msg_type"}
        )
    except ValueError as exc:
        print(f"WARN: skipping {input_dir}, {exc}")
        return None

    if df_delay is not None:
        df_delay["direction"] = df_delay["direction"].astype(str).str.upper()
        df_delay["delay_ms"] = df_delay["delay_us"] / 1000.0

    delay_probe_rnti_hint = infer_unique_delay_probe_rnti(df_delay, input_dir)

    df_ul_rlc_plot = df_ul_rlc
    if df_ul_rlc is not None:
        df_ul_rlc["delay_ms"] = df_ul_rlc["delay_us"] / 1000.0
        df_ul_rlc_non_null = df_ul_rlc.dropna(subset=["delay_ms"])
        if not df_ul_rlc_non_null.empty:
            idx = df_ul_rlc_non_null.groupby(["rnti", "pkt_id"])["delay_ms"].idxmax()
            df_ul_rlc_plot = df_ul_rlc_non_null.loc[idx].sort_values("time_us")

    if df_rlc_sojourn is not None:
        df_rlc_sojourn["pre_hol_wait_ms"] = df_rlc_sojourn["pre_hol_wait_us"] / 1000.0

    if df_rlc_hol_wait is not None:
        df_rlc_hol_wait["hol_wait_ms"] = df_rlc_hol_wait["hol_grant_wait_us"] / 1000.0
        df_rlc_hol_wait = (
            df_rlc_hol_wait.sort_values("time_us")
            .drop_duplicates(subset=["rnti", "pkt_id"], keep="first")
        )

    df_sr = None
    if df_ue_phy_ctrl is not None:
        df_sr = df_ue_phy_ctrl[df_ue_phy_ctrl["msg_type"].astype(str).str.upper() == "SR"][["time_us", "rnti"]].copy()
    if df_sr is not None:
        for col in ["time_us", "rnti"]:
            df_sr[col] = pd.to_numeric(df_sr[col], errors="coerce")
        df_sr = df_sr.dropna(subset=["time_us", "rnti"]).sort_values(["time_us", "rnti"])

    df_pregrant_grant_wait = None
    if df_rlc_sojourn is not None and df_rlc_hol_wait is not None:
        soj = (
            df_rlc_sojourn.copy()
            .sort_values("time_us")
            .drop_duplicates(subset=["rnti", "pkt_id"], keep="first")
            [["rnti", "pkt_id", "pre_hol_wait_ms", "time_us"]]
            .rename(columns={"time_us": "soj_time_us"})
        )
        hol = (
            df_rlc_hol_wait.copy()
            .sort_values("time_us")
            .drop_duplicates(subset=["rnti", "pkt_id"], keep="first")
            [["rnti", "pkt_id", "hol_wait_ms", "time_us"]]
            .rename(columns={"time_us": "hol_time_us"})
        )
        df_pregrant_grant_wait = pd.merge(soj, hol, on=["rnti", "pkt_id"], how="inner")
        if not df_pregrant_grant_wait.empty:
            df_pregrant_grant_wait["pregrant_plus_grant_wait_ms"] = (
                df_pregrant_grant_wait["pre_hol_wait_ms"] + df_pregrant_grant_wait["hol_wait_ms"]
            )
            df_pregrant_grant_wait["time_us"] = df_pregrant_grant_wait["hol_time_us"]
            df_pregrant_grant_wait = df_pregrant_grant_wait.sort_values("time_us")

    df_link_delay = None
    if df_rlc_hol_wait is not None and df_ul_rlc is not None:
        grant = df_rlc_hol_wait[["rnti", "pkt_id", "time_us"]].copy()
        rlc_rx = df_ul_rlc[["rnti", "pkt_id", "time_us"]].copy()
        for col in ["rnti", "pkt_id", "time_us"]:
            grant[col] = pd.to_numeric(grant[col], errors="coerce")
            rlc_rx[col] = pd.to_numeric(rlc_rx[col], errors="coerce")
        grant = grant.dropna(subset=["rnti", "pkt_id", "time_us"])
        rlc_rx = rlc_rx.dropna(subset=["rnti", "pkt_id", "time_us"])
        grant = grant[grant["pkt_id"] != 0]
        rlc_rx = rlc_rx[rlc_rx["pkt_id"] != 0]
        grant = (
            grant.sort_values("time_us")
            .drop_duplicates(subset=["rnti", "pkt_id"], keep="first")
            .rename(columns={"time_us": "first_grant_time_us"})
        )
        rlc_rx = (
            rlc_rx.sort_values("time_us")
            .groupby(["rnti", "pkt_id"], as_index=False)["time_us"]
            .max()
            .rename(columns={"time_us": "last_rlc_rx_time_us"})
        )
        df_link_delay = pd.merge(grant, rlc_rx, on=["rnti", "pkt_id"], how="inner")
        if not df_link_delay.empty:
            df_link_delay["link_delay_us"] = (
                df_link_delay["last_rlc_rx_time_us"] - df_link_delay["first_grant_time_us"]
            )
            df_link_delay = df_link_delay[df_link_delay["link_delay_us"] >= 0]
            if not df_link_delay.empty:
                df_link_delay["link_delay_ms"] = df_link_delay["link_delay_us"] / 1000.0
                df_link_delay["time_us"] = df_link_delay["last_rlc_rx_time_us"]
                df_link_delay = df_link_delay.sort_values("time_us")

    df_segmentation_delay = None
    if df_link_delay is not None and df_ul_rlc_plot is not None:
        link = df_link_delay[["rnti", "pkt_id", "link_delay_ms", "time_us"]].rename(
            columns={"time_us": "link_time_us"}
        )
        txretx = df_ul_rlc_plot[["rnti", "pkt_id", "delay_ms", "time_us"]].rename(
            columns={"delay_ms": "tx_retx_delay_ms", "time_us": "txretx_time_us"}
        )
        df_segmentation_delay = pd.merge(link, txretx, on=["rnti", "pkt_id"], how="inner")
        if not df_segmentation_delay.empty:
            df_segmentation_delay["segmentation_delay_ms"] = (
                df_segmentation_delay["link_delay_ms"] - df_segmentation_delay["tx_retx_delay_ms"]
            )
            df_segmentation_delay["time_us"] = df_segmentation_delay["link_time_us"]
            df_segmentation_delay = df_segmentation_delay.sort_values("time_us")

    df_rlc_segments_per_pkt = None
    if df_ul_rlc_tx is not None:
        tx_comp = df_ul_rlc_tx[["time_us", "rnti", "pkt_id", "rlc_sn"]].copy()
        for col in ["time_us", "rnti", "pkt_id", "rlc_sn"]:
            tx_comp[col] = pd.to_numeric(tx_comp[col], errors="coerce")
        tx_comp = tx_comp.dropna(subset=["time_us", "rnti", "pkt_id", "rlc_sn"])
        tx_comp = tx_comp[tx_comp["pkt_id"] != 0]
        if not tx_comp.empty:
            tx_comp = tx_comp.sort_values("time_us")
            first_tx = (
                tx_comp.groupby(["rnti", "pkt_id"], as_index=False)["time_us"]
                .min()
                .rename(columns={"time_us": "first_tx_time_us"})
            )
            seg_count = (
                tx_comp.groupby(["rnti", "pkt_id"], as_index=False)["rlc_sn"]
                .nunique()
                .rename(columns={"rlc_sn": "rlc_segments_per_pkt"})
            )
            df_rlc_segments_per_pkt = pd.merge(first_tx, seg_count, on=["rnti", "pkt_id"], how="inner")
            if not df_rlc_segments_per_pkt.empty:
                df_rlc_segments_per_pkt["time_us"] = df_rlc_segments_per_pkt["first_tx_time_us"]
                df_rlc_segments_per_pkt = df_rlc_segments_per_pkt.sort_values("time_us")

    df_sched_delay2 = None
    if df_sr is not None and df_rlc_segments_per_pkt is not None:
        sr = df_sr.copy().sort_values(["time_us", "rnti"])
        first_pkt_tx = df_rlc_segments_per_pkt[["time_us", "rnti", "pkt_id"]].copy()
        first_pkt_tx = first_pkt_tx.rename(columns={"time_us": "first_pkt_tx_time_us"})
        for col in ["first_pkt_tx_time_us", "rnti", "pkt_id"]:
            first_pkt_tx[col] = pd.to_numeric(first_pkt_tx[col], errors="coerce")
        first_pkt_tx = first_pkt_tx.dropna(subset=["first_pkt_tx_time_us", "rnti", "pkt_id"])
        first_pkt_tx = first_pkt_tx.sort_values(["first_pkt_tx_time_us", "rnti"]).copy()
        if not first_pkt_tx.empty:
            first_pkt_tx["prev_first_pkt_tx_time_us"] = (
                first_pkt_tx.groupby("rnti")["first_pkt_tx_time_us"].shift(1)
            )
            df_sched_delay2 = pd.merge_asof(
                first_pkt_tx,
                sr.rename(columns={"time_us": "sr_time_us"}).sort_values(["sr_time_us", "rnti"]),
                left_on="first_pkt_tx_time_us",
                right_on="sr_time_us",
                by="rnti",
                direction="backward",
            ).dropna(subset=["sr_time_us"])
            if not df_sched_delay2.empty:
                # Keep only first-packet transmissions that have a fresh SR since the previous
                # first-packet transmission of the same UE.
                df_sched_delay2 = df_sched_delay2[
                    df_sched_delay2["prev_first_pkt_tx_time_us"].isna() |
                    (df_sched_delay2["sr_time_us"] > df_sched_delay2["prev_first_pkt_tx_time_us"])
                ]
                df_sched_delay2["sched_delay2_us"] = (
                    df_sched_delay2["first_pkt_tx_time_us"] - df_sched_delay2["sr_time_us"]
                )
                df_sched_delay2 = df_sched_delay2[df_sched_delay2["sched_delay2_us"] >= 0]
                if not df_sched_delay2.empty:
                    df_sched_delay2["sched_delay2_ms"] = (
                        df_sched_delay2["sched_delay2_us"] / 1000.0
                    )
                    df_sched_delay2["time_us"] = df_sched_delay2["first_pkt_tx_time_us"]
                    df_sched_delay2 = df_sched_delay2.sort_values("time_us")

    df_frame_alignment = None
    if df_sr is not None and df_ul_pdcp_tx is not None:
        sr = df_sr.copy()
        pdcp_tx = df_ul_pdcp_tx[["time_us", "rnti"]].rename(columns={"time_us": "pdcp_tx_time_us"}).copy()
        sr = sr.sort_values(["time_us", "rnti"]).copy()
        sr["prev_sr_time_us"] = sr.groupby("rnti")["time_us"].shift(1)
        for col in ["pdcp_tx_time_us", "rnti"]:
            pdcp_tx[col] = pd.to_numeric(pdcp_tx[col], errors="coerce")
        pdcp_tx = pdcp_tx.dropna(subset=["pdcp_tx_time_us", "rnti"]).sort_values(["pdcp_tx_time_us", "rnti"])
        if not sr.empty and not pdcp_tx.empty:
            df_frame_alignment = pd.merge_asof(
                sr,
                pdcp_tx,
                left_on="time_us",
                right_on="pdcp_tx_time_us",
                by="rnti",
                direction="backward",
            ).dropna(subset=["pdcp_tx_time_us"])
            # Keep only PDCP arrivals that happened since the previous SR of the same UE.
            # This avoids reusing an old PDCP timestamp for repeated SRs.
            df_frame_alignment = df_frame_alignment[
                df_frame_alignment["prev_sr_time_us"].isna() |
                (df_frame_alignment["pdcp_tx_time_us"] > df_frame_alignment["prev_sr_time_us"])
            ]
            df_frame_alignment["frame_alignment_delay_us"] = (
                df_frame_alignment["time_us"] - df_frame_alignment["pdcp_tx_time_us"]
            )
            df_frame_alignment = df_frame_alignment[df_frame_alignment["frame_alignment_delay_us"] >= 0]
            df_frame_alignment["frame_alignment_delay_ms"] = (
                df_frame_alignment["frame_alignment_delay_us"] / 1000.0
            )
            df_frame_alignment = df_frame_alignment.sort_values("time_us")

    # Reordering delay can be re-enabled later if needed.
    # It was intentionally commented out instead of being controlled by a CLI flag.
    #
    # df_ul_pdcp_rx = filter_data_only(load_tsv(input_dir / "NrUlPdcpRxStats.txt"))
    # df_ul_pdcp_rx = require_optional_columns(
    #     df_ul_pdcp_rx, "NrUlPdcpRxStats.txt", {"time_us", "rnti", "pkt_id"}
    # )
    # df_reordering_delay = None
    # if df_ul_rlc is not None and df_ul_pdcp_rx is not None:
    #     rlc_rx = df_ul_rlc[["rnti", "pkt_id", "time_us"]].copy()
    #     pdcp_rx = df_ul_pdcp_rx[["rnti", "pkt_id", "time_us"]].copy()
    #     for col in ["rnti", "pkt_id", "time_us"]:
    #         rlc_rx[col] = pd.to_numeric(rlc_rx[col], errors="coerce")
    #         pdcp_rx[col] = pd.to_numeric(pdcp_rx[col], errors="coerce")
    #     rlc_rx = rlc_rx.dropna(subset=["rnti", "pkt_id", "time_us"])
    #     pdcp_rx = pdcp_rx.dropna(subset=["rnti", "pkt_id", "time_us"])
    #     rlc_rx = rlc_rx[rlc_rx["pkt_id"] != 0]
    #     pdcp_rx = pdcp_rx[pdcp_rx["pkt_id"] != 0]
    #     if not rlc_rx.empty and not pdcp_rx.empty:
    #         rlc_last = (
    #             rlc_rx.sort_values("time_us")
    #             .groupby(["rnti", "pkt_id"], as_index=False)["time_us"]
    #             .max()
    #             .rename(columns={"time_us": "last_rlc_rx_time_us"})
    #         )
    #         pdcp_first = (
    #             pdcp_rx.sort_values("time_us")
    #             .groupby(["rnti", "pkt_id"], as_index=False)["time_us"]
    #             .min()
    #             .rename(columns={"time_us": "pdcp_rx_time_us"})
    #         )
    #         df_reordering_delay = pd.merge(rlc_last, pdcp_first, on=["rnti", "pkt_id"], how="inner")
    #         if not df_reordering_delay.empty:
    #             df_reordering_delay["reordering_delay_us"] = (
    #                 df_reordering_delay["pdcp_rx_time_us"] - df_reordering_delay["last_rlc_rx_time_us"]
    #             )
    #             df_reordering_delay = df_reordering_delay[df_reordering_delay["reordering_delay_us"] >= 0]
    #             if not df_reordering_delay.empty:
    #                 df_reordering_delay["reordering_delay_ms"] = (
    #                     df_reordering_delay["reordering_delay_us"] / 1000.0
    #                 )
    #                 df_reordering_delay["time_us"] = df_reordering_delay["pdcp_rx_time_us"]
    #                 df_reordering_delay = df_reordering_delay.sort_values("time_us")

    rntis = set()
    for df in [df_delay, df_ul_rlc, df_ul_rlc_tx, df_ul_pdcp_tx, df_rlc_sojourn, df_rlc_hol_wait]:
        if df is not None:
            rntis.update(df["rnti"].dropna().unique().tolist())
    rntis = sorted(int(r) for r in rntis)
    if not rntis:
        print(f"WARN: no RNTIs found in {input_dir}")
        return None

    selected_rnti = delay_probe_rnti_hint
    if selected_rnti is None and df_delay is not None:
        ul_delay = df_delay[df_delay["direction"] == "UL"].copy()
        if not ul_delay.empty:
            candidate_rntis = sorted(int(r) for r in ul_delay["rnti"].dropna().unique().tolist())
            if len(candidate_rntis) > 1:
                print(f"WARN: multiple delay-probe-only RNTIs in {input_dir}: {candidate_rntis}; skipping run")
                return None

    if selected_rnti is None:
        print(f"WARN: could not isolate a unique delay-probe-only RNTI in {input_dir}; skipping run")
        return None

    metric_items = [
        (df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == selected_rnti)]["delay_ms"]
         if df_delay is not None else empty_series(),
         "UL end-to-end delay (ms)"),
        (df_pregrant_grant_wait[df_pregrant_grant_wait["rnti"] == selected_rnti]["pregrant_plus_grant_wait_ms"]
         if df_pregrant_grant_wait is not None else empty_series(),
         "Queueing delay (ms)"),
        (df_frame_alignment[df_frame_alignment["rnti"] == selected_rnti]["frame_alignment_delay_ms"]
         if df_frame_alignment is not None else empty_series(),
         "Frame alignment delay (ms)"),
        (df_sched_delay2[df_sched_delay2["rnti"] == selected_rnti]["sched_delay2_ms"]
         if df_sched_delay2 is not None else empty_series(),
         "Scheduling delay (ms)"),
        # Re-enable this if HOL grant wait delay should be plotted again.
        # (df_rlc_hol_wait[df_rlc_hol_wait["rnti"] == selected_rnti]["hol_wait_ms"]
        #  if df_rlc_hol_wait is not None else empty_series(),
        #  "HOL grant wait delay (ms)"),
        (df_ul_rlc_plot[df_ul_rlc_plot["rnti"] == selected_rnti]["delay_ms"]
         if df_ul_rlc_plot is not None else empty_series(),
         "tx + retx delay (ms)"),
    ]
    ts_items = [
        (df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == selected_rnti)]
         if df_delay is not None else None,
         "time_us", "delay_ms", "UL end-to-end delay (ms)"),
        (df_pregrant_grant_wait[df_pregrant_grant_wait["rnti"] == selected_rnti]
         if df_pregrant_grant_wait is not None else None,
         "time_us", "pregrant_plus_grant_wait_ms", "Queueing delay (ms)"),
        (df_frame_alignment[df_frame_alignment["rnti"] == selected_rnti]
         if df_frame_alignment is not None else None,
         "time_us", "frame_alignment_delay_ms", "Frame alignment delay (ms)"),
        (df_sched_delay2[df_sched_delay2["rnti"] == selected_rnti]
         if df_sched_delay2 is not None else None,
         "time_us", "sched_delay2_ms", "Scheduling delay (ms)"),
        # Re-enable this if HOL grant wait delay should be plotted again.
        # (df_rlc_hol_wait[df_rlc_hol_wait["rnti"] == selected_rnti]
        #  if df_rlc_hol_wait is not None else None,
        #  "time_us", "hol_wait_ms", "HOL grant wait delay (ms)"),
        (df_ul_rlc_plot[df_ul_rlc_plot["rnti"] == selected_rnti]
         if df_ul_rlc_plot is not None else None,
         "time_us", "delay_ms", "tx + retx delay (ms)"),
    ]
    # Re-enable these if reordering delay should be plotted again.
    # metric_items.append(
    #     (df_reordering_delay[df_reordering_delay["rnti"] == selected_rnti]["reordering_delay_ms"]
    #      if df_reordering_delay is not None else empty_series(),
    #      "Reordering delay (ms)")
    # )
    # ts_items.append(
    #     (df_reordering_delay[df_reordering_delay["rnti"] == selected_rnti]
    #      if df_reordering_delay is not None else None,
    #      "time_us", "reordering_delay_ms", "Reordering delay (ms)")
    # )
    metric_items.extend([
        (df_segmentation_delay[df_segmentation_delay["rnti"] == selected_rnti]["segmentation_delay_ms"]
         if df_segmentation_delay is not None else empty_series(),
         "Segmentation delay (ms)"),
        (df_rlc_segments_per_pkt[df_rlc_segments_per_pkt["rnti"] == selected_rnti]["rlc_segments_per_pkt"]
         if df_rlc_segments_per_pkt is not None else empty_series(),
         "RLC segments per packet"),
    ])
    ts_items.extend([
        (df_segmentation_delay[df_segmentation_delay["rnti"] == selected_rnti]
         if df_segmentation_delay is not None else None,
         "time_us", "segmentation_delay_ms", "Segmentation delay (ms)"),
        (df_rlc_segments_per_pkt[df_rlc_segments_per_pkt["rnti"] == selected_rnti]
         if df_rlc_segments_per_pkt is not None else None,
         "time_us", "rlc_segments_per_pkt", "RLC segments per packet"),
    ])
    return {
        "rnti": selected_rnti,
        "metric_items": metric_items,
        "ts_items": ts_items,
    }


def build_expeca_compare_metric_items(df: pd.DataFrame) -> list[tuple[pd.Series, str]]:
    items = [
        (df["ul_end_to_end_delay_ms"], "UL end-to-end delay (ms)"),
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
        (df["segmentation_delay_ms"], "Segmentation delay (ms)"),
        (df["rlc_attempts"], "RLC segments per packet"),
    ])
    return items


def plot_compare_pair(run_no: int,
                      expeca_csv: Path,
                      lena_run_dir: Path,
                      output_root: Path) -> None:
    expeca_df = load_expeca_csv_metrics(expeca_csv)
    if expeca_df is None or expeca_df.empty:
        print(f"WARN: skipping run{run_no:02d}, unusable ExPeCA CSV: {expeca_csv}")
        return
    lena = load_lena_compare_metrics(lena_run_dir)
    if lena is None:
        print(f"WARN: skipping run{run_no:02d}, unusable 5G-LENA logs: {lena_run_dir}")
        return

    output_root.mkdir(parents=True, exist_ok=True)
    expeca_items = build_expeca_compare_metric_items(expeca_df)
    lena_items = lena["metric_items"]
    lena_ts_items = lena["ts_items"]

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
    for col, ((ex_series, ex_label), (lena_df, time_col, value_col, lena_label)) in enumerate(zip(expeca_items, lena_ts_items)):
        plot_series_by_index(ex_series, axes[0, col], ex_label)
        plot_timeseries(lena_df, time_col, value_col, axes[1, col], lena_label)
    fig.text(0.01, 0.74, "ExPeCA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.text(0.01, 0.28, "5G-LENA", rotation=90, va="center", ha="left", fontsize=LABEL_FONT_SIZE)
    fig.suptitle(f"{compare_label} | Series", fontsize=TITLE_FONT_SIZE, y=0.995)
    fig.tight_layout(rect=[0.03, 0, 1, 0.95])
    fig.savefig(output_root / f"{run_label}_series.png", dpi=150)
    plt.close(fig)

    print(f"Wrote comparison plots for {run_label} to {output_root}")

def main():
    parser = argparse.ArgumentParser(
        description="Plot histograms from ExPeCA and 5G-LENA log roots"
    )
    parser.add_argument(
        "--expeca-dir",
        required=True,
        help="Directory containing ExPeCA run folder(s) or ExPeCA delayCal*.csv files.",
    )
    parser.add_argument(
        "--lena-dir",
        required=True,
        help="Directory containing 5G-LENA run folder(s) or log files.",
    )
    args = parser.parse_args()

    expeca_dir = Path(args.expeca_dir).resolve()
    lena_dir = Path(args.lena_dir).resolve()
    plt.rcParams.update({"font.size": FONT_SIZE})
    csv_runs = find_expeca_csv_runs(expeca_dir)
    lena_runs = find_run_dirs(lena_dir)
    if not csv_runs:
        print(f"WARN: no ExPeCA CSV runs found under {expeca_dir}")
        return 0
    if not lena_runs:
        print(f"WARN: no 5G-LENA run directories found under {lena_dir}")
        return 0

    expeca_by_run = index_paths_by_run_number(csv_runs, "ExPeCA CSV")
    lena_by_run = index_paths_by_run_number(lena_runs, "5G-LENA run")
    common_runs = sorted(set(expeca_by_run).intersection(lena_by_run))

    missing_expeca = sorted(set(lena_by_run).difference(expeca_by_run))
    missing_lena = sorted(set(expeca_by_run).difference(lena_by_run))
    if missing_expeca:
        print(f"WARN: missing ExPeCA CSV for runs: {missing_expeca}")
    if missing_lena:
        print(f"WARN: missing 5G-LENA logs for runs: {missing_lena}")
    if not common_runs:
        print("WARN: no common run numbers found between ExPeCA and 5G-LENA inputs")
        return 0

    output_root = (
        Path(__file__).resolve().parent
        / "sim_campaign_logs"
        / "compare_expeca_5Glena_logs"
    )
    print(f"Writing comparison plots under: {output_root}")
    for run_no in common_runs:
        if run_no == 13:
            print("WARN: skipping run13 by request")
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
