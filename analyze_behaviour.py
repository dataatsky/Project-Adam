# analyze_behavior.py
# --------------------
# An advanced script to analyze the behavior of the enhanced Project Adam agent.

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
import ast

# Define the expected headers here to ensure consistency
LOG_HEADERS = [
    "timestamp", "world_time", "location", "mood", "mood_intensity",
    "sensory_events", "resonant_memories", "impulses", "chosen_action", "action_result"
]

def safe_literal_eval(val):
    """
    A safe version of ast.literal_eval that returns an empty list on failure.
    """
    if isinstance(val, str):
        try:
            return ast.literal_eval(val)
        except (ValueError, SyntaxError):
            # If the string is malformed, return an empty list as a fallback
            return []
    return val

def load_and_prepare_data(filepath="adam_behavior_log.csv"):
    """
    Loads and prepares the CSV log file, handling the new complex data structures.
    """
    try:
        # Explicitly provide the column names, as the log file might be missing its header.
        df = pd.read_csv(filepath, header=None, names=LOG_HEADERS, on_bad_lines='skip')
    except FileNotFoundError:
        print(f"Error: Log file not found at '{filepath}'.")
        print("Please run the cognitive_loop_gui.py script first to generate some data.")
        return None
    except pd.errors.EmptyDataError:
        print(f"Error: The log file '{filepath}' is empty. No data to analyze.")
        return None


    df.columns = df.columns.str.strip()

    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    else:
        print("Warning: 'timestamp' column not found in log file. Using index instead for time-based plots.")
        df['timestamp'] = df.index

    # Safely parse all columns that contain JSON strings
    json_columns = ['sensory_events', 'resonant_memories', 'impulses', 'action_result']
    for col in json_columns:
        if col in df.columns:
            # --- DEFINITIVE FIX ---
            # Use the new safe_literal_eval function to prevent crashes.
            df[col] = df[col].apply(safe_literal_eval)
        else:
            print(f"Warning: Column '{col}' not found in log file. Skipping.")

    print("Data loaded and prepared successfully.")
    return df

def plot_emotional_trajectory(df):
    """
    Plots Adam's mood intensity over time.
    """
    if not all(col in df.columns for col in ['mood_intensity', 'mood']):
        print("\nSkipping emotional trajectory plot: 'mood' or 'mood_intensity' column not found.")
        return

    if pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        time_column = 'timestamp'
        xlabel = "Time"
    elif 'world_time' in df.columns:
        time_column = 'world_time'
        xlabel = "World Time (Ticks)"
    else:
        time_column = df.index
        xlabel = "Cycle Number"
    
    plt.figure(figsize=(15, 7))
    sns.lineplot(data=df, x=time_column, y='mood_intensity', hue='mood', marker='o', palette='viridis')
    plt.title("Adam's Emotional Trajectory Over Time", fontsize=16)
    plt.xlabel(xlabel)
    plt.ylabel("Mood Intensity")
    plt.grid(True, linestyle='--', linewidth=0.5)
    plt.legend(title='Mood')
    plt.tight_layout()
    plt.savefig("emotional_trajectory.png")
    print("Saved plot: emotional_trajectory.png")
    plt.show()

def plot_action_frequency(df):
    """
    Creates a bar chart showing the frequency of each action Adam takes.
    """
    if 'chosen_action' not in df.columns:
        print("\nSkipping action frequency plot: 'chosen_action' column not found.")
        return

    plt.figure(figsize=(12, 8))
    sns.countplot(data=df, y='chosen_action', order=df['chosen_action'].value_counts().index, palette='crest')
    plt.title("Frequency of Adam's Chosen Actions", fontsize=16)
    plt.xlabel("Count")
    plt.ylabel("Action")
    plt.tight_layout()
    plt.savefig("action_frequency.png")
    print("Saved plot: action_frequency.png")
    plt.show()

def analyze_drive_motivation(df):
    """
    Analyzes the underlying drives behind Adam's impulses.
    """
    if 'impulses' not in df.columns:
        print("\nSkipping drive analysis: 'impulses' column not found.")
        return

    drive_counts = {}
    for impulse_list in df['impulses']:
        if not isinstance(impulse_list, list): continue
        for impulse in impulse_list:
            if isinstance(impulse, dict):
                drive = impulse.get('drive', 'Unknown')
                drive_counts[drive] = drive_counts.get(drive, 0) + 1

    if not drive_counts:
        print("\nNo drive data to analyze.")
        return

    drive_series = pd.Series(drive_counts)
    
    print("\n--- Analysis of Adam's Motivations ---")
    print(drive_series)

    plt.figure(figsize=(10, 8))
    drive_series.plot(kind='pie', autopct='%1.1f%%', startangle=90, colormap='viridis')
    plt.title("Distribution of Adam's Underlying Drives", fontsize=16)
    plt.ylabel('') # Hide the y-label for pie charts
    plt.tight_layout()
    plt.savefig("drive_analysis.png")
    print("Saved plot: drive_analysis.png")
    plt.show()


if __name__ == "__main__":
    # Load the data
    behavior_df = load_and_prepare_data()

    # Exit gracefully if the dataframe is empty or missing critical columns.
    if behavior_df is None or behavior_df.empty:
        print("\nNo data to analyze. Exiting.")
    else:
        critical_columns = ['mood', 'mood_intensity', 'chosen_action', 'impulses']
        if not all(col in behavior_df.columns for col in critical_columns):
            print("\nCritical columns are missing from the log file. The file may be from an old version or corrupted.")
            print("Please delete 'adam_behavior_log.csv' and generate a new one by running the simulation.")
        else:
            # Generate the analyses and plots
            print("\nGenerating plots...")
            plot_emotional_trajectory(behavior_df)
            plot_action_frequency(behavior_df)
            analyze_drive_motivation(behavior_df)
            print("\nAnalysis complete.")

