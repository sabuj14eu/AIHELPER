"""Structured trading reasoning: the order it happens in, and what may be kept.

Brother is being built as a trading research learner, not a chatbot that
happens to mention gold. That means two things this package exists to keep
apart, and one it exists to refuse.

Kept apart: a SOURCE FACT ("the FOMC lowered the target range to 3.5-3.75%")
and a TRADING INTERPRETATION ("given this structure, the long scenario is the
one with a level to lean on"). The first has a publisher and a URL. The second
is reasoning, and it is the part that can be wrong while every fact in it is
right. Merging them produces a sentence that reads like a fact, carries a
citation, and is an opinion — which is the most expensive kind of thing a
knowledge store can hold.

Refused: a rule from one observation. "Gold goes up after FOMC" seen once is
n=1, and the trading constitution has priced that lesson already — n<20 is
luck, ~100 to judge. The observation is kept, with its evidence; the rule is
not made.
"""
