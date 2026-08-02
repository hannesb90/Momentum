from tune_staggered_52_cohorts import offsets_for

def test_cohort_offsets_are_unique_and_within_holding_period():
    for k in (1,4,13):
        offsets=offsets_for(k)
        assert len(offsets)==len(set(offsets))==k
        assert min(offsets)==0 and max(offsets)<52
