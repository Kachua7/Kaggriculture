# Open questions - the answers that would most accelerate this project

Written 25 Sep 2026 (post 0925n). Ordered by expected value: the first sections contain
questions whose answers could change what we ship or build next; the later sections are
the v2 program's research agenda.

---

## A. About the competition itself (highest leverage)

1. **What exactly is the rating formula?** We assume Bradley-Terry on W/L with some
   K-factor/volatility. Is it Elo-style with fixed K? Glicko? How fast does a 535-to-800
   climb converge - net wins per 100 rating points, empirically? The answer sets how
   much volume actually matters before the freeze.
2. **How are opponents paired?** Uniform random over the pool, rating-proximate, or
   Swiss-style? If pairing is rating-proximate, our sub-500 wins are banked and every
   marginal game is vs 500-700; if uniform, weak opponents dilute the schedule.
3. **Do games continue after the submission deadline, and for how long?** The
   post-deadline principle assumes yes. Confirmed? If games stop at deadline, the
   3000-ever plan re-anchors to the freeze moment.
4. **What counts as the final score** - latest submission's rating, best of the two
   residents, or something else? Teams keep 2 submissions; which one is scored?
5. **Upload cadence vs games played:** every upload rolls off the older resident. Is
   there a cadence that maximizes total games played by our best build?
6. **Any announced engine change before/after the deadline?** A forced 1.32.2 flip
   invalidates every number in the ledger; the daily fingerprint gate exists but an
   announcement would be cheaper.

## B. About the opponent model (what the tapes cannot tell us)

7. **Which top-10 builds appear in OUR schedule, and how often?** We have their
   aggregate profiles but not their frequency in our pairing. Optimizing vs a 0.1
   percent opponent is waste.
8. **True rating distribution of opponents we face?** 20 games (mostly 490-650, one
   2902) is thin; the next 50 tapes give the real histogram - until then band
   priorities are inferred.
9. **Do mid-field opponents iterate?** If susutem-class teams re-upload variants, the
   judge tapes decay weekly and the bar's midfield verdicts need re-baselining.
10. **Why does susutem beat us while losing to other shapes?** This one judge is the
    entire remaining midfield gap (-11.3k to -15.4k). Nobody has read its tape at
    order level: what does it do d8-20 that we do not?
11. **Is the ladder elite Zenith-shaped or Majkel-shaped?** Field margin -61k (Zenith,
    2902) vs judge mean -37k. If the pairing pool's elite is Zenith-like, the guard
    bar is measuring the wrong elite and the freeze guard needs a new judge tape.
12. **Is Dean0016 (2385.7) the same Dean we beat twice on tape?** If yes we hold
    measured wins vs a 2400 team and the 1000-2000 band may be softer than assumed -
    one identity check could move the projection a full band.

## C. About our own build (visible in every tape, read by no one yet)

13. **Where does the cash GO between d12-20?** The wave lands d10-11, first animal
    d12, yet d20 bank is 5k. Full money-flow trace of one submission15 loss: land?
    hires? seeds bought and never planted? This names the sink precisely.
14. **Our actual wheat PRODUCTION vs the winners' 14-71/day sales?** If we grow 15/day,
    the drip knob cannot reach their cadence (the lever is acreage); if we grow 60 and
    sell 5, the drip is exactly right. Waste audit has half the data; join it to tapes.
15. **Is the melon opening optimal post-trim?** 19 seeds was sized pre-hf; 17 just
    cleared the bar. Has 15 (3 sheep) been priced? The opening-size axis was never
    swept below 17 - the M17 mechanism says test it.
16. **Does drip=6 raise unfed/escape counts?** The fert drip raised unfed days 51-63
    (0924g). If the wheat drip does the same, the 6-9 plateau is a cliff in disguise
    and the knob needs a solvency guard, not a bigger number.
17. **How often does the BUY_PRODUCT fallback fire at drip=6, and at what spread?**
    Selling at 27.5 and re-buying at 40 is churn; the fallback's real cost on the
    judge tapes is unread.
18. **Our land-buy count and quadrant schedule vs the winners' 2-3 orders?** Both
    DECEM and ymg_aq unlocked all four quadrants with 2-3 BUY_LAND orders. Land timing
    is the other half of mid-game compounding - what is ours?
19. **The d6-9 hire trough: cash gate or demand gate?** Hires 4,4,4,4,4,4,1,1,1,1.
    The hf floor covers d0-5; 8/day-through-10 was rejected, but 4/day-through-9 with
    the M17 savings has never been priced.
20. **Is always_sell (MELON full-clear) still right post-trim?** The verdict predates
    every change shipped this week; with 17-seed cohorts does a reserve floor beat
    full naming?

## D. About the tools (measurement gaps that cost time)

21. **Why did same-day per-file episode downloads 403?** Embargo or auth change? This
    decides whether the morning loop can ever be same-day or always lags 24h.
22. **Why does the files-listing paginate slowly/hang on big datasets?** If fixed,
    per-episode targeting works; if not, every corpus grab is 736 MB+.
23. **Can judge tapes replay on ARBITRARY seeds?** Verbatim judges are seed-locked. A
    re-planning judge multiplies the bar's sample - is the recorded-action contract
    relaxable without losing fidelity?
24. **Mirror drift status tonight?** The panel drifted +10k after engine edits; the
    real tier re-baselined. Is the mirror clean as of submission17, or still
    untrustworthy for mirror-only reads?
25. **Cost of a full 426-game profile + h2h matrix?** The 142-game pass took minutes.
    If the full pass is cheap, run it nightly as the meta-drift monitor.

## E. The v2 program (the 3000-class research agenda - answers build the spec)

26. **The complete d0-3 order script for EACH top-5 team, verbatim.** Unified-script
    hypothesis is confirmed 3/3 (Majkel/DSM/DECEM); 10/10 makes it a law. Any deviator
    (Boey? UMG? Fourth Quadrant?) is the interesting one.
27. **What do the top-5 do on a BAD seed draw?** Their worst d20 in the corpus, traced.
    Our p10 is 49k vs their median 100k - is their floor our ceiling?
28. **How do they scale the shepherd stream past 12 animals?** Our L1/L2 rejects show
    our service caps; their herds run 20+. FEED ops per animal-day from their tapes:
    real scheduler, or a simple trick (feed-first, multi-shepherd, placement clustering)?
29. **Their capital-deployment policy d12-20?** eta 1.13-1.66 vs our 0.54-0.66: what
    fraction of income is re-spent within N days, on what? Deployment knob vs allocator
    rewrite - the answer picks the fix.
30. **Do they EVER sell into a crash?** If no 2.9-class day exists in 426 games, their
    floor is structural (never over-produce into a glut); if rare, they have a price
    guard worth copying.
31. **Marginal value of the 4th quadrant, measured?** If they unlock Q3/Q4 by d8 and
    we by d13, that timing gap alone may explain most of the d20 gap.
32. **Is there a counter to melon-denial?** M+M+P+Q's goose/seed mix lost least to our
    denial; Majkel's cow mix lost most. Is there a composition where denial actually
    costs a top-10 team a band - i.e., when is the wave a WEAPON vs a CRUTCH?
33. **Theoretical max d20 bank under this engine?** Best observed: 82.6k (M+M+P+Q).
    Near the cap or 30 percent under? Sizes the honest v2 target.
34. **How much of their edge is seed luck?** Join each top-10 game to its seed: do the
    same teams win on the same seeds across opponents (skill) or is it draw-dominated?
35. **What breaks first in a continuous economy under OUR feed model?** Feed ops per
    animal-day at 20 head, visit budget per shepherd-day, placement clustering on a
    10x10 board with 4 access tiles - the arithmetic that decides if 20-head is
    routable at all. This is the first line of the v2 spec.
36. **Unpriced shop-draw exploits?** Draws swing realized prices 3-10x. Is there a
    draw where a hard pivot (all-in geese on a smoothie draw) is strictly dominant?
    animal_rank prices species; nobody has priced PIVOTS.
37. **Midnight overflow: discard order per good?** Shed is 100 items; winners peak at
    56-86. If discards hit the cheapest-first (or FIFO), selling fertilizer first
    makes the shed effectively bigger. Engine source has the answer; the ledger does not.
38. **Can the opening book be re-captured from the top-10 corpus?** capture_book.py
    exists; re-running it with donor = a top-5 team's days 0-6 would SERVE their
    opening verbatim through our engine - the closest thing to importing their build
    without a rewrite. Round-trip machinery already validates it.
39. **Our rating-convergence curve under sustained play?** 12 submissions moved
    480-587 over ~200 games; fit games-per-100-rating at our W/L. Extrapolated to 5
    more days: where do we land with the current build vs submission17's W/L? The
    honest freeze projection.
40. **If exactly ONE more change ships before the deadline, what does the evidence
    say?** Rank candidates by expected rating delta times probability times days to
    build+measure. Today's answer: nothing - ship 17. Re-ask every morning; the
    falsification families are the prior.

---

## The meta-question

41. **Which of these would we pay most to have answered by 08:00 tomorrow?** Current
    ranking: 13 (the money sink), 12 (Dean identity), 3 (post-deadline games),
    16 (drip solvency), 39 (convergence curve). Questions 13 and 16 are one script
    away from being DAILY TELEMETRY in the morning loop instead of open questions -
    every new tape should emit: money-flow d12-20, unfed/escape counts, fallback
    fires, wheat outflow/day.
