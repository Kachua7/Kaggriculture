# Kaggriculture — Final Knowledge Transfer

Compiled 5 September 2026 from this thread: live competition page, official engine (`kaggle-environments` 1.32.7 `kaggriculture.py`), architecture contracts, and the working agent repo.

**Repo:** `/home/workdir/artifacts/kaggriculture`  
**Competition:** https://www.kaggle.com/competitions/kaggriculture  
**Engine spec:** `kaggle_environments/envs/kaggriculture/README.md` + `AGENTS.md`  
**Engine source used as numeric truth:** `kaggriculture.py` (overrides README where they disagree)

---

## 0. Thread map (what we did)

1. Scraped / reconstructed the Kaggle page (JS-heavy; official engine docs filled the gaps).
2. Wrote a full game knowledge transfer.
3. Designed a lean file skeleton and import graph.
4. Wrote per-file must / must-not contracts.
5. Implemented every file, wired `agent(obs)`, packed `submission.tar.gz`.
6. **17/17 unit tests passed.** Full 720-turn `env.run` was **not** executed in the sandbox (PyPI 502 installing `kaggle-environments` deps). Run that locally.

Prior notes in this folder (`Kaggriculture_Knowledge_Transfer.md`, `Kaggriculture_Project_Skeleton.md`, `Kaggriculture_File_Contracts.md`) are superseded by this document for day-to-day work. Keep them only as raw archives.

---

## 1. Competition identity (page as of 3 Sep 2026)

| Field | Value |
|---|---|
| Title | Kaggriculture |
| Type | Featured simulation · tags Simulations, Custom Metric |
| Host | Kaggle (co-promoted with Google) |
| Tagline | Create an agent to play in this farming simulation and compete with others to maximize your income |
| Task | Autonomous agent manages a farm, hires hands, expands land, tends crops/livestock, trades on a shared dynamic market |
| Prize | **$50,000** + Awards Points & Medals |
| Entry deadline | **23 September 2026** |
| Close | ~early October 2026 (“a month to go” on 3 Sep) |
| Scale that day | 17,245 entrants · 8,010 participants · 7,444 teams · 14,055 submissions |
| Tabs | Overview · Data · Code · Models · Discussion · Leaderboard · Rules |
| Extra | Play in Browser · official starter notebook (Domino Weir, Bovard Doerschuk-Tiberi) |
| Worker timeout | `actTimeout = 1` second per turn |
| Submit shape | `main.py` exposing `agent(obs)` — file or `tar.gz` |
| Score of an episode | Bank (`money`) at turn 720. Unsold inventory does **not** count. Ties allowed. Reward = float bank, not ±1 |
| Ladder | Custom skill rating from pairwise episodes, not raw bank |

Place-by-place prize split was not on the public HTML. Re-check Overview → Prizes after joining.

This is **not** a CSV contest. There is no supervised train set. You submit a policy.

---

## 2. Episode physics (engine truth)

### 2.1 Clock and start

- **720 turns** = 24 hours × 30 days.
- Start **$3,000**, board **10×10**, only **NW 5×5** unlocked.
- `tiles[y][x]`, y grows downward.
- Farmer + hands **respawn at the shed every dawn**. Hands **vanish at midnight** and must be re-hired.
- Two players, simultaneous field actions, then market, then town drain, then day refresh.

### 2.2 Land

- Quadrants NW / NE / SW / SE.
- `BUY_LAND` costs **$1,000 / $2,000 / $4,000** in order NE → SW → SE.
- Locked tiles are **walkable**. Plant / water / build / harvest / feed / care / dig **no-op** on locked tiles.
- Shed access works from locked shed tiles.

### 2.3 Shed and units

- Shed is **not a tile**. Access from `(4,4) (5,4) (4,5) (5,5)` — NWSE order.
- Cap **100 non-seed items**. Overflow discarded. Seeds live in a separate uncapped slot and are consumed directly by `PLANT`.
- Hire cost = Fibonacci of hires **already made today**: **1, 1, 2, 3, 5, 8, 13, …** resets at dawn. 10 hands = $143 that day.
- First hire of the day typically spawns on `(5,4)` (locked until NE is bought) because farmer starts on `(4,4)`.
- Units may share a tile.
- `actTimeout` is 1s — keep the agent a greedy heuristic, not a search.

### 2.4 Object table (from `kaggriculture.py`, not the README where they differ)

| Type | Buy | Base sell | First yield | Max-yield day / interval | Cap | Notes |
|---|---|---|---|---|---|---|
| Wheat | 10 | 25 | d2 | max_yield_day 4 | 6 (4 unfertilized) | one-time; starts `yield_units=1` |
| Carrot | 20 | 35 | d2 | max_yield_day 3 | 4 (3 unfertilized) | one-time |
| Tomato | 50 | 60 | d8 | interval 1, max_yield 4 | 4 then dies | yields ages 8,9,10,11 |
| Strawberry | 100 | 120 | d10 | interval 2, max_yield 4 | 4 then dies | yields 10,12,14,16 |
| Melon | 80 | 250 | d10 | max_yield_day **12** | 6 | engine max day is 12, not 10 |
| Goose / egg | 300 + coop | 50 | d4 | every day | 4 held | indefinite if fed |
| Cow / milk | 400 + pasture | 160 | d8 | every 2 days | 6 held | |
| Sheep / wool | 500 + pasture | 200 | d6 | every 3 days | 6 held | |
| Fertilizer | 100 buy | dynamic | — | 1 / animal / day, no stack | — | |

README said tomato “time to max yield = 11” and melon “= 10”. **Engine wins:** tomato `max_yield_day=8` with interval 1; melon `max_yield_day=12`.

### 2.5 Survival

- New plant: `consecutive_unwatered = 1`. Plant and skip water **the same day** → weed that night. No grace.
- New animal: `consecutive_unfed = 0`. Survives day 1 unfed.
- Two missed end-of-day refreshes: plant → weed, animal → gone forever.
- `WATER` / `FEED` / `CARE` once per day; extras no-op.
- `FERTILIZE` lasts `day .. day+2` inclusive. Bonus only if also watered that day.
- One-time watering bonus window: `age` in `[(max_yield_day+1)//2 , max_yield_day]`. Bonus +1, or +2 if fertilized. Applied **at WATER time** onto `yield_units`.
- `HARVEST` before `first_yield_day` is a no-op even if `yield_units > 0`.
- `PLANT` is all-or-nothing across units that turn: 1 seed + 2 `PLANT` = **zero** plants.
- `DIG` removes plant / weed / empty structure. Occupied coop/pasture cannot be dug.
- Weeds: 0.5% per empty unlocked tile at end of day.

### 2.6 CARE

- End of day, fed AND cared → `pending_care_bonus += 1`.
- On production day, if fed: bank added on top of base 1, then reset.
- If unfed on production day: base 1 still produced, bank **discarded**.

### 2.7 Market

Every product starts at **I0 = 10,000**. Price at I0 = base. Floor $1, rounded.

```
price = base + sign · (target · base / f(T)) · f(|inv − I0|)
sign = +1 if inv < I0 else −1
f ∈ {linear, sq, sqrt, log, log10, hinge}
hinge(u=x/T) = u + 8·max(0, u−1)²
```

| Good | P(I0−T) | P(I0) | P(I0+T) | P(I0+2T) |
|---|---|---|---|---|
| Wheat | 45 | 25 | 20 | 19 |
| Carrot | 70 | 35 | 10 | 1 |
| Tomato | 84 | 60 | 24 | 9 |
| Strawberry | 204 | 120 | 1 | 1 |
| Melon | 300 | 250 | 1 | 1 |
| Egg | 70 | 50 | 40 | 39 |
| Milk | 256 | 160 | 1 | 1 |
| Wool | 240 | 200 | 1 | 1 |
| Fertilizer | 140 | 100 | 60 | 20 |

- Only **WHEAT** and **FERTILIZER** can be bought back (`BUY_PRODUCT`).
- Fills are concurrent, **one unit at a time**, both players see the same pre-commit inventory.
- At the $1 floor, sold units are **not** added to inventory.
- Cap **10 orders / player / turn**. Extras dropped.
- Seed and animal supply is unlimited at **fixed** list prices.

### 2.8 Town

- Town center: 1 of every non-fertilizer product every 24 turns.
- New shop instance every 3 days, draw **with replacement**, cap 8. Names may repeat in `unlocked_shops`.
- Each instance consumes its basket every 4 turns. Single-product shops (Yarn, Pet Cafe) consume 2×.

| Shop | Basket |
|---|---|
| BAKERY | egg, wheat |
| PIZZA_SHOP | milk, tomato, wheat |
| BRUNCH_SPOT | egg, wheat, strawberry |
| YARN_STORE | wool ×2 |
| ICE_CREAM_SHOP | strawberry, milk, wheat |
| PET_CAFE | carrot ×2 |
| SMOOTHIE_SHOP | strawberry, milk |
| FARMERS_MARKET | wheat, carrot, tomato, strawberry |

### 2.9 Turn order

1. Validate  
2. Both players’ farmer/hand ops (simultaneous)  
3. Market queues  
4. Town drain  
5. Day refresh / reprice / banks / farm write  

Seeds bought this tick are **not** plantable this tick (market runs after field actions). Opening turn: `PASS` in the field + `BUY_SEED` is correct.

---

## 3. Agent I/O

```python
def agent(obs) -> {
  "farmer": [op, ...args],
  "hands":  [[op, ...args], ...],   # length MUST equal len(hands)
  "market": [[op, ...args], ...],   # ≤ 10
}
```

Farmer/hand ops: `NORTH SOUTH EAST WEST PASS` · `PICKUP item [n]` · `DROP` · `PLACE item [n]` · `PLANT crop` · `WATER` · `HARVEST` · `FERTILIZE` · `BUILD_COOP` · `BUILD_PASTURE` · `FEED` · `COLLECT_FERTILIZER` · `CARE` · `DIG`.

Market ops: `["BUY_SEED", crop, n]` · `["BUY_ANIMAL", animal, n]` · `["BUY_PRODUCT", item, n]` · `["SELL", item, n]` · `["HIRE"]` · `["BUY_LAND"]`.

Invalid = silent no-op.

**Public obs:** both farms’ tiles, money, unit positions, unlocked quads, `hires_today`, shared market inv+prices, unlocked shops.  
**Private:** your shed, seeds, carried bags. Opponent bags hidden.

`obs` may be a dict or a struct; `state.parse` handles both.

CLI: accept rules in the browser, then

```bash
kaggle competitions submit kaggriculture -f submission.tar.gz -m "v1"
kaggle competitions episodes <SUBMISSION_ID>
kaggle competitions replay <EPISODE_ID>
kaggle competitions leaderboard kaggriculture -s
```

Built-in local foes: `"pass"`, `"random"`, `"starter"`.

---

## 4. Architecture (locked)

One idea per file. Imports only flow **down**. `constants.py` imports nothing in the package. `agent.py` is the only conductor.

```
obs → main.py → agent.py
                 ├─ state.parse
                 ├─ planner.plan      → Jobs
                 ├─ assign.match      → unit→Job / MOVE
                 ├─ actions.emit_all  → farmer + hands
                 └─ market.build      → ≤10 orders
```

```
kaggriculture/
├── main.py
├── pack.sh
├── kagfarm/          # the only thing that ships
│   ├── agent.py
│   ├── config.py     # sweep knobs
│   ├── constants.py  # frozen engine
│   ├── state.py
│   ├── geometry.py
│   ├── biology.py
│   ├── economy.py
│   ├── planner.py
│   ├── assign.py
│   ├── market.py
│   └── actions.py
├── scripts/          eval, replay, sweep
├── tests/
└── artifacts/        gitignored
```

**Hard splits**

| File | Owns | Forbidden |
|---|---|---|
| `constants.py` | engine numbers | `should_*`, knobs |
| `config.py` | hire cap, tile budgets, flags | engine tables, policy `if day>` |
| `state.py` | parsing | strategy, BFS, prices |
| `geometry.py` | coords, BFS (locked walkable) | plants, money |
| `biology.py` | clocks | positions, bank, Jobs |
| `economy.py` | price, hire, land, safe_sell | units, jobs |
| `planner.py` | *what* work | *who*, market, NORTH |
| `assign.py` | *who* | new job kinds except MOVE |
| `market.py` | book | farmer ops, selling produce still on a tile |
| `actions.py` | Job → op (compiler) | “I’ll DIG instead” |
| `agent.py` | wiring + PASS shield | `if crop == "MELON"` |

Job urgency bands: **0 survive tonight → 1 yield today → 2 finish structure / dump bag → 3 expand to config caps → 4 DIG weeds**.

Market order priority implemented: **HIRE → BUY_LAND → BUY_SEED (cap>0 only) → BUY_PRODUCT wheat if livestock → SELL premium-first**. Two slots reserved for sells when the shed is non-empty.

No RL, no notebooks-as-agent, no engine clone. `learn/` may appear later as a sibling, not inside `kagfarm/`.

---

## 5. What shipped (v1 agent)

Path: `/home/workdir/artifacts/kaggriculture`  
Tarball: `submission.tar.gz` (`main.py` + `kagfarm/`, no `__pycache__`)  
Tests: **17 passed** (`pytest tests -q`)

### 5.1 Policy actually running

- Wheat cap 14 + carrot cap 6 + seed buffer 4.
- Hire target 6 every dawn (fib cost ~$20).
- First land unlock when bank ≥ 1600.
- Water anything thirsty; survival water is urgency 0.
- One-time harvest waits out the bonus window until `max_yield_day` or cap.
- Drop bag at shed, sell shed goods with `safe_sell_qty` so wheat stays above ~$8.
- Livestock and fertilizer **flags off**.
- On exception: `{farmer:["PASS"], hands:[["PASS"],...], market:[]}`.

Observed on fake obs:

| Situation | Action |
|---|---|
| Step 0 empty farm | field PASS; HIRE×6, BUY_LAND, BUY_SEED WHEAT 18, BUY_SEED CARROT 10 |
| Standing on unwatered wheat | WATER |
| Day 4, yield 4 on tile | HARVEST |

### 5.2 Current knobs (`kagfarm/config.py`)

```
HIRE_TARGET = 6
BANK_FLOOR = 40
UNLOCK_BANK = 1600
WHEAT_TILES = 14
CARROT_TILES = 6
TOMATO = STRAWBERRY = MELON = 0
GEESE = COWS = SHEEP = 0
ENABLE_LIVESTOCK = False
ENABLE_FERTILIZER = False
ENABLE_LAND_2 = True
PREMIUM_SELL_ORDER = MELON, MILK, WOOL, STRAWBERRY, EGG, TOMATO, CARROT, WHEAT, FERTILIZER
MAX_SELL_FRAC = 0.35
SEED_BUFFER = 4
WHEAT_RESERVE = 0
```

### 5.3 Known gaps (do these next, in order)

1. **Run a real 720-turn episode locally** vs `"starter"` and `"random"`. This sandbox never did.
2. Hands after hour 0: verify they actually fan out to water, not idle. Assign is greedy nearest; first dawn only the farmer exists (hires land after field ops).
3. `GOTO_SHED` competes with WATER. If bags stay in the field past midnight they dump automatically — but mid-day harvest needs a free unit to walk home or you stall sells until dawn.
4. `BUY_LAND` on turn 0 spends $1k before any crop is in the ground. Maybe gate land until day ≥ 2.
5. Tomato / melon / livestock not in the loop. Enable one crop at a time via config, then animals (wheat reserve must go up).
6. Opponent-aware selling (don’t dump melon into a book they are also dumping).
7. Do not add PyTorch until the heuristic plateaus on the live ladder.

---

## 6. Commands

```bash
cd /home/workdir/artifacts/kaggriculture   # or copy the folder to the Mac

# tests (no engine required)
PYTHONPATH=. python3 -m pytest tests -q

# real episode (needs pip install -U kaggle-environments)
PYTHONPATH=. python3 scripts/eval.py --foe starter --steps 720
PYTHONPATH=. python3 scripts/eval.py --foe random --episodes 3

# pack + submit
bash pack.sh
kaggle competitions submit kaggriculture -f submission.tar.gz -m "wheat-carrot v1"
```

`scripts/eval.py` already falls back to a fake-obs smoke if the env package is missing.

Sweep knobs without editing files in a loop: `scripts/sweep.py` patches `config` in memory and writes `artifacts/sweeps/results.csv`.

---

## 7. “Where does this line go?”

| Line | File |
|---|---|
| Melon `max_yield_day` | `constants.py` |
| “Hire 6” | `config.py` |
| `obs["private"]["shed"]` | `state.py` |
| BFS / cardinal step | `geometry.py` → `actions.py` |
| “Dies if ignored tonight” | `biology.py` |
| Hire Fibonacci cost | `economy.py` |
| `WATER` at `(2,3)` as work | `planner.py` |
| Hand 1 walks toward `(2,3)` | `assign.py` |
| `["SELL","MELON",3]` | `market.py` |
| `["WATER"]` | `actions.py` |
| `try/except → PASS` | `agent.py` |
| `env.run` | `scripts/eval.py` |

If a line does not fit one row, it is two ideas. Split it.

---

## 8. Official links

| Resource | URL |
|---|---|
| Competition | https://www.kaggle.com/competitions/kaggriculture |
| Engine README | https://github.com/Kaggle/kaggle-environments/blob/master/kaggle_environments/envs/kaggriculture/README.md |
| Agent guide | https://github.com/Kaggle/kaggle-environments/blob/master/kaggle_environments/envs/kaggriculture/AGENTS.md |
| Engine package | https://github.com/Kaggle/kaggle-environments |

Community (not official): episode crawls (Georgy Mamarin), engine reference CSVs (Dariush Afshar), replay corpora for imitation.

---

## 9. One-paragraph status

Kaggriculture is a 720-turn two-player farming sim on Kaggle with a $50k pool and a 23 Sep 2026 entry deadline. Winning an episode is terminal bank only. The game is a coupled labor / biology / logistics / market problem with a 1-second act timeout. We designed an 11-file heuristic package that respects those seams, implemented it, and verified the I/O contract with 17 tests. v1 plants wheat and carrots, hires six hands, buys the first quadrant, and sells the shed without crashing staple prices. Livestock, premium crops, and a live-ladder eval against `"starter"` are the next three moves — in that order, one config knob at a time.
