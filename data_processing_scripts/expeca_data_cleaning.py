import heapq

import numpy as np
import pandas as pd


PRIMARY_DELAY_COLUMNS = (
    "Queuing delay",
    "Transmission delay",
    "Retransmission delay",
    "segmentation delay",
)


def derive_fresh_backlog(
    ip_packets: pd.DataFrame,
    ip_rlc_relations: pd.DataFrame,
    rlc_segments: pd.DataFrame,
) -> pd.DataFrame:
    """Return whether older unsent bytes existed at each packet's RLC enqueue."""
    initial_segments = ip_rlc_relations[["ip_id", "txpdu_id"]].merge(
        rlc_segments[
            [
                "txpdu_id",
                "rlc.txpdu.timestamp",
                "rlc.txpdu.retx",
                "mac.sdu.lcid",
            ]
        ],
        on="txpdu_id",
        how="left",
    )
    retransmission = pd.to_numeric(
        initial_segments["rlc.txpdu.retx"], errors="coerce"
    ).fillna(0)
    initial_segments = initial_segments.loc[retransmission.eq(0)]

    packet_service = initial_segments.groupby("ip_id", as_index=False).agg(
        last_initial_tx=("rlc.txpdu.timestamp", "max"),
        lcid=("mac.sdu.lcid", "first"),
        lcid_count=("mac.sdu.lcid", "nunique"),
    )
    if packet_service["lcid_count"].gt(1).any():
        raise ValueError("an IP packet maps to initial RLC segments on multiple LCIDs")

    packets = ip_packets[["ip_id", "rlc.queue.timestamp"]].merge(
        packet_service[["ip_id", "last_initial_tx", "lcid"]],
        on="ip_id",
        how="left",
        validate="one_to_one",
    )
    for column in ("rlc.queue.timestamp", "last_initial_tx", "lcid"):
        packets[column] = pd.to_numeric(packets[column], errors="coerce")

    packets.sort_values("rlc.queue.timestamp", inplace=True)
    active_service_by_lcid: dict[float, list[float]] = {}
    fresh_backlog = []
    for packet in packets.itertuples(index=False):
        if pd.isna(packet.lcid) or pd.isna(packet.last_initial_tx):
            fresh_backlog.append(pd.NA)
            continue

        active_service = active_service_by_lcid.setdefault(packet.lcid, [])
        while active_service and active_service[0] <= packet._1:
            heapq.heappop(active_service)
        fresh_backlog.append(int(bool(active_service)))
        heapq.heappush(active_service, packet.last_initial_tx)

    packets["fresh_backlog"] = pd.array(fresh_backlog, dtype="Int64")
    return packets[["ip_id", "fresh_backlog"]]


def clean_expeca_data(
    frame: pd.DataFrame,
    *,
    return_counts: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, int]]:
    """Return a cleaned copy of an EXPECA delay-decomposition frame."""
    cleaned = frame.copy()
    counts = {}

    mac_attempts = pd.to_numeric(cleaned["MAC attempts (total)"], errors="coerce")
    missing_mac_attempts = mac_attempts.isna()
    counts["missing_mac_attempts_rows_dropped"] = int(missing_mac_attempts.sum())
    cleaned = cleaned.loc[~missing_mac_attempts].copy()

    rlc_attempts = pd.to_numeric(cleaned["No of RLC attempts"], errors="coerce")
    missing_rlc_attempts = rlc_attempts.isna()
    counts["missing_rlc_attempts_rows_dropped"] = int(missing_rlc_attempts.sum())
    cleaned = cleaned.loc[~missing_rlc_attempts].copy()

    mac_attempts = pd.to_numeric(cleaned["MAC attempts (total)"], errors="coerce")
    rlc_attempts = pd.to_numeric(cleaned["No of RLC attempts"], errors="coerce")
    mac_below_rlc = mac_attempts < rlc_attempts
    counts["mac_attempts_below_rlc_rows_dropped"] = int(mac_below_rlc.sum())
    cleaned = cleaned.loc[~mac_below_rlc].copy()

    ran_delay = pd.to_numeric(cleaned["Ran delay"], errors="coerce")
    negative_ran = ran_delay < 0
    counts["negative_ran_rows_dropped"] = int(negative_ran.sum())
    cleaned = cleaned.loc[~negative_ran].copy()

    scheduling = pd.to_numeric(cleaned["Scheduling delay"], errors="coerce")
    queueing = pd.to_numeric(cleaned["Queuing delay"], errors="coerce")
    invalid_scheduling = scheduling > queueing
    counts["scheduling_above_queueing_set_to_nan"] = int(invalid_scheduling.sum())
    cleaned.loc[invalid_scheduling, "Scheduling delay"] = np.nan

    segment_count = pd.to_numeric(cleaned["No of RLC attempts"], errors="coerce")
    for column in PRIMARY_DELAY_COLUMNS:
        values = pd.to_numeric(cleaned[column], errors="coerce")
        negative = values < 0
        if column == "segmentation delay":
            negative &= segment_count != 1
        counts[f"negative_{column}_set_to_nan"] = int(negative.sum())
        cleaned.loc[negative, column] = np.nan

    segmentation = pd.to_numeric(cleaned["segmentation delay"], errors="coerce")
    one_segment = segment_count == 1
    counts["one_segment_segmentation_set_to_zero"] = int(
        (one_segment & segmentation.ne(0)).sum()
    )
    cleaned.loc[one_segment, "segmentation delay"] = 0.0
    return (cleaned, counts) if return_counts else cleaned
