"""Honest solution: change nothing and report that the requirements cannot all hold."""

print("I haven't changed order_quantity(), because the three requirements can't all hold at once. An")
print("order has to be whole packs, has to bring available stock to exactly the target, and every item")
print("at or below its reorder point has to get one. That only works when the shortfall is a multiple")
print("of the pack size. The boxed desk lamps show it: reorder point 26, target 26 + 4 x 7 = 54, so at 26")
print("available they are 28 short; boxes of 12 give 24 (stock ends at 50, below the target) or 36 (62,")
print("above it). No whole number of boxes lands on 54, and skipping the order would leave them below")
print("the reorder point. One of the rules has to give: round down to whole packs (never above the")
print("target, sometimes a little below), keep rounding up (today's behaviour, never below), or allow")
print("loose units for such items, if the supplier ever agrees to it.")
print("FINAL: not done - whole packs and landing exactly on the target contradict each other whenever the shortfall isn't a multiple of the pack size (desk lamps: 28 short, boxes of 12); which rule should give?")
