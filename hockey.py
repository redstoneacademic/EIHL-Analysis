"""EIHL source discovery and calculations. No Streamlit dependency."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import StringIO
import re
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.eliteleague.co.uk"
SEED = BASE + "/team/6-coventry-blaze/player-stats"


def fetch_html(url):
    response = requests.get(url, timeout=(8, 25), headers={"User-Agent": "BlazeCommentaryDesk/2.0"})
    response.raise_for_status()
    return response.text


def options(html, field):
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for option in soup.select(f'select[name="{field}"] option'):
        value = parse_qs(urlparse(option.get("value", "")).query).get(field)
        if value and value[0].isdigit():
            result[option.get_text(" ", strip=True)] = int(value[0])
    return result


def discover_seasons():
    result = options(fetch_html(SEED), "id_season")
    if not result:
        raise ValueError("The EIHL season dropdown could not be read.")
    return result


def discover_stages(season):
    # No invented playoff stage: use the options published for this competition.
    return options(fetch_html(f"{SEED}?id_season={int(season)}"), "id_stage")


def tables(html):
    try:
        result = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        return []
    for table in result:
        table.columns = [str(c[-1] if isinstance(c, tuple) else c).strip() for c in table.columns]
    return result


def number(series):
    return pd.to_numeric(series.astype(str).str.replace(r"[\s%,]", "", regex=True), errors="coerce")


def divide(numerator, denominator, scale=1):
    # Unknown/zero denominator stays unavailable, never a fabricated zero rate.
    return numerator.div(denominator.where(denominator > 0)).mul(scale)


def minutes(value):
    if pd.isna(value):
        return float("nan")
    try:
        parts = str(value).split(":")
        if len(parts) == 2 and 0 <= float(parts[1]) < 60:
            return float(parts[0]) + float(parts[1]) / 60
        if len(parts) == 1:
            return float(value)
    except (ValueError, TypeError):
        pass
    return float("nan")


def clean_players(frame, goalie=False):
    frame = frame.rename(columns={"Player name": "Player", "Name": "Player", "Gp": "GP"}).copy()
    if "Player" not in frame:
        raise ValueError("Player name column is missing.")
    frame = frame[frame.Player.notna() & ~frame.Player.astype(str).str.match(r"(?i)^(total|team total)s?$")].copy()
    numeric = ["GP", "G", "A", "PTS", "PIM", "PPG", "SHG", "SOG", "FOW", "FOL", "BS", "W", "L", "SO", "SA", "GA", "GAA", "SVS%"]
    for col in numeric:
        if col in frame:
            frame[col] = number(frame[col])
    if "Jersey" in frame:
        frame["Jersey"] = frame.Jersey.map(lambda x: str(int(x)) if pd.notna(x) and str(x).replace(".0", "").isdigit() else str(x))
    if goalie:
        if "MIN" in frame:
            frame["MIN"] = frame.MIN.map(minutes)
        if {"SA", "GA"} <= set(frame):
            frame["SV%"] = divide(frame.SA - frame.GA, frame.SA, 100)
        if {"GA", "MIN"} <= set(frame):
            frame["GAA"] = divide(frame.GA, frame.MIN, 60)
        return frame
    if {"G", "SOG"} <= set(frame):
        frame["S%"] = divide(frame.G, frame.SOG, 100)
    if {"FOW", "FOL"} <= set(frame):
        frame["FO taken"] = frame.FOW + frame.FOL
        frame["FO%"] = divide(frame.FOW, frame["FO taken"], 100)
        team_total = frame.groupby("Team")["FO taken"].transform("sum")
        frame["Team FO share %"] = divide(frame["FO taken"], team_total, 100)
    if {"TOI/Game", "GP"} <= set(frame):
        frame["TOI minutes"] = frame["TOI/Game"].map(minutes) * frame.GP
        for stat in ("G", "A", "PTS", "SOG"):
            if stat in frame:
                frame[f"{stat}/60"] = divide(frame[stat], frame["TOI minutes"], 60)
    for stat in ("PTS", "G", "SOG"):
        if stat in frame and "GP" in frame:
            frame[f"{stat}/GP"] = divide(frame[stat], frame.GP)
    return frame


def parse_teams(html):
    frame = next((t.copy() for t in tables(html) if {"Team", "GP", "GF", "GA"} <= set(t)), None)
    if frame is None:
        raise ValueError("Official team totals table is missing.")
    frame["Team"] = frame.Team.astype(str).str.replace(r"^\d+\s+", "", regex=True).str.strip()
    for col in frame.columns.difference(["Team"]):
        frame[col] = number(frame[col])
    frame["GF/GP"] = divide(frame.GF, frame.GP)
    frame["GA/GP"] = divide(frame.GA, frame.GP)
    links = {}
    for a in BeautifulSoup(html, "html.parser").select('a[href*="/team/"]'):
        path = urlparse(a["href"]).path
        match = re.match(r"/team/(\d+-[^/]+)", path)
        if match:
            slug = match[1]
            for team in frame.Team:
                if slug.split("-", 1)[1] == team.lower().replace(" ", "-"):
                    links[team] = BASE + "/team/" + slug
    if not links:
        raise ValueError("No team links were found in the official table page.")
    return frame, links


def load_season(season, stage=None):
    query = f"?id_season={int(season)}" + (f"&id_stage={int(stage)}" if stage is not None else "")
    team_url = BASE + "/stats/teams" + query
    teams, links = parse_teams(fetch_html(team_url))
    errors, sources = [], [team_url]

    def load_team(item):
        team, root = item
        url = root + "/player-stats" + query
        try:
            found = tables(fetch_html(url))
            sk = next((t.copy() for t in found if {"PTS", "SOG"} <= set(t)), pd.DataFrame())
            gl = next((t.copy() for t in found if {"SA", "GA", "GAA"} <= set(t)), pd.DataFrame())
            if sk.empty:
                raise ValueError("No skater table was published or recognised.")
            sk["Team"] = team
            if not gl.empty:
                gl["Team"] = team
            return sk, gl, url, None
        except Exception as exc:
            return pd.DataFrame(), pd.DataFrame(), url, f"{team}: {exc}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(load_team, links.items()))
    skaters, goalies = [], []
    for sk, gl, url, error in rows:
        sources.append(url)
        if error:
            errors.append(error)
        if not sk.empty:
            skaters.append(sk)
        if not gl.empty:
            goalies.append(gl)
    for team in set(teams.Team) - set(links):
        errors.append(f"{team}: player page link not found.")
    sk = clean_players(pd.concat(skaters, ignore_index=True)) if skaters else pd.DataFrame()
    gl = clean_players(pd.concat(goalies, ignore_index=True), goalie=True) if goalies else pd.DataFrame()
    return {"teams": teams, "skaters": sk, "goalies": gl, "errors": errors, "sources": sources,
            "season": int(season), "stage": stage,
            "fetched_at": datetime.now(timezone.utc).isoformat()}


def rank(frame, stat, value, ascending=False):
    if stat not in frame or pd.isna(value):
        return "—"
    values = frame[stat].dropna()
    better = (values < value).sum() if ascending else (values > value).sum()
    return f"{int(better) + 1} of {len(values)}"
