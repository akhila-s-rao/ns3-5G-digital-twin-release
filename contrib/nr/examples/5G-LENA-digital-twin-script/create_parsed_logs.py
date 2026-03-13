#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

# Time/context columns used across traces when aligning or filtering.
COMMON_CONTEXT: List[str] = [
    "rnti",
    "cell_id",
    "lcid",
    "direction",
    "msg_type",
    "time_us",
]

DRB_LCID_MIN = 3  # SRB0/1/2 are reserved; DRB/data LCIDs start at 3.

LOG_CONFIG: Dict[str, Dict[str, object]] = {
    "GnbBsrTrace.txt": {
        "direction": "UL",
        "metrics": {"queue_bytes": "max", "bsr_level": "median"},
        "fill": {"queue_bytes": "ffill", "bsr_level": "ffill"},
        "context": COMMON_CONTEXT,
    },
    # "SrsSinrTrace.txt": {
    #     "direction": "UL",
    #     "metrics": {"sinr_db": "median"},
    #     "fill": {"sinr_db": "ffill"},
    #     "context": COMMON_CONTEXT,
    # },
    # "DlCtrlSinr.txt": {
    #     "direction": "DL",
    #     "metrics": {"sinr_db": "median"},
    #     "fill": {"sinr_db": "ffill"},
    #     "context": COMMON_CONTEXT,
    # },
    # "DlDataSinr.txt": {
    #     "direction": "DL",
    #     "metrics": {"sinr_db": "median"},
    #     "fill": {"sinr_db": "ffill"},
    #     "context": COMMON_CONTEXT,
    # },
    "RsrpRsrqTrace.txt": {
        "direction": "DL",
        "metrics": {"rsrp_dbm": "median"},
        "fill": {"rsrp_dbm": "ffill"},
        "context": COMMON_CONTEXT,
    },
    "NrUlMacStats.txt": {
        "direction": "UL",
        "metrics": {"rv": "max", "mcs": "median", "tb_size": "sum", "num_prbs": "sum"},
        "fill": {"rv": "ffill", "mcs": "ffill", "tb_size": "zero", "num_prbs": "zero"},
        "context": COMMON_CONTEXT,
        "msg_type": "DATA",
    },
    "NrDlMacStats.txt": {
        "direction": "DL",
        "metrics": {"rv": "max", "mcs": "median", "tb_size": "sum", "num_prbs": "sum"},
        "fill": {"rv": "ffill", "mcs": "ffill", "tb_size": "zero", "num_prbs": "zero"},
        "context": COMMON_CONTEXT,
        "msg_type": "DATA",
    },
    "NrUlPdcpRxStats.txt": {
        "direction": "UL",
        "metrics": {"packet_size": "sum"},
        "fill": {"packet_size": "zero"},
        "context": COMMON_CONTEXT,
    },
    "NrDlPdcpRxStats.txt": {
        "direction": "DL",
        "metrics": {"packet_size": "sum"},
        "fill": {"packet_size": "zero"},
        "context": COMMON_CONTEXT,
    },
    "NrUlRlcRxStats.txt": {
        "direction": "UL",
        "metrics": {"packet_size": "sum"},
        "fill": {"packet_size": "zero"},
        "context": COMMON_CONTEXT,
    },
    "NrDlRlcRxStats.txt": {
        "direction": "DL",
        "metrics": {"packet_size": "sum"},
        "fill": {"packet_size": "zero"},
        "context": COMMON_CONTEXT,
    },
    "DlRxTbTrace.txt": {
        "direction": "DL",
        "metrics": {"sinr_db": "median", "cqi": "median", "tbler": "mean"},
        "fill": {"sinr_db": "ffill", "cqi": "ffill", "tbler": "ffill"},
        "context": COMMON_CONTEXT,
    },
    "UlRxTbTrace.txt": {
        "direction": "UL",
        "metrics": {"sinr_db": "median", "cqi": "median", "tbler": "mean"},
        "fill": {"sinr_db": "ffill", "cqi": "ffill", "tbler": "ffill"},
        "context": COMMON_CONTEXT,
    },
    "delay_trace.txt": {
        "direction": "UL/DL",
        "metrics": {"pkt_size": "sum", "delay_us": "max"},
        "fill": {"pkt_size": "zero", "delay_us": "ffill"},
        "context": COMMON_CONTEXT,
    },
    "rtt_trace.txt": {
        "direction": "UL/DL",
        "metrics": {"pkt_size": "sum", "delay_us": "max"},
        "fill": {"pkt_size": "zero", "delay_us": "ffill"},
        "context": COMMON_CONTEXT,
    },
    "vrFragment_trace.txt": {
        "direction": "UL/DL",
        "metrics": {"burst_size": "sum", "delay_us": "max"},
        "fill": {"burst_size": "zero", "delay_us": "ffill"},
        "context": COMMON_CONTEXT,
    },
    "vrBurst_trace.txt": {
        "direction": "UL/DL",
        "metrics": {"burst_size": "sum", "num_frags": "sum"},
        "fill": {"burst_size": "zero", "num_frags": "zero"},
        "context": COMMON_CONTEXT,
    },
}

TIME_COLUMNS: List[str] = ["time_us"]

def read_log(path: Path) -> pd.DataFrame:
    """Load a whitespace-delimited trace file into a DataFrame."""
    return pd.read_csv(path, sep=r"\s+")

def filter_log_columns(
    df: pd.DataFrame,
    metrics: Dict[str, str],
    context_cols: List[str],
) -> pd.DataFrame:
    """Keep only context/agg columns from the log."""
    allowed = pd.Index(list(metrics) + context_cols)
    cols = df.columns.intersection(allowed)
    return df.loc[:, cols]

def group_log_by_rnti(df: pd.DataFrame) -> Dict[object, pd.DataFrame]:
    """Group a log by rnti; raise if no rnti column is present."""
    if "rnti" in df.columns:
        return {rnti: group for rnti, group in df.groupby("rnti", sort=False)}
    raise KeyError("Expected rnti column not found in log")

def filter_data_bearers(df: pd.DataFrame) -> pd.DataFrame:
    """Keep DRB rows only (LCID >= 3)."""
    if "lcid" not in df.columns:
        return df
    lcid_series = pd.to_numeric(df["lcid"], errors="coerce")
    return df[lcid_series >= DRB_LCID_MIN]

def build_rnti_cell_map(raw_logs: Dict[str, pd.DataFrame]) -> Dict[object, object]:
    """Build a mapping of rnti -> cell_id from raw logs."""
    mapping: Dict[object, object] = {}
    conflicts: Dict[object, set] = {}
    for df in raw_logs.values():
        if "rnti" not in df.columns or "cell_id" not in df.columns:
            continue
        pairs = df[["rnti", "cell_id"]].dropna().drop_duplicates()
        for rnti, cell_id in pairs.itertuples(index=False):
            if rnti not in mapping:
                mapping[rnti] = cell_id
            elif mapping[rnti] != cell_id:
                conflicts.setdefault(rnti, set()).update([mapping[rnti], cell_id])
    if conflicts:
        conflict_list = ", ".join(str(rnti) for rnti in sorted(conflicts))
        print(f"WARN: multiple cell_id values for rnti(s): {conflict_list}")
        for rnti in conflicts:
            mapping[rnti] = pd.NA
    return mapping

def get_time_microseconds(df: pd.DataFrame) -> pd.Series:
    """Return a time series in microseconds based on available time columns."""
    for col in TIME_COLUMNS:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce")
    raise KeyError("Expected a time column (time_us) not found in log")

def apply_fill_rules(
    df: pd.DataFrame,
    fill: Optional[Dict[str, Union[str, int, float]]],
) -> pd.DataFrame:
    """Fill missing values per column based on explicit rules."""
    if not fill:
        raise ValueError("Fill rules are required for all aggregated columns")
    for col in df.columns:
        if col not in fill:
            raise ValueError(f"Missing fill rule for column '{col}'")
        rule = fill[col]
        if isinstance(rule, (int, float)):
            df[col] = df[col].fillna(rule)
        elif rule == "zero":
            df[col] = df[col].fillna(0)
        elif rule == "ffill":
            df[col] = df[col].ffill()
        else:
            raise ValueError(f"Unknown fill rule '{rule}' for column '{col}'")
    return df

def aggregate_time_windows(
    df: pd.DataFrame,
    window_ms: int,
    metrics: Dict[str, str],
    fill: Optional[Dict[str, Union[str, int, float]]] = None,
    start_us: int = 0,
    end_us: Optional[int] = None,
    impute: bool = True,
) -> pd.DataFrame:
    """Aggregate a log into fixed time windows using microsecond time units."""
    time_us = get_time_microseconds(df)
    work = df.copy()
    work["_time_us"] = time_us
    work = work.dropna(subset=["_time_us"])
    agg_map = {col: agg for col, agg in metrics.items() if col in work.columns}
    if work.empty or not agg_map:
        return pd.DataFrame(columns=list(agg_map))
    for col in agg_map:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    epoch = pd.Timestamp("1970-01-01")
    work = work.set_index(epoch + pd.to_timedelta(work["_time_us"], unit="us"))
    resampled = work.resample(f"{window_ms}ms", origin="epoch").agg(agg_map)
    if end_us is not None:
        # Align to fixed left-edge window starts in [start_us, end_us), avoiding
        # an extra inclusive endpoint bin at exactly end_us.
        window_us = window_ms * 1000
        if end_us <= start_us:
            starts_us = [start_us]
        else:
            starts_us = list(range(start_us, end_us, window_us))
        full_index = epoch + pd.to_timedelta(starts_us, unit="us")
        resampled = resampled.reindex(full_index)
    if impute:
        resampled = apply_fill_rules(resampled, fill)
    resampled.index = (
        (resampled.index - epoch) / pd.Timedelta(microseconds=1)
    ).astype("int64")
    resampled.index.name = "time_us"
    return resampled

def select_log_files(direction: str) -> List[str]:
    """Select log files that match the requested direction."""
    if direction == "BOTH":
        return list(LOG_CONFIG)
    selected: List[str] = []
    for name, config in LOG_CONFIG.items():
        log_dir = config["direction"]
        if direction in log_dir:
            selected.append(name)
    return selected

def filter_direction(
    df: pd.DataFrame,
    filename: str,
    direction: str,
    log_direction: str,
) -> pd.DataFrame:
    """Filter UL/DL logs to a single direction when a direction column exists."""
    if direction == "BOTH" or log_direction != "UL/DL" or filename == "rtt_trace.txt":
        return df
    if "direction" in df.columns:
        series = df["direction"].astype(str).str.upper()
        return df.loc[series == direction]
    return df

def load_logs(run_dir: Path, filenames: List[str]) -> Dict[str, pd.DataFrame]:
    """Load logs and keep only selected/context columns."""
    data: Dict[str, pd.DataFrame] = {}
    for filename in filenames:
        path = run_dir / filename
        config = LOG_CONFIG[filename]
        df = read_log(path)
        data[filename] = filter_log_columns(
            df,
            config["metrics"],
            config["context"],
        )
    return data

def has_log_files(run_dir: Path, filenames: List[str]) -> bool:
    """Return True if the directory contains any known log files."""
    return any((run_dir / name).exists() for name in filenames)

def find_run_dirs(base_dir: Path, filenames: List[str]) -> List[Path]:
    """Find run directories to parse."""
    if has_log_files(base_dir, filenames):
        return [base_dir]
    runs: List[Path] = []
    for entry in sorted(base_dir.iterdir()):
        if entry.is_dir() and has_log_files(entry, filenames):
            runs.append(entry)
    return runs

def parse_run(run_dir: Path, args: argparse.Namespace, filenames: List[str]) -> None:
    """Parse a single run directory and write the parsed CSV."""
    print(f"Processing run: {run_dir}")
    raw_logs = load_logs(run_dir, filenames)
    rnti_cell_map = build_rnti_cell_map(raw_logs)
    data_per_rnti: Dict[str, Dict[object, pd.DataFrame]] = {}
    data_overall: Dict[str, pd.DataFrame] = {}
    end_us = int(args.sim_duration * 1_000_000)

    for fname, df in raw_logs.items():
        config = LOG_CONFIG[fname]
        df = filter_direction(df, fname, args.direction, config["direction"])
        if fname == "GnbBsrTrace.txt" and "lcg" in df.columns:
            lcg_values = pd.to_numeric(df["lcg"], errors="coerce")
            df = df[lcg_values != 0]
        msg_type = config.get("msg_type")
        if msg_type and "msg_type" in df.columns:
            df = df[df["msg_type"].astype(str).str.upper() == str(msg_type).upper()]
        if fname in {
            "NrUlPdcpRxStats.txt",
            "NrDlPdcpRxStats.txt",
            "NrUlRlcRxStats.txt",
            "NrDlRlcRxStats.txt",
        }:
            df = filter_data_bearers(df)
        overall = None
        if fname not in {"delay_trace.txt", "rtt_trace.txt", "vrFragment_trace.txt", "vrBurst_trace.txt"}:
            allowed_overall = {"packet_size", "num_prbs", "tb_size", "queue_bytes"}
            overall_metrics = {
                key: value for key, value in config["metrics"].items() if key in allowed_overall
            }
            if overall_metrics:
                fill_cfg = config.get("fill") or {}
                overall_fill = {key: fill_cfg[key] for key in overall_metrics}
                overall = aggregate_time_windows(
                    df,
                    args.window_ms,
                    overall_metrics,
                    overall_fill,
                    start_us=0,
                    end_us=end_us,
                    impute=args.impute,
                ).add_prefix("overall_")
                data_overall[fname] = overall
        grouped = group_log_by_rnti(df)
        per_rnti: Dict[object, pd.DataFrame] = {}
        for rnti, group_df in grouped.items():
            per = aggregate_time_windows(
                group_df,
                args.window_ms,
                config["metrics"],
                config.get("fill"),
                start_us=0,
                end_us=end_us,
                impute=args.impute,
            ).add_prefix("per_rnti_")
            per_rnti[rnti] = per.join(overall, how="outer") if overall is not None else per
        data_per_rnti[fname] = per_rnti

    combined_rows: List[pd.DataFrame] = []
    all_rntis = {rnti for groups in data_per_rnti.values() for rnti in groups}
    for rnti in all_rntis:
        combined = None
        for fname, groups in data_per_rnti.items():
            df = groups.get(rnti)
            if df is None:
                continue
            prefix = f"{Path(fname).stem}_"
            prefixed = df.add_prefix(prefix)
            combined = prefixed if combined is None else combined.join(prefixed, how="outer")
        if combined is not None:
            combined = combined.reset_index()
            combined["rnti"] = rnti
            combined_rows.append(combined)

    combined_df = pd.concat(combined_rows, ignore_index=True) if combined_rows else pd.DataFrame()
    if not combined_df.empty:
        combined_df["cell_id"] = combined_df["rnti"].map(rnti_cell_map)
        cols = list(combined_df.columns)
        if "cell_id" in cols and "rnti" in cols:
            cols.remove("cell_id")
            rnti_idx = cols.index("rnti")
            cols.insert(rnti_idx + 1, "cell_id")
            combined_df = combined_df.loc[:, cols]

    output_path = run_dir / f"parsed_data_from_{run_dir.name}.csv"
    combined_df.to_csv(output_path, index=False)
    print(f"Wrote parsed log: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load run folder logs into pandas DataFrames."
    )
    parser.add_argument(
        "--run-dir",
        default=".",
        help="Run directory containing log files (default: current directory).",
    )
    parser.add_argument(
        "--direction",
        choices=["UL", "DL", "BOTH"],
        default="UL",
        help="Select UL/DL logs and filter mixed-direction traces (default: UL).",
    )
    parser.add_argument(
        "--impute",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If set, fill empty windows using the per-log fill rules (default: True).",
    )
    parser.add_argument(
        "--window-ms",
        type=int,
        default=100,
        help="Aggregation window in milliseconds (default: 100).",
    )
    parser.add_argument(
        "--sim-duration",
        type=float,
        required=True,
        help="Simulation duration in seconds for aligned resampling.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    filenames = select_log_files(args.direction)
    run_dirs = find_run_dirs(run_dir, filenames)
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {run_dir}")
    for rdir in run_dirs:
        parse_run(rdir, args, filenames)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
