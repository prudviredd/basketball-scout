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

# Fresh cache expires; stale cache is retained so 429s do not create a dead-end if data was seen before.
FRESH_CACHE = {}
STALE_CACHE = {}

DISPLAY_NAMES = {
    "date": "DATE", "team": "TEAM", "min": "MIN", "pts": "PTS", "reb": "REB", "ast": "AST",
    "fg3m": "3PM", "fg3a": "3PA", "fgm": "FGM", "fga": "FGA", "stl": "STL", "blk": "BLK",
    "turnover": "TO", "plus_minus": "+/-"
}
MAIN_STATS = ["pts", "reb", "ast", "fg3m", "fg3a", "stl", "blk"]
TABLE_STATS = ["date", "team", "min", "pts", "reb", "ast", "fg3m", "fg3a", "fgm", "fga", "stl", "blk", "turnover", "plus_minus"]

NAME_FIXES = {
    "cad": "cade cunningham", "cade": "cade cunningham", "kate cunningham": "cade cunningham",
    "steph": "stephen curry", "curry": "stephen curry", "bron": "lebron james", "lebron": "lebron james",
    "jokic": "nikola jokic", "joker": "nikola jokic", "luka": "luka doncic", "luca": "luka doncic",
    "wemby": "victor wembanyama", "wemb": "victor wembanyama", "ant": "anthony edwards",
    "sga": "shai gilgeous-alexander", "kat": "karl-anthony towns",
    "aja": "a'ja wilson", "aja wilson": "a'ja wilson",
    "cait": "caitlin clark", "caitlin": "caitlin clark", "clar": "caitlin clark", "clark": "caitlin clark",
    "jen": "daniss jenkins", "jenkins": "daniss jenkins", "dennis jenkins": "daniss jenkins",    "mitchell": "donovan mitchell",
    "mobley": "evan mobley",
    "garland": "darius garland",
    "brunson": "jalen brunson",
    "randle": "julius randle",
    "duren": "jalen duren",
    "fox": "de'aaron fox",
    "vassell": "devin vassell",
    "castle": "stephon castle",
    "naz": "naz reid",
    "hart": "josh hart",
    "og": "og anunoby",
    "dort": "luguentz dort",
    "strus": "max strus",

}

POPULAR_PLAYERS = [
    ("nba", "Donovan Mitchell"),
    ("nba", "Cade Cunningham"),
    ("nba", "Evan Mobley"),
    ("nba", "Darius Garland"),
    ("nba", "Victor Wembanyama"),
    ("nba", "Anthony Edwards"),
    ("nba", "Jalen Brunson"),
    ("nba", "Karl-Anthony Towns"),
    ("nba", "Shai Gilgeous-Alexander"),
    ("nba", "Jalen Williams"),
    ("nba", "Chet Holmgren"),
    ("nba", "Julius Randle"),
    ("nba", "Tobias Harris"),
    ("nba", "Jalen Duren"),
    ("nba", "De'Aaron Fox"),
    ("nba", "Jarrett Allen"),
    ("nba", "Ausar Thompson"),
    ("nba", "Malik Beasley"),
    ("nba", "Caris LeVert"),
    ("nba", "Devin Vassell"),
    ("nba", "Stephon Castle"),
    ("nba", "Keldon Johnson"),
    ("nba", "Jeremy Sochan"),
    ("nba", "Naz Reid"),
    ("nba", "Jaden McDaniels"),
    ("nba", "Donte DiVincenzo"),
    ("nba", "Josh Hart"),
    ("nba", "OG Anunoby"),
    ("nba", "Isaiah Hartenstein"),
    ("nba", "Alex Caruso"),
    ("nba", "Mike Conley"),
    ("nba", "Nickeil Alexander-Walker"),
    ("nba", "Mikal Bridges"),
    ("nba", "Miles McBride"),
    ("nba", "Luguentz Dort"),
    ("nba", "Cason Wallace"),
    ("nba", "Aaron Wiggins"),
    ("nba", "Isaiah Joe"),
    ("nba", "Isaac Okoro"),
    ("nba", "Max Strus"),
    ("nba", "Sam Merrill"),
    ("nba", "Harrison Barnes"),
    ("nba", "Rudy Gobert"),
    ("nba", "Darius Bazley"),
    ("nba", "Caris LeVert"),
    ("wnba", "Caitlin Clark"), ("wnba", "A'ja Wilson"), ("wnba", "Breanna Stewart"), ("wnba", "Sabrina Ionescu"),
    ("wnba", "Kelsey Plum"), ("wnba", "Arike Ogunbowale"), ("wnba", "Napheesa Collier"), ("wnba", "Aliyah Boston"),
    ("wnba", "Chelsea Gray"), ("wnba", "Jewell Loyd"), ("wnba", "Rhyne Howard"), ("wnba", "Alyssa Thomas"),
    ("wnba", "Kahleah Copper"), ("wnba", "Kelsey Mitchell"), ("wnba", "Angel Reese"),
]

TEAM_PLAYER_HINTS = {
    "DET": ["Cade Cunningham", "Tobias Harris", "Jalen Duren", "Daniss Jenkins"],
    "CLE": ["Donovan Mitchell", "Darius Garland", "Evan Mobley", "Jarrett Allen"],
    "BOS": ["Jayson Tatum", "Jaylen Brown", "Derrick White", "Kristaps Porzingis"],
    "NYK": ["Jalen Brunson", "Karl-Anthony Towns", "Josh Hart", "Mikal Bridges"],
    "IND": ["Tyrese Haliburton", "Pascal Siakam", "Myles Turner", "Caitlin Clark", "Aliyah Boston", "Kelsey Mitchell"],
    "OKC": ["Shai Gilgeous-Alexander", "Jalen Williams", "Chet Holmgren"],
    "MIN": ["Anthony Edwards", "Julius Randle", "Rudy Gobert", "Naz Reid", "Napheesa Collier", "Kayla McBride"],
    "DEN": ["Nikola Jokic", "Jamal Murray", "Aaron Gordon", "Michael Porter Jr."],
    "DAL": ["Kyrie Irving", "Klay Thompson", "Anthony Davis", "Arike Ogunbowale"],
    "GSW": ["Stephen Curry", "Jimmy Butler", "Draymond Green"],
    "LAL": ["LeBron James", "Austin Reaves", "Luka Doncic"],
    "MIL": ["Giannis Antetokounmpo", "Damian Lillard", "Kyle Kuzma"],
    "PHX": ["Devin Booker", "Kevin Durant", "Bradley Beal"],
    "PHI": ["Tyrese Maxey", "Joel Embiid", "Paul George"],
    "MIA": ["Bam Adebayo", "Tyler Herro"],
    "LVA": ["A'ja Wilson", "Chelsea Gray", "Kelsey Plum", "Jackie Young"],
    "NYL": ["Breanna Stewart", "Sabrina Ionescu", "Jonquel Jones"],
    "CHI": ["Angel Reese"],
    "SEA": ["Nneka Ogwumike", "Skylar Diggins"],
    "ATL": ["Rhyne Howard"],
}

def now(): return time.time()

def make_key(path, params):
    params = params or {}
    return ("GET", path, tuple(sorted((str(k), str(v)) for k, v in params.items())))

def cache_get(key):
    item = FRESH_CACHE.get(key)
    if not item: return None
    exp, val = item
    if now() > exp:
        FRESH_CACHE.pop(key, None)
        return None
    return val

def cache_set(key, val, seconds):
    FRESH_CACHE[key] = (now() + seconds, val)
    STALE_CACHE[key] = val
    return val

def league_path(league): return "/v1" if league == "nba" else f"/{league}/v1"
def auth_headers(): return {"Authorization": API_KEY} if API_KEY else {}
def normalize(text): return " ".join((text or "").lower().replace("’", "'").split()).strip()
def normalize_player(text): return NAME_FIXES.get(normalize(text), normalize(text))
def initials(name): return "".join(part[:1] for part in name.split()[:2]).upper() or "P"
def full_name(p): return f"{p.get('first_name','')} {p.get('last_name','')}".strip()
def team_abbr(team): return (team or {}).get("abbreviation") or (team or {}).get("name") or ""
def similarity(a, b): return SequenceMatcher(None, normalize(a), normalize(b)).ratio()

def bdl_get(path, params=None, cache_seconds=0):
    if not API_KEY:
        raise RuntimeError("BALLDONTLIE_API_KEY missing in Render.")
    params = params or {}
    key = make_key(path, params)

    hit = cache_get(key)
    if hit is not None:
        return hit

    try:
        r = requests.get(BASE_URL + path, headers=auth_headers(), params=params, timeout=25)
    except Exception:
        if key in STALE_CACHE:
            return STALE_CACHE[key]
        raise RuntimeError("Network/API request failed and no cached data exists.")

    if r.status_code == 429:
        if key in STALE_CACHE:
            return STALE_CACHE[key]
        raise RuntimeError("API is busy. Try a priority chip already cached, or wait briefly and tap again.")
    if r.status_code == 401:
        raise RuntimeError("API key rejected. Check Render environment variable.")
    if r.status_code == 403:
        raise RuntimeError("Endpoint blocked by plan.")
    if r.status_code >= 400:
        if key in STALE_CACHE:
            return STALE_CACHE[key]
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
    local = cache_get(ck)
    if local is not None: return local
    games, teams = [], []
    for d in game_dates_3day():
        data = bdl_get(f"{league_path(league)}/games", {"dates[]": d, "per_page": 100}, 1800)
        for g in data.get("data", []):
            h, v = g.get("home_team") or {}, g.get("visitor_team") or {}
            ha, va = team_abbr(h), team_abbr(v)
            if ha: teams.append(ha)
            if va: teams.append(va)
            games.append({
                "date": (g.get("date") or "")[:10], "status": g.get("status") or "",
                "home_abbr": ha, "visitor_abbr": va,
                "home_score": g.get("home_team_score"), "visitor_score": g.get("visitor_team_score"),
                "matchup": f"{va} @ {ha}" if va and ha else ""
            })
    return cache_set(ck, {"games": games, "teams": list(dict.fromkeys(teams))}, 1800)

def local_suggestions(q, league=None):
    qn = normalize_player(q)
    out = []
    for lg, name in POPULAR_PLAYERS:
        if league and league != "all" and lg != league: continue
        nl = normalize(name); parts = nl.split()
        first, last = (parts[0] if parts else nl), (parts[-1] if parts else nl)
        score = max(similarity(qn, nl), similarity(qn, first), similarity(qn, last), 0.99 if qn in nl else 0)
        if len(qn) >= 2 and (score >= 0.55 or qn in nl):
            out.append({"id": None, "league": lg, "name": name, "initials": initials(name), "team_abbr": "", "score": round(score, 3), "source": "quick"})
    return sorted(out, key=lambda x: x["score"], reverse=True)

def team_player_chips(league, teams):
    chips, seen = [], set()
    wnba_names = {p[1].lower() for p in POPULAR_PLAYERS if p[0] == "wnba"}
    for tm in teams:
        for name in TEAM_PLAYER_HINTS.get(tm, []):
            lg = "wnba" if name.lower() in wnba_names else "nba"
            if league != "all" and lg != league: continue
            key = (lg, name.lower())
            if key not in seen:
                chips.append({"league": lg, "name": name, "initials": initials(name), "team_abbr": tm})
                seen.add(key)
    if not chips:
        for lg, name in POPULAR_PLAYERS:
            if lg == league:
                chips.append({"league": lg, "name": name, "initials": initials(name), "team_abbr": ""})
    return chips[:36]

def search_players_api(league, q):
    qn = normalize_player(q)
    ck = f"players:{league}:{qn}"
    hit = cache_get(ck)
    if hit is not None: return hit
    terms = []
    if qn: terms.append(qn)
    parts = qn.split()
    if parts: terms += [parts[0], parts[-1]]
    if len(qn) >= 3: terms.append(qn[:3])
    if len(qn) >= 4: terms.append(qn[:4])
    seen, players = set(), []
    for term in dict.fromkeys(terms):
        data = bdl_get(f"{league_path(league)}/players", {"search": term, "per_page": 100}, 3600)
        for p in data.get("data", []):
            pid = p.get("id")
            if pid not in seen:
                seen.add(pid); players.append(p)
    return cache_set(ck, players, 3600)

def rank_players(players, q, league):
    qn = normalize_player(q)
    ranked = []
    for p in players:
        name = full_name(p); first, last = p.get("first_name", ""), p.get("last_name", "")
        team = p.get("team") or {}
        score = max(similarity(qn, name), similarity(qn, first), similarity(qn, last),
                    0.98 if qn in normalize(name) else 0, 0.94 if normalize(name).startswith(qn) else 0)
        ranked.append({"id": p.get("id"), "league": league, "name": name, "initials": initials(name),
                       "team_abbr": team_abbr(team), "position": p.get("position"), "score": round(score, 3), "source": "api"})
    return sorted(ranked, key=lambda x: x["score"], reverse=True)

def extract_player_name(query):
    q = normalize(query)
    junk = ["nba","wnba","show","me","last","games","game","points","point","pts","rebounds","rebound","boards",
            "assists","assist","threes","three pointers","3 pointers","3pm","field goals","fgm","fga","3pa",
            "steals","steal","blocks","block","turnovers","plus minus","+/-","scored","score","how","many","did","in","the"]
    q = re.sub(r"\b\d+\b", " ", q)
    for word in sorted(junk, key=len, reverse=True):
        q = q.replace(word, " ")
    return normalize_player(q)

def parse_last_n(query):
    m = re.search(r"last\s+(\d+)", normalize(query))
    return max(1, min(int(m.group(1)), 25)) if m else DEFAULT_LAST_N

def row_date(row):
    raw = (row.get("game") or {}).get("date") or ""
    try: return datetime.fromisoformat(raw.replace("Z","+00:00"))
    except: return datetime.min

def get_stat(row, stat):
    if stat == "plus_minus": return row.get("plus_minus", row.get("plusMinus", row.get("pm","")))
    if stat == "fg3a": return row.get("fg3a", row.get("three_pt_attempts", row.get("fg3_attempts", "")))
    return row.get(stat)

def num(row, stat):
    try: return float(get_stat(row, stat) or 0)
    except: return 0

def player_stats(league, player_id):
    data = bdl_get(f"{league_path(league)}/stats", {"player_ids[]": player_id, "seasons[]": CURRENT_SEASON_YEAR, "per_page": 100}, 900)
    return data.get("data", [])

def sequence(rows, stat): return [num(r, stat) for r in rows]

def hit_rate(rows, stat, line):
    vals = sequence(rows, stat)
    hits = sum(1 for v in vals if v > line)
    return {"label": f"{DISPLAY_NAMES.get(stat, stat)} > {line}", "hits": hits, "total": len(vals), "pct": round(hits / len(vals) * 100) if vals else 0}

def summarize(rows, last_n):
    rows = sorted([r for r in rows if r.get("game")], key=row_date, reverse=True)[:last_n]
    games = []
    for r in rows:
        g, t = r.get("game") or {}, r.get("team") or {}
        games.append({
            "date": (g.get("date") or "")[:10], "team": team_abbr(t), "min": r.get("min"),
            "pts": get_stat(r, "pts"), "reb": get_stat(r, "reb"), "ast": get_stat(r, "ast"),
            "fg3m": get_stat(r, "fg3m"), "fg3a": get_stat(r, "fg3a"), "fgm": get_stat(r, "fgm"),
            "fga": get_stat(r, "fga"), "stl": get_stat(r, "stl"), "blk": get_stat(r, "blk"),
            "turnover": get_stat(r, "turnover"), "plus_minus": get_stat(r, "plus_minus")
        })
    avgs, highs, seqs = {}, {}, {}
    for stat in MAIN_STATS:
        vals = sequence(rows, stat)
        avgs[stat] = round(sum(vals)/len(vals), 2) if vals else 0
        highs[stat] = round(max(vals), 2) if vals else 0
        seqs[stat] = vals
    hit_cards = [hit_rate(rows, "pts", 19.5), hit_rate(rows, "reb", 4.5), hit_rate(rows, "ast", 4.5),
                 hit_rate(rows, "fg3m", 2.5), hit_rate(rows, "stl", 0.5), hit_rate(rows, "blk", 0.5)]
    return games, avgs, highs, seqs, hit_cards

@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/games3")
def games3():
    league = request.args.get("league", "nba").lower()
    if league not in ("nba", "wnba"): league = "nba"
    try:
        data = get_games_for_dates(league)
        chips = team_player_chips(league, data["teams"])
        return jsonify({"ok": True, "league": league.upper(), "dates": game_dates_3day(), **data, "chips": chips})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "league": league.upper(), "games": [], "teams": [], "chips": []}), 500

@app.route("/api/suggest")
def suggest():
    q = request.args.get("q", "").strip()
    league = request.args.get("league", "nba").lower()
    if league not in ("nba", "wnba", "all"): league = "nba"
    # Important: autocomplete is local-first and does not require API.
    suggestions = local_suggestions(q, league)[:10]
    return jsonify({"ok": True, "suggestions": suggestions})

@app.route("/api/ask")
def ask():
    query = request.args.get("q", "")
    league = request.args.get("league", "nba").lower()
    if league not in ("nba", "wnba"): league = "nba"
    player_name = extract_player_name(query)
    last_n = parse_last_n(query)
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
        games, avgs, highs, seqs, hit_cards = summarize(rows, last_n)
        return jsonify({"ok": True, "brand": "BetBoard V5.2", "source": "BALLDONTLIE", "league": best["league"].upper(),
                        "season": CURRENT_SEASON, "player": best, "last_n": last_n, "display_names": DISPLAY_NAMES,
                        "table_stats": TABLE_STATS, "main_stats": MAIN_STATS, "games": games, "averages": avgs,
                        "highs": highs, "sequences": seqs, "hit_cards": hit_cards, "last_game": games[0] if games else {},
                        "cache_items": len(FRESH_CACHE)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "player_name": player_name}), 500

@app.route("/api/priority")
def priority():
    league = request.args.get("league", "nba").lower()
    if league not in ("nba", "wnba", "all"):
        league = "nba"
    players = []
    for lg, name in POPULAR_PLAYERS:
        if league == "all" or lg == league:
            players.append({"league": lg, "name": name, "initials": initials(name), "team_abbr": ""})
    return jsonify({"ok": True, "players": players[:60]})

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "brand": "BetBoard V5.2", "has_key": bool(API_KEY),
                    "fresh_cache_items": len(FRESH_CACHE), "stale_cache_items": len(STALE_CACHE)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5050")), debug=False)
