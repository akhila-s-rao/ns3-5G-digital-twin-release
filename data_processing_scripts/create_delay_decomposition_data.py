#!/usr/bin/env python3
import argparse
from pathlib import Path
import re

import pandas as pd

DRB_LCID_MIN = 3  # SRB0/1/2 are reserved; DRB/data LCIDs start at 3.
KNOWN_LOGS = [
    "NrUlPdcpRxStats.txt",
    "NrUlRlcRxComponentStats.txt",
    "NrUlRlcTxComponentStats.txt",
    "RlcTxQueueSojournTrace.txt",
    "RlcHolGrantWaitTrace.txt",
]
LENA_DELAY_DECOMPOSITION_CSV = "5Glena_delay_decomposition.csv"
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


def has_required_logs(run_dir: Path) -> bool:
    """Return True if the directory contains any known log file."""
    return any((run_dir / name).exists() for name in KNOWN_LOGS)


def find_run_dirs(base_dir: Path) -> list[Path]:
    """Find run directories containing known 5G-LENA logs."""
    if has_required_logs(base_dir):
        return [base_dir]
    runs: list[Path] = []
    for entry in sorted(base_dir.iterdir()):
        if entry.is_dir() and has_required_logs(entry):
            runs.append(entry)
    return runs


def extract_run_number(name: str) -> int | None:
    m = re.search(r"(?i)(?:benchmark|delaydecom)[^0-9]*0*(\d+)", name)
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


def merge_metric_column(base: pd.DataFrame,
                        metric: pd.DataFrame | None,
                        columns: list[str]) -> pd.DataFrame:
    if metric is None or metric.empty:
        return base
    available = ["rnti", "pkt_id"] + [col for col in columns if col in metric.columns]
    return base.merge(
        metric[available].drop_duplicates(subset=["rnti", "pkt_id"], keep="first"),
        on=["rnti", "pkt_id"],
        how="left",
    )


def build_lena_delay_decomposition_table(
    df_ul_pdcp_rx: pd.DataFrame | None,
    df_pregrant_grant_wait: pd.DataFrame | None,
    df_frame_alignment: pd.DataFrame | None,
    df_sched_delay2: pd.DataFrame | None,
    df_ul_rlc_plot: pd.DataFrame | None,
    df_link_delay: pd.DataFrame | None,
    df_segmentation_delay: pd.DataFrame | None,
    df_reordering_delay: pd.DataFrame | None,
    df_rlc_segments_per_pkt: pd.DataFrame | None,
) -> pd.DataFrame:
    table = pd.DataFrame(columns=["rnti", "pkt_id"])

    if df_ul_pdcp_rx is not None:
        pdcp_rx = df_ul_pdcp_rx[["rnti", "pkt_id", "packet_size", "time_us", "delay_us"]].copy()
        for col in ["rnti", "pkt_id", "packet_size", "time_us", "delay_us"]:
            pdcp_rx[col] = pd.to_numeric(pdcp_rx[col], errors="coerce")
        pdcp_rx = pdcp_rx.dropna(subset=["rnti", "pkt_id", "time_us", "delay_us"])
        if not pdcp_rx.empty:
            pdcp_rx["pdcp_rx_time_us"] = pdcp_rx["time_us"]
            pdcp_rx["ran_delay_ms"] = pdcp_rx["delay_us"] / 1000.0
            pdcp_rx = pdcp_rx.rename(columns={"packet_size": "pkt_size_bytes"})
            table = (
                pdcp_rx[["rnti", "pkt_id", "pkt_size_bytes", "pdcp_rx_time_us", "ran_delay_ms"]]
                .sort_values("pdcp_rx_time_us")
                .drop_duplicates(subset=["rnti", "pkt_id"], keep="first")
            )

    if table.empty:
        return table

    table = merge_metric_column(
        table,
        df_pregrant_grant_wait,
        [
            "soj_time_us",
            "hol_time_us",
            "pre_hol_wait_ms",
            "hol_wait_ms",
            "pregrant_plus_grant_wait_ms",
        ],
    )
    table = merge_metric_column(
        table,
        df_frame_alignment,
        ["pdcp_tx_time_us", "time_us", "frame_alignment_delay_ms"],
    ).rename(columns={"time_us": "sr_time_us"})
    table = merge_metric_column(
        table,
        df_sched_delay2,
        ["first_pkt_tx_time_us", "sched_delay2_ms"],
    )
    table = merge_metric_column(
        table,
        df_ul_rlc_plot,
        ["time_us", "delay_ms"],
    ).rename(columns={"time_us": "tx_retx_time_us", "delay_ms": "tx_retx_delay_ms"})
    table = merge_metric_column(
        table,
        df_link_delay,
        ["first_grant_time_us", "last_rlc_rx_time_us", "link_delay_ms"],
    )
    table = merge_metric_column(
        table,
        df_segmentation_delay,
        ["segmentation_delay_ms"],
    )
    table = merge_metric_column(
        table,
        df_reordering_delay,
        ["reordering_delay_ms"],
    )
    table = merge_metric_column(
        table,
        df_rlc_segments_per_pkt,
        ["first_tx_time_us", "rlc_segments_per_pkt"],
    )

    table = table.rename(
        columns={
            "pkt_size": "pkt_size_bytes",
            "pregrant_plus_grant_wait_ms": "queueing_delay_ms",
            "sched_delay2_ms": "scheduling_delay_ms",
        }
    )
    residual_cols = {"ran_delay_ms", "queueing_delay_ms", "link_delay_ms"}
    if residual_cols.issubset(table.columns):
        table["delay_residual_ms"] = (
            table["ran_delay_ms"] - (table["queueing_delay_ms"] + table["link_delay_ms"])
        )
    ordered_cols = [
        "rnti",
        "pkt_id",
        "pkt_size_bytes",
        "pdcp_rx_time_us",
        "ran_delay_ms",
        "pre_hol_wait_ms",
        "hol_wait_ms",
        "queueing_delay_ms",
        "frame_alignment_delay_ms",
        "scheduling_delay_ms",
        "tx_retx_delay_ms",
        "link_delay_ms",
        "delay_residual_ms",
        "segmentation_delay_ms",
        "reordering_delay_ms",
        "rlc_segments_per_pkt",
    ]
    existing_ordered = [col for col in ordered_cols if col in table.columns]
    return table[existing_ordered].sort_values(["rnti", "pkt_id"])


def load_lena_delay_decomposition(input_dir: Path) -> pd.DataFrame | None:
    if not has_required_logs(input_dir):
        print(f"WARN: skipping {input_dir}, no known log files found")
        return None

    df_ul_rlc = filter_data_only(load_tsv(input_dir / "NrUlRlcRxComponentStats.txt"))
    df_ul_rlc_tx = filter_data_only(load_tsv(input_dir / "NrUlRlcTxComponentStats.txt"))
    df_ul_pdcp_tx = filter_data_only(load_tsv(input_dir / "NrUlPdcpTxStats.txt"))
    df_ul_pdcp_rx = filter_data_only(load_tsv(input_dir / "NrUlPdcpRxStats.txt"))
    df_rlc_sojourn = filter_data_only(load_tsv(input_dir / "RlcTxQueueSojournTrace.txt"))
    df_rlc_hol_wait = filter_data_only(load_tsv(input_dir / "RlcHolGrantWaitTrace.txt"))
    df_ue_phy_ctrl = load_tsv(input_dir / "UePhyCtrlTxTrace.txt")

    try:
        df_ul_rlc = require_optional_columns(
            df_ul_rlc, "NrUlRlcRxComponentStats.txt", {"time_us", "rnti", "pkt_id", "delay_us"}
        )
        df_ul_rlc_tx = require_optional_columns(
            df_ul_rlc_tx, "NrUlRlcTxComponentStats.txt", {"time_us", "rnti", "pkt_id", "rlc_sn"}
        )
        df_ul_pdcp_tx = require_optional_columns(
            df_ul_pdcp_tx, "NrUlPdcpTxStats.txt", {"time_us", "rnti", "pkt_id"}
        )
        df_ul_pdcp_rx = require_optional_columns(
            df_ul_pdcp_rx, "NrUlPdcpRxStats.txt", {"time_us", "rnti", "pkt_id", "packet_size", "delay_us"}
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

    if df_ul_pdcp_rx is not None:
        df_ul_pdcp_rx["ran_delay_ms"] = pd.to_numeric(df_ul_pdcp_rx["delay_us"], errors="coerce") / 1000.0

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
        pdcp_tx_cols = ["time_us", "rnti"] + (["pkt_id"] if "pkt_id" in df_ul_pdcp_tx.columns else [])
        pdcp_tx = df_ul_pdcp_tx[pdcp_tx_cols].rename(columns={"time_us": "pdcp_tx_time_us"}).copy()
        sr = sr.sort_values(["time_us", "rnti"]).copy()
        sr["prev_sr_time_us"] = sr.groupby("rnti")["time_us"].shift(1)
        for col in ["pdcp_tx_time_us", "rnti"]:
            pdcp_tx[col] = pd.to_numeric(pdcp_tx[col], errors="coerce")
        if "pkt_id" in pdcp_tx.columns:
            pdcp_tx["pkt_id"] = pd.to_numeric(pdcp_tx["pkt_id"], errors="coerce")
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

    df_reordering_delay = None
    if df_ul_rlc is not None and df_ul_pdcp_rx is not None:
        rlc_rx = df_ul_rlc[["rnti", "pkt_id", "time_us"]].copy()
        pdcp_rx = df_ul_pdcp_rx[["rnti", "pkt_id", "time_us"]].copy()
        for col in ["rnti", "pkt_id", "time_us"]:
            rlc_rx[col] = pd.to_numeric(rlc_rx[col], errors="coerce")
            pdcp_rx[col] = pd.to_numeric(pdcp_rx[col], errors="coerce")
        rlc_rx = rlc_rx.dropna(subset=["rnti", "pkt_id", "time_us"])
        pdcp_rx = pdcp_rx.dropna(subset=["rnti", "pkt_id", "time_us"])
        if not rlc_rx.empty and not pdcp_rx.empty:
            rlc_last = (
                rlc_rx.sort_values("time_us")
                .groupby(["rnti", "pkt_id"], as_index=False)["time_us"]
                .max()
                .rename(columns={"time_us": "last_rlc_rx_time_us"})
            )
            pdcp_first = (
                pdcp_rx.sort_values("time_us")
                .groupby(["rnti", "pkt_id"], as_index=False)["time_us"]
                .min()
                .rename(columns={"time_us": "pdcp_rx_time_us"})
            )
            df_reordering_delay = pd.merge(rlc_last, pdcp_first, on=["rnti", "pkt_id"], how="inner")
            if not df_reordering_delay.empty:
                df_reordering_delay["reordering_delay_us"] = (
                    df_reordering_delay["pdcp_rx_time_us"] - df_reordering_delay["last_rlc_rx_time_us"]
                )
                df_reordering_delay = df_reordering_delay[df_reordering_delay["reordering_delay_us"] >= 0]
                if not df_reordering_delay.empty:
                    df_reordering_delay["reordering_delay_ms"] = (
                        df_reordering_delay["reordering_delay_us"] / 1000.0
                    )
                    df_reordering_delay["time_us"] = df_reordering_delay["pdcp_rx_time_us"]
                    df_reordering_delay = df_reordering_delay.sort_values("time_us")

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

    return build_lena_delay_decomposition_table(
        df_ul_pdcp_rx,
        df_pregrant_grant_wait,
        df_frame_alignment,
        df_sched_delay2,
        df_ul_rlc_plot,
        df_link_delay,
        df_segmentation_delay,
        df_reordering_delay,
        df_rlc_segments_per_pkt,
    )


def write_lena_delay_decomposition_csv(run_no: int, lena_run_dir: Path, csv_output_dir: Path) -> None:
    delay_decomposition = load_lena_delay_decomposition(lena_run_dir)
    if delay_decomposition is None:
        print(f"WARN: skipping run{run_no:02d}, unusable 5G-LENA logs: {lena_run_dir}")
        return

    csv_output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_output_dir / f"benchmark{run_no:02d}_{LENA_DELAY_DECOMPOSITION_CSV}"
    delay_decomposition.to_csv(csv_path, index=False)
    print(f"Wrote 5G-LENA delay decomposition CSV for run{run_no:02d} to {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Create 5G-LENA delay decomposition CSVs from 5G-LENA log roots"
    )
    parser.add_argument(
        "--lena-dir",
        required=True,
        help="Directory containing 5G-LENA run folder(s) or log files.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where 5G-LENA delay decomposition CSVs should be written.",
    )
    args = parser.parse_args()

    lena_dir = Path(args.lena_dir).resolve()
    lena_runs = find_run_dirs(lena_dir)
    if not lena_runs:
        print(f"WARN: no 5G-LENA run directories found under {lena_dir}")
        return 0

    lena_by_run = index_paths_by_run_number(lena_runs, "5G-LENA run")
    csv_output_dir = Path(args.output_dir).resolve()
    print(f"Writing 5G-LENA delay decomposition CSVs under: {csv_output_dir}")
    for run_no, lena_run_dir in sorted(lena_by_run.items()):
        if run_no == 13:
            print("WARN: skipping run13 by request")
            continue
        write_lena_delay_decomposition_csv(run_no, lena_run_dir, csv_output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
