# dashboard.py
# -------------
# An interactive dashboard to analyze Adam's behavior using Streamlit.
# To run:
# 1. pip install streamlit
# 2. streamlit run dashboard.py

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import ast

# Use Streamlit's caching to load the data only once
@st.cache_data
def load_and_prepare_data(filepath="adam_behavior_log.csv"):
    """
    Loads and prepares the CSV log file for analysis.
    """
    try:
        df = pd.read_csv(filepath)
    except FileNotFoundError:
        return None

    df.columns = df.columns.str.strip()

    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    else:
        df['timestamp'] = df.index

    json_columns = ['sensory_events', 'resonant_memories', 'impulses']
    for col in json_columns:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else [])
        else:
            # If a column is missing, create it as an empty list for compatibility
            df[col] = [[] for _ in range(len(df))]
            
    return df

# --- Main Dashboard App ---
st.set_page_config(layout="wide")
st.title("🧠 Project Adam - Behavior Dashboard")
st.markdown("An interactive tool to analyze the emergent behavior of the AI agent, Adam.")

# Load the data
df = load_and_prepare_data()

if df is None:
    st.error("Log file 'adam_behavior_log.csv' not found. Please run the simulation to generate data.")
else:
    # --- Interactive Controls ---
    st.sidebar.header("Dashboard Controls")
    
    # Show/Hide Raw Data
    if st.sidebar.checkbox("Show Raw Data Table"):
        st.subheader("Raw Behavior Log")
        st.dataframe(df)

    # Time Range Slider
    min_time, max_time = int(df['world_time'].min()), int(df['world_time'].max())
    time_range = st.sidebar.slider(
        "Filter by World Time (Ticks)",
        min_value=min_time,
        max_value=max_time,
        value=(min_time, max_time)
    )
    
    # Filter the dataframe based on the slider
    filtered_df = df[(df['world_time'] >= time_range[0]) & (df['world_time'] <= time_range[1])]

    # --- NEW: Key Performance Indicators (KPIs) ---
    st.header("Analysis Summary")
    
    kpi1, kpi2, kpi3 = st.columns(3)
    
    # Safely get the most frequent values
    most_freq_action = filtered_df['chosen_action'].mode()[0] if not filtered_df['chosen_action'].empty else "N/A"
    most_freq_mood = filtered_df['mood'].mode()[0] if not filtered_df['mood'].empty else "N/A"

    kpi1.metric(label="Total Cycles Analyzed", value=len(filtered_df))
    kpi2.metric(label="Most Frequent Action", value=most_freq_action)
    kpi3.metric(label="Most Common Mood", value=most_freq_mood)


    st.header("Emotional & Behavioral Trends")
    
    # --- Plotting Area ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Emotional Trajectory")
        fig1, ax1 = plt.subplots(figsize=(10, 5))
        sns.lineplot(data=filtered_df, x='world_time', y='mood_intensity', hue='mood', marker='o', palette='viridis', ax=ax1)
        ax1.set_title("Mood Intensity Over Time")
        ax1.set_xlabel("World Time (Ticks)")
        ax1.set_ylabel("Intensity")
        ax1.grid(True, linestyle='--')
        st.pyplot(fig1)

    with col2:
        st.subheader("Action Frequency")
        fig2, ax2 = plt.subplots(figsize=(10, 5))
        sns.countplot(data=filtered_df, y='chosen_action', order=filtered_df['chosen_action'].value_counts().index, palette='crest', ax=ax2)
        ax2.set_title("Frequency of Chosen Actions")
        ax2.set_xlabel("Count")
        ax2.set_ylabel("Action")
        st.pyplot(fig2)

    # --- NEW: Detailed Cycle Inspector ---
    st.header("Deep Dive: Cycle Inspector")
    
    # Allow user to select a specific tick from the filtered range
    selected_tick = st.selectbox(
        "Select a specific World Time tick to inspect:",
        options=sorted(filtered_df['world_time'].unique())
    )
    
    if selected_tick:
        # Get the full data for that specific cycle
        cycle_data = filtered_df[filtered_df['world_time'] == selected_tick].iloc[0]
        
        st.subheader(f"Inspecting Cycle at Tick {selected_tick}")
        
        insp_col1, insp_col2, insp_col3 = st.columns(3)
        
        with insp_col1:
            st.markdown("**World State**")
            st.json({
                "Location": cycle_data['location'],
                "Sensory Events": cycle_data['sensory_events']
            })
        
        with insp_col2:
            st.markdown("**Memory & Emotion**")
            st.json({
                "Resonant Memories": cycle_data['resonant_memories'],
                "Resulting Mood": cycle_data['mood'],
                "Mood Intensity": f"{cycle_data['mood_intensity']:.2f}"
            })

        with insp_col3:
            st.markdown("**Decision Making**")
            st.json({
                "Competing Impulses": cycle_data['impulses'],
                "Chosen Action": cycle_data['chosen_action'],
                "Action Result": cycle_data['action_result']
            })

