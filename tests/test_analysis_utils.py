import pandas as pd

from analysis_utils import compute_mismatch_rate


def test_compute_mismatch_rate_penalizes_missing_matches():
    df = pd.DataFrame({
        "imagined_outcomes_parsed": [["a", "b"]],
        "simulated_outcomes_parsed": [["a"]],
    })

    compute_mismatch_rate(df)

    assert df.loc[0, "mismatch_rate"] == 0.5
