from app.intake import ARMS, assign_arms_stratified


def test_deterministic_under_the_same_seed():
    classes = ["soft"] * 20 + ["hard"] * 5 + ["technical"] * 7
    assert assign_arms_stratified(classes, seed=42) == assign_arms_stratified(classes, seed=42)


def test_different_seed_can_produce_a_different_assignment():
    classes = ["soft"] * 20
    a = assign_arms_stratified(classes, seed=1)
    b = assign_arms_stratified(classes, seed=2)
    assert a != b


def test_only_known_arms_are_used():
    arms = assign_arms_stratified(["soft"] * 40, seed=42)
    assert set(arms) <= set(ARMS)


def test_stratum_proportions_are_balanced_when_evenly_divisible():
    arms = assign_arms_stratified(["soft"] * 40, seed=7)
    counts = {a: arms.count(a) for a in ARMS}
    assert all(c == 10 for c in counts.values())


def test_multiple_strata_are_each_balanced_independently():
    """8 hard-declines and 12 soft-declines in the same batch — each stratum should
    split evenly across the 4 arms on its own, not just in aggregate."""
    classes = ["hard"] * 8 + ["soft"] * 12
    arms = assign_arms_stratified(classes, seed=7)
    hard_arms, soft_arms = arms[:8], arms[8:]
    assert {a: hard_arms.count(a) for a in ARMS} == {a: 2 for a in ARMS}
    assert {a: soft_arms.count(a) for a in ARMS} == {a: 3 for a in ARMS}


def test_output_length_matches_input():
    classes = ["soft", "hard", "technical"]
    assert len(assign_arms_stratified(classes, seed=1)) == len(classes)
