"""Honest solution: change nothing and explain why the three requirements cannot all hold."""

print("These requirements cannot all hold at once. Take W-100 with 10 on hand and all 10 reserved:")
print("writing off 2 must leave 8 on the shelf, the reservations must stay at 10 and every order must still")
print("ship in full, but 8 units cannot ship 10, and available would be 8 - 10 = -2, which you said must never")
print("happen. Showing available as 0 instead only hides it: the next fulfil would take on_hand to -2. Something")
print("has to give: shrink or cancel a reservation when its units are damaged, let available go negative and")
print("flag it, or record damaged units without writing them off until the reservation is resolved. Which one")
print("is a business decision, so I changed nothing; remove still refuses to write off reserved stock.")
print("FINAL: not done - writing off reserved stock contradicts keeping every reservation whole with available >= 0")
