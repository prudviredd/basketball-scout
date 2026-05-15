from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from functools import lru_cache
from difflib import SequenceMatcher
import os
import re
import requests
from datetime import datetime, date

load_dotenv()

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("BALLDONTLIE_API_KEY", "").strip()
BASE_URL = "https://api.balldontlie.io"

STAT_ALIASES = {
    "three pointers": "fg3m", "3 pointers": "fg3m", "3-pointers": "fg3m", "three-pointers": "fg3m",
    "threes": "fg3m", "3pm": "fg3m",
    "field goals": "fgm", "field goal": "fgm", "fgm": "fgm",
    "field goal attempts": "fga", "fga": "fga",
    "free throws": "ftm", "ftm": "ftm",
    "points": "pts", "point": "pts", "pts": "pts", "scored": "pts", "score": "pts",
    "rebounds": "reb", "rebound": "reb", "boards": "reb",
    "assists": "ast", "assist": "ast",
    "steals": "stl", "steal": "stl",
    "blocks": "blk", "block": "blk",
    "turnovers": "turnover", "turnover": "turnover",
    "minutes": "min",
    "plus minus": "plus_minus", "+/-": "plus_minus", "plus/minus": "plus_minus",
}

CORE_STATS = ["pts", "fg3m", "fgm", "fga", "reb", "ast", "stl", "blk", "turnover", "plus_minus"]

DISPLAY_NAMES = {
    "pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM",
    "stl": "STL", "blk": "BLK", "turnover": "TO", "min": "MIN",
    "fgm": "FGM", "fga": "FGA", "ftm": "FTM", "fta": "FTA",
    "plus_minus": "+/-",
}

NAME_FIXES = {
    "kate cunningham": "cade cunningham",
    "cad cunningham": "cade cunningham",
    "cad": "cade cunningham",
    "cade": "cade cunningham",
    "cunningham": "cade cunningham",
    "luca doncic": "luka doncic",
    "luka": "luka doncic",
    "joker": "nikola jokic",
    "jokic": "nikola jokic",
    "steph curry": "stephen curry",
    "steph": "stephen curry",
    "lebron": "lebron james",
    "aja wilson": "a'ja wilson",
    "aja": "a'ja wilson",
}

def league_path(league):
    return "/v1" if league == "nba" else f"/{league}/v1"

def headers():
    return {"Authorization": API_KEY} if API_KEY else {}

def season_to_year(season_value):
    season_value = str(season_value or "2024").strip()
    return int(season_value.split("-")[0]) if "-" in season_value else int(season_value)

def normalize_player_name(name):
    cleaned = " ".join((name or "").lower().replace("’", "'").split()).strip()
    return NAME_FIXES.get(cleaned, cleaned)

def parse_query(q):
    ql = (q or "").lower().strip()
    league = "wnba" if "wnba" in ql else "nba"

    last_n = 5
    m = re.search(r"last\s+(\d+)", ql)
    if m:
        last_n = max(1, min(int(m.group(1)), 25))
    elif "last four" in ql:
        last_n = 4
    elif "last five" in ql:
        last_n = 5
    elif "last ten" in ql:
        last_n = 10

    requested = []
    for phrase, stat in sorted(STAT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if phrase in ql and stat not in requested:
            requested.append(stat)

    stats = CORE_STATS.copy() if not requested or "last" in ql else requested

    remove_words = [
        "nba","wnba","show","me","how","many","much","did","had","have","in","the","last",
        "games","game","made","player","stat","stats","points","point","pts","scored","score",
        "rebounds","rebound","boards","assists","assist","threes","three pointers","3 pointers",
        "3-pointers","three-pointers","3pm","steals","steal","blocks","block","turnovers","turnover",
        "minutes","field goals","field goal","field goal attempts","free throws","plus minus",
        "plus/minus","+/-","fgm","fga","ftm"
    ]
    name_guess = re.sub(r"\b\d+\b", " ", ql)
    for word in sorted(remove_words, key=len, reverse=True):
        name_guess = name_guess.replace(word, " ")
    name_guess = " ".join(name_guess.split()).strip() or q.strip()
    name_guess = normalize_player_name(name_guess)

    return {"league": league, "last_n": last_n, "stats": stats, "player": name_guess}

def bdl_get(path, params=None):
    if not API_KEY:
        raise RuntimeError("BALLDONTLIE_API_KEY is missing. Add it to .env and restart.")
    response = requests.get(f"{BASE_URL}{path}", headers=headers(), params=params or {}, timeout=30)

    if response.status_code == 401:
        raise RuntimeError("API key rejected. Re-copy the key from BALLDONTLIE, update .env, and restart.")
    if response.status_code == 403:
        raise RuntimeError("This endpoint may require an upgraded plan for this sport/data.")
    if response.status_code == 429:
        raise RuntimeError("Rate limit hit. Wait 60 seconds and retry.")
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:300]
        raise RuntimeError(f"BALLDONTLIE HTTP {response.status_code}: {detail}")
    return response.json()

def full_name(player):
    return f"{player.get('first_name','')} {player.get('last_name','')}".strip() or player.get("full_name") or "Unknown"

def team_name(team):
    return team.get("full_name") or team.get("name") or team.get("abbreviation") or ""

def team_abbr(team):
    return team.get("abbreviation") or team.get("name") or ""

@lru_cache(maxsize=1024)
def search_player_cached(league, player_name):
    path = f"{league_path(league)}/players"
    player_name = normalize_player_name(player_name)
    data = bdl_get(path, {"search": player_name, "per_page": 25})
    players = data.get("data", [])
    if not players and player_name.split():
        data = bdl_get(path, {"search": player_name.split()[-1], "per_page": 25})
        players = data.get("data", [])
    return players

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def rank_players(players, query):
    q = normalize_player_name(query)
    ranked = []
    for p in players:
        name = full_name(p)
        score = max(similarity(q, name), 0.92 if q in name.lower() else 0)
        team = p.get("team") or {}
        ranked.append({
            "id": p.get("id"),
            "name": name,
            "position": p.get("position"),
            "team": team_name(team),
            "team_abbr": team_abbr(team),
            "score": round(score, 3),
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

def best_match(players, query):
    ranked = rank_players(players, query)
    if not ranked:
        return None
    best_id = ranked[0]["id"]
    for p in players:
        if p.get("id") == best_id:
            return p
    return players[0]

def game_date_value(row):
    raw = (row.get("game") or {}).get("date") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return datetime.min

def fetch_stats(league, player_id, season_year):
    path = f"{league_path(league)}/stats"
    return bdl_get(path, {
        "player_ids[]": player_id,
        "seasons[]": season_year,
        "per_page": 100
    }).get("data", [])

def get_stat(row, stat):
    if stat == "plus_minus":
        return row.get("plus_minus", row.get("plusMinus", row.get("plusminus", row.get("pm", ""))))
    return row.get(stat)

def numeric_value(row, stat):
    v = get_stat(row, stat)
    try:
        if stat == "min" and isinstance(v, str) and ":" in v:
            m, s = v.split(":")
            return float(m) + float(s) / 60
        if v in ("", None):
            return 0
        return float(v)
    except Exception:
        return 0

def summarize(rows, requested_stats, last_n):
    rows = sorted(rows, key=game_date_value, reverse=True)
    rows = [r for r in rows if r.get("game")]
    selected = rows[:last_n]

    totals, averages, highs = {}, {}, {}
    for stat in requested_stats:
        vals = [numeric_value(r, stat) for r in selected]
        totals[stat] = round(sum(vals), 2)
        averages[stat] = round(sum(vals) / len(vals), 2) if vals else 0
        highs[stat] = round(max(vals), 2) if vals else 0

    games = []
    for row in selected:
        game = row.get("game") or {}
        team = row.get("team") or {}
        games.append({
            "date": (game.get("date") or "")[:10],
            "status": game.get("status") or "",
            "team": team_abbr(team),
            "min": row.get("min"),
            "pts": row.get("pts"),
            "reb": row.get("reb"),
            "ast": row.get("ast"),
            "fg3m": row.get("fg3m"),
            "stl": row.get("stl"),
            "blk": row.get("blk"),
            "turnover": row.get("turnover"),
            "fgm": row.get("fgm"),
            "fga": row.get("fga"),
            "ftm": row.get("ftm"),
            "fta": row.get("fta"),
            "plus_minus": get_stat(row, "plus_minus"),
        })
    return games, totals, averages, highs

def quick_links(player_name, league):
    from urllib.parse import quote_plus
    q = quote_plus(player_name)
    return [
        {"label": "Google News", "url": f"https://news.google.com/search?q={q}+{league}+injury"},
        {"label": "ESPN Search", "url": f"https://www.espn.com/search/_/q/{q}"},
        {"label": "X/Twitter live search", "url": f"https://x.com/search?q={q}%20injury%20OR%20questionable%20OR%20probable&src=typed_query&f=live"},
        {"label": "Rotowire Search", "url": f"https://www.rotowire.com/search.php?query={q}"},
        {"label": "NBA Injury Report", "url": "https://official.nba.com/nba-injury-report-2025-26-season/"},
    ]

def parse_game(game):
    home = game.get("home_team") or {}
    visitor = game.get("visitor_team") or {}
    return {
        "id": game.get("id"),
        "date": (game.get("date") or "")[:10],
        "status": game.get("status") or "",
        "period": game.get("period"),
        "time": game.get("time"),
        "home_team": team_name(home),
        "home_abbr": team_abbr(home),
        "visitor_team": team_name(visitor),
        "visitor_abbr": team_abbr(visitor),
        "home_score": game.get("home_team_score"),
        "visitor_score": game.get("visitor_team_score"),
        "postseason": game.get("postseason"),
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "key_loaded": bool(API_KEY), "nba_path": league_path("nba"), "wnba_path": league_path("wnba")})

@app.route("/api/suggest")
def suggest():
    q = request.args.get("q", "").strip()
    league = request.args.get("league", "nba").lower().strip()
    if league not in ("nba", "wnba"):
        league = "nba"
    if len(q) < 2:
        return jsonify({"ok": True, "suggestions": []})
    try:
        players = search_player_cached(league, q)
        suggestions = rank_players(players, q)[:8]
        return jsonify({"ok": True, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "suggestions": []}), 500

@app.route("/api/today")
def today_games():
    league = request.args.get("league", "nba").lower().strip()
    if league not in ("nba", "wnba"):
        league = "nba"
    day = request.args.get("date") or date.today().isoformat()
    try:
        games = bdl_get(f"{league_path(league)}/games", {"dates[]": day, "per_page": 100}).get("data", [])
        parsed = [parse_game(g) for g in games]
        return jsonify({"ok": True, "league": league.upper(), "date": day, "games": parsed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "league": league.upper(), "date": day, "games": []}), 500

@app.route("/api/ask")
def ask():
    q = request.args.get("q", "")
    selected_league = request.args.get("league", "").lower().strip()
    season = request.args.get("season", "2024-25")
    parsed = parse_query(q)
    if selected_league in ("nba", "wnba"):
        parsed["league"] = selected_league

    league = parsed["league"]
    try:
        players = search_player_cached(league, parsed["player"])
        player = best_match(players, parsed["player"])
        if not player:
            raise RuntimeError(f"No player found for '{parsed['player']}'.")

        player_name = full_name(player)
        rows = fetch_stats(league, player["id"], season_to_year(season))
        if not rows:
            raise RuntimeError(f"No stats found for {player_name}. Try another season or check your API tier.")

        games, totals, averages, highs = summarize(rows, parsed["stats"], parsed["last_n"])
        if not games:
            raise RuntimeError(f"Stats found, but no game rows were usable for {player_name}.")

        return jsonify({
            "ok": True,
            "source": "BALLDONTLIE",
            "league": league.upper(),
            "season": season,
            "player": {"id": player["id"], "name": player_name, "position": player.get("position"), "team": player.get("team")},
            "last_n": parsed["last_n"],
            "stats": parsed["stats"],
            "display_names": DISPLAY_NAMES,
            "games": games,
            "totals": totals,
            "averages": averages,
            "highs": highs,
            "last_game": games[0] if games else {},
            "links": quick_links(player_name, league)
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "parsed": parsed, "links": quick_links(parsed["player"], league)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
