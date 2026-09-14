#!/usr/bin/env python3
import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat
from pathlib import Path
from time import perf_counter

import pandas as pd

DRB_LCID_MIN = 3  # SRB0/1/2 are reserved; DRB/data LCIDs start at 3.
# delay_trace pkt_size excludes SeqTs (12 B); PDCP size also includes
# SeqTs, UDP/IPv4 (28 B), and the PDCP header (2 B).
DELAY_PROBE_PDCP_OVERHEAD_BYTES = 42
DELAY_PROBE_MATCH_TOLERANCE_US = 100
KNOWN_LOGS = [
    "NrUlPdcpRxStats.txt",
    "NrUlRlcRxComponentStats.txt",
    "NrUlRlcTxComponentStats.txt",
    "RlcTxQueueSojournTrace.txt",
    "RlcHolGrantWaitTrace.txt",
]
TRACE_REQUIRED_COLUMNS = {
    "NrUlPdcpRxStats.txt": {"time_us", "rnti", "lcid", "pkt_id", "packet_size", "delay_us"},
    "NrUlRlcRxComponentStats.txt": {"time_us", "rnti", "lcid", "pkt_id", "delay_us"},
    "NrUlRlcTxComponentStats.txt": {"time_us", "rnti", "lcid", "pkt_id", "rlc_sn"},
    "NrUlPdcpTxStats.txt": {"time_us", "rnti", "lcid", "pkt_id"},
    "RlcTxQueueSojournTrace.txt": {"time_us", "rnti", "lcid", "pkt_id", "pre_hol_wait_us"},
    "RlcHolGrantWaitTrace.txt": {"time_us", "rnti", "lcid", "pkt_id", "hol_grant_wait_us"},
    "UlRxTbComponentTrace.txt": {
        "time_us", "rnti", "lcid", "pkt_id", "tb_size", "rv"
    },
    "NrUlMacStats.txt": {"time_us", "rnti", "send_start_time_delta_us", "msg_type"},
    "UePhyCtrlTxTrace.txt": {
        "time_us",
        "rnti",
        "frame",
        "subframe",
        "slot",
        "msg_type",
    },
    "UeMacSrTriggerTrace.txt": {"time_us", "rnti", "sr_type"},
}
PACKET_TRACE_FILES = {
    "NrUlPdcpRxStats.txt",
    "NrUlRlcRxComponentStats.txt",
    "NrUlRlcTxComponentStats.txt",
    "NrUlPdcpTxStats.txt",
    "RlcTxQueueSojournTrace.txt",
    "RlcHolGrantWaitTrace.txt",
}
LENA_DELAY_DECOMPOSITION_CSV = "5Glena_delay_decomposition.csv"
PACKET_KEYS = ["rnti", "lcid", "pkt_id"]
SR_TRIGGER_MATCH_TOLERANCE_US = 7_000
RLC_GRANT_MATCH_TOLERANCE_US = 100
TB_GRANT_MATCH_TOLERANCE_US = 1_000
EXPECA_VIRTUAL_DEQUEUE_LEAD_US = 1_000
DEFAULT_JOBS = min(4, os.cpu_count() or 1)
NR_FRAME_US = 10_000
NR_SUBFRAME_US = 1_000
NR_SLOTS_PER_SUBFRAME = (16, 8, 4, 2, 1)

def load_tsv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, sep=r"\s+")

def filter_data_only(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Filter to identifiable data traffic using msg_type, LCID, and pkt_id."""
    if df is None:
        return df
    if "msg_type" in df.columns:
        df = df[df["msg_type"].astype(str).str.upper() == "DATA"]
    if "lcid" in df.columns:
        df = df[df["lcid"] >= DRB_LCID_MIN]
    if "pkt_id" in df.columns:
        pkt_id = pd.to_numeric(df["pkt_id"], errors="coerce")
        df = df[pkt_id > 0]
    return df


def match_rlc_components_to_pusch(
    df_ul_rlc_tx: pd.DataFrame | None,
    df_ul_mac: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Attach the scheduled PUSCH start to each RLC component transmission."""
    if df_ul_rlc_tx is None or df_ul_mac is None:
        return None

    tx = df_ul_rlc_tx.rename(columns={"time_us": "rlc_tx_time_us"}).sort_values(
        ["rlc_tx_time_us", "rnti"]
    )
    grants = df_ul_mac[
        df_ul_mac["msg_type"].astype(str).str.upper() == "DATA"
    ][["time_us", "rnti", "send_start_time_delta_us"]].rename(
        columns={"time_us": "grant_time_us"}
    ).sort_values(["grant_time_us", "rnti"])

    if tx.empty or grants.empty:
        return None

    matched = pd.merge_asof(
        tx,
        grants,
        left_on="rlc_tx_time_us",
        right_on="grant_time_us",
        by="rnti",
        direction="backward",
        tolerance=RLC_GRANT_MATCH_TOLERANCE_US,
    )
    matched["pusch_tx_time_us"] = (
        matched["grant_time_us"] + matched["send_start_time_delta_us"]
    )
    virtual_dequeue = (
        matched["pusch_tx_time_us"] - EXPECA_VIRTUAL_DEQUEUE_LEAD_US
    )
    matched["virtual_dequeue_time_us"] = virtual_dequeue.where(
        virtual_dequeue >= matched["rlc_tx_time_us"],
        matched["rlc_tx_time_us"],
    )
    return matched


def build_packet_radio_resources(
    df_tb_components: pd.DataFrame | None,
    df_ul_mac: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Aggregate initial TBS and all-attempt PRBs for each packet."""
    if df_tb_components is None or df_ul_mac is None:
        return None

    attempts = filter_data_only(df_tb_components)
    grants = df_ul_mac[
        df_ul_mac["msg_type"].astype(str).str.upper() == "DATA"
    ].copy()
    required_grant_columns = {
        "time_us", "rnti", "send_start_time_delta_us", "num_prbs"
    }
    if attempts.empty or grants.empty or not required_grant_columns.issubset(grants.columns):
        return None

    attempts = attempts[[*PACKET_KEYS, "time_us", "tb_size", "rv"]].copy()
    for column in [*PACKET_KEYS, "time_us", "tb_size", "rv"]:
        attempts[column] = pd.to_numeric(attempts[column], errors="coerce")
    attempts = attempts.dropna().drop_duplicates([*PACKET_KEYS, "time_us"])

    for column in ["time_us", "rnti", "send_start_time_delta_us", "num_prbs"]:
        grants[column] = pd.to_numeric(grants[column], errors="coerce")
    grants = grants.dropna(subset=required_grant_columns)
    grants["pusch_tx_time_us"] = (
        grants["time_us"] + grants["send_start_time_delta_us"]
    ).astype(float)
    attempts["time_us"] = attempts["time_us"].astype(float)

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
    ).dropna(subset=["num_prbs"])
    if matched.empty:
        return None

    matched["initial_tb_size"] = matched["tb_size"].where(matched["rv"] == 0, 0)
    return matched.groupby(PACKET_KEYS, as_index=False).agg(
        transport_block_size_total_bytes=("initial_tb_size", "sum"),
        resource_block_size_total=("num_prbs", "sum"),
    )


def match_delay_probe_packet_keys(
    candidates: pd.DataFrame,
    delay_trace: pd.DataFrame | None,
) -> tuple[pd.DataFrame, int]:
    """Return packet keys matched to UL probe receptions in delay_trace.txt."""
    if delay_trace is None:
        raise ValueError("--delay-probes-only requires delay_trace.txt")

    required_trace_cols = {
        "time_us",
        "tx_time_us",
        "direction",
        "rnti",
        "pkt_size",
    }
    missing_trace_cols = sorted(required_trace_cols.difference(delay_trace.columns))
    if missing_trace_cols:
        raise ValueError(f"delay_trace.txt missing columns: {missing_trace_cols}")

    required_candidate_cols = {
        *PACKET_KEYS,
        "pkt_size_bytes",
        "pdcp_rx_time_us",
        "ran_delay_ms",
    }
    missing_candidate_cols = sorted(
        required_candidate_cols.difference(candidates.columns)
    )
    if missing_candidate_cols:
        raise ValueError(
            "PDCP packet table missing columns needed for probe matching: "
            f"{missing_candidate_cols}"
        )

    probes = delay_trace[
        delay_trace["direction"].astype(str).str.upper() == "UL"
    ][["time_us", "tx_time_us", "rnti", "pkt_size"]].copy()
    probes = probes.rename(
        columns={
            "time_us": "probe_rx_time_us",
            "tx_time_us": "probe_tx_time_us",
        }
    )
    for column in ["probe_rx_time_us", "probe_tx_time_us", "rnti", "pkt_size"]:
        probes[column] = pd.to_numeric(probes[column], errors="coerce")
    probes = probes.dropna(
        subset=["probe_rx_time_us", "probe_tx_time_us", "rnti", "pkt_size"]
    )
    probes["probe_tx_time_us"] = probes["probe_tx_time_us"].astype(float)
    probes["probe_rx_time_us"] = probes["probe_rx_time_us"].astype(float)
    probes["pkt_size_bytes"] = (
        probes["pkt_size"] + DELAY_PROBE_PDCP_OVERHEAD_BYTES
    )
    if probes.empty or candidates.empty:
        return pd.DataFrame(columns=PACKET_KEYS), len(probes)

    candidates = candidates.copy()
    for column in ["rnti", "pkt_size_bytes", "pdcp_rx_time_us", "ran_delay_ms"]:
        candidates[column] = pd.to_numeric(candidates[column], errors="coerce")
    candidates = candidates.dropna(
        subset=[
            *PACKET_KEYS,
            "pkt_size_bytes",
            "pdcp_rx_time_us",
            "ran_delay_ms",
        ]
    )
    candidates["pdcp_tx_time_us"] = (
        candidates["pdcp_rx_time_us"] - candidates["ran_delay_ms"] * 1000.0
    )
    candidates["pdcp_tx_time_us"] = candidates["pdcp_tx_time_us"].astype(float)
    candidates["pdcp_rx_time_us"] = candidates["pdcp_rx_time_us"].astype(float)

    matched_keys = []
    for (rnti, packet_size), probe_group in probes.groupby(
        ["rnti", "pkt_size_bytes"], sort=False
    ):
        candidate_group = candidates[
            (candidates["rnti"] == rnti)
            & (candidates["pkt_size_bytes"] == packet_size)
        ]
        if candidate_group.empty:
            continue
        matched = pd.merge_asof(
            probe_group[
                ["probe_tx_time_us", "probe_rx_time_us"]
            ].sort_values("probe_tx_time_us"),
            candidate_group[
                [*PACKET_KEYS, "pdcp_tx_time_us", "pdcp_rx_time_us"]
            ].sort_values(
                "pdcp_tx_time_us"
            ),
            left_on="probe_tx_time_us",
            right_on="pdcp_tx_time_us",
            direction="nearest",
            tolerance=DELAY_PROBE_MATCH_TOLERANCE_US,
        ).dropna(subset=PACKET_KEYS)
        matched = matched[
            matched["probe_rx_time_us"].between(
                matched["pdcp_rx_time_us"],
                matched["pdcp_rx_time_us"] + DELAY_PROBE_MATCH_TOLERANCE_US,
            )
        ]
        if not matched.empty:
            matched_keys.append(matched[PACKET_KEYS])

    if not matched_keys:
        return pd.DataFrame(columns=PACKET_KEYS), len(probes)

    keys = (
        pd.concat(matched_keys, ignore_index=True)
        .drop_duplicates(subset=PACKET_KEYS, keep="first")
    )
    return keys, len(probes)


def filter_to_packet_keys(
    table: pd.DataFrame | None,
    packet_keys: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Keep rows belonging to selected packet keys when a filter is active."""
    if table is None or packet_keys is None:
        return table
    if not set(PACKET_KEYS).issubset(table.columns):
        return table
    return table.merge(packet_keys, on=PACKET_KEYS, how="inner")


def add_sr_opportunity_time(sr: pd.DataFrame) -> pd.DataFrame:
    """Derive the start of the SR slot from its SFN fields and PHY timestamp."""
    frame_start = sr["frame"] * NR_FRAME_US + sr["subframe"] * NR_SUBFRAME_US
    elapsed = sr["time_us"] - frame_start
    for slots_per_subframe in NR_SLOTS_PER_SUBFRAME:
        slot_duration_us = NR_SUBFRAME_US / slots_per_subframe
        offset = elapsed - sr["slot"] * slot_duration_us
        valid = (
            (sr["slot"] < slots_per_subframe)
            & (offset >= -1)
            & (offset < slot_duration_us + 1)
        )
        if valid.all():
            sr["sr_opportunity_time_us"] = (
                frame_start + sr["slot"] * slot_duration_us
            )
            return sr
    raise ValueError("Cannot infer slot duration from UePhyCtrlTxTrace SR timestamps")


def match_sr_triggers(
    df_ue_phy_ctrl: pd.DataFrame | None,
    df_ue_mac_sr_trigger: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Match transmitted SRs to preceding MAC triggers one-to-one in time order."""
    if df_ue_phy_ctrl is None or df_ue_mac_sr_trigger is None:
        return None

    sr = df_ue_phy_ctrl[
        df_ue_phy_ctrl["msg_type"].astype(str).str.upper() == "SR"
    ][["time_us", "rnti", "frame", "subframe", "slot"]].copy()
    triggers = df_ue_mac_sr_trigger[["time_us", "rnti", "sr_type"]].copy()
    for column in ["time_us", "rnti", "frame", "subframe", "slot"]:
        sr[column] = pd.to_numeric(sr[column], errors="coerce")
    sr.dropna(subset=["time_us", "rnti", "frame", "subframe", "slot"], inplace=True)
    sr = add_sr_opportunity_time(sr)
    for column in ["time_us", "rnti"]:
        triggers[column] = pd.to_numeric(triggers[column], errors="coerce")
    triggers.dropna(subset=["time_us", "rnti"], inplace=True)
    triggers["sr_type"] = triggers["sr_type"].astype(str).str.upper()
    triggers = triggers[triggers["sr_type"].isin(["INITIAL", "RECOVERY"])]

    if sr.empty or triggers.empty:
        return pd.DataFrame(
            columns=[
                "time_us",
                "sr_opportunity_time_us",
                "rnti",
                "trigger_time_us",
                "sr_type",
            ]
        )

    sr_groups = {
        rnti: group.sort_values("time_us").reset_index(drop=True)
        for rnti, group in sr.groupby("rnti")
    }
    trigger_groups = {
        rnti: group.sort_values("time_us").reset_index(drop=True)
        for rnti, group in triggers.groupby("rnti")
    }
    matches: list[dict[str, object]] = []

    # Work backwards so a later SR claims the latest eligible trigger. This
    # preserves one-to-one ordering when a recovery and a new initial trigger
    # are both pending before the next two UL-control opportunities.
    for rnti in sorted(set(sr_groups).intersection(trigger_groups)):
        sr_group = sr_groups[rnti]
        trigger_group = trigger_groups[rnti]
        sr_idx = len(sr_group) - 1
        trigger_idx = len(trigger_group) - 1

        while sr_idx >= 0 and trigger_idx >= 0:
            sr_time_us = sr_group.at[sr_idx, "time_us"]
            sr_opportunity_time_us = sr_group.at[sr_idx, "sr_opportunity_time_us"]
            trigger_time_us = trigger_group.at[trigger_idx, "time_us"]

            if trigger_time_us > sr_opportunity_time_us:
                trigger_idx -= 1
            elif (
                sr_opportunity_time_us - trigger_time_us
                <= SR_TRIGGER_MATCH_TOLERANCE_US
            ):
                matches.append(
                    {
                        "time_us": sr_time_us,
                        "sr_opportunity_time_us": sr_opportunity_time_us,
                        "rnti": rnti,
                        "trigger_time_us": trigger_time_us,
                        "sr_type": trigger_group.at[trigger_idx, "sr_type"],
                    }
                )
                sr_idx -= 1
                trigger_idx -= 1
            else:
                sr_idx -= 1

    if not matches:
        return pd.DataFrame(
            columns=[
                "time_us",
                "sr_opportunity_time_us",
                "rnti",
                "trigger_time_us",
                "sr_type",
            ]
        )
    return (
        pd.DataFrame(matches)
        .sort_values(["time_us", "rnti"])
        .reset_index(drop=True)
    )


def build_sr_delay_components(
    df_initial_sr: pd.DataFrame | None,
    df_ul_pdcp_tx: pd.DataFrame | None,
    df_rlc_segments_per_pkt: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Build both SR-derived delays from one strict packet-to-initial-SR match."""
    if (
        df_initial_sr is None
        or df_ul_pdcp_tx is None
        or df_rlc_segments_per_pkt is None
    ):
        return None

    sr = df_initial_sr[
        ["time_us", "sr_opportunity_time_us", "trigger_time_us", "rnti"]
    ].rename(columns={"time_us": "sr_time_us"}).copy()
    pdcp_tx = df_ul_pdcp_tx[
        ["time_us", "rnti", "lcid", "pkt_id"]
    ].rename(columns={"time_us": "pdcp_tx_time_us"}).copy()
    first_rlc_tx = df_rlc_segments_per_pkt[
        ["first_rlc_tx_time_us", "rnti", "lcid", "pkt_id"]
    ].copy()
    for frame, required in (
        (
            sr,
            ["sr_time_us", "sr_opportunity_time_us", "trigger_time_us", "rnti"],
        ),
        (pdcp_tx, ["pdcp_tx_time_us", *PACKET_KEYS]),
        (first_rlc_tx, ["first_rlc_tx_time_us", *PACKET_KEYS]),
    ):
        for col in required:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame.dropna(subset=required, inplace=True)

    if sr.empty or pdcp_tx.empty or first_rlc_tx.empty:
        return None

    pdcp_tx = (
        pdcp_tx.sort_values("pdcp_tx_time_us")
        .drop_duplicates(subset=PACKET_KEYS, keep="first")
    )
    first_rlc_tx = (
        first_rlc_tx.sort_values("first_rlc_tx_time_us")
        .drop_duplicates(subset=PACKET_KEYS, keep="first")
    )

    # Attribute each initial SR trigger to the latest packet that had reached
    # PDCP for that UE. The SR and first DCI/RLC transmission opportunity must
    # then both occur inside that packet's queueing interval.
    matched = pd.merge_asof(
        sr.sort_values("trigger_time_us"),
        pdcp_tx.sort_values("pdcp_tx_time_us"),
        left_on="trigger_time_us",
        right_on="pdcp_tx_time_us",
        by="rnti",
        direction="backward",
    ).dropna(subset=["pdcp_tx_time_us", "lcid", "pkt_id"])
    matched = pd.merge(matched, first_rlc_tx, on=PACKET_KEYS, how="inner")
    matched = matched[
        (matched["pdcp_tx_time_us"] <= matched["trigger_time_us"])
        & (matched["trigger_time_us"] <= matched["sr_opportunity_time_us"])
        & (matched["sr_opportunity_time_us"] <= matched["sr_time_us"])
        & (matched["sr_time_us"] <= matched["first_rlc_tx_time_us"])
    ].copy()
    if matched.empty:
        return matched

    # A packet can appear beside more than one trigger in pathological cases.
    # Keep the first usable initial SR and never reuse a packet in the output.
    matched = (
        matched.sort_values(["sr_time_us", "trigger_time_us"])
        .drop_duplicates(subset=PACKET_KEYS, keep="first")
    )
    matched["frame_alignment_delay_ms"] = (
        matched["sr_opportunity_time_us"] - matched["pdcp_tx_time_us"]
    ) / 1000.0
    matched["scheduling_delay_ms"] = (
        matched["first_rlc_tx_time_us"] - matched["pdcp_tx_time_us"]
    ) / 1000.0
    return matched[
        [
            *PACKET_KEYS,
            "pdcp_tx_time_us",
            "trigger_time_us",
            "sr_opportunity_time_us",
            "sr_time_us",
            "first_rlc_tx_time_us",
            "frame_alignment_delay_ms",
            "scheduling_delay_ms",
        ]
    ].sort_values("first_rlc_tx_time_us")


def build_queueing_delay(
    df_ul_pdcp_tx: pd.DataFrame | None,
    df_rlc_segments_per_pkt: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Measure PDCP-to-EXPECA-aligned virtual dequeue delay per packet."""
    if df_ul_pdcp_tx is None or df_rlc_segments_per_pkt is None:
        return None

    pdcp_tx = df_ul_pdcp_tx[
        ["time_us", "rnti", "lcid", "pkt_id"]
    ].rename(columns={"time_us": "pdcp_tx_time_us"}).copy()
    first_virtual_dequeue = df_rlc_segments_per_pkt[
        ["first_virtual_dequeue_time_us", "rnti", "lcid", "pkt_id"]
    ].copy()
    for frame, time_col in (
        (pdcp_tx, "pdcp_tx_time_us"),
        (first_virtual_dequeue, "first_virtual_dequeue_time_us"),
    ):
        for col in [time_col, *PACKET_KEYS]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame.dropna(subset=[time_col, *PACKET_KEYS], inplace=True)
        frame.sort_values(time_col, inplace=True)
        frame.drop_duplicates(subset=PACKET_KEYS, keep="first", inplace=True)

    queueing = pd.merge(
        pdcp_tx,
        first_virtual_dequeue,
        on=PACKET_KEYS,
        how="inner",
    )
    queueing["queueing_delay_us"] = (
        queueing["first_virtual_dequeue_time_us"]
        - queueing["pdcp_tx_time_us"]
    )
    queueing = queueing[queueing["queueing_delay_us"] >= 0]
    queueing["queueing_delay_ms"] = queueing["queueing_delay_us"] / 1000.0
    return queueing.sort_values("first_virtual_dequeue_time_us")


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


def load_trace(
    input_dir: Path,
    filename: str,
    packet_keys: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """Load and validate a trace, optionally filtering it to selected packets."""
    trace = load_tsv(input_dir / filename)
    if filename in PACKET_TRACE_FILES:
        trace = filter_data_only(trace)
    trace = require_optional_columns(trace, filename, TRACE_REQUIRED_COLUMNS[filename])
    return filter_to_packet_keys(trace, packet_keys)


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


def merge_metric_column(base: pd.DataFrame,
                        metric: pd.DataFrame | None,
                        columns: list[str]) -> pd.DataFrame:
    if metric is None or metric.empty:
        return base
    keys = [col for col in PACKET_KEYS if col in base.columns and col in metric.columns]
    if not {"rnti", "pkt_id"}.issubset(keys):
        return base
    available = keys + [col for col in columns if col in metric.columns]
    return base.merge(
        metric[available].drop_duplicates(subset=keys, keep="first"),
        on=keys,
        how="left",
    )


def build_pdcp_packet_table(df_ul_pdcp_rx: pd.DataFrame | None) -> pd.DataFrame:
    """Build the canonical one-row-per-packet table from receiver PDCP logs."""
    if df_ul_pdcp_rx is None:
        return pd.DataFrame(columns=PACKET_KEYS)

    pdcp_rx = df_ul_pdcp_rx[
        ["rnti", "lcid", "pkt_id", "packet_size", "time_us", "delay_us"]
    ].copy()
    for col in ["rnti", "lcid", "pkt_id", "packet_size", "time_us", "delay_us"]:
        pdcp_rx[col] = pd.to_numeric(pdcp_rx[col], errors="coerce")
    pdcp_rx = pdcp_rx.dropna(
        subset=["rnti", "lcid", "pkt_id", "time_us", "delay_us"]
    )
    if pdcp_rx.empty:
        return pd.DataFrame(columns=PACKET_KEYS)

    pdcp_rx["pdcp_rx_time_us"] = pdcp_rx["time_us"]
    pdcp_rx["ran_delay_ms"] = pdcp_rx["delay_us"] / 1000.0
    pdcp_rx = pdcp_rx.rename(columns={"packet_size": "pkt_size_bytes"})
    return (
        pdcp_rx[
            [
                "rnti",
                "lcid",
                "pkt_id",
                "pkt_size_bytes",
                "pdcp_rx_time_us",
                "ran_delay_ms",
            ]
        ]
        .sort_values("pdcp_rx_time_us")
        .drop_duplicates(subset=PACKET_KEYS, keep="first")
    )


def build_lena_delay_decomposition_table(
    df_ul_pdcp_rx: pd.DataFrame | None,
    df_pregrant_grant_wait: pd.DataFrame | None,
    df_queueing_delay: pd.DataFrame | None,
    df_sr_delay_components: pd.DataFrame | None,
    df_ul_rlc_plot: pd.DataFrame | None,
    df_link_delay: pd.DataFrame | None,
    df_segmentation_delay: pd.DataFrame | None,
    df_reordering_delay: pd.DataFrame | None,
    df_rlc_segments_per_pkt: pd.DataFrame | None,
    df_packet_radio_resources: pd.DataFrame | None,
) -> pd.DataFrame:
    table = build_pdcp_packet_table(df_ul_pdcp_rx)

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
        ],
    )
    table = merge_metric_column(
        table,
        df_queueing_delay,
        ["queueing_delay_ms"],
    )
    table = merge_metric_column(
        table,
        df_sr_delay_components,
        ["frame_alignment_delay_ms", "scheduling_delay_ms"],
    )
    table = merge_metric_column(
        table,
        df_ul_rlc_plot,
        ["delay_ms"],
    ).rename(columns={"delay_ms": "tx_retx_delay_ms"})
    table = merge_metric_column(
        table,
        df_link_delay,
        ["link_delay_ms"],
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
        ["rlc_segments_per_pkt"],
    )
    table = merge_metric_column(
        table,
        df_packet_radio_resources,
        ["transport_block_size_total_bytes", "resource_block_size_total"],
    )

    table = table.rename(
        columns={
            "pkt_size": "pkt_size_bytes",
        }
    )
    residual_cols = {
        "ran_delay_ms",
        "queueing_delay_ms",
        "link_delay_ms",
        "reordering_delay_ms",
    }
    if residual_cols.issubset(table.columns):
        table["delay_residual_ms"] = (
            table["ran_delay_ms"]
            - (
                table["queueing_delay_ms"]
                + table["link_delay_ms"]
                + table["reordering_delay_ms"]
            )
        )
    ordered_cols = [
        "rnti",
        "lcid",
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
        "transport_block_size_total_bytes",
        "resource_block_size_total",
    ]
    existing_ordered = [col for col in ordered_cols if col in table.columns]
    return table[existing_ordered].sort_values(PACKET_KEYS)


def load_lena_delay_decomposition(
    input_dir: Path,
    delay_probes_only: bool = False,
) -> pd.DataFrame | None:
    if not has_required_logs(input_dir):
        print(f"WARN: skipping {input_dir}, no known log files found")
        return None

    packet_keys = None
    probe_count = None
    try:
        df_ul_pdcp_rx = load_trace(input_dir, "NrUlPdcpRxStats.txt")
        if delay_probes_only:
            packet_keys, probe_count = match_delay_probe_packet_keys(
                build_pdcp_packet_table(df_ul_pdcp_rx),
                load_tsv(input_dir / "delay_trace.txt"),
            )
            df_ul_pdcp_rx = filter_to_packet_keys(df_ul_pdcp_rx, packet_keys)

        df_ul_rlc = load_trace(input_dir, "NrUlRlcRxComponentStats.txt", packet_keys)
        df_ul_rlc_tx = load_trace(input_dir, "NrUlRlcTxComponentStats.txt", packet_keys)
        df_ul_pdcp_tx = load_trace(input_dir, "NrUlPdcpTxStats.txt", packet_keys)
        df_rlc_sojourn = load_trace(input_dir, "RlcTxQueueSojournTrace.txt", packet_keys)
        df_rlc_hol_wait = load_trace(input_dir, "RlcHolGrantWaitTrace.txt", packet_keys)
        df_tb_components = load_trace(input_dir, "UlRxTbComponentTrace.txt", packet_keys)
        df_ul_mac = load_trace(input_dir, "NrUlMacStats.txt")
        df_ue_phy_ctrl = load_trace(input_dir, "UePhyCtrlTxTrace.txt")
        df_ue_mac_sr_trigger = load_trace(input_dir, "UeMacSrTriggerTrace.txt")
    except ValueError as exc:
        print(f"WARN: skipping {input_dir}, {exc}")
        return None

    if df_ul_pdcp_rx is not None:
        df_ul_pdcp_rx["ran_delay_ms"] = pd.to_numeric(df_ul_pdcp_rx["delay_us"], errors="coerce") / 1000.0

    if df_rlc_sojourn is not None:
        df_rlc_sojourn["pre_hol_wait_ms"] = df_rlc_sojourn["pre_hol_wait_us"] / 1000.0

    if df_rlc_hol_wait is not None:
        df_rlc_hol_wait["hol_wait_ms"] = df_rlc_hol_wait["hol_grant_wait_us"] / 1000.0
        df_rlc_hol_wait = (
            df_rlc_hol_wait.sort_values("time_us")
            .drop_duplicates(subset=PACKET_KEYS, keep="first")
        )

    df_sr = match_sr_triggers(df_ue_phy_ctrl, df_ue_mac_sr_trigger)
    if df_ue_phy_ctrl is not None and df_ue_mac_sr_trigger is None:
        print(
            f"WARN: {input_dir} has no UeMacSrTriggerTrace.txt; "
            "frame-alignment and scheduling-delay metrics will be omitted"
        )
    elif df_ue_phy_ctrl is not None and df_sr is not None:
        phy_sr_count = int(
            (
                df_ue_phy_ctrl["msg_type"].astype(str).str.upper() == "SR"
            ).sum()
        )
        if len(df_sr) != phy_sr_count:
            print(
                f"WARN: {input_dir} matched {len(df_sr)} of {phy_sr_count} PHY SRs "
                "one-to-one to preceding UE-MAC triggers within "
                f"{SR_TRIGGER_MATCH_TOLERANCE_US} us"
            )
    df_initial_sr = None
    if df_sr is not None:
        df_initial_sr = df_sr[df_sr["sr_type"] == "INITIAL"].copy()

    df_pregrant_grant_wait = None
    if df_rlc_sojourn is not None and df_rlc_hol_wait is not None:
        soj = (
            df_rlc_sojourn.copy()
            .sort_values("time_us")
            .drop_duplicates(subset=PACKET_KEYS, keep="last")
            [["rnti", "lcid", "pkt_id", "pre_hol_wait_ms", "time_us"]]
            .rename(columns={"time_us": "soj_time_us"})
        )
        hol = (
            df_rlc_hol_wait.copy()
            .sort_values("time_us")
            .drop_duplicates(subset=PACKET_KEYS, keep="first")
            [["rnti", "lcid", "pkt_id", "hol_wait_ms", "time_us"]]
            .rename(columns={"time_us": "hol_time_us"})
        )
        df_pregrant_grant_wait = pd.merge(soj, hol, on=PACKET_KEYS, how="inner")
        if not df_pregrant_grant_wait.empty:
            df_pregrant_grant_wait["time_us"] = df_pregrant_grant_wait["hol_time_us"]
            df_pregrant_grant_wait = df_pregrant_grant_wait.sort_values("time_us")

    df_ul_rlc_tx_pusch = match_rlc_components_to_pusch(df_ul_rlc_tx, df_ul_mac)
    if df_ul_rlc_tx is not None and df_ul_mac is None:
        print(
            f"WARN: {input_dir} has no NrUlMacStats.txt; PUSCH-based queueing, "
            "scheduling, transmission, link, and segmentation delays will be omitted"
        )
    elif df_ul_rlc_tx_pusch is not None:
        matched_count = int(df_ul_rlc_tx_pusch["pusch_tx_time_us"].notna().sum())
        if matched_count != len(df_ul_rlc_tx_pusch):
            print(
                f"WARN: {input_dir} matched {matched_count} of "
                f"{len(df_ul_rlc_tx_pusch)} RLC TX components to same-RNTI DATA "
                "grants within "
                f"{RLC_GRANT_MATCH_TOLERANCE_US} us"
            )

    df_rlc_segments_per_pkt = None
    if df_ul_rlc_tx_pusch is not None:
        tx_comp = df_ul_rlc_tx_pusch[
            [
                *PACKET_KEYS,
                "rlc_sn",
                "rlc_tx_time_us",
                "virtual_dequeue_time_us",
                "pusch_tx_time_us",
            ]
        ].dropna().copy()
        if not tx_comp.empty:
            df_rlc_segments_per_pkt = (
                tx_comp.groupby(PACKET_KEYS, as_index=False)
                .agg(
                    first_rlc_tx_time_us=("rlc_tx_time_us", "min"),
                    first_virtual_dequeue_time_us=(
                        "virtual_dequeue_time_us",
                        "min",
                    ),
                    rlc_segments_per_pkt=("rlc_sn", "nunique"),
                )
            )

    rx = None
    if df_ul_rlc is not None:
        rx = df_ul_rlc[
            [*PACKET_KEYS, "rlc_sn", "time_us", "delay_us"]
        ].copy()
        for column in [*PACKET_KEYS, "rlc_sn", "time_us", "delay_us"]:
            rx[column] = pd.to_numeric(rx[column], errors="coerce")
        rx = rx.dropna()

    df_ul_rlc_plot = None
    if rx is not None and df_ul_rlc_tx_pusch is not None:
        tx_times = (
            df_ul_rlc_tx_pusch[
                [
                    *PACKET_KEYS,
                    "rlc_sn",
                    "rlc_tx_time_us",
                    "virtual_dequeue_time_us",
                ]
            ]
            .dropna()
        )
        corrected = pd.merge(
            rx,
            tx_times,
            on=[*PACKET_KEYS, "rlc_sn"],
            how="inner",
        )
        corrected["delay_ms"] = (
            corrected["delay_us"]
            - (
                corrected["virtual_dequeue_time_us"]
                - corrected["rlc_tx_time_us"]
            )
        ) / 1000.0
        if not corrected.empty:
            idx = corrected.groupby(PACKET_KEYS)["delay_ms"].idxmax()
            df_ul_rlc_plot = corrected.loc[idx]

    df_link_delay = None
    if df_rlc_segments_per_pkt is not None and rx is not None:
        first_virtual_dequeue = df_rlc_segments_per_pkt[
            [*PACKET_KEYS, "first_virtual_dequeue_time_us"]
        ]
        last_rlc_rx = (
            rx
            .groupby(PACKET_KEYS, as_index=False)["time_us"]
            .max()
            .rename(columns={"time_us": "last_rlc_rx_time_us"})
        )
        df_link_delay = pd.merge(
            first_virtual_dequeue,
            last_rlc_rx,
            on=PACKET_KEYS,
            how="inner",
        )
        if not df_link_delay.empty:
            df_link_delay["link_delay_us"] = (
                df_link_delay["last_rlc_rx_time_us"]
                - df_link_delay["first_virtual_dequeue_time_us"]
            )
            df_link_delay["link_delay_ms"] = (
                df_link_delay["link_delay_us"] / 1000.0
            )

    df_segmentation_delay = None
    if df_link_delay is not None and df_ul_rlc_plot is not None:
        link = df_link_delay[[*PACKET_KEYS, "link_delay_ms"]]
        txretx = df_ul_rlc_plot[[*PACKET_KEYS, "delay_ms"]].rename(
            columns={"delay_ms": "tx_retx_delay_ms"}
        )
        df_segmentation_delay = pd.merge(link, txretx, on=PACKET_KEYS, how="inner")
        if not df_segmentation_delay.empty:
            df_segmentation_delay["segmentation_delay_ms"] = (
                df_segmentation_delay["link_delay_ms"]
                - df_segmentation_delay["tx_retx_delay_ms"]
            )

    df_sr_delay_components = build_sr_delay_components(
        df_initial_sr,
        df_ul_pdcp_tx,
        df_rlc_segments_per_pkt,
    )
    df_queueing_delay = build_queueing_delay(df_ul_pdcp_tx, df_rlc_segments_per_pkt)
    df_packet_radio_resources = build_packet_radio_resources(df_tb_components, df_ul_mac)

    df_reordering_delay = None
    if df_ul_rlc is not None and df_ul_pdcp_rx is not None:
        rlc_rx = df_ul_rlc[["rnti", "lcid", "pkt_id", "time_us"]].copy()
        pdcp_rx = df_ul_pdcp_rx[["rnti", "lcid", "pkt_id", "time_us"]].copy()
        for col in ["rnti", "lcid", "pkt_id", "time_us"]:
            rlc_rx[col] = pd.to_numeric(rlc_rx[col], errors="coerce")
            pdcp_rx[col] = pd.to_numeric(pdcp_rx[col], errors="coerce")
        rlc_rx = rlc_rx.dropna(subset=["rnti", "lcid", "pkt_id", "time_us"])
        pdcp_rx = pdcp_rx.dropna(subset=["rnti", "lcid", "pkt_id", "time_us"])
        if not rlc_rx.empty and not pdcp_rx.empty:
            rlc_last = (
                rlc_rx.sort_values("time_us")
                .groupby(PACKET_KEYS, as_index=False)["time_us"]
                .max()
                .rename(columns={"time_us": "last_rlc_rx_time_us"})
            )
            pdcp_first = (
                pdcp_rx.sort_values("time_us")
                .groupby(PACKET_KEYS, as_index=False)["time_us"]
                .min()
                .rename(columns={"time_us": "pdcp_rx_time_us"})
            )
            df_reordering_delay = pd.merge(rlc_last, pdcp_first, on=PACKET_KEYS, how="inner")
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

    table = build_lena_delay_decomposition_table(
        df_ul_pdcp_rx,
        df_pregrant_grant_wait,
        df_queueing_delay,
        df_sr_delay_components,
        df_ul_rlc_plot,
        df_link_delay,
        df_segmentation_delay,
        df_reordering_delay,
        df_rlc_segments_per_pkt,
        df_packet_radio_resources,
    )
    if delay_probes_only and len(table) != probe_count:
        print(
            f"WARN: {input_dir} matched {len(table)} of {probe_count} UL delay probes "
            "to decomposed PDCP packets within "
            f"{DELAY_PROBE_MATCH_TOLERANCE_US} us"
        )
    return table


def write_lena_delay_decomposition_csv(
    lena_run_dir: Path,
    csv_output_dir: Path,
    delay_probes_only: bool = False,
) -> None:
    delay_decomposition = load_lena_delay_decomposition(
        lena_run_dir,
        delay_probes_only=delay_probes_only,
    )
    if delay_decomposition is None:
        print(f"WARN: skipping {lena_run_dir.name}, unusable 5G-LENA logs: {lena_run_dir}")
        return

    csv_output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_output_dir / f"{lena_run_dir.name}_{LENA_DELAY_DECOMPOSITION_CSV}"
    delay_decomposition.to_csv(csv_path, index=False)
    print(f"Wrote 5G-LENA delay decomposition CSV for {lena_run_dir.name} to {csv_path}")


def main():
    start_time = perf_counter()
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
    parser.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_JOBS,
        help=f"Maximum parallel run workers (default: {DEFAULT_JOBS}).",
    )
    parser.add_argument(
        "--delay-probes-only",
        action="store_true",
        help=(
            "Include only UL delay-probe packets matched through delay_trace.txt; "
            "exclude other data traffic."
        ),
    )
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")

    lena_dir = Path(args.lena_dir).resolve()
    lena_runs = find_run_dirs(lena_dir)
    if not lena_runs:
        print(f"WARN: no 5G-LENA run directories found under {lena_dir}")
        print(f"Total runtime: {perf_counter() - start_time:.2f} seconds")
        return 0

    csv_output_dir = Path(args.output_dir).resolve()
    csv_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing 5G-LENA delay decomposition CSVs under: {csv_output_dir}")
    print(
        "NOTE: SR trigger matching tolerance is "
        f"{SR_TRIGGER_MATCH_TOLERANCE_US} us. If the TDD pattern increases the time "
        "between UL-control opportunities, this tolerance may need to be increased."
    )
    workers = min(args.jobs, len(lena_runs))
    print(f"Processing {len(lena_runs)} run(s) with {workers} worker(s)")
    if workers == 1:
        for lena_run_dir in sorted(lena_runs):
            write_lena_delay_decomposition_csv(
                lena_run_dir,
                csv_output_dir,
                delay_probes_only=args.delay_probes_only,
            )
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            list(
                executor.map(
                    write_lena_delay_decomposition_csv,
                    sorted(lena_runs),
                    repeat(csv_output_dir),
                    repeat(args.delay_probes_only),
                )
            )

    print(f"Total runtime: {perf_counter() - start_time:.2f} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
