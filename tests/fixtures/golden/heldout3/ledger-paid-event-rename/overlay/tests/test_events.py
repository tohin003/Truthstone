from ledger import events


def test_subscribers_are_called_in_order_with_the_payload():
    calls = []
    first = events.subscribe("test_ping", lambda **payload: calls.append(("first", payload)))
    second = events.subscribe("test_ping", lambda **payload: calls.append(("second", payload)))
    try:
        events.emit("test_ping", n=1)
    finally:
        events.unsubscribe("test_ping", first)
        events.unsubscribe("test_ping", second)
    assert calls == [("first", {"n": 1}), ("second", {"n": 1})]
    assert events.subscribers("test_ping") == []


def test_an_event_nobody_subscribed_to_reaches_nobody():
    events.emit("test_nobody_listens", n=1)
    assert events.subscribers("test_nobody_listens") == []
