from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from difflib import SequenceMatcher
import os, re, time, requests
from datetime import date, datetime

load_dotenv()
app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("BALLDONTLIE_API_KEY", "").strip()
BASE_URL = "https://api.balldontlie.io"
CACHE = {}

CURRENT_SEASON = "2025-26"
CURRENT_SEASON_YEAR = 2025
DEFAULT_LAST_N = 6

CORE_STATS = ["pts", "fg3m", "fgm", "fga", "reb", "ast", "stl", "blk", "turnover", "plus_minus"]
DISPLAY_NAMES = {
    "pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM", "stl": "STL", "blk": "BLK",
    "turnover": "TO", "min": "MIN", "fgm": "FGM", "fga": "FGA", "plus_minus": "+/-"
}
STAT_ALIASES = {
    "three pointers": "fg3m", "3 pointers": "fg3m", "3-pointers": "fg3m", "threes": "fg3m", "3pm": "fg3m",
    "field goals": "fgm", "fgm": "fgm", "field goal attempts": "fga", "fga": "fga",
    "points": "pts", "point": "pts", "pts": "pts", "scored": "pts", "score": "pts",
    "rebounds": "reb", "rebound": "reb", "boards": "reb",
    "assists": "ast", "assist": "ast",
    "steals": "stl", "blocks": "blk", "turnovers": "turnover",
    "plus minus": "plus_minus", "+/-": "plus_minus", "plus/minus": "plus_minus"
}
NAME_FIXES = {
    "kate cunningham": "cade cunningham", "cad": "cade cunningham", "cade": "cade cunningham",
    "cunningham": "cade cunningham", "steph": "stephen curry", "steph curry": "stephen curry",
    "luka": "luka doncic", "luca doncic": "luka doncic", "joker": "nikola jokic",
    "jokic": "nikola jokic", "lebron": "lebron james", "aja": "a'ja wilson", "aja wilson": "a'ja wilson",
}

def cache_get(k):
    item = CACHE.get(k)
    if not item:
        return None
    exp, val = item
    if time.time() > exp:
        CACHE.pop(k, None)
        return None
    return val

def cache_set(k, val, sec):
    CACHE[k] = (time.time() + sec, val)
    return val

def league_path(league):
    return "/v1" if league == "nba" else f"/{league}/v1"

def headers():
    return {"Authorization": API_KEY} if API_KEY else {}

def normalize_name(name):
    cleaned = " ".join((name or "").lower().replace("’", "'").split()).strip()
    return NAME_FIXES.get(cleaned, cleaned)

def bdl_get(path, params=None, cache_seconds=0):
    if not API_KEY:
        raise RuntimeError("BALLDONTLIE_API_KEY is missing in Render Environment.")
    params = params or {}
    key = ("GET", path, tuple(sorted((str(k), str(v)) for k, v in params.items())))
    if cache_seconds:
        cached = cache_get(key)
        if cached is not None:
            return cached

    r = requests.get(BASE_URL + path, headers=headers(), params=params, timeout=25)
    if r.status_code == 401:
        raise RuntimeError("API key rejected. Check Render env variable.")
    if r.status_code == 403:
        raise RuntimeError("Endpoint blocked by current BALLDONTLIE plan.")
    if r.status_code == 429:
        raise RuntimeError("Rate limit hit. Wait 60 seconds and retry.")
    if r.status_code >= 400:
        raise RuntimeError(f"BALLDONTLIE HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    if cache_seconds:
        cache_set(key, data, cache_seconds)
    return data

def full_name(p):
    return f"{p.get('first_name','')} {p.get('last_name','')}".strip() or "Unknown"

def initials(name):
    return "".join([x[:1] for x in name.split()[:2]]).upper() or "P"

def team_abbr(t):
    return (t or {}).get("abbreviation") or (t or {}).get("name") or ""

def team_name(t):
    return (t or {}).get("full_name") or (t or {}).get("name") or team_abbr(t)

def sim(a,b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def extract_name(q):
    ql = (q or "").lower()
    remove_words = [
        "nba","wnba","show","me","how","many","much","did","had","have","in","the","last","games","game",
        "points","point","pts","scored","score","rebounds","rebound","boards","assists","assist","threes",
        "three pointers","3 pointers","3-pointers","3pm","steals","blocks","turnovers","minutes",
        "field goals","field goal","field goal attempts","plus minus","plus/minus","+/-","fgm","fga"
    ]
    name = re.sub(r"\b\d+\b", " ", ql)
    for w in sorted(remove_words, key=len, reverse=True):
        name = name.replace(w, " ")
    return normalize_name(" ".join(name.split()).strip() or q)

def parse_query(q):
    ql = (q or "").lower()
    last_n = DEFAULT_LAST_N
    m = re.search(r"last\s+(\d+)", ql)
    if m:
        last_n = max(1, min(int(m.group(1)), 25))
    stats = []
    for phrase, stat in sorted(STAT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if phrase in ql and stat not in stats:
            stats.append(stat)
    # Betting mode always returns full useful table even if user asks one stat.
    return {"player": extract_name(q), "last_n": last_n, "stats": CORE_STATS}

def search_players(league, q):
    q = normalize_name(q)
    ck = f"players:{league}:{q}"
    cached = cache_get(ck)
    if cached is not None:
        return cached

    terms = []
    if q:
        terms.append(q)
    parts = q.split()
    if parts:
        terms.append(parts[-1])
    if len(q) >= 3:
        terms.append(q[:3])
    if len(q) >= 4:
        terms.append(q[:4])

    seen, players = set(), []
    for term in dict.fromkeys(terms):
        try:
            data = bdl_get(f"{league_path(league)}/players", {"search": term, "per_page": 100}, 3600)
            for p in data.get("data", []):
                if p.get("id") not in seen:
                    seen.add(p.get("id"))
                    players.append(p)
        except Exception:
            pass
    return cache_set(ck, players, 3600)

def rank_players(players, q):
    q = normalize_name(q)
    out = []
    for p in players:
        nm = full_name(p)
        first = (p.get("first_name") or "")
        last = (p.get("last_name") or "")
        score = max(
            sim(q, nm), sim(q, first), sim(q, last),
            0.99 if q == nm.lower() else 0,
            0.96 if q in nm.lower() else 0,
            0.92 if q in last.lower() else 0
        )
        t = p.get("team") or {}
        out.append({
            "id": p.get("id"), "name": nm, "initials": initials(nm), "position": p.get("position"),
            "team": team_name(t), "team_abbr": team_abbr(t), "score": round(score,3)
        })
    return sorted(out, key=lambda x: x["score"], reverse=True)

def best_player(players, q):
    ranked = rank_players(players, q)
    if not ranked:
        return None
    bid = ranked[0]["id"]
    return next((p for p in players if p.get("id") == bid), None)

def gdate(row):
    raw = (row.get("game") or {}).get("date") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z","+00:00"))
    except Exception:
        return datetime.min

def stat_val(row, stat):
    if stat == "plus_minus":
        return row.get("plus_minus", row.get("plusMinus", row.get("pm","")))
    return row.get(stat)

def num(row, stat):
    try:
        return float(stat_val(row,stat) or 0)
    except Exception:
        return 0

def summarize(rows, stats, last_n):
    # Only rows from the current season endpoint results are used.
    rows = sorted([r for r in rows if r.get("game")], key=gdate, reverse=True)[:last_n]
    totals, avgs, highs = {}, {}, {}
    for s in stats:
        vals = [num(r,s) for r in rows]
        totals[s] = round(sum(vals),2)
        avgs[s] = round(sum(vals)/len(vals),2) if vals else 0
        highs[s] = round(max(vals),2) if vals else 0
    games = []
    for r in rows:
        g,t = r.get("game") or {}, r.get("team") or {}
        games.append({
            "date": (g.get("date") or "")[:10], "status": g.get("status") or "", "team": team_abbr(t),
            "min": r.get("min"), "pts": r.get("pts"), "fg3m": r.get("fg3m"), "fgm": r.get("fgm"), "fga": r.get("fga"),
            "reb": r.get("reb"), "ast": r.get("ast"), "stl": r.get("stl"), "blk": r.get("blk"),
            "turnover": r.get("turnover"), "plus_minus": stat_val(r,"plus_minus")
        })
    return games, totals, avgs, highs

@app.route("/")
def index():
    return render_template("index.html", season=CURRENT_SEASON)

@app.route("/api/suggest")
def suggest():
    q = request.args.get("q","").strip()
    league = request.args.get("league","nba").lower()
    if league not in ("nba","wnba"):
        league = "nba"
    if len(q) < 3:
        return jsonify({"ok": True, "suggestions": []})
    try:
        return jsonify({"ok": True, "suggestions": rank_players(search_players(league,q),q)[:10]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "suggestions": []}), 500

@app.route("/api/today")
def today():
    league = request.args.get("league","nba").lower()
    if league not in ("nba","wnba"):
        league = "nba"
    day = request.args.get("date") or date.today().isoformat()
    try:
        data = bdl_get(f"{league_path(league)}/games", {"dates[]": day, "per_page": 100}, 300)
        games = []
        for g in data.get("data",[]):
            h,v = g.get("home_team") or {}, g.get("visitor_team") or {}
            games.append({
                "date": (g.get("date") or "")[:10], "status": g.get("status") or "",
                "home_abbr": team_abbr(h), "visitor_abbr": team_abbr(v),
                "home_score": g.get("home_team_score"), "visitor_score": g.get("visitor_team_score")
            })
        return jsonify({"ok": True, "league": league.upper(), "date": day, "games": games})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "league": league.upper(), "date": day, "games": []}), 500

@app.route("/api/ask")
def ask():
    q = request.args.get("q","")
    league = request.args.get("league","nba").lower()
    if league not in ("nba","wnba"):
        league = "nba"
    parsed = parse_query(q)
    try:
        players = search_players(league, parsed["player"])
        player = best_player(players, parsed["player"])
        if not player:
            raise RuntimeError(f"No player found for '{parsed['player']}'. Try first and last name.")
        rows = bdl_get(
            f"{league_path(league)}/stats",
            {"player_ids[]": player["id"], "seasons[]": CURRENT_SEASON_YEAR, "per_page": 100},
            240
        ).get("data",[])
        if not rows:
            raise RuntimeError(f"No {CURRENT_SEASON} stats found for {full_name(player)}.")
        games, totals, avgs, highs = summarize(rows, parsed["stats"], parsed["last_n"])
        nm = full_name(player)
        return jsonify({
            "ok": True, "source": "BALLDONTLIE", "league": league.upper(), "season": CURRENT_SEASON,
            "player": {"id": player["id"], "name": nm, "initials": initials(nm), "position": player.get("position")},
            "last_n": parsed["last_n"], "stats": parsed["stats"], "display_names": DISPLAY_NAMES,
            "games": games, "totals": totals, "averages": avgs, "highs": highs, "last_game": games[0] if games else {}
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "parsed": parsed}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","5050")), debug=False)
