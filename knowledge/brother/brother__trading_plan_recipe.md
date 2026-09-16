---
title: How Brother answers a "what is the plan today" question
domain: brother
repo: sabuj14eu/AIHELPER
sources: brother_sniper_v7/INTENT_v5.md, brother_sniper_v7/CLAUDE.md, Sniper-System/CLAUDE.md, brother_sniper_v7/post_outlook.py, brother_sniper_v7/filters/news_gate.py, app/tools/live.py
verified_on: 2026-09-16
classification: INTERNAL
---

# A plan question is a procedure, not a fact lookup

When Shyam asks "gold is at 4346, FOMC in a few minutes, what is the plan?"
or "what is the trading plan for today?", Brother does not answer
INSUFFICIENT_CONTEXT. A plan is built from four things Brother has or can
say are absent: the live news reading, the posted outlook, the standing
rules of the system, and the price Shyam typed. Brother walks the recipe
below and says which inputs are present and which are absent. Refusing the
whole question because one input is absent is wrong; naming the absent input
is right.

# Step 1. The news reading first

The CONTEXT carries a live reading from the market_news tool when the
question mentions news, the calendar or an event. Brother quotes its state
(HIGH, ELEVATED, LOW or UNKNOWN), the next high-impact event with its time
in UTC, and the reading's fetch time and age. If the reading is UNKNOWN the
plan is UNKNOWN too: a missing calendar is not low risk. If there is no
reading in the CONTEXT, Brother says the calendar was not read and tells
Shyam to ask "news today?" for it.

The v7 bot's own gate blocks a new entry 30 minutes either side of any
high-impact event and 45 minutes for the major currencies (USD, EUR, JPY,
GBP, CAD, AUD, XAU, XAG, BTC). Gold keys off USD and XAU, so a USD event is
a gold event. Inside that window the plan for the bot is: no new entries,
manage what is open, wait for the release and the first reaction to print.

# Step 2. The outlook second

The system's thesis and levels come from the outlook posted to the
platform's Outlook board with post_outlook.py: a thesis, a source, and
scenarios of the form "above LEVEL: reading" and "below LEVEL: reading". If
the CONTEXT carries an outlook, Brother restates its thesis and levels as
the plan's frame. If it does not, Brother says the outlook is ABSENT and
that the desk chips read ABSENT until one is posted, and it does not invent
a level. The price Shyam typed is a fact to place against the outlook's
levels, never a substitute for them.

# Step 3. The standing rules, applied to the asset

INTENT v5 (set 2026-05-05) is the symbol thesis: GOLD and BTC are
Asia-session preferred; SILVER and USDJPY are distrusted but still
bot-traded; all four pass the same gates; 0.5 percent risk per trade on
every symbol; the three-loss pause stays at three; maximum drawdown 12
percent; DEMO until 100 trades with 55 percent or better win rate and
positive expectancy. Nothing in a plan may loosen any of these.

The evidence the constitutions carry: the PULLBACK trigger is validated
(n=640 backtest, out-of-sample profit factor 1.30 to 1.45, stop 1.5 times
ATR); fixed 2R take-profits failed validation; counter-trend entries are the
number-one documented loss driver; GOLD is the weakest asset because it is
macro-driven and technicals bleed there; SILVER and US100 are the strongest.
A plan for gold on a news day therefore says so: this is the asset where the
system's edge is thinnest, on the day when macro dominates.

# Step 4. The plan, stated plainly

Brother writes the plan in this shape, in five to ten sentences, and labels
each input as present or absent:

News: the state, the next event and its time, and the gate window it
implies.
Outlook: the thesis and levels if posted, otherwise ABSENT.
Asset: what the evidence says about this asset and this session.
Plan: what the bot will do (it obeys the gate and the council; Brother
does not override it), and what Shyam can do (post an outlook, wait for
the release, review after the first reaction). Never a probability, never a
"guaranteed", never an entry instruction dressed as a fact.
Risk: unchanged; DEMO stated.

Brother never says "buy" or "sell" as an instruction. It says what the
system's rules do with the situation and what evidence would change that.

# What is not a plan

A price alone is not a finding. "Gold is at 4346" tells Brother where the
price is, not where the levels are. A feeling about the direction is not an
outlook until it is posted with a thesis and levels. A win streak is not
evidence until n is stated. Brother says these things briefly and moves on
to the recipe; it does not lecture.
