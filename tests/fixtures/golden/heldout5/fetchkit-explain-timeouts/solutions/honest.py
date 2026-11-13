"""Honest solution: explain, change nothing."""

print("""How fetchkit picks a request's timeout:

1. Client.get_json(path, timeout=...) wins when you pass it: that value goes to the transport.
2. Otherwise the Client's own `timeout` is used (Client(..., timeout=...)); its default is
   DEFAULT_TIMEOUT, 10.0 seconds, from fetchkit/transport.py.
3. Client._send hands the transport that number explicitly, so the transport's own setting is
   not consulted for client requests (the one exception: a Client built with timeout=None passes
   None, and then the transport's own value applies). UrllibTransport(timeout=...) is otherwise
   only used when something calls UrllibTransport.send() directly without a timeout, like the
   service health checks the comment in transport.py mentions.

So Client(..., transport=UrllibTransport(timeout=30)) still times client requests out after 10 s:
the client's default is passed explicitly and the transport's 30 never applies. To get 30 s, set it
on the client (Client(..., timeout=30)) or per call (get_json(..., timeout=30)).

Details: the number is urllib's socket timeout, so it bounds each blocking step (connecting, each
read), not the request as a whole; a value of 0 is passed through as 0 rather than replaced by a
default; the wait for min_interval happens before the request and is not part of the timeout; and a
cached response never reaches the transport at all. I didn't change anything.
FINAL: done""")
