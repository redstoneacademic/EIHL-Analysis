"""
EIHL Stats Hub — Broadcast Analytics Dashboard
Stuart Coles | Warwick University / EIHL Broadcast
Deployable via Streamlit Community Cloud
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ─────────────────────────────────────────────────────────
# PAGE CONFIG  (must be first Streamlit call)
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EIHL Stats Hub",
    page_icon="🏒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────
SEASONS = {
    "EIHL League 2024/25": 43,
    "Challenge Cup 2024/25": 44,
}

TEAMS = {
    "Belfast Giants":      4,
    "Cardiff Devils":      5,
    "Coventry Blaze":      6,
    "Dundee Stars":        7,
    "Fife Flyers":         8,
    "Glasgow Clan":        9,
    "Guildford Flames":   10,
    "Manchester Storm":   11,
    "Nottingham Panthers":12,
    "Sheffield Steelers": 13,
}

TEAM_COLOURS = {
    "Belfast Giants":       "#00843D",
    "Cardiff Devils":       "#CF0000",
    "Coventry Blaze":       "#FF6600",
    "Dundee Stars":         "#002D62",
    "Fife Flyers":          "#CC0000",
    "Glasgow Clan":         "#004B87",
    "Guildford Flames":     "#FF4500",
    "Manchester Storm":     "#006994",
    "Nottingham Panthers":  "#FFD700",
    "Sheffield Steelers":   "#C8A028",
}

BASE_PLAYER_URL = "https://www.eliteleague.co.uk/team/{team_id}-{slug}/player-stats?id_season={season}"
BASE_TEAM_URL   = "https://www.eliteleague.co.uk/team/{team_id}-{slug}/team-stats?id_season={season}"

# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────
def slugify(name: str) -> str:
    return name.lower().replace(" ", "-")


def toi_to_minutes(toi) -> float:
    if pd.isna(toi):
        return 0.0
    try:
        m, s = str(toi).split(":")
        return int(m) + int(s) / 60
    except Exception:
        return 0.0


def safe_div(num, den, scale=1, fill=0.0):
    """Vectorised safe division with optional scale."""
    return (num / den.replace(0, float("nan")) * scale).fillna(fill)


def name_col(df: pd.DataFrame) -> str:
    """Return the player-name column regardless of label used by site."""
    for c in ("Player", "Name", "PLAYER", "NAME"):
        if c in df.columns:
            return c
    return df.columns[0]


def metric_card(label: str, value: str, sub: str = "", colour: str = "#4a9eff") -> str:
    return f"""
    <div style="background:#1c2333;border-radius:10px;padding:14px 18px;
                border-left:4px solid {colour};margin-bottom:8px">
        <div style="color:#8b9ab5;font-size:11px;font-weight:700;
                    text-transform:uppercase;letter-spacing:.5px">{label}</div>
        <div style="color:#fff;font-size:26px;font-weight:700;line-height:1.2">{value}</div>
        <div style="color:#6c7a91;font-size:11px;margin-top:2px">{sub}</div>
    </div>"""


def talking_point(text: str) -> str:
    return (
        f'<div style="background:linear-gradient(135deg,#1a2744,#0f1a2e);'
        f'border:1px solid #2d4070;border-radius:8px;padding:12px 16px;'
        f'margin:5px 0;color:#c8d6f0;font-size:14px">📢 {text}</div>'
    )


def rank_label(rank: int, total: int) -> str:
    return f"#{rank} of {total}"


# ─────────────────────────────────────────────────────────
# SCRAPING  (cached 30 min)
# ─────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def scrape_season(season_id: int):
    skaters, goalies, team_pp = [], [], []

    for team, team_id in TEAMS.items():
        slug = slugify(team)

        # ── Player stats ──────────────────────────────────
        player_url = BASE_PLAYER_URL.format(
            team_id=team_id, slug=slug, season=season_id
        )
        try:
            tables = pd.read_html(player_url)
            for t in tables:
                t["Team"] = team
                if "FOW" in t.columns:
                    skaters.append(t)
                elif "SVS%" in t.columns:
                    goalies.append(t)
        except Exception:
            pass

        # ── Team stats ────────────────────────────────────
        team_url = BASE_TEAM_URL.format(
            team_id=team_id, slug=slug, season=season_id
        )
        try:
            for t in pd.read_html(team_url):
                if "Powerplays" in t.columns:
                    t["Team"] = team
                    team_pp.append(t)
        except Exception:
            pass

    if not skaters:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_sk = pd.concat(skaters, ignore_index=True)
    df_gl = pd.concat(goalies, ignore_index=True) if goalies else pd.DataFrame()
    df_pp = pd.concat(team_pp, ignore_index=True) if team_pp else pd.DataFrame()

    # ── Skater cleanup ────────────────────────────────────
    sk_num = ["G", "A", "PTS", "PIM", "PPG", "SHG", "SOG", "FOW", "FOL", "Gp"]
    for c in sk_num:
        if c in df_sk.columns:
            df_sk[c] = pd.to_numeric(df_sk[c], errors="coerce").fillna(0)

    if "TOI/Game" in df_sk.columns:
        df_sk["TOI_min"] = df_sk["TOI/Game"].apply(toi_to_minutes) * df_sk["Gp"]
    else:
        df_sk["TOI_min"] = 0.0

    # Per-60 rates
    for stat in ["G", "A", "PTS", "SOG"]:
        df_sk[f"{stat}/60"] = safe_div(df_sk[stat], df_sk["TOI_min"], scale=60).round(2)

    # Per-game rates
    for stat in ["G", "A", "PTS", "PIM", "SOG"]:
        df_sk[f"{stat}/GP"] = safe_div(df_sk[stat], df_sk["Gp"]).round(3)

    df_sk["S%"]       = safe_div(df_sk["G"], df_sk["SOG"], scale=100).round(2)
    df_sk["FO_Total"] = df_sk["FOW"] + df_sk["FOL"]
    df_sk["FO%"]      = safe_div(df_sk["FOW"], df_sk["FO_Total"], scale=100).round(2)

    # ── Goalie cleanup ────────────────────────────────────
    if not df_gl.empty:
        gl_num = ["Gp", "W", "L", "SO", "GA", "SA", "MIN", "GAA", "SVS%"]
        for c in gl_num:
            if c in df_gl.columns:
                df_gl[c] = pd.to_numeric(df_gl[c], errors="coerce").fillna(0)

        league_sa = df_gl["SA"].sum()
        league_ga = df_gl["GA"].sum()
        if league_sa > 0:
            lg_sv_rate        = (league_sa - league_ga) / league_sa
            df_gl["xGA"]      = (df_gl["SA"] * (1 - lg_sv_rate)).round(2)
            df_gl["GSAA"]     = (df_gl["xGA"] - df_gl["GA"]).round(2)
            df_gl["GSAA/60"]  = safe_div(df_gl["GSAA"], df_gl["MIN"] / 60).round(3)

    return df_sk, df_gl, df_pp


@st.cache_data(ttl=600, show_spinner=False)
def scrape_game(game_id: str) -> dict:
    out = {}
    for suffix, key in [("/stats", "player"), ("/team-stats", "team")]:
        url = f"https://www.eliteleague.co.uk/game/{game_id}{suffix}"
        try:
            out[key] = pd.read_html(url)
        except Exception as e:
            out[key] = []
            out[f"{key}_error"] = str(e)
    return out


# ─────────────────────────────────────────────────────────
# TEAM SUMMARY BUILDER
# ─────────────────────────────────────────────────────────
def build_team_summary(df_sk: pd.DataFrame, df_gl: pd.DataFrame, df_pp: pd.DataFrame):
    if df_sk.empty:
        return pd.DataFrame()

    extra_aggs = {}
    if "SHG" in df_sk.columns:
        extra_aggs["SHG"] = ("SHG", "sum")
    if "PPG" in df_sk.columns:
        extra_aggs["PPG_sum"] = ("PPG", "sum")

    sk = df_sk.groupby("Team").agg(
        GP    = ("Gp",  "max"),
        Goals = ("G",   "sum"),
        Shots = ("SOG", "sum"),
        PIM   = ("PIM", "sum"),
        FOW   = ("FOW", "sum"),
        FOL   = ("FOL", "sum"),
        **extra_aggs
    ).reset_index()

    sk["GF/GP"]    = safe_div(sk["Goals"], sk["GP"]).round(2)
    sk["Team S%"]  = safe_div(sk["Goals"], sk["Shots"], scale=100).round(2)
    sk["Team FO%"] = safe_div(sk["FOW"], sk["FOW"] + sk["FOL"], scale=100).round(2)
    sk["SF/GP"]    = safe_div(sk["Shots"], sk["GP"]).round(1)
    sk["PIM/GP"]   = safe_div(sk["PIM"], sk["GP"]).round(2)

    if not df_gl.empty:
        g  = df_gl.copy()
        g["wGAA"] = g["GAA"]  * g["Gp"]
        g["wSV%"] = g["SVS%"] * g["Gp"]
        gl = g.groupby("Team").agg(
            GP_G   = ("Gp",   "sum"),
            wGAA   = ("wGAA", "sum"),
            wSV    = ("wSV%", "sum"),
            Total_GA = ("GA", "sum"),
            Total_SA = ("SA", "sum"),
        ).reset_index()
        gl["GA/GP"]   = safe_div(gl["Total_GA"], gl["GP_G"]).round(2)
        gl["SA/GP"]   = safe_div(gl["Total_SA"], gl["GP_G"]).round(1)
        gl["Avg GAA"] = safe_div(gl["wGAA"],    gl["GP_G"]).round(2)
        gl["Avg SV%"] = safe_div(gl["wSV"],     gl["GP_G"]).round(2)
        team = sk.merge(gl[["Team", "GA/GP", "SA/GP", "Avg GAA", "Avg SV%"]], on="Team", how="left")
        team["PDO"] = (team["Team S%"] + team["Avg SV%"]).round(2)
    else:
        team = sk.copy()

    # PP stats from team pages
    if not df_pp.empty and "Powerplays" in df_pp.columns:
        pp_goals_col = next((c for c in df_pp.columns if "Goals" in str(c) and c != "Goals"), None)
        agg = {"PP_att": ("Powerplays", "sum")}
        if pp_goals_col:
            agg["PP_goals"] = (pp_goals_col, "sum")
        pp = df_pp.groupby("Team").agg(**agg).reset_index()
        if "PP_goals" in pp.columns:
            pp["PP%"] = safe_div(pp["PP_goals"], pp["PP_att"], scale=100).round(2)
        team = team.merge(pp.drop(columns=["PP_att"], errors="ignore"), on="Team", how="left")

    return team


# ─────────────────────────────────────────────────────────
# GLOBAL STYLES
# ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color:#0e1117; }
    .section-hdr {
        color:#4a9eff; font-size:17px; font-weight:700;
        margin:18px 0 10px; border-bottom:2px solid #1c3060; padding-bottom:5px;
    }
    div[data-testid="stDataFrame"] { border-radius:8px; overflow:hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────
st.markdown("# 🏒 EIHL Stats Hub")
st.markdown("*Broadcast-ready analytics · Live data from eliteleague.co.uk*")
st.divider()

# ─────────────────────────────────────────────────────────
# CONTROLS
# ─────────────────────────────────────────────────────────
col_season, col_mingp, col_refresh = st.columns([3, 3, 2])

with col_season:
    season_label = st.selectbox("Season / Competition", list(SEASONS.keys()))
    season_id = SEASONS[season_label]

with col_mingp:
    # Determine sensible max after load (default before load)
    min_gp = st.slider("Min games played (leaderboards)", 1, 54, 10)

with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ─────────────────────────────────────────────────────────
# DATA LOAD
# ─────────────────────────────────────────────────────────
with st.spinner("Fetching live data from eliteleague.co.uk …"):
    df_sk, df_gl, df_pp = scrape_season(season_id)
    team_summary = build_team_summary(df_sk, df_gl, df_pp)

if df_sk.empty:
    st.error("⚠️ Could not load season data. The EIHL website may be temporarily unavailable. Try refreshing.")
    st.stop()

nc = name_col(df_sk)           # actual column name for player name
sk_q = df_sk[df_sk["Gp"] >= min_gp].copy()   # GP-filtered skaters
gl_q = df_gl[df_gl["Gp"] >= max(1, min_gp // 4)].copy() if not df_gl.empty else pd.DataFrame()
n_teams = len(team_summary)

# ─────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Team Overview",
    "⛸️ Skaters",
    "🥅 Goalies",
    "🎙️ Talking Points",
    "🔎 Player Search",
    "🎮 Game Lookup",
])

# ══════════════════════════════════════════════════════════
# TAB 1 — TEAM OVERVIEW
# ══════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-hdr">League Snapshot</div>', unsafe_allow_html=True)

    if not team_summary.empty:
        # ── Headline metric cards ─────────────────────────
        def best_card(df, col, label, fmt="{}", asc=False):
            if col not in df.columns:
                return ""
            row = df.loc[df[col].idxmin() if asc else df[col].idxmax()]
            c = TEAM_COLOURS.get(row["Team"], "#4a9eff")
            v = fmt.format(row[col]) if "{}" in fmt else fmt(row[col])
            return metric_card(label, v, row["Team"], c)

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.markdown(best_card(team_summary, "GF/GP",    "Best Offence (GF/GP)", "{:.2f}"),           unsafe_allow_html=True)
        with c2: st.markdown(best_card(team_summary, "GA/GP",    "Best Defence (GA/GP)", "{:.2f}", asc=True), unsafe_allow_html=True)
        with c3: st.markdown(best_card(team_summary, "Avg SV%",  "Best SV%",             "{:.2f}%"),          unsafe_allow_html=True)
        with c4: st.markdown(best_card(team_summary, "PDO",      "PDO Leader",           "{:.2f}"),           unsafe_allow_html=True)
        with c5: st.markdown(best_card(team_summary, "Team FO%", "FO% Leader",           "{:.1f}%"),          unsafe_allow_html=True)

        st.markdown("---")

        # ── Full table ────────────────────────────────────
        display_cols = [c for c in [
            "Team","GP","GF/GP","GA/GP","SF/GP","SA/GP",
            "Team S%","Avg SV%","Avg GAA","PDO","Team FO%","PP%","PIM/GP"
        ] if c in team_summary.columns]

        sort_col = "PDO" if "PDO" in team_summary.columns else "GF/GP"

        st.dataframe(
            team_summary[display_cols].sort_values(sort_col, ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Team S%":   st.column_config.NumberColumn("S%",    format="%.2f %%"),
                "Avg SV%":   st.column_config.NumberColumn("SV%",   format="%.2f %%"),
                "Team FO%":  st.column_config.NumberColumn("FO%",   format="%.1f %%"),
                "PP%":       st.column_config.NumberColumn("PP%",   format="%.1f %%"),
                "PDO":       st.column_config.NumberColumn("PDO",   help="S% + SV%. ≈100 is average."),
                "Avg GAA":   st.column_config.NumberColumn("Avg GAA", format="%.2f"),
                "GF/GP":     st.column_config.NumberColumn("GF/GP", format="%.2f"),
                "GA/GP":     st.column_config.NumberColumn("GA/GP", format="%.2f"),
            }
        )

        # ── Shots chart ───────────────────────────────────
        if "SF/GP" in team_summary.columns and "SA/GP" in team_summary.columns:
            st.markdown('<div class="section-hdr">Shots For / Against Per Game</div>', unsafe_allow_html=True)
            srt = team_summary.sort_values("SF/GP")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=srt["Team"], x=srt["SF/GP"],
                name="Shots For/GP", orientation="h",
                marker_color=[TEAM_COLOURS.get(t,"#4a9eff") for t in srt["Team"]],
            ))
            fig.add_trace(go.Bar(
                y=srt["Team"], x=-srt["SA/GP"],
                name="Shots Against/GP", orientation="h",
                marker_color="rgba(255,80,80,0.55)",
            ))
            fig.update_layout(
                barmode="relative", height=380,
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font_color="white",
                xaxis=dict(title="← Shots Against  |  Shots For →", showgrid=False, zeroline=True, zerolinecolor="#555"),
                yaxis=dict(showgrid=False),
                legend=dict(orientation="h", y=1.05),
                margin=dict(l=10, r=10, t=30, b=30),
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── PDO scatter ───────────────────────────────────
        if "PDO" in team_summary.columns and "GF/GP" in team_summary.columns:
            st.markdown('<div class="section-hdr">PDO vs Goals For Per Game</div>', unsafe_allow_html=True)
            fig2 = px.scatter(
                team_summary, x="PDO", y="GF/GP",
                color="Team", color_discrete_map=TEAM_COLOURS,
                size="GP", text="Team",
                template="plotly_dark",
                hover_data=["Team S%","Avg SV%"],
            )
            fig2.update_traces(textposition="top center", textfont_size=10)
            fig2.add_vline(x=team_summary["PDO"].mean(), line_dash="dash", line_color="grey", opacity=0.5)
            fig2.update_layout(
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                height=400, showlegend=False,
                margin=dict(l=10, r=10, t=20, b=30),
            )
            st.plotly_chart(fig2, use_container_width=True)


# ══════════════════════════════════════════════════════════
# TAB 2 — SKATERS
# ══════════════════════════════════════════════════════════
with tab2:
    sub1, sub2, sub3 = st.tabs(["🏆 Points Leaders", "📈 Rate Stats", "🤼 Specialists"])

    # ── Points Leaders ────────────────────────────────────
    with sub1:
        st.markdown('<div class="section-hdr">Points Leaders</div>', unsafe_allow_html=True)

        top5 = sk_q.nlargest(5, "PTS")
        cols5 = st.columns(5)
        for i, (_, row) in enumerate(top5.iterrows()):
            with cols5[i]:
                c = TEAM_COLOURS.get(row["Team"], "#4a9eff")
                st.markdown(metric_card(
                    f"#{i+1} Points",
                    str(int(row["PTS"])),
                    f"{row.get(nc,'N/A')} · {row['Team'][:3].upper()}",
                    c,
                ), unsafe_allow_html=True)

        pts_cols = [c for c in [nc,"Team","Pos","Gp","G","A","PTS","PTS/GP","G/GP","PPG","SOG","S%","PIM"] if c in sk_q.columns]
        st.dataframe(
            sk_q[pts_cols].sort_values("PTS", ascending=False).head(100),
            use_container_width=True, hide_index=True,
            column_config={
                "S%":     st.column_config.NumberColumn("S%",     format="%.1f %%"),
                "PTS/GP": st.column_config.NumberColumn("Pts/GP", format="%.2f"),
                "G/GP":   st.column_config.NumberColumn("G/GP",   format="%.2f"),
            }
        )

    # ── Rate Stats ────────────────────────────────────────
    with sub2:
        st.markdown('<div class="section-hdr">Per-60-Minute Production</div>', unsafe_allow_html=True)
        st.caption("Normalises for ice time — identifies most dangerous players per minute.")

        rate_cols = [c for c in [nc,"Team","Pos","Gp","TOI/Game","G","A","PTS","G/60","A/60","PTS/60","SOG/60","S%"] if c in sk_q.columns]
        sort_r = "PTS/60" if "PTS/60" in sk_q.columns else "PTS"
        st.dataframe(
            sk_q[rate_cols].sort_values(sort_r, ascending=False).head(100),
            use_container_width=True, hide_index=True,
            column_config={
                "PTS/60": st.column_config.NumberColumn("Pts/60", format="%.2f"),
                "G/60":   st.column_config.NumberColumn("G/60",   format="%.2f"),
                "A/60":   st.column_config.NumberColumn("A/60",   format="%.2f"),
                "S%":     st.column_config.NumberColumn("S%",     format="%.1f %%"),
            }
        )

        # Scatter: PTS/60 vs TOI
        if "PTS/60" in sk_q.columns and "TOI/Game" in sk_q.columns:
            st.markdown('<div class="section-hdr">Production vs Ice Time</div>', unsafe_allow_html=True)
            sk_scatter = sk_q[sk_q["TOI_min"] > 20].copy()
            sk_scatter["TOI_avg"] = sk_scatter["TOI/Game"].apply(toi_to_minutes)
            fig3 = px.scatter(
                sk_scatter, x="TOI_avg", y="PTS/60",
                color="Team", color_discrete_map=TEAM_COLOURS,
                hover_name=nc, hover_data=["Gp","PTS"],
                template="plotly_dark",
                labels={"TOI_avg": "Avg TOI (min/game)", "PTS/60": "Points per 60 min"},
            )
            fig3.update_layout(
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                height=420, margin=dict(l=10, r=10, t=20, b=30),
            )
            st.plotly_chart(fig3, use_container_width=True)

    # ── Specialists ───────────────────────────────────────
    with sub3:
        c_fo, c_pim = st.columns(2)

        with c_fo:
            st.markdown('<div class="section-hdr">Faceoff Specialists</div>', unsafe_allow_html=True)
            fo_min = st.number_input("Min faceoffs taken", value=50, min_value=1, key="fo_min")
            fo_df = sk_q[sk_q["FO_Total"] >= fo_min] if "FO_Total" in sk_q.columns else sk_q
            fo_cols = [c for c in [nc,"Team","Pos","Gp","FOW","FOL","FO_Total","FO%"] if c in fo_df.columns]
            st.dataframe(
                fo_df[fo_cols].sort_values("FO%", ascending=False).head(30),
                use_container_width=True, hide_index=True,
                column_config={
                    "FO%":      st.column_config.NumberColumn("FO%",    format="%.1f %%"),
                    "FO_Total": st.column_config.NumberColumn("FO Taken"),
                }
            )

        with c_pim:
            st.markdown('<div class="section-hdr">Penalty Leaders</div>', unsafe_allow_html=True)
            pim_cols = [c for c in [nc,"Team","Pos","Gp","PIM","PIM/GP"] if c in sk_q.columns]
            st.dataframe(
                sk_q[pim_cols].sort_values("PIM", ascending=False).head(30),
                use_container_width=True, hide_index=True,
                column_config={
                    "PIM/GP": st.column_config.NumberColumn("PIM/GP", format="%.2f"),
                }
            )


# ══════════════════════════════════════════════════════════
# TAB 3 — GOALIES
# ══════════════════════════════════════════════════════════
with tab3:
    if gl_q.empty:
        st.warning("No goalie data available for this competition.")
    else:
        gnc = name_col(df_gl)
        st.markdown('<div class="section-hdr">Goaltending Leaderboard</div>', unsafe_allow_html=True)

        # Headline cards
        def gl_card(df, col, label, fmt, asc=False):
            if col not in df.columns: return ""
            row = df.loc[df[col].idxmin() if asc else df[col].idxmax()]
            c = TEAM_COLOURS.get(row["Team"], "#4a9eff")
            return metric_card(label, fmt.format(row[col]), f"{row.get(gnc,'N/A')} · {row['Team'][:3].upper()}", c)

        g1,g2,g3,g4 = st.columns(4)
        with g1: st.markdown(gl_card(gl_q, "SVS%",     "Best SV%",  "{:.2f}%"),         unsafe_allow_html=True)
        with g2: st.markdown(gl_card(gl_q, "GAA",      "Best GAA",  "{:.2f}", asc=True), unsafe_allow_html=True)
        with g3: st.markdown(gl_card(gl_q, "GSAA",     "Best GSAA", "+{:.2f}"),          unsafe_allow_html=True)
        with g4: st.markdown(gl_card(gl_q, "SO",       "Shutouts",  "{:.0f}"),           unsafe_allow_html=True)

        # Full table
        gl_cols = [c for c in [gnc,"Team","Gp","W","L","SO","MIN","GAA","SVS%","SA","GA","xGA","GSAA","GSAA/60"] if c in gl_q.columns]
        sort_gl = "GSAA" if "GSAA" in gl_q.columns else "SVS%"
        st.dataframe(
            gl_q[gl_cols].sort_values(sort_gl, ascending=False),
            use_container_width=True, hide_index=True,
            column_config={
                "SVS%":    st.column_config.NumberColumn("SV%",     format="%.2f %%"),
                "GAA":     st.column_config.NumberColumn("GAA",     format="%.2f"),
                "GSAA":    st.column_config.NumberColumn("GSAA",    format="%.2f", help="Goals Saved Above Average vs league-average goalie"),
                "GSAA/60": st.column_config.NumberColumn("GSAA/60", format="%.3f"),
                "xGA":     st.column_config.NumberColumn("xGA",     format="%.2f", help="Expected goals against at league-average SV%"),
            }
        )

        # Scatter: SVS% vs GSAA
        if "GSAA" in gl_q.columns and "SVS%" in gl_q.columns:
            st.markdown('<div class="section-hdr">SV% vs GSAA (bubble = games played)</div>', unsafe_allow_html=True)
            fig4 = px.scatter(
                gl_q, x="SVS%", y="GSAA",
                color="Team", color_discrete_map=TEAM_COLOURS,
                size="Gp", hover_name=gnc if gnc in gl_q.columns else None,
                template="plotly_dark",
                labels={"SVS%": "Save Percentage", "GSAA": "Goals Saved Above Average"},
            )
            fig4.add_hline(y=0, line_dash="dash", line_color="#555")
            fig4.update_layout(
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                height=420, margin=dict(l=10, r=10, t=20, b=30),
            )
            st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════════
# TAB 4 — TALKING POINTS
# ══════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-hdr">Auto-Generated Broadcast Talking Points</div>', unsafe_allow_html=True)
    st.caption(f"Pulled from live data · {season_label} · Min {min_gp} GP applied")

    pts_list = []

    def safe_max(df, col):
        if col not in df.columns or df.empty: return None
        return df.loc[df[col].idxmax()]

    def safe_min(df, col):
        if col not in df.columns or df.empty: return None
        return df.loc[df[col].idxmin()]

    # ── Scoring ───────────────────────────────────────────
    if not sk_q.empty:
        r = safe_max(sk_q, "PTS")
        if r is not None:
            rank = int((sk_q["PTS"] > r["PTS"]).sum()) + 1
            pts_list.append(
                f"<b>{r.get(nc,'N/A')}</b> ({r['Team']}) leads {season_label} scoring with "
                f"<b>{int(r['PTS'])} points</b> ({int(r['G'])}G+{int(r['A'])}A) in {int(r['Gp'])} games "
                f"— {r.get('PTS/GP',0):.2f} per game."
            )

        g = safe_max(sk_q, "G")
        if g is not None and g.get(nc) != r.get(nc):
            pts_list.append(
                f"Top goal scorer: <b>{g.get(nc,'N/A')}</b> ({g['Team']}) with "
                f"<b>{int(g['G'])} goals</b> on a {g['S%']:.1f}% shooting rate."
            )

        if "PTS/60" in sk_q.columns:
            r60 = safe_max(sk_q, "PTS/60")
            if r60 is not None:
                pts_list.append(
                    f"Per-60-minute: <b>{r60.get(nc,'N/A')}</b> ({r60['Team']}) generates "
                    f"<b>{r60['PTS/60']:.2f} points per 60</b> of ice time — highest rate in the league."
                )

        if "FO%" in sk_q.columns:
            fo_df = sk_q[sk_q.get("FO_Total", sk_q["FOW"] + sk_q["FOL"]) >= 50] if "FO_Total" in sk_q.columns else sk_q[(sk_q["FOW"]+sk_q["FOL"]) >= 50]
            fo_best = safe_max(fo_df, "FO%")
            if fo_best is not None:
                pts_list.append(
                    f"Faceoff king: <b>{fo_best.get(nc,'N/A')}</b> ({fo_best['Team']}) wins "
                    f"<b>{fo_best['FO%']:.1f}%</b> of draws ({int(fo_best['FOW'])}W / {int(fo_best['FOL'])}L)."
                )

        pim_r = safe_max(sk_q, "PIM")
        if pim_r is not None:
            pts_list.append(
                f"<b>{pim_r.get(nc,'N/A')}</b> ({pim_r['Team']}) is the league's most penalised player "
                f"with <b>{int(pim_r['PIM'])} PIM</b> — {pim_r.get('PIM/GP',0):.2f} per game."
            )

        sh_r = safe_max(sk_q, "S%")
        if sh_r is not None and sh_r.get("SOG",0) >= 20:
            pts_list.append(
                f"Shooting efficiency: <b>{sh_r.get(nc,'N/A')}</b> ({sh_r['Team']}) converts at "
                f"<b>{sh_r['S%']:.1f}%</b> — the best rate among skaters with ≥20 shots."
            )

    # ── Goalies ───────────────────────────────────────────
    if not gl_q.empty:
        gnc2 = name_col(gl_q)
        sv = safe_max(gl_q, "SVS%")
        if sv is not None:
            pts_list.append(
                f"Between the pipes, <b>{sv.get(gnc2,'N/A')}</b> ({sv['Team']}) posts a "
                f"<b>{sv['SVS%']:.2f}% SV%</b> — best among qualified goalies."
            )
        if "GSAA" in gl_q.columns:
            gsaa = safe_max(gl_q, "GSAA")
            if gsaa is not None:
                pts_list.append(
                    f"<b>{gsaa.get(gnc2,'N/A')}</b> ({gsaa['Team']}) leads in GSAA with "
                    f"<b>+{gsaa['GSAA']:.2f}</b> — saving roughly {abs(gsaa['GSAA']):.0f} more goals than "
                    f"a league-average goalie would have behind the same shot volume."
                )

    # ── Teams ─────────────────────────────────────────────
    if not team_summary.empty:
        if "PDO" in team_summary.columns:
            pdo_hi = team_summary.loc[team_summary["PDO"].idxmax()]
            pdo_lo = team_summary.loc[team_summary["PDO"].idxmin()]
            lg_pdo = team_summary["PDO"].mean()
            pts_list.append(
                f"PDO (S% + SV%): <b>{pdo_hi['Team']}</b> leads at <b>{pdo_hi['PDO']:.2f}</b> "
                f"vs league average {lg_pdo:.2f} — statistically among the luckiest teams. "
                f"<b>{pdo_lo['Team']}</b> sits lowest at {pdo_lo['PDO']:.2f}, suggesting positive regression could be due."
            )

        if "Team FO%" in team_summary.columns:
            fo_t = team_summary.loc[team_summary["Team FO%"].idxmax()]
            pts_list.append(
                f"Team faceoffs: <b>{fo_t['Team']}</b> win <b>{fo_t['Team FO%']:.1f}%</b> of draws — "
                f"more puck possession starts than any other team in the league."
            )

        if "SF/GP" in team_summary.columns and "SA/GP" in team_summary.columns:
            sf_best = team_summary.loc[team_summary["SF/GP"].idxmax()]
            pts_list.append(
                f"Shot volume leader: <b>{sf_best['Team']}</b> average "
                f"<b>{sf_best['SF/GP']:.1f} shots per game</b> — the most attack-minded team in the league."
            )

    for pt in pts_list:
        st.markdown(talking_point(pt), unsafe_allow_html=True)

    # ── Team deep-dive ────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-hdr">Team Deep-Dive</div>', unsafe_allow_html=True)
    sel_team = st.selectbox("Select team", list(TEAMS.keys()), key="team_dd")

    t_sk  = sk_q[sk_q["Team"] == sel_team] if not sk_q.empty else pd.DataFrame()
    t_gl  = gl_q[gl_q["Team"] == sel_team] if not gl_q.empty else pd.DataFrame()
    t_sum = team_summary[team_summary["Team"] == sel_team] if not team_summary.empty else pd.DataFrame()
    t_col = TEAM_COLOURS.get(sel_team, "#4a9eff")

    team_pts = []

    if not t_sk.empty:
        ldr = t_sk.loc[t_sk["PTS"].idxmax()]
        team_pts.append(
            f"<b>{ldr.get(nc,'N/A')}</b> leads {sel_team} with "
            f"<b>{int(ldr['PTS'])} points</b> ({int(ldr['G'])}G+{int(ldr['A'])}A) "
            f"in {int(ldr['Gp'])} games."
        )
        if not t_sum.empty:
            row = t_sum.iloc[0]
            if "GF/GP" in row:
                lg_avg = team_summary["GF/GP"].mean()
                team_pts.append(
                    f"{sel_team} score <b>{row['GF/GP']:.2f} goals/game</b> — "
                    f"{'above' if row['GF/GP'] >= lg_avg else 'below'} the league average of {lg_avg:.2f}."
                )
            if "Team S%" in row:
                lg_avg = team_summary["Team S%"].mean()
                team_pts.append(
                    f"Team shooting: <b>{row['Team S%']:.2f}%</b> "
                    f"vs league avg {lg_avg:.2f}%."
                )
            if "PDO" in row:
                lg_avg = team_summary["PDO"].mean()
                team_pts.append(
                    f"PDO: <b>{row['PDO']:.2f}</b> vs league avg {lg_avg:.2f} — "
                    f"{'over-performing' if row['PDO'] > lg_avg else 'under-performing'} the mean."
                )
            if "Team FO%" in row:
                lg_avg = team_summary["Team FO%"].mean()
                team_pts.append(
                    f"Faceoff win rate: <b>{row['Team FO%']:.1f}%</b> "
                    f"vs league avg {lg_avg:.1f}%."
                )

    if not t_gl.empty:
        gnc2 = name_col(t_gl)
        gl_row = t_gl.loc[t_gl["SVS%"].idxmax()]
        team_pts.append(
            f"Starter <b>{gl_row.get(gnc2,'N/A')}</b> posts a "
            f"<b>{gl_row['SVS%']:.2f}% SV%</b> with GAA of {gl_row['GAA']:.2f}."
            + (f" GSAA: +{gl_row['GSAA']:.2f}." if "GSAA" in gl_row and gl_row["GSAA"] > 0 else "")
        )

    for pt in team_pts:
        st.markdown(talking_point(pt), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# TAB 5 — PLAYER SEARCH & COMPARE
# ══════════════════════════════════════════════════════════
with tab5:
    # ── Search ────────────────────────────────────────────
    st.markdown('<div class="section-hdr">Player Search</div>', unsafe_allow_html=True)
    query = st.text_input("Search by name", placeholder="e.g. Mitchell Balmas")

    if query:
        sk_matches = df_sk[df_sk[nc].str.contains(query, case=False, na=False)] if nc in df_sk.columns else pd.DataFrame()

        if sk_matches.empty and not df_gl.empty:
            gnc2 = name_col(df_gl)
            gl_match = df_gl[df_gl[gnc2].str.contains(query, case=False, na=False)]
        else:
            gl_match = pd.DataFrame()

        if sk_matches.empty and gl_match.empty:
            st.info("No players found.")
        else:
            for _, row in sk_matches.iterrows():
                c = TEAM_COLOURS.get(row["Team"], "#4a9eff")
                st.markdown(f"### {row.get(nc,'N/A')} — {row['Team']}")
                s1,s2,s3,s4,s5,s6,s7 = st.columns(7)
                with s1: st.markdown(metric_card("GP",     str(int(row["Gp"])),       "", c), unsafe_allow_html=True)
                with s2: st.markdown(metric_card("Goals",  str(int(row["G"])),         f"S%: {row['S%']:.1f}%", c), unsafe_allow_html=True)
                with s3: st.markdown(metric_card("Assists",str(int(row["A"])),         "", c), unsafe_allow_html=True)
                with s4: st.markdown(metric_card("Points", str(int(row["PTS"])),       f"{row.get('PTS/GP',0):.2f}/GP", c), unsafe_allow_html=True)
                with s5:
                    if "PTS/60" in row: st.markdown(metric_card("Pts/60", f"{row['PTS/60']:.2f}", "", c), unsafe_allow_html=True)
                with s6:
                    if row.get("FO_Total", 0) > 0: st.markdown(metric_card("FO%", f"{row['FO%']:.1f}%", f"{int(row.get('FOW',0))}W/{int(row.get('FOL',0))}L", c), unsafe_allow_html=True)
                with s7:
                    st.markdown(metric_card("PIM", str(int(row["PIM"])), f"{row.get('PIM/GP',0):.2f}/GP", c), unsafe_allow_html=True)
                st.divider()

            for _, row in gl_match.iterrows():
                gnc2 = name_col(gl_match)
                c = TEAM_COLOURS.get(row["Team"], "#4a9eff")
                st.markdown(f"### 🥅 {row.get(gnc2,'N/A')} — {row['Team']}")
                g1,g2,g3,g4,g5 = st.columns(5)
                with g1: st.markdown(metric_card("GP",  str(int(row["Gp"])),          "", c), unsafe_allow_html=True)
                with g2: st.markdown(metric_card("SV%", f"{row['SVS%']:.2f}%",         "", c), unsafe_allow_html=True)
                with g3: st.markdown(metric_card("GAA", f"{row['GAA']:.2f}",           "", c), unsafe_allow_html=True)
                with g4:
                    if "GSAA" in row: st.markdown(metric_card("GSAA", f"{row['GSAA']:+.2f}", "", c), unsafe_allow_html=True)
                with g5:
                    if "SO" in row: st.markdown(metric_card("SO", str(int(row["SO"])), "", c), unsafe_allow_html=True)
                st.divider()

    # ── Compare ───────────────────────────────────────────
    st.markdown('<div class="section-hdr">Compare Two Players</div>', unsafe_allow_html=True)
    all_names = sorted(df_sk[nc].dropna().unique().tolist()) if nc in df_sk.columns else []
    cc1, cc2 = st.columns(2)
    with cc1: p1 = st.selectbox("Player 1", [""] + all_names, key="cmp1")
    with cc2: p2 = st.selectbox("Player 2", [""] + all_names, key="cmp2")

    if p1 and p2 and p1 != p2:
        r1 = df_sk[df_sk[nc] == p1].iloc[0]
        r2 = df_sk[df_sk[nc] == p2].iloc[0]
        compare_stats = [s for s in ["Gp","G","A","PTS","PTS/GP","G/60","PTS/60","SOG","S%","FO%","PPG","PIM/GP"] if s in df_sk.columns]

        col_p1, col_mid, col_p2 = st.columns([5, 2, 5])
        c1 = TEAM_COLOURS.get(r1["Team"], "#4a9eff")
        c2 = TEAM_COLOURS.get(r2["Team"], "#ff6b6b")

        with col_p1:
            st.markdown(f"**{p1}** — {r1['Team']}")
            for stat in compare_stats:
                v = r1.get(stat, 0)
                v_str = f"{v:.2f}" if isinstance(v, float) else str(int(v)) if not pd.isna(v) else "—"
                st.markdown(metric_card(stat, v_str, "", c1), unsafe_allow_html=True)

        with col_mid:
            st.markdown("<br>", unsafe_allow_html=True)
            for stat in compare_stats:
                v1 = r1.get(stat, 0) or 0
                v2 = r2.get(stat, 0) or 0
                asc = stat in ("PIM/GP",)
                if v1 > v2:
                    arrow = "◀" if not asc else "▶"
                elif v2 > v1:
                    arrow = "▶" if not asc else "◀"
                else:
                    arrow = "—"
                st.markdown(f"<div style='text-align:center;color:#8b9ab5;padding:14px 0;font-size:18px'>{arrow}</div>", unsafe_allow_html=True)

        with col_p2:
            st.markdown(f"**{p2}** — {r2['Team']}")
            for stat in compare_stats:
                v = r2.get(stat, 0)
                v_str = f"{v:.2f}" if isinstance(v, float) else str(int(v)) if not pd.isna(v) else "—"
                st.markdown(metric_card(stat, v_str, "", c2), unsafe_allow_html=True)

        # Radar
        radar_stats = [s for s in ["PTS/GP","G/60","A/60","S%","FO%","SOG/60"] if s in df_sk.columns]
        if len(radar_stats) >= 3:
            st.markdown('<div class="section-hdr">Radar Comparison</div>', unsafe_allow_html=True)
            def normalise(df, stats):
                out = {}
                for s in stats:
                    col_max = df[s].max()
                    out[s] = (r1.get(s,0) / col_max * 100 if col_max else 0,
                               r2.get(s,0) / col_max * 100 if col_max else 0)
                return out
            norms = normalise(df_sk, radar_stats)
            cats = radar_stats + [radar_stats[0]]
            vals1 = [norms[s][0] for s in radar_stats] + [norms[radar_stats[0]][0]]
            vals2 = [norms[s][1] for s in radar_stats] + [norms[radar_stats[0]][1]]
            fig5 = go.Figure()
            fig5.add_trace(go.Scatterpolar(r=vals1, theta=cats, fill="toself", name=p1, line_color=c1))
            fig5.add_trace(go.Scatterpolar(r=vals2, theta=cats, fill="toself", name=p2, line_color=c2, opacity=0.7))
            fig5.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0,100])),
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font_color="white", height=450,
                margin=dict(l=30, r=30, t=30, b=30),
            )
            st.plotly_chart(fig5, use_container_width=True)


# ══════════════════════════════════════════════════════════
# TAB 6 — GAME LOOKUP
# ══════════════════════════════════════════════════════════
with tab6:
    st.markdown('<div class="section-hdr">Single-Game Stats Lookup</div>', unsafe_allow_html=True)
    st.caption(
        "Enter the game ID from the EIHL website URL.  \n"
        "Example: for `eliteleague.co.uk/game/5044-she-man` enter **5044-she-man**"
    )

    game_id = st.text_input("Game ID", placeholder="5044-she-man")

    if game_id:
        with st.spinner(f"Loading game {game_id} …"):
            gdata = scrape_game(game_id.strip())

        st.markdown(f"🔗 [Open on EIHL website](https://www.eliteleague.co.uk/game/{game_id})")

        if gdata.get("player"):
            st.markdown('<div class="section-hdr">Player Stats</div>', unsafe_allow_html=True)
            for i, t in enumerate(gdata["player"]):
                with st.expander(f"Table {i+1}", expanded=(i < 2)):
                    st.dataframe(t, use_container_width=True, hide_index=True)
        else:
            st.warning(f"Could not load player stats. {gdata.get('player_error','')}")

        if gdata.get("team"):
            st.markdown('<div class="section-hdr">Team Stats</div>', unsafe_allow_html=True)
            for t in gdata["team"]:
                st.dataframe(t, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Data: eliteleague.co.uk · Cached 30 min · "
    f"Loaded {datetime.utcnow().strftime('%H:%M UTC, %d %b %Y')}  |  "
    f"EIHL Stats Hub · Stuart Coles"
)
