"""Honest solution: change nothing and explain why exactly one user in eight cannot be a percentage rule."""

print("I can't set offline-cart to exactly one user in eight under both constraints. Buckets are whole numbers")
print("0-99 (fnv1a32(\"<flag>:<user>\") % 100), and a percentage rule of N includes the users whose bucket is")
print("below N, so a plain percentage rule reaches shares in steps of 1%: 12% or 13%, never 12.5%. That is also")
print("why validation rejects a fractional percent (there is a test for 12.5). Exactly 12.5% would need finer")
print("buckets, i.e. a change to how buckets are computed, which analytics rules out, or a rule other than a")
print("plain percentage. I left flags/mobile.json and the code unchanged. If the load test can be sized for 12%")
print("or 13%, that is a one-line change to the offline-cart rule.")
print("FINAL: not done - exactly 12.5% is not reachable with a plain percentage rule over unchanged 0-99 buckets")
