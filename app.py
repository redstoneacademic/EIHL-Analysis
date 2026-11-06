"""Run with: streamlit run app.py"""
from datetime import datetime
import json
import pandas as pd
import streamlit as st
import hockey

st.set_page_config(page_title="Commentary Desk", page_icon="🏒", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def seasons():
    return hockey.discover_seasons()


@st.cache_data(ttl=3600, show_spinner=False)
def stages(season):
    return hockey.discover_stages(season)


@st.cache_data(ttl=1800, show_spinner=False)
def data(season, stage):
    """Fetch season context; revision 3 invalidates pre-GSAA cached bundles."""
    return hockey.load_season(season, stage)


def fmt(value, digits=1, suffix=""):
    return "—" if pd.isna(value) else f"{value:,.{digits}f}{suffix}"


def show_table(frame, columns=None):
    if frame.empty:
        st.info("No matching published statistics.")
        return
    cols = [c for c in (columns or list(frame)) if c in frame]
    st.dataframe(frame[cols], hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%.2f")
                                for c in cols if pd.api.types.is_float_dtype(frame[c])})


def pin(text, key):
    if st.button("Pin to notes", key=key):
        if not any(n["text"] == text for n in notes):
            notes.append({"text": text, "used": False})
        st.toast("Pinned to Match notes")


def snapshot_bytes(bundle):
    payload = {k: v.to_json(orient="table", index=False) if isinstance(v, pd.DataFrame) else v
               for k, v in bundle.items()}
    return json.dumps({"format": "blaze-desk-1", "bundle": payload}, indent=2)


def restore_snapshot(raw):
    from io import StringIO
    payload = json.loads(raw)
    if payload.get("format") != "blaze-desk-1":
        raise ValueError("This is not a Blaze Desk snapshot.")
    result = payload["bundle"]
    for key in ("teams", "skaters", "goalies"):
        result[key] = pd.read_json(StringIO(result[key]), orient="table")
    if not {"Team", "GP", "GF", "GA"} <= set(result["teams"]):
        raise ValueError("Snapshot team columns are missing.")
    for key in ("season", "stage", "fetched_at", "sources", "errors"):
        if key not in result:
            raise ValueError(f"Snapshot is missing {key}.")
    result["goalies"] = hockey.add_gsaa(result["goalies"], complete=not result["errors"])
    return result


st.title("Commentary Desk")
with st.sidebar:
    st.header("Match setup")
    source_mode = st.radio("Data source", ["EIHL website", "Saved snapshot"])
    if source_mode == "Saved snapshot":
        upload = st.file_uploader("Open saved stats snapshot", type="json")
        if upload is None:
            st.info("Upload a snapshot exported from this app to use previously fetched statistics.")
            st.stop()
        try:
            bundle = restore_snapshot(upload.getvalue())
        except Exception as exc:
            st.error(f"Could not open snapshot: {exc}")
            st.stop()
        season_id, stage_id = bundle["season"], bundle["stage"]
        season_label = bundle.get("season_label", f"Season {season_id}")
        stage_label = bundle.get("stage_label", "Published default")
    else:
        if st.button("Reload season list"):
            seasons.clear()
            stages.clear()
        try:
            season_options = seasons()
        except Exception as exc:
            st.warning(f"Season discovery unavailable: {exc}")
            season_options = {}
        manual = st.checkbox("Enter competition IDs manually", value=not bool(season_options))
        if manual:
            st.caption("Copy id_season and id_stage from the EIHL stats page URL.")
            season_id = int(st.number_input("Season ID", min_value=1, value=57, step=1))
            stage_number = int(st.number_input("Stage ID (0 = website default)", min_value=0, value=1, step=1))
            stage_id = stage_number or None
            season_label, stage_label = f"Season {season_id}", f"Stage {stage_id or 'default'}"
        else:
            season_label = st.selectbox("Season / competition", list(season_options))
            season_id = season_options[season_label]
            try:
                stage_options = stages(season_id)
            except Exception as exc:
                st.error(f"Stage discovery failed: {exc}. Use manual IDs or a saved snapshot.")
                st.stop()
            stage_label = st.selectbox("Stage", list(stage_options)) if stage_options else "Published default"
            stage_id = stage_options.get(stage_label)
        if st.button("Refresh statistics", use_container_width=True):
            data.clear(season_id, stage_id)
        cache_key = f"last_good_{season_id}_{stage_id}"
        try:
            with st.spinner("Reading official EIHL statistics…"):
                bundle = data(season_id, stage_id)
            if bundle["errors"]:
                # Do not cache transient or partial failures for half an hour.
                data.clear(season_id, stage_id)
            else:
                st.session_state[cache_key] = bundle
        except Exception as exc:
            if cache_key not in st.session_state:
                st.error(f"Could not load this competition: {exc}")
                st.info("Try Refresh statistics, select another competition, or open a saved snapshot.")
                st.stop()
            bundle = st.session_state[cache_key]
            st.warning(f"Refresh failed. Showing this session's last successful fetch: {exc}")
        bundle = dict(bundle, season_label=season_label, stage_label=stage_label)

# Derived metrics must also work with cached bundles from earlier app versions.
# Recompute before both the cards and snapshot export, using the full population.
bundle = dict(bundle)
bundle["goalies"] = hockey.add_gsaa(bundle["goalies"], complete=not bundle["errors"])
teams, skaters, goalies = (bundle[k] for k in ("teams", "skaters", "goalies"))
team_names = teams.Team.tolist()
if not team_names:
    st.warning("No team totals have been published for this competition.")
    st.stop()
with st.sidebar:
    focus = st.selectbox("Your team", team_names, index=None, placeholder="Select your team")
    opponents = [t for t in team_names if t != focus]
    if not opponents:
        st.info("At least two teams are needed for a match comparison.")
        st.stop()
    opponent = st.selectbox("Opponent", opponents, index=None, placeholder="Select opponent", disabled=focus is None)
    match_label = st.text_input("Match label", value=datetime.now().strftime("%Y-%m-%d"), help="Use a date or fixture label to keep notes for different games separate.")
    st.divider()
    st.caption("Statistics are fetched on demand and cached for up to 30 minutes. This is season context, not a live game feed.")
    st.download_button("Save stats snapshot", snapshot_bytes(bundle), "blaze_stats_snapshot.json", "application/json")

if focus is None or opponent is None:
    st.info("Choose your team and opponent in the sidebar to open the commentary desk.")
    st.stop()

scope = f"notes:{season_id}:{stage_id}:{focus}:{opponent}:{match_label}"
notes = st.session_state.setdefault(scope, [])
st.subheader(f"{focus}  ·  {opponent}")
st.caption(f"{season_label} · {stage_label} · Fetched {bundle['fetched_at']}" + (" · SAVED SNAPSHOT" if source_mode == "Saved snapshot" else ""))
complete = not bundle["errors"] and not skaters.empty
if bundle["errors"]:
    st.warning("Some player data is missing. Player league ranks are disabled until every team loads.")
    with st.expander("Source problems"):
        for error in bundle["errors"]:
            st.write(error)

view = st.radio("Desk view", ["Tonight’s game", "Player lookup", "Situation lookup", "Match notes"], horizontal=True, label_visibility="collapsed")
selected_teams = [focus, opponent]

if view == "Tonight’s game":
    st.markdown("### At a glance")
    compare = teams.set_index("Team")
    stat_labels = [("GF/GP", "Goals for / game"), ("GA/GP", "Goals against / game"), ("PP%", "Power play %"), ("PK%", "Penalty kill %")]
    for col, (stat, label) in zip(st.columns(4), stat_labels):
        with col:
            if stat in compare:
                st.metric(label, f"{fmt(compare.loc[focus, stat])} / {fmt(compare.loc[opponent, stat])}")
    st.caption(f"Each pair shows {focus} / {opponent}.")
    rows = []
    for stat, label in stat_labels + [("SF Av.", "Shots for / game"), ("SA Av.", "Shots against / game")]:
        if stat in teams:
            row = {"Measure": label}
            for team in selected_teams:
                val = compare.loc[team, stat]
                row[team] = fmt(val)
                row[f"{team} rank"] = hockey.rank(teams, stat, val, ascending=stat in ("GA/GP", "SA Av."))
            rows.append(row)
    show_table(pd.DataFrame(rows))
    st.markdown("### Ready to say")
    for i, team in enumerate(selected_teams):
        for j, (stat, label) in enumerate(stat_labels):
            val = compare.loc[team, stat] if stat in compare else float("nan")
            if pd.notna(val):
                text = f"{team}: {fmt(val)} {label.lower()}, ranked {hockey.rank(teams, stat, val, ascending=stat == 'GA/GP')} in this competition."
                st.write(text)
                pin(text, f"point_{i}_{j}")
    st.markdown("### Scoring leaders in this matchup")
    if not skaters.empty:
        show_table(skaters[skaters.Team.isin(selected_teams)].sort_values("PTS", ascending=False).head(10),
                   ["Jersey", "Player", "Team", "GP", "G", "A", "PTS", "PTS/GP", "TOI/Game"])
    with st.expander("All teams · official totals"):
        show_table(teams)

elif view == "Player lookup":
    pool = st.selectbox("Search within", ["Tonight’s teams", "Whole competition"])
    position = st.radio("Player type", ["Skaters", "Goalies"], horizontal=True)
    frame = skaters if position == "Skaters" else goalies
    if frame.empty:
        st.info("No published player statistics were loaded.")
    else:
        frame = frame.copy()
        if pool == "Tonight’s teams":
            frame = frame[frame.Team.isin(selected_teams)]
        query = st.text_input("Name or shirt number", placeholder="Buzoverya or 77")
        if query:
            matches = frame.Player.astype(str).str.contains(query, case=False, regex=False)
            if "Jersey" in frame:
                matches |= frame.Jersey.astype(str).eq(query.strip().lstrip("#"))
            frame = frame[matches]
        if frame.empty:
            st.info("No players match that search.")
        else:
            indexes = frame.index.tolist()
            chosen = st.selectbox("Player", indexes, format_func=lambda i: f"#{frame.loc[i].get('Jersey', '—')} · {frame.loc[i, 'Player']} · {frame.loc[i, 'Team']}")
            row = frame.loc[chosen]
            st.markdown(f"### {row.Player} · {row.Team}")
            metrics = ["GP", "G", "A", "PTS", "S%", "FO%", "Team FO share %", "PTS/60", "G/60", "A/60"] if position == "Skaters" else ["GP", "W", "SV%", "GAA", "SO", "MIN", "GSAA", "GSAA/60"]
            for i in range(0, len(metrics), 4):
                for col, stat in zip(st.columns(4), metrics[i:i+4]):
                    value = row.get(stat, float("nan"))
                    display = f"{value:+.2f}" if stat in ("GSAA", "GSAA/60") and pd.notna(value) else fmt(value, 0 if stat in ("GP", "G", "A", "PTS", "W", "SO") else 2)
                    col.metric(stat, display)
            if position == "Goalies":
                st.caption("GSAA compares goals conceded with a competition-average goalie facing the same number of shots. Positive means goals saved above average; GSAA/60 adjusts for minutes played. The baseline uses all loaded goalies in the selected competition and stage, before any player filters. Unavailable if source coverage is incomplete.")
                if pd.isna(row.get("GSAA", float("nan"))):
                    st.warning("GSAA is unavailable because the competition-wide goalie totals are incomplete or invalid. Check Source problems above and try Refresh statistics.")
                elif pd.isna(row.get("GSAA/60", float("nan"))):
                    st.info("GSAA/60 is unavailable because this goalie's minutes are missing or zero.")
            show_table(pd.DataFrame([row]))
            stat = "PTS" if position == "Skaters" else "SV%"
            population = skaters if position == "Skaters" else goalies
            min_gp = st.number_input("Minimum GP for comparison rank", min_value=1, value=1, step=1)
            eligible = population[population.GP >= min_gp]
            if complete and row.GP >= min_gp and stat in eligible:
                text = f"{row.Player} ({row.Team}): {fmt(row.get(stat), 2)} {stat}; rank {hockey.rank(eligible, stat, row.get(stat))} among players with at least {min_gp} GP."
                st.write(text)
                pin(text, "pin_player")
            st.caption("Per-60 uses published TOI/game × GP, so it is approximate. Faceoff share is the player's share of recorded team faceoffs. Rate ranks depend on the GP filter; small samples need care.")

elif view == "Situation lookup":
    situation = st.radio("Situation", ["Power play / penalty kill", "Faceoff", "Goaltending", "Shooting"], horizontal=True)
    if situation == "Power play / penalty kill":
        show_table(teams[teams.Team.isin(selected_teams)], ["Team", "GP", "PP%", "PK%"])
        if not skaters.empty:
            show_table(skaters[skaters.Team.isin(selected_teams)].sort_values("PPG", ascending=False), ["Jersey", "Player", "Team", "GP", "PPG", "SHG", "PTS"])
    elif situation == "Goaltending":
        show_table(goalies[goalies.Team.isin(selected_teams)] if not goalies.empty else goalies, ["Jersey", "Player", "Team", "GP", "MIN", "SA", "GA", "SV%", "GAA", "SO"])
    elif not skaters.empty:
        frame = skaters[skaters.Team.isin(selected_teams)]
        if situation == "Faceoff" and "FO taken" in frame:
            minimum = st.number_input("Minimum faceoffs taken", min_value=0, value=10, step=5)
            show_table(frame[frame["FO taken"] >= minimum].sort_values("FO%", ascending=False), ["Jersey", "Player", "Team", "FO taken", "FOW", "FOL", "FO%", "Team FO share %"])
        elif situation == "Shooting" and "S%" in frame:
            minimum = st.number_input("Minimum shots on goal", min_value=0, value=10, step=5)
            show_table(frame[frame.SOG >= minimum].sort_values("S%", ascending=False), ["Jersey", "Player", "Team", "G", "SOG", "S%", "SOG/GP", "SOG/60"])
        else:
            st.info("This source does not publish the requested statistics.")
    st.caption("These are season totals for the selected competition and stage, not in-game or strength-specific splits.")

else:
    st.markdown("### Your running sheet")
    st.caption("Notes stay in this browser session. Export them before closing or reloading the app; import to resume later.")
    with st.form("new_note", clear_on_submit=True):
        note_text = st.text_area("Add a talking point")
        if st.form_submit_button("Add note") and note_text.strip():
            notes.append({"text": note_text.strip(), "used": False})
    for i, note in enumerate(notes):
        a, b = st.columns([9, 1])
        with a:
            note["used"] = st.checkbox("Used", value=note["used"], key=f"{scope}:{i}:used")
            st.text_area("Note", value=note["text"], key=f"{scope}:{i}:text", on_change=lambda idx=i: notes[idx].update(text=st.session_state[f"{scope}:{idx}:text"]))
        with b:
            if st.button("Delete", key=f"{scope}:{i}:delete"):
                notes.pop(i)
                # Clear indexed widget state so later rows cannot inherit deleted values.
                for key in list(st.session_state):
                    if key.startswith(scope + ":"):
                        del st.session_state[key]
                st.rerun()
    if not notes:
        st.info("Pin a statistic from Tonight’s game or Player lookup, or add your own note here.")
    exported = {"format": "blaze-notes-1", "match": match_label, "teams": selected_teams, "season": season_id, "stage": stage_id, "notes": notes}
    st.download_button("Export notes to resume later", json.dumps(exported, indent=2), "blaze_match_notes.json", "application/json")
    sheet = f"# {focus} vs {opponent}\n{season_label} · {stage_label} · {match_label}\n\n" + "\n\n".join(f"{'[USED]' if n['used'] else '[ ]'} {n['text']}" for n in notes)
    st.download_button("Download readable running sheet", sheet, "blaze_running_sheet.md", "text/markdown")
    imported = st.file_uploader("Import notes into this match", type="json", key="notes_upload")
    if imported and st.button("Merge imported notes"):
        try:
            payload = json.loads(imported.getvalue())
            if payload.get("format") != "blaze-notes-1" or not isinstance(payload.get("notes"), list):
                raise ValueError("Not a Blaze notes export.")
            additions = []
            for n in payload["notes"]:
                if not isinstance(n, dict) or not isinstance(n.get("text"), str) or not isinstance(n.get("used"), bool):
                    raise ValueError("Invalid note entry.")
                additions.append({"text": n["text"], "used": n["used"]})
            for n in additions:
                if n["text"] not in [existing["text"] for existing in notes]:
                    notes.append(n)
            st.rerun()
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f"Could not import notes: {exc}")

with st.expander("Sources and calculation notes"):
    st.write("Team GP, GF, GA, PP% and PK% come from the official team totals table. Player totals are not substituted for team totals. Player club spells remain separate. Goalies: SV% = (SA − GA) / SA × 100; GAA = GA / minutes × 60. Missing rates display as —. Ranks use unrounded values and competition ties.")
    st.write("Official goals are preserved, including EIHL shootout attribution. No inferred expected-goals or possession statistics are presented.")
    for url in bundle["sources"]:
        st.link_button("EIHL · " + url.split("eliteleague.co.uk/")[-1], url)
