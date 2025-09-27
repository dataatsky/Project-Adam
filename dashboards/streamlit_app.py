import os
import sys
import json
from pathlib import Path
from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from analysis_utils import prepare_dataframe


st.set_page_config(page_title="Project Adam Analytics", layout="wide")
st.title("Project Adam — Analytics Dashboard")

DEFAULT_LOG = os.getenv("LOG_FILE", "adam_loop.log")


@st.cache_data(show_spinner="Loading log file…")
def load_dataframe(path: str) -> Optional[pd.DataFrame]:
    try:
        df = prepare_dataframe(path)
    except FileNotFoundError:
        st.error(f"Log file not found: {path}")
        return None
    except Exception as exc:
        st.error(f"Failed to load log file: {exc}")
        return None
    return df


sidebar = st.sidebar
sidebar.header("Controls")
log_path = sidebar.text_input("CSV log path", value=DEFAULT_LOG)
loop_threshold = sidebar.slider("Loop score threshold", 0.0, 1.0, 0.6, 0.05)

if not log_path:
    st.info("Provide a log path to begin.")
    st.stop()

log_path = Path(log_path).expanduser().as_posix()
df = load_dataframe(log_path)
if df is None or df.empty:
    st.stop()

cycle_min, cycle_max = int(df["cycle_num"].min()), int(df["cycle_num"].max())
selected_range = sidebar.slider(
    "Cycle range", cycle_min, cycle_max, (cycle_min, cycle_max), step=1
)
mask = (df["cycle_num"] >= selected_range[0]) & (df["cycle_num"] <= selected_range[1])
df_slice = df[mask].copy()
if df_slice.empty:
    st.warning("No rows in the selected cycle range.")
    st.stop()

# Goal completion estimate: count how often the goal name changes
goal_changes = df_slice["current_goal"].ne(df_slice["current_goal"].shift()).sum()
goal_completions = max(0, goal_changes - 1)
loop_alerts = int((df_slice["loop_score"] >= loop_threshold).sum())

kpi_cols = st.columns(4)
kpi_cols[0].metric("Cycles analysed", len(df_slice))
kpi_cols[1].metric("Unique actions", df_slice["chosen_target"].nunique())
kpi_cols[2].metric("Goal completions", goal_completions)
kpi_cols[3].metric("Loop alerts", loop_alerts)

# Mood trend and loop score line charts
chart_col, chart_col2 = st.columns(2)
with chart_col:
    mood_chart = alt.Chart(df_slice).mark_line(point=True).encode(
        x="cycle_num", y=alt.Y("mood_intensity", scale=alt.Scale(domain=[0, 1]))
    ).properties(title="Mood Intensity")
    st.altair_chart(mood_chart, use_container_width=True)

with chart_col2:
    loop_chart = alt.Chart(df_slice).mark_line(point=True).encode(
        x="cycle_num", y=alt.Y("loop_score", scale=alt.Scale(domain=[0, 1]))
    ).properties(title="Loop Score")
    st.altair_chart(loop_chart, use_container_width=True)

st.subheader("Loop Alerts")
loop_df = df_slice[df_slice["loop_score"] >= loop_threshold][
    ["cycle_num", "chosen_verb", "chosen_target", "loop_score", "action_result", "mood"]
]
if loop_df.empty:
    st.info("No cycles exceeded the chosen loop threshold.")
else:
    st.dataframe(loop_df.reset_index(drop=True), use_container_width=True)

st.subheader("Object Engagement Heatmap")
heatmap_source = (
    df_slice.groupby(["chosen_verb", "chosen_target"], dropna=False)
    .size()
    .reset_index(name="count")
)
heatmap_source["chosen_target"] = heatmap_source["chosen_target"].fillna("(none)")
engagement_chart = (
    alt.Chart(heatmap_source)
    .mark_rect()
    .encode(
        x=alt.X("chosen_target:N", title="Target"),
        y=alt.Y("chosen_verb:N", title="Verb"),
        color=alt.Color("count:Q", title="Count", scale=alt.Scale(scheme="lighttealblue")),
        tooltip=["chosen_verb", "chosen_target", "count"],
    )
    .properties(height=400)
)
st.altair_chart(engagement_chart, use_container_width=True)

st.subheader("Goal Progress Timeline")
if "current_goal" in df_slice:
    timeline_source = df_slice[["cycle_num", "current_goal", "goal_step"]].copy()
    timeline_source["goal_step"] = timeline_source["goal_step"].apply(
        lambda v: json.loads(v) if isinstance(v, str) and v.startswith("{") else v
    )
    timeline_source["goal_step_desc"] = timeline_source["goal_step"].apply(
        lambda step: f"{step.get('action')} → {step.get('target')}" if isinstance(step, dict) else "(Goal satisfied)"
    )
    goal_chart = alt.Chart(timeline_source).mark_circle(size=90).encode(
        x="cycle_num",
        y=alt.Y("current_goal", title="Goal"),
        color=alt.Color("goal_step_desc", title="Next step"),
        tooltip=["cycle_num", "current_goal", "goal_step_desc"],
    )
    st.altair_chart(goal_chart, use_container_width=True)
else:
    st.info("Goal metadata not present in log.")

st.subheader("Raw Data Preview")
st.dataframe(df_slice.head(50), use_container_width=True)

st.caption(
    "Tip: run with `streamlit run dashboards/streamlit_app.py` and point to any saved log to explore historical runs."
)
