#!/usr/bin/env python3
import argparse
import math
from pathlib import Path
import sys

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

FONT_SIZE = 12
LABEL_FONT_SIZE = 14
ANNOTATION_FONT_SIZE = 16
TITLE_FONT_SIZE = LABEL_FONT_SIZE * 2
TITLE_PAD = 10
DRB_LCID_MIN = 3  # SRB0/1/2 are reserved; DRB/data LCIDs start at 3.
KNOWN_LOGS = [
    "UlRxTbTrace.txt",
    "delay_trace.txt",
    "vrFragment_trace.txt",
    "load_trace.txt",
    "NrUlRlcRxStats.txt",
    "NrUlPdcpRxStats.txt",
    "RlcHolDelayTrace.txt",
    "mobility_trace.txt",
    "NrUlMacStats.txt",
    "RlcTxQueueSojournTrace.txt",
    "RlcHolGrantWaitTrace.txt",
    "GnbBsrTrace.txt",
]

def empty_series() -> pd.Series:
    return pd.Series(dtype=float)

def load_tsv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, sep=r"\s+")

def filter_data_bearers(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or "lcid" not in df.columns:
        return df
    return df[df["lcid"] >= DRB_LCID_MIN]

def filter_data_only(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Filter to data traffic when possible using msg_type or LCID."""
    if df is None:
        return df
    if "msg_type" in df.columns:
        df = df[df["msg_type"].astype(str).str.upper() == "DATA"]
    if "lcid" in df.columns:
        df = df[df["lcid"] >= DRB_LCID_MIN]
    return df

def format_annotation_value(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"

def plot_hist(values, bins, xlabel, ax, ylabel=None, title=None):
    values = values.dropna()
    if values.shape[0] == 0:
        ax.set_visible(False)
        return
    vmin = float(values.min())
    vmax = float(values.max())
    ax.hist(values, bins=bins, edgecolor="black", alpha=0.85, density=True)
    ax.set_xlabel(xlabel, fontsize=LABEL_FONT_SIZE)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=LABEL_FONT_SIZE)
    else:
        ax.set_ylabel("")
    if title:
        ax.set_title(title)
    ax.text(
        0.98, 0.98, f"min: {format_annotation_value(vmin)}\nmax: {format_annotation_value(vmax)}",
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
    vmax = float(values.max())
    values = np.sort(values.to_numpy())
    y = np.linspace(0.0, 1.0, num=values.size, endpoint=True)
    ax.plot(values, y, linewidth=0.9)
    ax.set_xlabel(xlabel, fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel(ylabel, fontsize=LABEL_FONT_SIZE)
    ax.text(
        0.98, 0.98, f"min: {format_annotation_value(vmin)}\nmax: {format_annotation_value(vmax)}",
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
    vmax = float(series[value_col].max())
    ax.plot(series[time_col] / 1e6, series[value_col], linewidth=0.8)
    ax.set_xlabel("Time (s)", fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel(label, fontsize=LABEL_FONT_SIZE)
    ax.text(
        0.98, 0.98, f"min: {format_annotation_value(vmin)}\nmax: {format_annotation_value(vmax)}",
        ha="right", va="top", transform=ax.transAxes,
        fontsize=ANNOTATION_FONT_SIZE,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, edgecolor="none"),
    )

def plot_ul_delay_windowed(df_delay: pd.DataFrame | None, rnti: int, output_dir: Path,
                           run_label: str) -> None:
    if df_delay is None:
        return
    df = df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == rnti)]
    if df.empty:
        return
    series = df[["time_us", "delay_ms"]].dropna()
    if series.empty:
        return
    series = series.sort_values("time_us")
    series["time_td"] = pd.to_timedelta(series["time_us"], unit="us")
    windowed = series.set_index("time_td")["delay_ms"].resample("1s").mean()
    if windowed.empty:
        return
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(windowed.index.total_seconds(), windowed.values, linewidth=1.0)
    ax.set_xlabel("Time (s)", fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel("UL probe delay (ms)", fontsize=LABEL_FONT_SIZE)
    ax.set_title(
        f"{run_label} | Timeseries | UL probe delay (1s mean)",
        fontsize=TITLE_FONT_SIZE,
        pad=TITLE_PAD,
    )
    fig.tight_layout()
    fig.savefig(output_dir / f"rnti_{rnti}_ul_delay_1s.png", dpi=150)
    plt.close(fig)

def compute_ul_probe_drop_rate(df_delay: pd.DataFrame | None, rnti: int) -> float:
    if df_delay is None:
        return float("nan")
    df = df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == rnti)]
    if df.empty or "seq_num" not in df.columns:
        return float("nan")
    seq = df["seq_num"].dropna()
    if seq.empty:
        return float("nan")
    unique_seq = pd.Series(seq.unique()).astype(int)
    min_seq = int(unique_seq.min())
    max_seq = int(unique_seq.max())
    expected = max_seq - min_seq + 1
    if expected <= 0:
        return float("nan")
    received = unique_seq.shape[0]
    return 1.0 - (received / expected)

def compute_prbs_per_ms(df_ul_mac: pd.DataFrame | None, rnti: int) -> float:
    if df_ul_mac is None or "num_prbs" not in df_ul_mac.columns or "time_us" not in df_ul_mac.columns:
        return float("nan")
    df = df_ul_mac[df_ul_mac["rnti"] == rnti][["time_us", "num_prbs"]].dropna()
    if df.empty:
        return float("nan")
    total_prbs = float(df["num_prbs"].sum())
    time_span_us = float(df["time_us"].max() - df["time_us"].min())
    if time_span_us <= 0:
        return float("nan")
    return total_prbs / (time_span_us / 1000.0)

def compute_load_throughput(df_load: pd.DataFrame | None) -> dict[str, float]:
    if df_load is None or df_load.empty:
        return {}
    if "time_us" not in df_load.columns or "packet_size" not in df_load.columns or "proto" not in df_load.columns:
        return {}
    df = df_load.copy()
    df["proto"] = df["proto"].astype(str).str.lower()
    df["packet_size"] = pd.to_numeric(df["packet_size"], errors="coerce")
    df["time_us"] = pd.to_numeric(df["time_us"], errors="coerce")
    df = df.dropna(subset=["proto", "packet_size", "time_us"])
    if df.empty:
        return {}
    throughput: dict[str, float] = {}
    for proto, group in df.groupby("proto"):
        time_span_us = float(group["time_us"].max() - group["time_us"].min())
        if time_span_us <= 0:
            continue
        total_bits = float(group["packet_size"].sum()) * 8.0
        throughput[proto] = total_bits / (time_span_us / 1e6) / 1e6
    return throughput

def compute_ul_pdcp_throughput_by_rnti(df_ul_pdcp: pd.DataFrame | None) -> dict[int, float]:
    if df_ul_pdcp is None or df_ul_pdcp.empty:
        return {}
    required_cols = {"time_us", "rnti", "packet_size"}
    if not required_cols.issubset(df_ul_pdcp.columns):
        return {}
    df = df_ul_pdcp.copy()
    df["time_us"] = pd.to_numeric(df["time_us"], errors="coerce")
    df["rnti"] = pd.to_numeric(df["rnti"], errors="coerce")
    df["packet_size"] = pd.to_numeric(df["packet_size"], errors="coerce")
    df = df.dropna(subset=["time_us", "rnti", "packet_size"])
    if df.empty:
        return {}

    throughput: dict[int, float] = {}
    for rnti, group in df.groupby("rnti"):
        time_span_us = float(group["time_us"].max() - group["time_us"].min())
        if time_span_us <= 0:
            continue
        total_bits = float(group["packet_size"].sum()) * 8.0
        throughput[int(rnti)] = total_bits / (time_span_us / 1e6) / 1e6
    return throughput

def compute_rlc_pdus_per_ip(df_ul_rlc: pd.DataFrame | None, rnti: int) -> pd.Series:
    if df_ul_rlc is None or "pkt_id" not in df_ul_rlc.columns:
        return empty_series()
    df = df_ul_rlc[df_ul_rlc["rnti"] == rnti]
    if df.empty:
        return empty_series()
    counts = df.groupby("pkt_id").size()
    if counts.empty:
        return empty_series()
    return counts.astype(float)

def compute_rlc_pdus_per_ip_ts(df_ul_rlc: pd.DataFrame | None, rnti: int) -> pd.DataFrame | None:
    if df_ul_rlc is None or "pkt_id" not in df_ul_rlc.columns or "time_us" not in df_ul_rlc.columns:
        return None
    df = df_ul_rlc[df_ul_rlc["rnti"] == rnti]
    if df.empty:
        return None
    grouped = (
        df.groupby("pkt_id")
        .agg(time_us=("time_us", "min"), rlc_pdus_per_ip=("pkt_id", "size"))
        .reset_index(drop=True)
    )
    if grouped.empty:
        return None
    return grouped

def has_required_logs(run_dir: Path) -> bool:
    """Return True if the directory contains any known log file."""
    return any((run_dir / name).exists() for name in KNOWN_LOGS)

def find_run_dirs(base_dir: Path) -> list[Path]:
    """Find run directories to plot."""
    if has_required_logs(base_dir):
        return [base_dir]
    runs: list[Path] = []
    for entry in sorted(base_dir.iterdir()):
        if entry.is_dir() and has_required_logs(entry):
            runs.append(entry)
    return runs

def plot_run(input_dir: Path, output_dir: Path) -> None:
    """Plot histograms for a single run directory."""
    if not has_required_logs(input_dir):
        print(f"WARN: skipping {input_dir}, no known log files found")
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_results_path = output_dir / "analysis_results.txt"
    analysis_results = analysis_results_path.open("w", encoding="utf-8")

    def emit(msg: str) -> None:
        print(msg)
        analysis_results.write(f"{msg}\n")

    emit(f"Processing run: {input_dir}")

    df_ul_tb = load_tsv(input_dir / "UlRxTbTrace.txt")
    df_delay = load_tsv(input_dir / "delay_trace.txt")
    df_vr_frag = load_tsv(input_dir / "vrFragment_trace.txt")
    df_load = load_tsv(input_dir / "load_trace.txt")
    df_gnb_bsr = load_tsv(input_dir / "GnbBsrTrace.txt")
    df_ul_tb = filter_data_only(df_ul_tb)
    df_delay = filter_data_only(df_delay)
    df_vr_frag = filter_data_only(df_vr_frag)
    df_gnb_bsr = filter_data_only(df_gnb_bsr)

    if df_delay is not None:
        df_delay["direction"] = df_delay["direction"].astype(str).str.upper()
        df_delay["delay_ms"] = df_delay["delay_us"] / 1000.0
    if df_vr_frag is not None:
        df_vr_frag["delay_ms"] = df_vr_frag["delay_us"] / 1000.0

    df_ul_rlc = load_tsv(input_dir / "NrUlRlcRxStats.txt")
    df_ul_pdcp = load_tsv(input_dir / "NrUlPdcpRxStats.txt")
    df_hol = load_tsv(input_dir / "RlcHolDelayTrace.txt")
    df_rlc_sojourn = load_tsv(input_dir / "RlcTxQueueSojournTrace.txt")
    df_rlc_hol_wait = load_tsv(input_dir / "RlcHolGrantWaitTrace.txt")
    df_mobility = load_tsv(input_dir / "mobility_trace.txt")
    df_ul_mac = load_tsv(input_dir / "NrUlMacStats.txt")

    df_ul_rlc = filter_data_only(df_ul_rlc)
    df_ul_pdcp = filter_data_only(df_ul_pdcp)
    df_hol = filter_data_only(df_hol)
    df_rlc_sojourn = filter_data_only(df_rlc_sojourn)
    df_rlc_hol_wait = filter_data_only(df_rlc_hol_wait)
    df_ul_mac = filter_data_only(df_ul_mac)
    df_mobility = filter_data_only(df_mobility)

    if df_ul_rlc is not None:
        df_ul_rlc["delay_ms"] = df_ul_rlc["delay_us"] / 1000.0
    if df_ul_pdcp is not None:
        df_ul_pdcp["delay_ms"] = df_ul_pdcp["delay_us"] / 1000.0
    if df_hol is not None:
        df_hol["hol_ms"] = df_hol["tx_queue_hol_us"] / 1000.0
        df_hol["retx_hol_ms"] = df_hol["retx_queue_hol_us"] / 1000.0
        df_hol["tx_queue_kbytes"] = df_hol["tx_queue_bytes"] / 1024.0
    if df_rlc_sojourn is not None:
        if "pre_hol_wait_us" in df_rlc_sojourn.columns:
            df_rlc_sojourn["pre_hol_wait_ms"] = df_rlc_sojourn["pre_hol_wait_us"] / 1000.0
    if df_rlc_hol_wait is not None:
        df_rlc_hol_wait["hol_wait_ms"] = df_rlc_hol_wait["hol_grant_wait_us"] / 1000.0
    if df_mobility is not None:
        df_mobility["dist_to_bs"] = (
            (df_mobility["pos_x"] ** 2 + df_mobility["pos_y"] ** 2 + df_mobility["pos_z"] ** 2) ** 0.5
        )
    load_throughput = compute_load_throughput(df_load)
    if load_throughput:
        for proto, mbps in sorted(load_throughput.items()):
            emit(f"{proto}_ul_throughput (Mbps)={mbps:.6f}")
    ul_pdcp_throughput = compute_ul_pdcp_throughput_by_rnti(df_ul_pdcp)
    # Collect RNTIs from all available logs.
    rntis = set()
    for df in [
        df_ul_tb, df_delay, df_vr_frag, df_gnb_bsr,
        df_ul_rlc, df_ul_pdcp, df_hol, df_rlc_sojourn, df_rlc_hol_wait, df_ul_mac
    ]:
        if df is not None and "rnti" in df.columns:
            rntis.update(df["rnti"].dropna().unique().tolist())
    rntis = sorted(int(r) for r in rntis)

    bsr_counts: dict[int, int] = {}
    if df_gnb_bsr is not None and not df_gnb_bsr.empty:
        if "lcg" in df_gnb_bsr.columns:
            lcg_numeric = pd.to_numeric(df_gnb_bsr["lcg"], errors="coerce")
            df_gnb_bsr = df_gnb_bsr[lcg_numeric != 0]
        if "queue_bytes" in df_gnb_bsr.columns:
            queue_bytes = pd.to_numeric(df_gnb_bsr["queue_bytes"], errors="coerce")
            df_gnb_bsr = df_gnb_bsr[queue_bytes > 0]
        required_cols = {"time_us", "rnti", "frame", "subframe", "slot", "bwp_id", "node_id"}
        if required_cols.issubset(df_gnb_bsr.columns):
            unique_bsrs = df_gnb_bsr.drop_duplicates(
                subset=["time_us", "rnti", "frame", "subframe", "slot", "bwp_id", "node_id"]
            )
        elif {"time_us", "rnti"}.issubset(df_gnb_bsr.columns):
            unique_bsrs = df_gnb_bsr.drop_duplicates(subset=["time_us", "rnti"])
        else:
            unique_bsrs = df_gnb_bsr
        bsr_counts = unique_bsrs.groupby("rnti").size().to_dict()

    for rnti in rntis:
        run_label = f"{input_dir.name} | RNTI {rnti}"
        tbler_mean = float("nan")
        if df_ul_tb is not None and "tbler" in df_ul_tb.columns:
            tbler_series = df_ul_tb[df_ul_tb["rnti"] == rnti]["tbler"]
            tbler_mean = float(tbler_series.mean()) if not tbler_series.empty else float("nan")
        ul_probe_drop_rate = compute_ul_probe_drop_rate(df_delay, rnti)
        ul_prbs_per_ms = compute_prbs_per_ms(df_ul_mac, rnti)
        # Assumes 106 PRBs per slot and, within a 10 ms frame, 4 UL slots plus 4 S slots
        # that can carry UL. That yields up to 8 UL-capable slots per 10 ms, so the UL PRB
        # budget is 106 * 8 = 848 PRBs per 10 ms, i.e., 84.8 PRBs/ms.
        ul_prb_fraction = ul_prbs_per_ms / 84.8 if not math.isnan(ul_prbs_per_ms) else float("nan")
        def summarize(series: pd.Series, label: str) -> str:
            series = series.dropna()
            if series.empty:
                return f"{label}=n/a"
            return (
                f"{label}=max:{series.max():.3f} p95:{series.quantile(0.95):.3f} n:{series.size}"
            )

        ul_probe_series = (
            df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == rnti)]["delay_ms"]
            if df_delay is not None else empty_series()
        )
        rlc_pdus_per_ip = compute_rlc_pdus_per_ip(df_ul_rlc, rnti)
        rlc_pdus_per_ip_ts = compute_rlc_pdus_per_ip_ts(df_ul_rlc, rnti)
        rlc_hol_series = (
            df_hol[df_hol["rnti"] == rnti]["hol_ms"] if df_hol is not None else empty_series()
        )
        rlc_hol_wait_series = (
            df_rlc_hol_wait[df_rlc_hol_wait["rnti"] == rnti]["hol_wait_ms"]
            if df_rlc_hol_wait is not None else empty_series()
        )
        pdcp_series = (
            df_ul_pdcp[df_ul_pdcp["rnti"] == rnti]["delay_ms"]
            if df_ul_pdcp is not None else empty_series()
        )

        app_pdus = (
            df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == rnti)].shape[0]
            if df_delay is not None else 0
        )
        pdcp_pdus = df_ul_pdcp[df_ul_pdcp["rnti"] == rnti].shape[0] if df_ul_pdcp is not None else 0
        rlc_pdus = df_ul_rlc[df_ul_rlc["rnti"] == rnti].shape[0] if df_ul_rlc is not None else 0
        if df_ul_mac is not None:
            mac_pdus = df_ul_mac[df_ul_mac["rnti"] == rnti].shape[0]
        else:
            mac_pdus = df_ul_tb[df_ul_tb["rnti"] == rnti].shape[0] if df_ul_tb is not None else 0
        ul_pdcp_tp_mbps = ul_pdcp_throughput.get(rnti, float("nan"))

        emit(
            f"rnti {rnti}: ul_prbs_frac={ul_prb_fraction:.6f} "
            f"ul_tbler_mean={tbler_mean:.6f} ul_probe_drop_rate={ul_probe_drop_rate:.6f} "
            f"app_pdus={app_pdus} pdcp_pdus={pdcp_pdus} rlc_pdus={rlc_pdus} mac_pdus={mac_pdus} "
            f"gnb_bsr_count={bsr_counts.get(rnti, 0)} "
            f"ul_pdcp_throughput (Mbps)={ul_pdcp_tp_mbps:.6f}"
        )

        metric_items = [
            (df_ul_tb[df_ul_tb["rnti"] == rnti]["mcs"] if df_ul_tb is not None else empty_series(),
             "UL MCS"),
            (df_ul_tb[df_ul_tb["rnti"] == rnti]["sinr_db"] if df_ul_tb is not None else empty_series(),
             "UL SINR (dB)"),
            (df_ul_mac[df_ul_mac["rnti"] == rnti]["num_prbs"] if df_ul_mac is not None else empty_series(),
             "UL PRBs allocated"),
            (df_mobility[df_mobility["rnti"] == rnti]["dist_to_bs"] if df_mobility is not None else empty_series(),
             "Distance to BS (m)"),

            (df_ul_pdcp[df_ul_pdcp["rnti"] == rnti]["packet_size"]
             if df_ul_pdcp is not None else empty_series(),
             "UL PDCP PDU size (bytes)"),
            (df_ul_rlc[df_ul_rlc["rnti"] == rnti]["packet_size"]
             if df_ul_rlc is not None else empty_series(),
             "UL RLC PDU size (bytes)"),
            (df_ul_tb[df_ul_tb["rnti"] == rnti]["tb_size"] if df_ul_tb is not None else empty_series(),
             "UL MAC PDU size (bytes)"),
            (df_hol[df_hol["rnti"] == rnti]["tx_queue_kbytes"] if df_hol is not None else empty_series(),
             "RLC TX queue (KBytes)"),

            (df_ul_rlc[df_ul_rlc["rnti"] == rnti]["delay_ms"] if df_ul_rlc is not None else empty_series(),
             "UL HARQ (tx + retx) delay (ms)"),
            (df_rlc_sojourn[df_rlc_sojourn["rnti"] == rnti]["pre_hol_wait_ms"]
             if df_rlc_sojourn is not None else empty_series(),
             "RLC TX pre-HOL wait (ms)"),
            (df_rlc_hol_wait[df_rlc_hol_wait["rnti"] == rnti]["hol_wait_ms"]
             if df_rlc_hol_wait is not None else empty_series(),
             "RLC HOL-to-grant wait (ms)"), 
            (rlc_pdus_per_ip, "RLC PDUs per IP packet"),

            # the logs in the PDCP files are after the PDCP hands it pver to the RLC, hence the naming is based on the layers it spent time in which is RLC and below 
            (df_ul_pdcp[df_ul_pdcp["rnti"] == rnti]["delay_ms"] if df_ul_pdcp is not None else empty_series(),
             "UL RLC-RLC combined delay (ms)"),
            (df_hol[df_hol["rnti"] == rnti]["hol_ms"] if df_hol is not None else empty_series(),
             "RLC TX HOL delay (ms)"),
            (df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == rnti)]["delay_ms"]
             if df_delay is not None else empty_series(),
             "UL probe delay (ms)"),
            (df_vr_frag[df_vr_frag["rnti"] == rnti]["delay_ms"] if df_vr_frag is not None else empty_series(),
             "VR fragment delay (ms)"),
            
        ]
        cols = 4
        rows = math.ceil(len(metric_items) / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 5.5, rows * 4.5))
        axes = axes.ravel()
        for ax, (series, xlabel) in zip(axes, metric_items):
            plot_hist(series, bins=50, xlabel=xlabel, ax=ax)
        for ax in axes[len(metric_items):]:
            ax.set_visible(False)
        fig.suptitle(f"{run_label} | Histograms", fontsize=TITLE_FONT_SIZE, y=0.99)
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        fig.savefig(output_dir / f"rnti_{rnti}_metrics.png", dpi=150)
        plt.close(fig)

        cols = 4
        rows = math.ceil(len(metric_items) / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 5.5, rows * 4.5))
        axes = axes.ravel()
        for ax, (series, xlabel) in zip(axes, metric_items):
            plot_cdf(series, xlabel=xlabel, ax=ax)
        for ax in axes[len(metric_items):]:
            ax.set_visible(False)
        fig.suptitle(f"{run_label} | CDFs", fontsize=TITLE_FONT_SIZE, y=0.99)
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        fig.savefig(output_dir / f"rnti_{rnti}_cdf.png", dpi=150)
        plt.close(fig)

        ts_items = [
            (df_ul_tb[df_ul_tb["rnti"] == rnti] if df_ul_tb is not None else None,
             "time_us", "mcs", "UL MCS"),
            (df_ul_tb[df_ul_tb["rnti"] == rnti] if df_ul_tb is not None else None,
             "time_us", "sinr_db", "UL SINR (dB)"),
            (df_ul_mac[df_ul_mac["rnti"] == rnti] if df_ul_mac is not None else None,
             "time_us", "num_prbs", "UL PRBs allocated"),
            (df_mobility[df_mobility["rnti"] == rnti] if df_mobility is not None else None,
             "time_us", "dist_to_bs", "Distance to BS (m)"),

            
            (df_ul_pdcp[df_ul_pdcp["rnti"] == rnti]
             if df_ul_pdcp is not None else empty_series(),
             "time_us", "packet_size", "UL PDCP PDU size (bytes)"),
            (df_ul_rlc[df_ul_rlc["rnti"] == rnti]
             if df_ul_rlc is not None else empty_series(),
             "time_us", "packet_size", "UL RLC PDU size (bytes)"),
            (df_ul_tb[df_ul_tb["rnti"] == rnti] if df_ul_tb is not None else empty_series(),
             "time_us", "tb_size", "UL MAC PDU size (bytes)"),
            (df_hol[df_hol["rnti"] == rnti] if df_hol is not None else None,
             "time_us", "tx_queue_kbytes", "RLC TX queue (KBytes)"),

            (df_ul_rlc[df_ul_rlc["rnti"] == rnti] if df_ul_rlc is not None else None,
             "time_us", "delay_ms", "UL HARQ (tx + retx) delay (ms)"),
            (df_rlc_sojourn[df_rlc_sojourn["rnti"] == rnti]
             if df_rlc_sojourn is not None else None,
             "time_us", "pre_hol_wait_ms", "RLC TX pre-HOL wait (ms)"),
            (df_rlc_hol_wait[df_rlc_hol_wait["rnti"] == rnti]
             if df_rlc_hol_wait is not None else None,
             "time_us", "hol_wait_ms", "RLC HOL-to-grant wait (ms)"),
            (rlc_pdus_per_ip_ts, "time_us", "rlc_pdus_per_ip",
             "RLC PDUs per IP packet"),

            (df_ul_pdcp[df_ul_pdcp["rnti"] == rnti] if df_ul_pdcp is not None else None,
             "time_us", "delay_ms", "UL RLC-RLC combined delay (ms)"),
            (df_hol[df_hol["rnti"] == rnti] if df_hol is not None else None,
             "time_us", "hol_ms", "RLC TX HOL delay (ms)"),
            (df_delay[(df_delay["direction"] == "UL") & (df_delay["rnti"] == rnti)]
             if df_delay is not None else None,
             "time_us", "delay_ms", "UL probe delay (ms)"),
            (df_vr_frag[df_vr_frag["rnti"] == rnti] if df_vr_frag is not None else None,
             "time_us", "delay_ms", "VR fragment delay (ms)"),
            
        ]
        cols = 4
        rows = math.ceil(len(ts_items) / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 5.5, rows * 4.5))
        axes = axes.ravel()
        for ax, (df, time_col, value_col, label) in zip(axes, ts_items):
            plot_timeseries(df, time_col, value_col, ax, label)
        for ax in axes[len(ts_items):]:
            ax.set_visible(False)
        fig.suptitle(f"{run_label} | Timeseries", fontsize=TITLE_FONT_SIZE, y=0.99)
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        fig.savefig(output_dir / f"rnti_{rnti}_timeseries.png", dpi=150)
        plt.close(fig)
        plot_ul_delay_windowed(df_delay, rnti, output_dir, run_label)

    emit(f"Wrote per-RNTI plots under: {output_dir}")
    analysis_results.close()

def main():
    parser = argparse.ArgumentParser(
        description="Plot histograms from raw data"
    )
    parser.add_argument(
        "--input-dir",
        default=".",
        help="Directory containing run folder(s) or log files (default: .)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    plt.rcParams.update({"font.size": FONT_SIZE})

    run_dirs = find_run_dirs(input_dir)
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {input_dir}")

    for run_dir in run_dirs:
        plot_run(run_dir, run_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
