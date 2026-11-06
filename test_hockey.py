"""Synthetic fixtures exercise source changes and commentary-critical calculations."""
import math
from pathlib import Path
import pandas as pd
import pytest
import hockey


def test_season_ids_are_parsed_from_urls():
    html = '<select name="id_season"><option value="/stats?id_season=58">Cup 2026/27</option></select>'
    assert hockey.options(html, "id_season") == {"Cup 2026/27": 58}
    assert hockey.options(html, "id_stage") == {}


def test_rates_and_faceoff_workload():
    frame = pd.DataFrame({"Player name": ["A", "B"], "Team": ["X", "X"], "Gp": [2, 2], "G": [2, 0], "PTS": [4, 0], "SOG": [10, 0], "FOW": [6, 0], "FOL": [4, 0], "TOI/Game": ["20:00", "00:00"]})
    out = hockey.clean_players(frame)
    assert out.loc[0, "PTS/60"] == 6
    assert out.loc[0, "FO%"] == 60
    assert out.loc[0, "Team FO share %"] == 100
    assert math.isnan(out.loc[1, "S%"])
    assert math.isnan(out.loc[1, "PTS/60"])


def test_goalie_time_and_percentages():
    frame = pd.DataFrame({"Player name": ["G"], "Team": ["X"], "Gp": [2], "MIN": ["120:30"], "SA": [50], "GA": [5]})
    out = hockey.clean_players(frame, goalie=True)
    assert out.loc[0, "SV%"] == 90
    assert out.loc[0, "GAA"] == pytest.approx(5 * 60 / 120.5)


def test_ties_and_unavailable():
    frame = pd.DataFrame({"PTS": [10, 10, 5]})
    assert hockey.rank(frame, "PTS", 10) == "1 of 3"
    assert hockey.rank(frame, "PTS", 5) == "3 of 3"
    assert hockey.rank(frame, "PTS", float("nan")) == "—"


def source_fixture(url):
    season = 58 if "58" in url else 57
    if "/stats/teams" in url:
        table = pd.DataFrame({"Team": ["1 Coventry Blaze", "2 Cardiff Devils"], "GP": [4, 4], "GF": [12, 10], "GA": [8, 12], "PP%": [20, 25], "PK%": [85, 80]})
        return table.to_html(index=False) + '<a href="/team/6-coventry-blaze">Coventry Blaze</a><a href="/team/5-cardiff-devils">Cardiff Devils</a>'
    selects = f'<select name="id_season"><option value="?id_season=57">League 2026/27</option><option value="?id_season=58">Cup 2026/27</option></select><select name="id_stage"><option value="?id_season={season}&id_stage=1">Regular Season</option></select>'
    table = pd.DataFrame({"Player name": ["Test Skater"], "Jersey": [77], "Gp": [4], "G": [2], "A": [3], "PTS": [5], "PPG": [1], "SHG": [0], "SOG": [10], "FOW": [6], "FOL": [4], "TOI/Game": ["20:00"]})
    gl = pd.DataFrame({"Player name": ["Test Goalie"], "Gp": [4], "SA": [100], "GA": [8], "GAA": [2], "SVS%": [92], "MIN": [240], "W": [3], "SO": [1]})
    return selects + table.to_html(index=False) + gl.to_html(index=False)


def test_competition_query_and_official_team_totals(monkeypatch):
    urls = []
    def fetch(url):
        urls.append(url)
        return source_fixture(url)
    monkeypatch.setattr(hockey, "fetch_html", fetch)
    bundle = hockey.load_season(58, 1)
    assert all("id_season=58&id_stage=1" in url for url in urls)
    assert bundle["teams"].iloc[0]["GF/GP"] == 3
    assert not bundle["errors"]


def test_partial_fetch_reports_team(monkeypatch):
    def fetch(url):
        if "/5-cardiff" in url:
            raise ValueError("Source down")
        return source_fixture(url)
    monkeypatch.setattr(hockey, "fetch_html", fetch)
    bundle = hockey.load_season(57, 1)
    assert len(bundle["teams"]) == 2
    assert len(bundle["skaters"]) == 1
    assert "Cardiff Devils" in bundle["errors"][0]


def test_app_views_season_switch_and_notes(monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(hockey, "fetch_html", source_fixture)
    st.cache_data.clear()
    app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run(timeout=30)
    assert not app.exception
    app.selectbox[0].select("Cup 2026/27").run()
    assert not app.exception
    assert any("Cup 2026/27" in c.value for c in app.caption)
    next(b for b in app.button if b.label == "Pin to notes").click().run()
    desk = next(r for r in app.radio if r.label == "Desk view")
    desk.set_value("Match notes").run()
    assert not app.exception
    assert any("Coventry Blaze" in a.value for a in app.text_area)
    next(c for c in app.checkbox if c.label == "Used").check().run()
    assert not app.exception
    next(r for r in app.radio if r.label == "Desk view").set_value("Player lookup").run()
    assert not app.exception
    next(t for t in app.text_input if t.label == "Name or shirt number").set_value("77").run()
    assert not app.exception
    next(r for r in app.radio if r.label == "Player type").set_value("Goalies").run()
    assert not app.exception
    next(r for r in app.radio if r.label == "Desk view").set_value("Situation lookup").run()
    assert not app.exception
    for view in ["Faceoff", "Goaltending", "Shooting"]:
        next(r for r in app.radio if r.label == "Situation").set_value(view).run()
        assert not app.exception
