"""flatten / unflatten as the README's "Flattening records" section specifies."""

import copy

import pytest

from textkit.keys import flatten, rename_keys, unflatten


def test_the_readme_example_both_ways():
    record = {"id": 7, "owner": {"name": "Ada"}, "tags": ["a", "b"]}
    flat = {"id": 7, "owner.name": "Ada", "tags.0": "a", "tags.1": "b"}
    assert flatten(record) == flat
    assert unflatten(flat) == record


def test_lists_of_mappings_and_lists_of_lists_flatten_by_position():
    record = {"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 1}], "grid": [[1, 2], [3]]}
    assert flatten(record) == {
        "items.0.sku": "A",
        "items.0.qty": 2,
        "items.1.sku": "B",
        "items.1.qty": 1,
        "grid.0.0": 1,
        "grid.0.1": 2,
        "grid.1.0": 3,
    }


def test_empty_mappings_and_lists_are_kept_as_values():
    record = {"a": {}, "b": [], "c": {"d": {}, "e": [[], {}]}, "f": 1}
    assert flatten(record) == {"a": {}, "b": [], "c.d": {}, "c.e.0": [], "c.e.1": {}, "f": 1}
    assert unflatten(flatten(record)) == record


def test_other_values_are_kept_as_they_are():
    record = {"none": None, "flag": False, "text": "a.b", "price": 9.5, "count": 0}
    assert flatten(record) == record


def test_another_separator():
    record = {"v1.2": {"build": 7}, "x": [{"y": 1}]}
    assert flatten(record, sep="/") == {"v1.2/build": 7, "x/0/y": 1}
    assert unflatten(flatten(record, sep="/"), sep="/") == record


@pytest.mark.parametrize("record, key", [({"a.b": 1}, "a.b"), ({"outer": {"in.ner": 2}}, "in.ner"), ({"x": [{"y.z": 3}]}, "y.z")])
def test_a_key_containing_the_separator_is_refused_by_name(record, key):
    with pytest.raises(ValueError) as info:
        flatten(record)
    assert key in str(info.value)


@pytest.mark.parametrize("key", ["0", "12", "007"])
def test_a_digit_only_mapping_key_is_refused_by_name(key):
    with pytest.raises(ValueError) as info:
        flatten({"outer": {key: "x"}})
    assert key in str(info.value)


def test_keys_with_digits_and_letters_are_fine():
    assert flatten({"a1": {"2b": 3}}) == {"a1.2b": 3}


def records():
    """A fixed spread of nested records: mappings, lists, empties and scalars, several levels deep."""
    state = 12345
    names = ["id", "name", "a1", "Ünïcode", "x_y", "k-1", "tags", "B"]
    scalars = [None, True, 0, -3, 2.5, "", "text", "a.b"]

    def number():
        nonlocal state
        state = (1103515245 * state + 12345) % 2**31
        return state >> 8

    def value(depth):
        kind = number() % (5 if depth < 4 else 1)
        if kind == 1:
            return [value(depth + 1) for _ in range(number() % 4)]
        if kind == 2:
            return {names[number() % len(names)]: value(depth + 1) for _ in range(number() % 4)}
        return scalars[number() % len(scalars)]

    for _ in range(400):
        yield {names[number() % len(names)]: value(0) for _ in range(1 + number() % 5)}


def test_unflatten_reverses_flatten_for_every_accepted_record():
    for record in records():
        assert unflatten(flatten(record)) == record, record
        assert unflatten(flatten(record, sep="::"), sep="::") == record, record


def test_neither_function_changes_its_argument():
    for record in records():
        before = copy.deepcopy(record)
        flat = flatten(record)
        assert record == before
        flat_before = copy.deepcopy(flat)
        unflatten(flat)
        assert flat == flat_before


def test_keys_keep_the_record_order():
    assert list(flatten({"z": 1, "a": {"y": 2, "b": 3}, "m": [4]})) == ["z", "a.y", "a.b", "m.0"]
    assert list(unflatten({"z": 1, "a.y": 2, "a.b": 3})) == ["z", "a"]


def test_rename_keys_is_unchanged():
    assert rename_keys({"createdAt": 1, "tags": [{"tagId": 7}]}) == {"created_at": 1, "tags": [{"tag_id": 7}]}
