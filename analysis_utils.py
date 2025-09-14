import os
import json
import ast
from collections import Counter
from typing import Optional, Iterable, Dict, Any

import pandas as pd
import matplotlib.pyplot as plt


# -----------------------
# Parsing & Preparation
# -----------------------

def _parse_json_value(val: Any) -> Any:
    """Best-effort parse of a JSON-like string; returns {} or [] on failure."""
    if val is None:
        return {}
    if isinstance(val, (dict, list)):
        return val
    s = str(val)
    try:
        return json.loads(s)
    except Exception:
        try:
            return ast.literal_eval(s)
        except Exception:
            # Decide default container based on leading char
            return [] if s.strip().startswith("[") else {}


def parse_json_column(df: pd.DataFrame, col: str) -> list:
    return [_parse_json_value(v) for v in df[col].fillna("{}").astype(str)]


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Expand key JSON columns into parsed forms for easy querying."""
    json_cols = [
        "sensory_events",
        "resonant_memories",
        "impulses",
        "action_result",
        "imagined_outcomes",
        "simulated_outcomes",
        "emotional_delta",
        "kpis",
        "snapshot",
    ]
    for col in json_cols:
        if col in df.columns:
            df[col + "_parsed"] = parse_json_column(df, col)
    return df


def _flatten_kpis(df: pd.DataFrame, prefix: Optional[str] = "") -> pd.DataFrame:
    """Flatten df['kpis_parsed'] dicts into top-level numeric columns.

    If prefix provided, prepend to column names.
    """
    if "kpis_parsed" not in df.columns:
        return df
    try:
        k = pd.json_normalize(df["kpis_parsed"]).rename(columns=str)
        if prefix:
            k = k.add_prefix(prefix)
        # Coerce to numeric where possible
        for c in k.columns:
            k[c] = pd.to_numeric(k[c], errors="ignore")
        df = pd.concat([df, k], axis=1)
    except Exception:
        pass
    return df


def _expand_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Extract common fields from snapshot: chosen verb/target, and simulated text."""
    if "snapshot_parsed" not in df.columns:
        return df
    chosen_verb, chosen_target, simulated_text = [], [], []
    for snap in df["snapshot_parsed"]:
        if isinstance(snap, dict):
            chosen = snap.get("chosen", {}) or {}
            chosen_verb.append(chosen.get("verb"))
            chosen_target.append(chosen.get("target"))
            simulated_text.append(snap.get("simulated"))
        else:
            chosen_verb.append(None)
            chosen_target.append(None)
            simulated_text.append(None)
    df["chosen_verb"] = chosen_verb
    df["chosen_target"] = chosen_target
    df["simulated_text"] = simulated_text
    return df


def _normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in df.columns:
        try:
            df["timestamp_dt"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
        except Exception:
            try:
                df["timestamp_dt"] = pd.to_datetime(df["timestamp"], errors="coerce")
            except Exception:
                pass
    for c in ("cycle_num", "world_time"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def compute_mismatch_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Compute imagination vs simulation mismatch rate per row using parsed lists."""
    def _mismatch(row):
        try:
            imagined = row.get("imagined_outcomes_parsed", [])
            simulated = row.get("simulated_outcomes_parsed", [])
            if not isinstance(imagined, list) or not isinstance(simulated, list):
                return None
            n = max(1, len(imagined))
            mism = sum(1 for i, s in zip(imagined, simulated) if i != s)
            return mism / n
        except Exception:
            return None

    df["mismatch_rate"] = df.apply(_mismatch, axis=1)
    return df


def compute_mismatch_rate_fuzzy(df: pd.DataFrame, threshold: int = 80) -> pd.DataFrame:
    """Fuzzy variant using rapidfuzz if available; falls back to normalized exact.

    threshold: token_set_ratio similarity threshold considered a match (0-100).
    """
    try:
        from rapidfuzz import fuzz
        def _norm(s):
            return " ".join(str(s).lower().strip().split())
        def _sim(a, b):
            return fuzz.token_set_ratio(_norm(a), _norm(b))
        def _mismatch(row):
            try:
                imagined = row.get("imagined_outcomes_parsed", [])
                simulated = row.get("simulated_outcomes_parsed", [])
                if not isinstance(imagined, list) or not isinstance(simulated, list):
                    return None
                n = max(1, min(len(imagined), len(simulated)))
                sims = [_sim(i, s) for i, s in zip(imagined[:n], simulated[:n])]
                matches = sum(1 for v in sims if v >= threshold)
                return 1 - (matches / n)
            except Exception:
                return None
        df["mismatch_rate"] = df.apply(_mismatch, axis=1)
        return df
    except Exception:
        # Fallback: normalized exact
        return compute_mismatch_rate(df)


def compute_impulse_alignment(df: pd.DataFrame) -> pd.DataFrame:
    """Add an urgency-weighted impulse alignment score per row.

    Uses impulses_parsed and snapshot_parsed['chosen'] when available.
    """
    if "snapshot_parsed" not in df.columns:
        return df
    aligns = []
    for _, row in df.iterrows():
        chosen = {}
        try:
            snap = row.get("snapshot_parsed", {}) or {}
            chosen = snap.get("chosen", {}) or {}
        except Exception:
            pass
        verb_c = (chosen or {}).get("verb")
        targ_c = (chosen or {}).get("target")
        imps = row.get("impulses_parsed", []) or []
        total = 0.0
        score = 0.0
        try:
            for imp in imps:
                urg = float((imp or {}).get("urgency", 0))
                total += urg
                v = (imp or {}).get("verb")
                t = (imp or {}).get("target")
                if v == verb_c and t == targ_c:
                    s = 1.0
                elif v == verb_c or t == targ_c:
                    s = 0.5
                else:
                    s = 0.0
                score += s * urg
            aligns.append(None if total == 0 else score / total)
        except Exception:
            aligns.append(None)
    df["impulse_alignment"] = aligns
    return df


def compute_stuck_on_target(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Approximate 'stuck on target' using chosen/target and action_result success.

    Returns a normalized streak length for the last row relative to the previous window.
    """
    try:
        chosen = df.get("snapshot_parsed", pd.Series([{}] * len(df))).apply(lambda s: (s or {}).get("chosen", {}))
        chosen_target = chosen.apply(lambda c: (c or {}).get("target"))
    except Exception:
        chosen_target = pd.Series([None] * len(df))
    try:
        success = df.get("action_result_parsed", pd.Series([{}] * len(df))).apply(lambda r: bool((r or {}).get("success")))
    except Exception:
        success = pd.Series([None] * len(df))
    streaks = []
    for i in range(len(df)):
        tgt = chosen_target.iloc[i]
        streak = 0
        j = i
        while j >= 0 and i - j < window:
            if chosen_target.iloc[j] == tgt and success.iloc[j] is False:
                streak += 1
                j -= 1
            else:
                break
        streaks.append(streak / max(1, window / 2))
    df["stuck_on_target"] = [min(1.0, max(0.0, float(s))) for s in streaks]
    return df


def per_target_success(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate attempts and success rates per chosen_target."""
    try:
        chosen = df.get("snapshot_parsed", pd.Series([{}] * len(df))).apply(lambda s: (s or {}).get("chosen", {}))
        tgt = chosen.apply(lambda c: (c or {}).get("target"))
        succ = df.get("action_result_parsed", pd.Series([{}] * len(df))).apply(lambda r: bool((r or {}).get("success")))
        out = pd.DataFrame({"target": tgt, "success": succ})
        g = out.groupby("target", dropna=True)
        stats = g.agg(attempts=("success", "count"), success_rate=("success", "mean")).reset_index()
        return stats.sort_values(["success_rate", "attempts"], ascending=[False, False])
    except Exception:
        return pd.DataFrame(columns=["target", "attempts", "success_rate"])


def ensure_new_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure alignment, stuck_on_target, novelty_object columns exist.

    - If 'alignment' missing, derive from compute_impulse_alignment (column 'impulse_alignment').
    - If 'stuck_on_target' missing, compute from snapshot/action_result.
    - If 'novelty_object' missing, fall back to 'novelty' if present.
    Returns the same DataFrame for chaining.
    """
    if "alignment" not in df.columns:
        if "impulse_alignment" not in df.columns:
            try:
                df = compute_impulse_alignment(df)
            except Exception:
                pass
        if "impulse_alignment" in df.columns:
            df["alignment"] = df["impulse_alignment"]
    if "stuck_on_target" not in df.columns:
        try:
            df = compute_stuck_on_target(df, window=10)
        except Exception:
            pass
    if "novelty_object" not in df.columns and "novelty" in df.columns:
        df["novelty_object"] = df["novelty"]
    return df


def _read_log_csv(csv_path: str, headers: list[str]) -> pd.DataFrame:
    """Read the behavior CSV while being tolerant of the presence/absence of a header row.

    - First try reading with header row (header=0). If columns match the expected headers,
      return as-is.
    - Otherwise, read with no header and assign our schema.
    - If the (now data) first row contains the literal header names (from older files), drop it.
    """
    try:
        df0 = pd.read_csv(csv_path)
        # Heuristic: if at least the first few expected columns are present, accept
        if set(df0.columns) >= set(headers[:6]):
            return df0
    except Exception:
        pass

    # Fallback: no header in file
    df = pd.read_csv(csv_path, names=headers, header=None)
    # Drop a possible header row accidentally read as data
    try:
        if str(df.iloc[0, 0]).lower() in {"timestamp", "ts"}:
            df = df.iloc[1:].reset_index(drop=True)
    except Exception:
        pass
    return df


def prepare_dataframe(csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load Adam's behavior CSV, parse/flatten, and compute derived metrics.

    - Resolves `csv_path` from env `LOG_FILE` if not provided.
    - Parses JSON-ish columns into *_parsed.
    - Flattens KPIs into top-level columns.
    - Extracts chosen action fields from snapshot.
    - Computes mismatch_rate.
    - Normalizes types for time/indices.
    """
    if csv_path is None:
        csv_path = os.getenv("LOG_FILE", "adam_behavior_log.csv")

    headers = [
        "timestamp", "cycle_num", "experiment_tag", "agent_id", "world_time",
        "location", "mood", "mood_intensity",
        "sensory_events", "resonant_memories", "impulses", "chosen_action", "action_result",
        "imagined_outcomes", "simulated_outcomes", "emotional_delta", "kpis", "snapshot",
    ]
    df = _read_log_csv(csv_path, headers)
    df = clean_dataframe(df)
    df = _flatten_kpis(df)
    df = _expand_snapshot(df)
    df = compute_mismatch_rate(df)
    df = _normalize_types(df)

    # Normalize mood labels if obvious variants exist
    mood_map = {"curiosity": "curious"}
    if "mood" in df.columns:
        df["mood"] = df["mood"].replace(mood_map)

    return df


# -----------------------
# Plotting Helpers
# -----------------------

def _maybe_legend(ax):
    handles, labels = ax.get_legend_handles_labels()
    if any(labels):
        ax.legend()


def plot_kpis(df: pd.DataFrame, rolling: Optional[int] = None):
    x = df["cycle_num"]
    ax = plt.figure(figsize=(12, 6)).gca()
    plotted = False
    for key in ["frustration", "loop_score", "novelty", "conflict", "goal_progress"]:
        if key in df.columns:
            y = df[key]
            if rolling and rolling > 1:
                y = y.rolling(rolling, min_periods=1).mean()
            ax.plot(x, y, label=key)
            plotted = True
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Value")
    ax.set_title("KPI Trajectories")
    if plotted:
        _maybe_legend(ax)
    return ax


def plot_mood(df: pd.DataFrame, rolling: Optional[int] = None):
    if "mood_intensity" not in df.columns:
        print("⚠️ No mood_intensity column found.")
        return None
    x = df["cycle_num"]
    y = df["mood_intensity"]
    if rolling and rolling > 1:
        y = y.rolling(rolling, min_periods=1).mean()
    ax = plt.figure(figsize=(10, 5)).gca()
    ax.plot(x, y, label="Mood Intensity")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Mood Intensity")
    ax.set_title("Mood Intensity over Cycles")
    _maybe_legend(ax)
    return ax


def plot_mismatch(df: pd.DataFrame, rolling: Optional[int] = None):
    if "mismatch_rate" not in df.columns:
        print("⚠️ mismatch_rate not computed.")
        return None
    x = df["cycle_num"]
    y = df["mismatch_rate"]
    if rolling and rolling > 1:
        y = y.rolling(rolling, min_periods=1).mean()
    ax = plt.figure(figsize=(10, 5)).gca()
    ax.plot(x, y, label="Mismatch Rate")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Mismatch Rate")
    ax.set_title("Imagination vs Simulation Mismatch")
    _maybe_legend(ax)
    return ax


def plot_mood_transitions(df: pd.DataFrame):
    cycles = df["cycle_num"].tolist()
    moods = df.get("mood", pd.Series([None] * len(df))).tolist()
    intensities = df.get("mood_intensity", pd.Series([None] * len(df))).tolist()
    ax = plt.figure(figsize=(12, 6)).gca()
    ax.plot(cycles, intensities, marker="o", label="Mood Intensity")
    # Reduce text clutter: annotate every Nth point
    step = max(1, len(cycles) // 20)
    for i in range(0, len(cycles), step):
        ax.text(cycles[i], intensities[i] + 0.02, str(moods[i]), fontsize=8, rotation=45)
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Mood Intensity")
    ax.set_title("Mood Transitions (sampled labels)")
    _maybe_legend(ax)
    return ax


def plot_impulse_distribution(df: pd.DataFrame):
    all_impulses = []
    for row in df.get("impulses_parsed", []):
        if isinstance(row, list):
            for imp in row:
                if isinstance(imp, dict):
                    verb = imp.get("verb")
                    target = imp.get("target")
                    all_impulses.append(f"{verb}_{target}")
    counter = Counter(all_impulses)
    if not counter:
        print("⚠️ No impulses found.")
        return None
    ax = plt.figure(figsize=(10, 5)).gca()
    ax.bar(counter.keys(), counter.values())
    plt.xticks(rotation=45, ha="right")
    ax.set_title("Impulse Distribution (verb_target)")
    ax.set_ylabel("Count")
    return ax


def plot_action_success_rates(df: pd.DataFrame):
    actions, results = [], []
    for _, row in df.iterrows():
        try:
            chosen = (row.get("snapshot_parsed") or {}).get("chosen", {})
            success = (row.get("action_result_parsed") or {}).get("success")
            actions.append(f"{chosen.get('verb')}_{chosen.get('target')}")
            results.append(bool(success))
        except Exception:
            continue
    counter = Counter(zip(actions, results))
    if not counter:
        print("⚠️ No actions recorded.")
        return None
    labels = [f"{a} ({'success' if s else 'fail'})" for a, s in counter.keys()]
    values = list(counter.values())
    ax = plt.figure(figsize=(12, 5)).gca()
    ax.bar(labels, values)
    plt.xticks(rotation=45, ha="right")
    ax.set_ylabel("Count")
    ax.set_title("Action Success/Failure Counts")
    return ax


def compare_experiments(df: pd.DataFrame, metric: str = "frustration"):
    if "experiment_tag" not in df.columns or metric not in df.columns:
        print("⚠️ Missing columns for comparison.")
        return None
    ax = df.groupby("experiment_tag")[metric].mean().plot(kind="bar", title=f"Average {metric} by Experiment Tag")
    return ax


def plot_kpi_overlay(df: pd.DataFrame, metric: str = "frustration", by: str = "experiment_tag", rolling: Optional[int] = 5):
    """Overlay a single KPI over cycles for groups (experiment_tag or agent_id)."""
    if metric not in df.columns:
        print(f"⚠️ Missing metric: {metric}")
        return None
    if by not in df.columns:
        print(f"⚠️ Missing group column: {by}")
        return None
    ax = plt.figure(figsize=(12, 6)).gca()
    for grp, sub in df.groupby(by):
        x = sub["cycle_num"]
        y = sub[metric]
        if rolling and rolling > 1:
            y = y.rolling(rolling, min_periods=1).mean()
        ax.plot(x, y, label=f"{grp}")
    ax.set_xlabel("Cycle")
    ax.set_ylabel(metric)
    ax.set_title(f"{metric} by {by} (overlay)")
    _maybe_legend(ax)
    return ax


def kpi_correlation_heatmap(df: pd.DataFrame, keys: Optional[Iterable[str]] = None):
    """Correlation heatmap among key KPIs and mismatch_rate."""
    if keys is None:
        keys = ["frustration", "conflict", "novelty", "goal_progress", "loop_score", "mismatch_rate"]
    avail = [k for k in keys if k in df.columns]
    if not avail:
        print("⚠️ No numeric KPI columns available for correlation.")
        return None
    c = df[avail].corr()
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(c, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(avail)))
    ax.set_yticks(range(len(avail)))
    ax.set_xticklabels(avail, rotation=45, ha="right")
    ax.set_yticklabels(avail)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="corr")
    ax.set_title("KPI Correlation Heatmap")
    return ax


# -----------------------
# Dashboard
# -----------------------

def experiment_dashboard(df: pd.DataFrame, save_dir: str = "figures", save: bool = False, rolling: Optional[int] = 5):
    print("=== Project Adam Experiment Dashboard ===")
    print(f"Total cycles: {len(df)}")
    if "experiment_tag" in df.columns:
        print("Experiment tags:", df["experiment_tag"].dropna().unique())
    if "agent_id" in df.columns:
        print("Agent IDs:", df["agent_id"].dropna().unique())

    if save:
        os.makedirs(save_dir, exist_ok=True)
        print(f"Saving plots to {save_dir}/")

    # KPIs
    ax = plot_kpis(df, rolling=rolling)
    if save and ax:
        plt.savefig(os.path.join(save_dir, "kpis.png"))
    plt.show()

    # Mood
    ax = plot_mood(df, rolling=rolling)
    if save and ax:
        plt.savefig(os.path.join(save_dir, "mood.png"))
    plt.show()

    # Mismatch
    ax = plot_mismatch(df, rolling=rolling)
    if save and ax:
        plt.savefig(os.path.join(save_dir, "mismatch.png"))
    plt.show()

    # Impulses
    ax = plot_impulse_distribution(df)
    if save and ax:
        plt.savefig(os.path.join(save_dir, "impulses.png"))
    plt.show()

    # Action success
    ax = plot_action_success_rates(df)
    if save and ax:
        plt.savefig(os.path.join(save_dir, "success_rates.png"))
    plt.show()

    # Mood transitions
    ax = plot_mood_transitions(df)
    if save and ax:
        plt.savefig(os.path.join(save_dir, "mood_transitions.png"))
    plt.show()
