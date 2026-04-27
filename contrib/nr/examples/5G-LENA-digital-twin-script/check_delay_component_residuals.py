#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DRB_LCID_MIN = 3


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
    parser.add_argument("--run-start", type=int, default=1)
    parser.add_argument("--run-end", type=int, default=18)
    args = parser.parse_args()

    root = Path(args.root)
    print("run\tpackets\tavg_residual_ms")
    for run_no in range(args.run_start, args.run_end + 1):
        run_dir = root / f"benchmark{run_no:02d}"
        table = build_run_packet_table(run_dir)
        if table is None or table.empty:
            print(f"{run_no:02d}\t0\tNA")
            continue
        print(f"{run_no:02d}\t{len(table)}\t{table['residual_ms'].mean():.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
