# Blaze Commentary Desk

A replacement Python/Streamlit app for Stuart Coles's EIHL commentary workflow.

## Update your existing Streamlit app

1. Unzip this package on your computer.
2. Add `app.py`, `hockey.py`, `requirements.txt` and the `.streamlit` folder to the root of the GitHub repository used by your existing Streamlit app. Keep the two Python files together. Commit the changes.
3. In Streamlit Community Cloud, use `app.py` as the main file. If the existing main file has another name, you can instead copy the contents of this package's `app.py` into that file, leaving `hockey.py` next to it.
4. Use Python 3.11 or 3.12. Reboot the app after updating dependencies or configuration. If you previously chose a personal theme in the Streamlit settings menu, switch back to the app's theme.
5. Check that the season list contains the current competition, select your opponent and try player lookup. The sidebar includes Refresh statistics and Reload season list.

This package has not been committed to your repository or deployed to blazewebcast.streamlit.app. It does not require Sites or another hosting service.

## At the rink

- **Tonight's game:** selected team versus opponent, official team totals and competition ranks, pinnable talking points and matchup scoring leaders.
- **Player lookup:** name or shirt-number search, selected matchup or whole competition, skaters or goalies, approximate per-60 production and share of recorded team faceoffs.
- **Situation lookup:** PP/PK, faceoffs, goalies and shooting; faceoff/shot minimums help avoid small-sample comparisons.
- **Match notes:** add, edit, pin, mark used and delete talking points. Export JSON to resume later, or download a readable Markdown running sheet.

Notes are session-local, not a permanent database. Export before closing/reloading. Scope is selected competition, stage, teams and match label; set a fixture date/label to keep games separate. Import merges notes into the currently selected match and preserves used flags.

Before travelling, save a stats snapshot using the sidebar. Later choose Saved snapshot and upload that JSON to bypass EIHL requests. The app itself must still be accessible on Streamlit: this is not an offline-installable application. A downloaded running sheet can be read without the app. Snapshot timestamps and competition labels remain visible. Treat snapshots as historical data until refreshed.

## Data and season behaviour

Reads season and stage dropdowns from the official EIHL site, then the official competition team totals and each listed team's player tables. Team URLs are discovered rather than limited to a fixed roster of ten clubs. A manual season/stage ID override is available if dropdown discovery fails. A zero manual stage means the site's default; the app does not invent playoff stages.

Source verification on 6 November 2026 found current competition IDs 57 (2026/27 league) and 58 (2026/27 Challenge Cup); 2025/26 league is 43 and its Cup is 44. These numbers are not used as a hard-coded season menu. Default manual fallback is 57/1.

Successful statistics are cached for up to 30 minutes; season/stage menus for one hour. Refresh clears the selected statistics cache. Transient partial player loads are reported and not kept in the cache. If a refresh fails completely, the app can show a complete successful fetch retained in the current session for that same season/stage, with a warning and its original timestamp. Otherwise it stops with an explanation. It never silently switches competition or substitutes synthetic data.

## Statistical corrections

- Pass separate integer season/stage arguments. The uploaded original passed a tuple as `id_season`.
- Official team GP/GF/GA and published PP/PK rates replace player-derived estimates. Maximum skater appearances is not a reliable team GP count.
- Goalie save percentage uses total saves divided by shots faced. GAA uses actual minutes, including `MM:SS` where published. No averaging of goalie percentages by appearances.
- Missing/zero denominators remain unavailable rather than becoming zero-percent performance.
- Skater per-60 = total statistic / (published TOI/game × GP) × 60. These are approximate due to source rounding and are not even-strength splits.
- Faceoff workload = player FOW + FOL divided by the sum for that player's team in this competition/stage. This describes recorded faceoffs, not time on ice or situational usage.
- Tied values share competition rank (1, 1, 3). Rates are ranked before display rounding. Player ranks include a GP threshold; there is no automatic goalie-minute qualification. Use the threshold and situation-specific sample filters deliberately.
- Player club spells remain separate; official shootout goal attribution is retained. No inferred xG, possession or conventional five-on-five PDO is presented.
- Incomplete team player scraping disables player league ranks. All source URLs and errors are visible.

The uploaded original used several incorrect team colour assignments and mixed hard-coded dark HTML with Streamlit's configurable widget theme. This replacement uses native Streamlit controls and one consistent navy/sky-blue project theme; it does not assign unverified team colours.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

For verification:

```bash
python -m pip install pytest
python -m pytest -q
```

Tests cover URL discovery, season/stage query propagation, official team totals, missing rates, faceoff workload, goalie rates, ties, partial failures and Streamlit interaction through all four views, including competition switching and notes.

## Limitations and next steps

The app offers season context while commentating. It does not ingest the game in progress, calculate recent-form streaks or know the next fixture automatically. Opponent and match label are selected manually. Persistent cross-device notes would require storage beyond Streamlit session state. Source layout changes, missing historic stats and differences in server access can still affect scraping; diagnostics and snapshots make those failures visible.

References: https://www.eliteleague.co.uk/stats/teams ; https://www.eliteleague.co.uk/team/6-coventry-blaze/player-stats ; https://docs.streamlit.io/develop/api-reference/configuration/config.toml ; https://docs.streamlit.io/deploy/streamlit-community-cloud
