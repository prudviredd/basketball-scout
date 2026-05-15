from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from difflib import SequenceMatcher
from datetime import date, timedelta, datetime
import os, re, time, requests

load_dotenv()
app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("BALLDONTLIE_API_KEY", "").strip()
BASE_URL = "https://api.balldontlie.io"
CURRENT_SEASON = "2025-26"
CURRENT_SEASON_YEAR = 2025
DEFAULT_LAST_N = 6

CACHE = {}
COOLDOWN_UNTIL = 0

DISPLAY_NAMES = {
    "date": "DATE", "team": "TEAM", "min": "MIN", "pts": "PTS", "reb": "REB", "ast": "AST",
    "fg3m": "3PM", "fgm": "FGM", "fga": "FGA", "stl": "STL", "blk": "BLK",
    "turnover": "TO", "plus_minus": "+/-"
}
CORE_STATS = ["pts", "fg3m", "fgm", "fga", "reb", "ast", "stl", "blk", "turnover", "plus_minus"]

NAME_FIXES = {
    "cad": "cade cunningham", "cade": "cade cunningham", "kate cunningham": "cade cunningham",
    "steph": "stephen curry", "curry": "stephen curry", "lebron": "lebron james",
    "jokic": "nikola jokic", "joker": "nikola jokic", "luka": "luka doncic", "luca": "luka doncic",
    "aja": "a'ja wilson", "aja wilson": "a'ja wilson",
    "cait": "caitlin clark", "caitlin": "caitlin clark", "clar": "caitlin clark", "clark": "caitlin clark",
}

POPULAR_PLAYERS = [
    ("nba", "Cade Cunningham"), ("nba", "Tobias Harris"), ("nba", "Stephen Curry"), ("nba", "LeBron James"),
    ("nba", "Nikola Jokic"), ("nba", "Luka Doncic"), ("nba", "Jayson Tatum"), ("nba", "Jaylen Brown"),
    ("nba", "Shai Gilgeous-Alexander"), ("nba", "Anthony Edwards"), ("nba", "Jalen Brunson"),
    ("nba", "Donovan Mitchell"), ("nba", "Tyrese Haliburton"), ("nba", "Pascal Siakam"),
    ("nba", "Karl-Anthony Towns"), ("nba", "Jalen Williams"), ("nba", "Chet Holmgren"),
    ("wnba", "Caitlin Clark"), ("wnba", "A'ja Wilson"), ("wnba", "Breanna Stewart"),
    ("wnba", "Sabrina Ionescu"), ("wnba", "Kelsey Plum"), ("wnba", "Arike Ogunbowale"),
    ("wnba", "Napheesa Collier"), ("wnba", "Aliyah Boston"), ("wnba", "Chelsea Gray"),
    ("wnba", "Jewell Loyd"), ("wnba", "Rhyne Howard"),
]

def now():
    return time.time()

def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    exp, val = item
    if now() > exp:
        CACHE.pop(key, None)
        return None
    return val

def cache_set(key, val, seconds):
    CACHE[key] = (now() + seconds, val)
    return val

def cooldown_left():
    return max(0, int(COOLDOWN_UNTIL - now()))

def league_path(league):
    return "/v1" if league == "nba" else f"/{league}/v1"

def auth_headers():
    return {"Authorization": API_KEY} if API_KEY else {}

def normalize(text):
    return " ".join((text or "").lower().replace("’", "'").split()).strip()

def normalize_player(text):
    n = normalize(text)
    return NAME_FIXES.get(n, n)

def initials(name):
    return "".join(part[:1] for part in name.split()[:2]).upper() or "P"

def full_name(p):
    return f"{p.get('first_name','')} {p.get('last_name','')}".strip()

def team_abbr(team):
    return (team or {}).get("abbreviation") or (team or {}).get("name") or ""

def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()

def bdl_get(path, params=None, cache_seconds=0):
    global COOLDOWN_UNTIL
    params = params or {}
    key = ("GET", path, tuple(sorted((str(k), str(v)) for k, v in params.items())))
    hit = cache_get(key)
    if hit is not None:
        return hit

    if not API_KEY:
        raise RuntimeError("BALLDONTLIE_API_KEY missing in Render.")
    if cooldown_left() > 0:
        raise RuntimeError(f"API guard active. Wait {cooldown_left()} seconds.")

    r = requests.get(BASE_URL + path, headers=auth_headers(), params=params, timeout=25)

    if r.status_code == 429:
        COOLDOWN_UNTIL = now() + 75
        raise RuntimeError("Rate limit hit. Guard enabled for 75 seconds.")
    if r.status_code == 401:
        raise RuntimeError("API key rejected.")
    if r.status_code == 403:
        raise RuntimeError("Endpoint blocked by plan.")
    if r.status_code >= 400:
        raise RuntimeError(f"BALLDONTLIE HTTP {r.status_code}: {r.text[:180]}")

    data = r.json()
    if cache_seconds:
        cache_set(key, data, cache_seconds)
    return data

def game_dates_3day():
    today = date.today()
    return [(today - timedelta(days=1)).isoformat(), today.isoformat(), (today + timedelta(days=1)).isoformat()]

def get_games_for_dates(league):
    ck = f"games3:{league}:{date.today().isoformat()}"
    hit = cache_get(ck)
    if hit is not None:
        return hit

    games = []
    teams = []
    for d in game_dates_3day():
        data = bdl_get(f"{league_path(league)}/games", {"dates[]": d, "per_page": 100}, 1800)
        for g in data.get("data", []):
            h, v = g.get("home_team") or {}, g.get("visitor_team") or {}
            ha, va = team_abbr(h), team_abbr(v)
            if ha: teams.append(ha)
            if va: teams.append(va)
            games.append({
                "date": (g.get("date") or "")[:10],
                "status": g.get("status") or "",
                "home_abbr": ha,
                "visitor_abbr": va,
                "home_score": g.get("home_team_score"),
                "visitor_score": g.get("visitor_team_score"),
            })
    return cache_set(ck, {"games": games, "teams": list(dict.fromkeys(teams))}, 1800)

def local_suggestions(q, league=None):
    qn = normalize_player(q)
    out = []
    for lg, name in POPULAR_PLAYERS:
        if league and league != "all" and lg != league:
            continue
        nl = normalize(name)
        first = nl.split()[0] if nl.split() else nl
        last = nl.split()[-1] if nl.split() else nl
        score = max(similarity(qn, nl), similarity(qn, first), similarity(qn, last), 0.99 if qn in nl else 0)
        if len(qn) >= 2 and (score >= 0.55 or qn in nl):
            out.append({"id": None, "league": lg, "name": name, "initials": initials(name), "team_abbr": "", "score": round(score, 3), "source": "local"})
    return sorted(out, key=lambda x: x["score"], reverse=True)

def search_players_api(league, q):
    qn = normalize_player(q)
    ck = f"players:{league}:{qn}"
    hit = cache_get(ck)
    if hit is not None:
        return hit

    terms = []
    if qn: terms.append(qn)
    parts = qn.split()
    if parts:
        terms += [parts[0], parts[-1]]
    if len(qn) >= 3:
        terms.append(qn[:3])
    if len(qn) >= 4:
        terms.append(qn[:4])

    seen, players = set(), []
    for term in dict.fromkeys(terms):
        data = bdl_get(f"{league_path(league)}/players", {"search": term, "per_page": 100}, 3600)
        for p in data.get("data", []):
            pid = p.get("id")
            if pid not in seen:
                seen.add(pid)
                players.append(p)
    return cache_set(ck, players, 3600)

def rank_players(players, q, league):
    qn = normalize_player(q)
    ranked = []
    for p in players:
        name = full_name(p)
        first, last = p.get("first_name", ""), p.get("last_name", "")
        team = p.get("team") or {}
        score = max(
            similarity(qn, name), similarity(qn, first), similarity(qn, last),
            0.98 if qn in normalize(name) else 0,
            0.94 if normalize(name).startswith(qn) else 0
        )
        ranked.append({
            "id": p.get("id"), "league": league, "name": name, "initials": initials(name),
            "team_abbr": team_abbr(team), "position": p.get("position"), "score": round(score, 3), "source": "api"
        })
    return sorted(ranked, key=lambda x: x["score"], reverse=True)

def extract_player_name(query):
    q = normalize(query)
    junk = [
        "nba","wnba","show","me","last","games","game","points","point","pts","rebounds","rebound","boards",
        "assists","assist","threes","three pointers","3 pointers","3pm","field goals","fgm","fga",
        "steals","blocks","turnovers","plus minus","+/-","scored","score","how","many","did","in","the"
    ]
    q = re.sub(r"\b\d+\b", " ", q)
    for word in sorted(junk, key=len, reverse=True):
        q = q.replace(word, " ")
    return normalize_player(q)

def parse_last_n(query):
    m = re.search(r"last\s+(\d+)", normalize(query))
    return max(1, min(int(m.group(1)), 25)) if m else DEFAULT_LAST_N

def row_date(row):
    raw = (row.get("game") or {}).get("date") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z","+00:00"))
    except:
        return datetime.min

def get_stat(row, stat):
    if stat == "plus_minus":
        return row.get("plus_minus", row.get("plusMinus", row.get("pm","")))
    return row.get(stat)

def num(row, stat):
    try:
        return float(get_stat(row, stat) or 0)
    except:
        return 0

def player_stats(league, player_id):
    data = bdl_get(
        f"{league_path(league)}/stats",
        {"player_ids[]": player_id, "seasons[]": CURRENT_SEASON_YEAR, "per_page": 100},
        900
    )
    return data.get("data", [])

def summarize(rows, last_n):
    rows = sorted([r for r in rows if r.get("game")], key=row_date, reverse=True)[:last_n]
    games = []
    for r in rows:
        g, t = r.get("game") or {}, r.get("team") or {}
        games.append({
            "date": (g.get("date") or "")[:10],
            "team": team_abbr(t),
            "min": r.get("min"),
            "pts": r.get("pts"),
            "reb": r.get("reb"),
            "ast": r.get("ast"),
            "fg3m": r.get("fg3m"),
            "fgm": r.get("fgm"),
            "fga": r.get("fga"),
            "stl": r.get("stl"),
            "blk": r.get("blk"),
            "turnover": r.get("turnover"),
            "plus_minus": get_stat(r, "plus_minus")
        })
    avgs, highs = {}, {}
    for stat in CORE_STATS:
        vals = [num(r, stat) for r in rows]
        avgs[stat] = round(sum(vals)/len(vals), 2) if vals else 0
        highs[stat] = round(max(vals), 2) if vals else 0
    return games, avgs, highs

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/games3")
def games3():
    league = request.args.get("league", "nba").lower()
    if league not in ("nba", "wnba"):
        league = "nba"
    try:
        data = get_games_for_dates(league)
        return jsonify({"ok": True, "league": league.upper(), "dates": game_dates_3day(), **data, "cooldown": cooldown_left()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "league": league.upper(), "cooldown": cooldown_left(), "games": [], "teams": []}), 500

@app.route("/api/suggest")
def suggest():
    q = request.args.get("q", "").strip()
    league = request.args.get("league", "nba").lower()
    if league not in ("nba", "wnba", "all"):
        league = "nba"

    if len(q) < 3:
        return jsonify({"ok": True, "suggestions": local_suggestions(q, league), "cooldown": cooldown_left()})

    suggestions = []
    seen = set()

    # Local first: fast and no API call.
    for s in local_suggestions(q, league):
        suggestions.append(s); seen.add((s["league"], s["name"].lower()))

    # API selected league, then fallback other league if weak/no result.
    leagues = ["nba", "wnba"] if league == "all" else [league, "wnba" if league == "nba" else "nba"]
    try:
        for lg in leagues:
            ranked = rank_players(search_players_api(lg, q), q, lg)[:8]
            for s in ranked:
                key = (s["league"], s["name"].lower())
                if key not in seen:
                    suggestions.append(s); seen.add(key)
            if len(suggestions) >= 8 and suggestions[0].get("source") == "api":
                break
    except Exception as e:
        return jsonify({"ok": True, "warning": str(e), "suggestions": suggestions[:10], "cooldown": cooldown_left()})

    return jsonify({"ok": True, "suggestions": suggestions[:10], "cooldown": cooldown_left()})

@app.route("/api/ask")
def ask():
    query = request.args.get("q", "")
    league = request.args.get("league", "nba").lower()
    if league not in ("nba", "wnba"):
        league = "nba"
    player_name = extract_player_name(query)
    last_n = parse_last_n(query)

    # Search selected league first, then fallback other league.
    try:
        selected = rank_players(search_players_api(league, player_name), player_name, league)
        fallback_league = "wnba" if league == "nba" else "nba"
        ranked = selected
        if not ranked or ranked[0]["score"] < 0.70:
            ranked += rank_players(search_players_api(fallback_league, player_name), player_name, fallback_league)

        if not ranked:
            raise RuntimeError(f"No player found for '{player_name}'. Try first or last name.")

        best = sorted(ranked, key=lambda x: x["score"], reverse=True)[0]
        rows = player_stats(best["league"], best["id"])
        if not rows:
            raise RuntimeError(f"No {CURRENT_SEASON} stats found for {best['name']}.")

        games, avgs, highs = summarize(rows, last_n)
        return jsonify({
            "ok": True,
            "source": "BALLDONTLIE",
            "league": best["league"].upper(),
            "season": CURRENT_SEASON,
            "player": best,
            "last_n": last_n,
            "display_names": DISPLAY_NAMES,
            "games": games,
            "averages": avgs,
            "highs": highs,
            "last_game": games[0] if games else {},
            "cooldown": cooldown_left()
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "cooldown": cooldown_left(), "player_name": player_name}), 500

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "has_key": bool(API_KEY), "cooldown": cooldown_left(), "cache_items": len(CACHE)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5050")), debug=False)
