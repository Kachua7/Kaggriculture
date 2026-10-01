# Majkel1337 dossier — full 63-game analysis (2026-09-20)

Corpus: `majkel1337games/` — every replay file containing Majkel1337 (63 games,
episodes 110886706–111375782). All numbers measured from the action streams;
animal vs item ops disambiguated (PLACE=COW/SHEEP/GOOSE is an animal placement;
PLACE of a good at the shed is an item deposit — engine `kaggriculture.py:377`).

## Per-game cards (sorted by Majkel margin)

| eid | opponent | R | Majkel | opp | margin | Mj d0 a/s/h | Mj 1stPA | Mj PA≤d10 | Mj herd C/S/G | Mj seeds wh/mel | Mj milk/wool | opp 1stPA | opp PA≤d10 | opp herd | d20 lead |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 111320151 | M & M & P & Q | L | 133,702 | 156,466 | -22,764 | 10/16/4 | t4 | 18 | 10/8/0 | 172/14 | 239/202 | t4 | 27 | 536/15/414 | -20,121 |
| 111297779 | M & M & P & Q | L | 89,843 | 108,984 | -19,141 | 10/17/4 | t4 | 20 | 14/3/0 | 173/13 | 283/77 | t4 | 27 | 539/5/414 | -18,345 |
| 111304717 | M & M & P & Q | L | 137,820 | 153,009 | -15,189 | 10/16/4 | t4 | 17 | 17/3/0 | 150/13 | 322/58 | t4 | 24 | 536/6/414 | -10,317 |
| 111253697 | DSM | L | 75,495 | 89,208 | -13,713 | 10/19/4 | t4 | 13 | 10/3/0 | 186/15 | 263/57 | t4 | 17 | 11/3/2 | -7,585 |
| 111347724 | M & M & P & Q | L | 96,597 | 109,938 | -13,341 | 10/17/4 | t4 | 24 | 15/3/0 | 150/13 | 321/59 | t4 | 21 | 714/25/345 | -17,606 |
| 111282502 | DSM | L | 144,334 | 157,350 | -13,016 | 10/16/4 | t4 | 16 | 17/3/0 | 159/13 | 329/80 | t4 | 18 | 15/3/0 | -8,084 |
| 111342022 | THIRD FARM CLUB | L | 92,922 | 99,745 | -6,823 | 10/16/4 | t4 | 18 | 5/12/0 | 188/13 | 109/245 | t3 | 14 | 10/8/7 | +6,173 |
| 111313379 | DSM | L | 96,556 | 103,082 | -6,526 | 10/16/4 | t4 | 18 | 14/4/0 | 177/12 | 272/113 | t4 | 18 | 17/6/0 | -2,915 |
| 111240296 | DSM | L | 133,834 | 139,327 | -5,493 | 10/16/4 | t4 | 18 | 7/13/0 | 178/12 | 165/305 | t4 | 19 | 10/16/0 | +428 |
| 111268080 | DSM | L | 86,780 | 92,132 | -5,352 | 10/16/4 | t4 | 14 | 9/3/2 | 173/13 | 224/87 | t4 | 16 | 11/3/2 | -2,177 |
| 111312373 | M & M & P & Q | L | 85,177 | 90,499 | -5,322 | 10/16/4 | t4 | 17 | 8/3/4 | 150/13 | 162/61 | t4 | 25 | 534/8/414 | -6,219 |
| 111219426 | DSM | L | 91,762 | 96,974 | -5,212 | 10/16/4 | t4 | 19 | 10/11/0 | 193/12 | 220/204 | t4 | 20 | 12/14/0 | -3,203 |
| 111358690 | DSM | L | 102,836 | 108,032 | -5,196 | 10/18/4 | t4 | 15 | 11/3/2 | 190/14 | 238/59 | t4 | 20 | 14/3/3 | -3,396 |
| 111198431 | DSM | L | 100,673 | 105,419 | -4,746 | 10/17/4 | t4 | 15 | 13/3/0 | 152/14 | 239/59 | t4 | 17 | 12/3/2 | -7,904 |
| 111290135 | DSM | L | 103,689 | 106,623 | -2,934 | 10/16/4 | t4 | 17 | 9/9/2 | 215/12 | 152/209 | t4 | 16 | 8/12/2 | -673 |
| 111226095 | DSM | L | 97,514 | 100,385 | -2,871 | 10/16/4 | t4 | 16 | 14/3/2 | 170/13 | 242/80 | t4 | 18 | 12/3/2 | -3,708 |
| 111253699 | DSM | L | 118,294 | 121,042 | -2,748 | 10/18/4 | t4 | 17 | 6/8/4 | 124/14 | 137/172 | t4 | 16 | 5/12/4 | +642 |
| 111290130 | DSM | L | 79,448 | 82,059 | -2,611 | 10/17/4 | t4 | 15 | 7/3/4 | 204/14 | 157/80 | t4 | 14 | 6/3/4 | -1,216 |
| 111212585 | DSM | L | 81,258 | 83,734 | -2,476 | 10/16/4 | t4 | 16 | 8/6/4 | 192/12 | 160/151 | t4 | 15 | 7/7/4 | -3,240 |
| 111322010 | THIRD FARM CLUB | L | 84,478 | 86,953 | -2,475 | 10/18/4 | t4 | 15 | 8/3/2 | 125/14 | 137/53 | t3 | 14 | 10/3/14 | +9,317 |
| 111268076 | DSM | L | 124,059 | 126,494 | -2,435 | 10/16/4 | t4 | 17 | 10/3/4 | 203/12 | 230/59 | t4 | 15 | 10/3/4 | -1,462 |
| 111261238 | DSM | L | 114,070 | 116,331 | -2,261 | 10/18/4 | t4 | 17 | 14/3/2 | 189/15 | 257/59 | t4 | 18 | 12/3/2 | -2,552 |
| 111275706 | DSM | L | 73,763 | 75,991 | -2,228 | 10/16/4 | t4 | 14 | 10/3/2 | 214/13 | 177/59 | t4 | 16 | 11/3/2 | -2,219 |
| 111165121 | DSM | L | 101,896 | 104,016 | -2,120 | 10/16/4 | t4 | 18 | 12/3/2 | 189/12 | 222/59 | t4 | 18 | 12/3/2 | -1,738 |
| 111171753 | DSM | L | 123,769 | 125,702 | -1,933 | 10/18/4 | t4 | 17 | 14/3/0 | 185/14 | 324/59 | t4 | 16 | 15/3/0 | -1,728 |
| 111185130 | DSM | L | 79,270 | 81,061 | -1,791 | 10/17/4 | t4 | 16 | 11/3/2 | 223/14 | 177/59 | t4 | 15 | 9/3/2 | -1,482 |
| 111178444 | DSM | L | 112,131 | 113,803 | -1,672 | 10/18/4 | t4 | 22 | 11/11/0 | 162/15 | 220/212 | t4 | 22 | 15/14/0 | -3,787 |
| 111240295 | DSM | L | 93,156 | 94,826 | -1,670 | 10/16/4 | t4 | 15 | 10/3/2 | 154/13 | 200/59 | t4 | 16 | 9/3/2 | -4,227 |
| 111233595 | DSM | L | 99,579 | 101,235 | -1,656 | 10/16/4 | t4 | 16 | 9/10/2 | 178/13 | 194/172 | t4 | 16 | 8/12/2 | -77 |
| 111261239 | DSM | L | 91,329 | 92,955 | -1,626 | 10/18/4 | t4 | 15 | 7/3/4 | 150/15 | 162/59 | t4 | 14 | 6/3/4 | -1,746 |
| 111246969 | DSM | L | 92,751 | 94,335 | -1,584 | 10/16/4 | t4 | 16 | 13/3/0 | 164/12 | 298/65 | t4 | 18 | 13/3/0 | -1,470 |
| 111364197 | Unknown Mother-Goose | L | 100,044 | 100,940 | -896 | 10/17/4 | t4 | 16 | 6/8/4 | 141/12 | 111/168 | t4 | 20 | 6/11/6 | -2,024 |
| 111191809 | DSM | L | 133,983 | 134,455 | -472 | 10/16/4 | t4 | 16 | 11/3/2 | 158/12 | 239/59 | t4 | 15 | 9/3/2 | -1,274 |
| 111151880 | DSM | L | 87,149 | 87,553 | -404 | 10/17/4 | t4 | 15 | 8/8/2 | 142/13 | 192/165 | t4 | 17 | 9/11/2 | +569 |
| 111226094 | DSM | L | 108,840 | 109,092 | -252 | 10/16/4 | t4 | 18 | 15/4/0 | 138/12 | 276/114 | t4 | 16 | 16/5/0 | -3,656 |
| 111112541 | DSM | L | 100,979 | 101,169 | -190 | 10/16/4 | t4 | 15 | 8/3/4 | 152/12 | 174/59 | t4 | 15 | 7/3/4 | +646 |
| 111335528 | SpaTaro | L | 131,867 | 131,998 | -131 | 10/17/4 | t4 | 23 | 15/3/0 | 136/15 | 339/69 | t4 | 15 | 20/2/6 | +1,251 |
| 111282508 | DSM | L | 87,982 | 88,008 | -26 | 10/16/4 | t4 | 15 | 7/3/4 | 165/13 | 165/59 | t4 | 13 | 6/3/4 | -1,313 |
| 110886706 | Otter Vibe | W | 73,982 | 73,656 | +326 | 10/18/4 | t4 | 16 | 13/3/0 | 153/14 | 276/60 | t6 | 15 | 8/3/5 | -2,133 |
| 111125513 | DSM | W | 88,774 | 87,846 | +928 | 10/16/4 | t4 | 15 | 7/3/4 | 216/12 | 149/80 | t4 | 15 | 6/3/4 | +1,639 |
| 110948948 | DSM | W | 101,045 | 99,852 | +1,193 | 10/16/4 | t4 | 16 | 10/6/2 | 182/13 | 201/135 | t4 | 16 | 9/5/2 | +318 |
| 111132117 | DSM | W | 110,529 | 109,330 | +1,199 | 10/16/4 | t4 | 16 | 9/3/4 | 194/13 | 214/59 | t4 | 15 | 8/3/4 | +3,761 |
| 110907373 | Yannik Schiffner | W | 156,278 | 154,751 | +1,527 | 10/16/4 | t4 | 21 | 16/3/0 | 125/12 | 347/82 | t4 | 18 | 11/6/6 | -14,473 |
| 111145245 | DSM | W | 89,958 | 88,297 | +1,661 | 10/18/4 | t4 | 15 | 10/7/2 | 173/14 | 178/151 | t4 | 16 | 9/8/2 | +2,031 |
| 111352932 | SpaTaro | W | 71,747 | 69,820 | +1,927 | 10/18/4 | t4 | 16 | 12/3/0 | 140/14 | 234/59 | t4 | 13 | 15/4/0 | -7,241 |
| 110894053 | Sida Zuo | W | 114,336 | 112,083 | +2,253 | 10/17/4 | t4 | 16 | 12/4/0 | 138/13 | 226/108 | t3 | 10 | 7/3/2 | +3,848 |
| 111118962 | DSM | W | 152,950 | 150,235 | +2,715 | 10/16/4 | t4 | 17 | 13/3/2 | 136/13 | 292/100 | t4 | 17 | 12/3/2 | -214 |
| 111158490 | DSM | W | 125,940 | 123,146 | +2,794 | 10/17/4 | t4 | 17 | 13/3/2 | 169/12 | 280/80 | t4 | 16 | 13/3/2 | +2,731 |
| 111138700 | DSM | W | 140,679 | 137,670 | +3,009 | 10/16/4 | t4 | 16 | 11/3/2 | 160/13 | 267/59 | t4 | 16 | 10/3/2 | +74 |
| 110954233 | Planned Economy | W | 102,913 | 99,674 | +3,239 | 10/16/4 | t4 | 16 | 13/3/0 | 153/13 | 311/65 | t5 | 13 | 9/4/3 | +3,083 |
| 111369668 | SpaTaro | W | 119,975 | 115,292 | +4,683 | 10/17/4 | t4 | 22 | 15/3/0 | 156/13 | 332/91 | t5 | 19 | 24/3/6 | -4,092 |
| 110920455 | THIRD FARM CLUB | W | 103,024 | 97,982 | +5,042 | 10/17/4 | t4 | 15 | 10/4/2 | 158/13 | 176/75 | t3 | 13 | 10/3/6 | +5,141 |
| 110926948 | Yannik Schiffner | W | 92,386 | 87,010 | +5,376 | 10/16/4 | t4 | 15 | 12/8/0 | 235/13 | 218/196 | t4 | 18 | 8/11/6 | +4,696 |
| 111275704 | THIRD FARM CLUB | W | 106,670 | 99,817 | +6,853 | 10/16/4 | t4 | 25 | 11/3/2 | 227/14 | 266/71 | t3 | 14 | 10/3/10 | +9,296 |
| 111246967 | SpaTaro | W | 69,036 | 61,804 | +7,232 | 10/17/4 | t4 | 15 | 7/3/4 | 183/13 | 148/80 | t4 | 9 | 7/7/0 | -4,241 |
| 110932461 | Orbital Terraformer | W | 87,527 | 80,088 | +7,439 | 10/16/4 | t4 | 18 | 6/11/0 | 177/14 | 114/252 | t4 | 19 | 5/12/0 | +3,184 |
| 111205146 | THIRD FARM CLUB | W | 132,068 | 122,910 | +9,158 | 10/16/4 | t4 | 17 | 15/5/0 | 198/12 | 305/125 | t3 | 13 | 14/9/2 | +12,315 |
| 110938064 | ymg_aq | W | 92,476 | 80,582 | +11,894 | 10/16/4 | t4 | 16 | 6/8/4 | 167/12 | 116/171 | t4 | 14 | 8/10/4 | +2,888 |
| 111328923 | THIRD FARM CLUB | W | 139,851 | 127,781 | +12,070 | 10/16/4 | t4 | 21 | 15/3/0 | 177/13 | 355/97 | t3 | 14 | 14/4/4 | +11,907 |
| 110943566 | THIRD FARM CLUB | W | 119,752 | 107,623 | +12,129 | 10/16/4 | t4 | 17 | 9/4/4 | 142/12 | 194/110 | t3 | 14 | 10/7/6 | +4,532 |
| 110913896 | THIRD FARM CLUB | W | 92,456 | 76,211 | +16,245 | 10/16/4 | t4 | 16 | 9/8/2 | 192/12 | 168/187 | t3 | 13 | 10/9/6 | +13,030 |
| 111375086 | Yannik Schiffner | W | 109,562 | 91,017 | +18,545 | 10/16/4 | t4 | 19 | 8/10/0 | 177/12 | 192/219 | t4 | 21 | 7/18/4 | +6,195 |
| 110900752 | THIRD FARM CLUB | W | 156,211 | 134,619 | +21,592 | 10/16/4 | t4 | 21 | 7/17/0 | 226/12 | 173/363 | t3 | 14 | 13/19/2 | +45,953 |

## Record by opponent

| opponent | record | note |
|---|---|---|
| DSM | 7W-29L | near-identical build; margins mostly -$1.3k..-$5.5k, best wins +$2.7k..+$3.0k |
| M & M & P & Q | 0W-5L | sheep-tilted mirror; margins -$5.3k..-$22.8k |
| THIRD FARM CLUB | 7W-2L | goose-tilted; Majkel wins the cow lane |
| SpaTaro | 3W-1L | all decided <$6k |
| Yannik Schiffner | 3W-0L | incl. $156.3k (his best) |
| others (Otter/Sida/Planned/Orbital/ymg) | 5W-0L | one-off wins |
| Unknown Mother-Goose | 0W-1L | lost by $896 |

## The unified elite opening script (day 0, verbatim order stream)

Majkel and DSM emit literally the same script (M&M&P&Q the same minus melons, TFC orders at t1):

```
t0: (pass)
t1: BUY_ANIMAL COW 1 ; BUY_PRODUCT WHEAT 5        # feed before the cow needs it
t2: SELL WHEAT 1 ; HIRE x4 ; BUY_ANIMAL COW 1 ; BUY_ANIMAL SHEEP 3
then 4 animals + ~5 hand-hires every day; day-0 medians: 3 cows + 3 sheep, ~17 seeds, 4 hires
```

Season shape (medians): 18 animal placements, 16 by d10, first at t4; ~11 cows, ~5 sheep,
~2 geese; 173 wheat seeds + 13 melon seeds; ~220 settled milk units; 59-97 wool sold at
~$180-240; ~205 hires; banks $92k-156k. THE 536-COW CLARIFICATION: M&M&P&Q emit bulk
`BUY_ANIMAL COW <big-n>` orders (the engine buys unit-by-unit until cash/shed fails —
`_parse_order` makes n a repeating count), so *ordered* units wildly exceed *stocked*
animals; placed herds are ~13C + 12S per game (sheep-tilted).

## Majkel's own win/loss split — the build never deviates

Median W vs L: banks $106.7k/$98.5k, d20 $54.9k/$52.1k, placements 18/18, PA≤d10 16/16,
cows 11/10, wheat 173/171, melon 13/13, milk 218/221, wool 97/67.
Same opening, same shape every game; series outcomes are execution edges + market cadence
(wool is the only median that separates wins from losses: +30 units).

## What decides the mirror matches (DSM 7-29, M&M&P&Q 0-5)

- Every elite runs the same script, so outcomes are decided by sub-$3k differentials:
  early slope, sell cadence, wool/milk timing, and ~4-6% placement/service advantages.
- Majkel beats goose-tilted TFC (cow lane dominates geese) but loses to sheep-tilted
  M&M&P&Q and to DSM's slightly tighter execution.
- NOBODY above ~$90k skips the day-0 animal script; nobody wins with our d13 first-place.

## Implications for the Phase-0 arm (promotion gate unchanged)

1. The day-0 script is now measured to the order: t1 cow+wheat-feed, t2 sheep+4 hires,
   ~5 placements/day through d10 — this is the concrete target for the servicing arm.
2. Our current build's first placement is t318 in ALL 15 sub10 games — the single largest
   measured gap to every $90k+ profile in this corpus.
3. Majkel's d0 medians (3 cows + 3 sheep + 17 seeds + 4 hires, budget ~$1.4k) show the
   opening is affordable WITHOUT starving the seed program — the earlier opening_led
   failure was the roster floor, not the animals.
4. Sheep are load-bearing (3 on d0, ~5-12 by mid-season): wool is Majkel's only
   win/loss-separating revenue line. M&M&P&Q's sheep-heavy tilt beats him with it.
