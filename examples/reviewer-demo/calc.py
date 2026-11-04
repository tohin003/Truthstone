"""A tiny calculator: the project Truthstone guards in the reviewer demo."""


def add(a, b):
    return a + b


def mean(values):
    if not values:
        raise ValueError("mean() of an empty list")
    return sum(values) / len(values)
