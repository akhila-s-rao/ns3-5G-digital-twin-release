#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd


DRB_LCID_MIN = 3
DELAYDECOM_REQUIRED_COLUMNS = {
    "Packet ID",
    "Queuing delay",
    "segmentation delay",
    "Transmission delay",
    "Retransmission delay",
    "End to End Delay",
}


def load_tsv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, sep=r"\s+")


def filter_data_only(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        return None
    if "msg_type" in df.columns:
        df = df[df["msg_type"].astype(str).str.upper() == "DATA"]
    if "lcid" in df.columns:
        df = df[df["lcid"] >= DRB_LCID_MIN]
    return df


def infer_selected_rnti(df_delay: pd.DataFrame | None, run_dir: Path) -> int | None:
    if df_delay is None:
        return None
    ul_delay = df_delay[df_delay["direction"].astype(str).str.upper() == "UL"].copy()
    if ul_delay.empty:
        return None
    if (run_dir / "load_trace.txt").exists() and "ue_id" in ul_delay.columns:
        ul_delay = ul_delay[ul_delay["ue_id"] != 1]
    rntis = sorted(int(v) for v in ul_delay["rnti"].dropna().unique().tolist())
    if len(rntis) == 1:
        return rntis[0]
    return None


def build_run_packet_table(run_dir: Path) -> pd.DataFrame | None:
    df_delay = load_tsv(run_dir / "delay_trace.txt")
    df_rlc = filter_data_only(load_tsv(run_dir / "NrUlRlcRxComponentStats.txt"))
    df_pdcp = filter_data_only(load_tsv(run_dir / "NrUlPdcpRxStats.txt"))
    df_soj = filter_data_only(load_tsv(run_dir / "RlcTxQueueSojournTrace.txt"))
    df_hol = filter_data_only(load_tsv(run_dir / "RlcHolGrantWaitTrace.txt"))

    if any(df is None for df in [df_delay, df_rlc, df_pdcp, df_soj, df_hol]):
        return None

    selected_rnti = infer_selected_rnti(df_delay, run_dir)
    if selected_rnti is None:
        return None

    df_delay = df_delay[
        (df_delay["direction"].astype(str).str.upper() == "UL") & (df_delay["rnti"] == selected_rnti)
    ].copy()
    df_delay["pkt_id"] = pd.to_numeric(df_delay["seq_num"], errors="coerce")
    df_delay["e2e_delay_ms"] = pd.to_numeric(df_delay["delay_us"], errors="coerce") / 1000.0
    df_delay = df_delay.dropna(subset=["pkt_id", "e2e_delay_ms"])[["pkt_id", "e2e_delay_ms"]]

    df_rlc = df_rlc[df_rlc["rnti"] == selected_rnti].copy()
    df_rlc["pkt_id"] = pd.to_numeric(df_rlc["pkt_id"], errors="coerce")
    df_rlc["time_us"] = pd.to_numeric(df_rlc["time_us"], errors="coerce")
    df_rlc["delay_ms"] = pd.to_numeric(df_rlc["delay_us"], errors="coerce") / 1000.0
    df_rlc = df_rlc.dropna(subset=["pkt_id", "time_us", "delay_ms"])

    df_pdcp = df_pdcp[df_pdcp["rnti"] == selected_rnti].copy()
    df_pdcp["pkt_id"] = pd.to_numeric(df_pdcp["pkt_id"], errors="coerce")
    df_pdcp["time_us"] = pd.to_numeric(df_pdcp["time_us"], errors="coerce")
    df_pdcp = df_pdcp.dropna(subset=["pkt_id", "time_us"])

    df_soj = df_soj[df_soj["rnti"] == selected_rnti].copy()
    df_soj["pkt_id"] = pd.to_numeric(df_soj["pkt_id"], errors="coerce")
    df_soj["pre_hol_wait_ms"] = pd.to_numeric(df_soj["pre_hol_wait_us"], errors="coerce") / 1000.0
    df_soj = (
        df_soj.dropna(subset=["pkt_id", "pre_hol_wait_ms", "time_us"])
        .sort_values("time_us")
        .drop_duplicates(subset=["pkt_id"], keep="first")[["pkt_id", "pre_hol_wait_ms", "time_us"]]
        .rename(columns={"time_us": "soj_time_us"})
    )

    df_hol = df_hol[df_hol["rnti"] == selected_rnti].copy()
    df_hol["pkt_id"] = pd.to_numeric(df_hol["pkt_id"], errors="coerce")
    df_hol["hol_wait_ms"] = pd.to_numeric(df_hol["hol_grant_wait_us"], errors="coerce") / 1000.0
    df_hol = (
        df_hol.dropna(subset=["pkt_id", "hol_wait_ms", "time_us"])
        .sort_values("time_us")
        .drop_duplicates(subset=["pkt_id"], keep="first")[["pkt_id", "hol_wait_ms", "time_us"]]
        .rename(columns={"time_us": "hol_time_us"})
    )

    queueing = pd.merge(df_soj, df_hol, on="pkt_id", how="inner")
    queueing["queueing_delay_ms"] = queueing["pre_hol_wait_ms"] + queueing["hol_wait_ms"]
    queueing = queueing[["pkt_id", "queueing_delay_ms"]]

    txretx = df_rlc.loc[df_rlc.groupby("pkt_id")["delay_ms"].idxmax()][["pkt_id", "delay_ms"]]
    txretx = txretx.rename(columns={"delay_ms": "tx_retx_delay_ms"})

    link_grant = df_hol[["pkt_id", "hol_time_us"]].rename(columns={"hol_time_us": "first_grant_time_us"})
    link_rlc_last = (
        df_rlc[df_rlc["pkt_id"] != 0]
        .groupby("pkt_id", as_index=False)["time_us"]
        .max()
        .rename(columns={"time_us": "last_rlc_rx_time_us"})
    )
    link = pd.merge(link_grant, link_rlc_last, on="pkt_id", how="inner")
    link["link_delay_ms"] = (link["last_rlc_rx_time_us"] - link["first_grant_time_us"]) / 1000.0
    link = link[link["link_delay_ms"] >= 0]

    segmentation = pd.merge(link[["pkt_id", "link_delay_ms"]], txretx, on="pkt_id", how="inner")
    segmentation["segmentation_delay_ms"] = (
        segmentation["link_delay_ms"] - segmentation["tx_retx_delay_ms"]
    )
    segmentation = segmentation[["pkt_id", "segmentation_delay_ms"]]

    reorder_rlc_last = (
        df_rlc[df_rlc["pkt_id"] != 0]
        .groupby("pkt_id", as_index=False)["time_us"]
        .max()
        .rename(columns={"time_us": "last_rlc_rx_time_us"})
    )
    reorder_pdcp_first = (
        df_pdcp[df_pdcp["pkt_id"] != 0]
        .groupby("pkt_id", as_index=False)["time_us"]
        .min()
        .rename(columns={"time_us": "pdcp_rx_time_us"})
    )
    reordering = pd.merge(reorder_rlc_last, reorder_pdcp_first, on="pkt_id", how="inner")
    reordering["reordering_delay_ms"] = (
        reordering["pdcp_rx_time_us"] - reordering["last_rlc_rx_time_us"]
    ) / 1000.0
    reordering = reordering[reordering["reordering_delay_ms"] >= 0][["pkt_id", "reordering_delay_ms"]]

    merged = df_delay.merge(queueing, on="pkt_id", how="inner")
    merged = merged.merge(txretx, on="pkt_id", how="inner")
    merged = merged.merge(segmentation, on="pkt_id", how="inner")
    merged = merged.merge(reordering, on="pkt_id", how="inner")
    if merged.empty:
        return None

    merged["component_sum_ms"] = (
        merged["queueing_delay_ms"]
        + merged["tx_retx_delay_ms"]
        + merged["segmentation_delay_ms"]
        + merged["reordering_delay_ms"]
    )
    merged["residual_ms"] = merged["e2e_delay_ms"] - merged["component_sum_ms"]
    return merged.sort_values("pkt_id")


def build_delaydecom_packet_table(csv_path: Path) -> pd.DataFrame | None:
    if not csv_path.exists():
        return None

    df = pd.read_csv(csv_path)
    missing = sorted(DELAYDECOM_REQUIRED_COLUMNS.difference(df.columns))
    if missing:
        print(f"WARN: skipping {csv_path}, missing columns: {missing}")
        return None

    table = pd.DataFrame()
    table["pkt_id"] = pd.to_numeric(df["Packet ID"], errors="coerce")
    table["queueing_delay_ms"] = pd.to_numeric(df["Queuing delay"], errors="coerce")
    table["segmentation_delay_ms"] = pd.to_numeric(df["segmentation delay"], errors="coerce")
    table["tx_delay_ms"] = pd.to_numeric(df["Transmission delay"], errors="coerce")
    table["retx_delay_ms"] = pd.to_numeric(df["Retransmission delay"], errors="coerce")
    table["e2e_delay_ms"] = pd.to_numeric(df["End to End Delay"], errors="coerce")
    table = table.dropna()
    if table.empty:
        return None

    table["component_sum_ms"] = (
        table["queueing_delay_ms"]
        + table["segmentation_delay_ms"]
        + table["tx_delay_ms"]
        + table["retx_delay_ms"]
    )
    table["residual_ms"] = table["e2e_delay_ms"] - table["component_sum_ms"]
    return table.sort_values("pkt_id")


def extract_run_number(name: str, prefix: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(prefix)}0*(\d+)", name, flags=re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1))


def find_lena_runs(root: Path) -> dict[int, Path]:
    runs: dict[int, Path] = {}
    if not root.exists():
        return runs
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        run_no = extract_run_number(path.name, "benchmark")
        if run_no is not None:
            runs[run_no] = path
    return runs


def find_delaydecom_runs(root: Path) -> dict[int, Path]:
    runs: dict[int, Path] = {}
    if not root.exists():
        return runs
    for path in sorted(root.glob("*.csv")):
        run_no = extract_run_number(path.stem, "delayDecom")
        if run_no is not None:
            runs[run_no] = path
    return runs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=(
            Path(__file__).resolve().parent
            / "sim_campaign_logs"
            / "compare_expeca_5Glena_logs"
            / "5gLena"
        ),
    )
    parser.add_argument(
        "--delaydecom-root",
        default=(
            Path(__file__).resolve().parent
            / "sim_campaign_logs"
            / "compare_expeca_5Glena_logs"
            / "delay_decomposition_data_from_edaf"
        ),
    )
    args = parser.parse_args()

    root = Path(args.root)
    delaydecom_root = Path(args.delaydecom_root)
    lena_runs = find_lena_runs(root)
    delaydecom_runs = find_delaydecom_runs(delaydecom_root)
    run_numbers = sorted(set(lena_runs).union(delaydecom_runs))
    if not run_numbers:
        raise FileNotFoundError(f"No benchmark or delayDecom runs found under {root} or {delaydecom_root}")

    print("run\tlena_packets\tlena_avg_residual_ms\tdelaydecom_packets\tdelaydecom_avg_residual_ms")
    for run_no in run_numbers:
        run_dir = lena_runs.get(run_no)
        delaydecom_csv = delaydecom_runs.get(run_no)
        table = build_run_packet_table(run_dir) if run_dir is not None else None
        delaydecom_table = (
            build_delaydecom_packet_table(delaydecom_csv)
            if delaydecom_csv is not None
            else None
        )

        if table is None or table.empty:
            lena_packets = "0"
            lena_residual = "NA"
        else:
            lena_packets = str(len(table))
            lena_residual = f"{table['residual_ms'].mean():.6f}"

        if delaydecom_table is None or delaydecom_table.empty:
            delaydecom_packets = "0"
            delaydecom_residual = "NA"
        else:
            delaydecom_packets = str(len(delaydecom_table))
            delaydecom_residual = f"{delaydecom_table['residual_ms'].mean():.6f}"

        print(
            f"{run_no:02d}\t{lena_packets}\t{lena_residual}\t"
            f"{delaydecom_packets}\t{delaydecom_residual}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
