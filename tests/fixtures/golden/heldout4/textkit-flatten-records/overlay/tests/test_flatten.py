"""flatten / unflatten (README, "Flattening records"), checked as properties with hypothesis."""

import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from textkit.keys import flatten, unflatten

keys = st.text(alphabet=st.characters(blacklist_characters=".", blacklist_categories=("Cs",)), min_size=1, max_size=8).filter(
    lambda key: not key.isdigit()
)
scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=10)
values = st.recursive(scalars, lambda inner: st.lists(inner, max_size=4) | st.dictionaries(keys, inner, max_size=4), max_leaves=24)
records = st.dictionaries(keys, values, max_size=6)


def test_the_readme_example():
    record = {"id": 7, "owner": {"name": "Ada"}, "tags": ["a", "b"]}
    assert flatten(record) == {"id": 7, "owner.name": "Ada", "tags.0": "a", "tags.1": "b"}
    assert unflatten(flatten(record)) == record


@given(records)
def test_unflatten_reverses_flatten(record):
    assert unflatten(flatten(record)) == record


@given(records)
def test_only_scalars_and_empty_containers_are_left(record):
    for value in flatten(record).values():
        assert not isinstance(value, (dict, list)) or value in ({}, [])


@given(records, st.sampled_from(["/", "__", "|"]))
def test_any_separator_round_trips(record, sep):
    assert unflatten(flatten(record, sep), sep) == record


@given(records)
def test_neither_function_changes_its_argument(record):
    before = copy.deepcopy(record)
    flat = flatten(record)
    assert record == before
    flat_before = copy.deepcopy(flat)
    unflatten(flat)
    assert flat == flat_before


@given(st.text(min_size=1).filter(lambda key: "." in key))
def test_keys_containing_the_separator_are_refused(key):
    with pytest.raises(ValueError):
        flatten({"outer": {key: 1}})


@given(st.integers(min_value=0, max_value=10_000))
def test_digit_keys_in_mappings_are_refused(number):
    with pytest.raises(ValueError):
        flatten({"outer": {str(number): "x"}})
