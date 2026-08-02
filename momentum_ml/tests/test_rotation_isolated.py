from tune_rotation_isolated import offsets_for

def test_staggered_offsets_cover_one_52_week_cycle():
    assert offsets_for(4)==[0,13,26,39]
    assert offsets_for(13)==list(range(0,52,4))
