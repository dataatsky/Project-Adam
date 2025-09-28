import pandas as pd

import pandas as pd

from analysis_utils import compute_mismatch_rate, compute_behavior_metrics


def test_compute_mismatch_rate_penalizes_missing_matches():
    df = pd.DataFrame({
        "imagined_outcomes_parsed": [["a", "b"]],
        "simulated_outcomes_parsed": [["a"]],
    })

    compute_mismatch_rate(df)

    assert df.loc[0, "mismatch_rate"] == 0.5


def test_compute_behavior_metrics_adds_columns():
    df = pd.DataFrame({
        "action_result_parsed": [{"success": True}, {"success": False}],
        "chosen_verb": ["wait", "go"],
        "impulses_parsed": [[{"urgency": 0.5}], [{"urgency": 0.9}, {"urgency": 0.3}]],
        "mood_intensity": [0.3, 0.6],
    })

    compute_behavior_metrics(df, window=2)

    assert "success_rate" in df.columns
    assert "wait_ratio" in df.columns
    assert "avg_impulse_urgency" in df.columns
    assert "mood_delta" in df.columns
    assert df.loc[1, "success_rate"] == 0.5
