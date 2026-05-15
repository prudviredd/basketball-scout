let chart;
let suggestTimer;
const $ = id => document.getElementById(id);

function setStatus(msg){ $("status").textContent = msg || ""; }
function fmt(v){ if(v === null || v === undefined || v === "") return "-"; return v; }

async function loadTodayGames(){
  const league = $("league").value;
  try{
    const res = await fetch(`/api/today?league=${league}`);
    const data = await res.json();
    $("todayTitle").textContent = `${data.league} · ${data.date}`;
    const board = $("gamesBoard");
    if(!data.ok){
      board.innerHTML = `<div class="gameCard"><b>Could not load games</b><p>${data.error}</p></div>`;
      return;
    }
    if(!data.games.length){
      board.innerHTML = `<div class="gameCard"><b>No ${data.league} games found today</b><p>Try changing league or check schedule later.</p></div>`;
      return;
    }
    board.innerHTML = data.games.map(g => {
      const statusClass = String(g.status || "").toLowerCase().includes("final") ? "final" :
        String(g.status || "").toLowerCase().includes("q") || String(g.status || "").includes(":") ? "live" : "scheduled";
      return `
        <div class="gameCard">
          <div class="gameTop"><span>${g.date}</span><span class="${statusClass}">${g.status || "Scheduled"}</span></div>
          <div class="teams">
            <div class="teamLine"><span>${g.visitor_abbr || g.visitor_team}</span><span class="score">${fmt(g.visitor_score)}</span></div>
            <div class="teamLine"><span>${g.home_abbr || g.home_team}</span><span class="score">${fmt(g.home_score)}</span></div>
          </div>
        </div>`;
    }).join("");
  }catch(e){
    $("gamesBoard").innerHTML = `<div class="gameCard"><b>Games load failed</b><p>${e.message}</p></div>`;
  }
}

async function fetchSuggestions(){
  const q = $("query").value.trim();
  if(q.length < 2){ hideSuggestions(); return; }
  const firstWords = q.replace(/\blast\s+\d+.*$/i, "").trim();
  if(firstWords.length < 2){ hideSuggestions(); return; }

  try{
    const params = new URLSearchParams({q:firstWords, league:$("league").value});
    const res = await fetch(`/api/suggest?${params}`);
    const data = await res.json();
    if(!data.ok || !data.suggestions.length){ hideSuggestions(); return; }
    $("suggestions").innerHTML = data.suggestions.map(s => `
      <div class="suggestion" data-name="${s.name}">
        <div><strong>${s.name}</strong><span>${s.position || ""} · ${s.team_abbr || s.team || ""}</span></div>
        <span>${Math.round((s.score || 0)*100)}%</span>
      </div>`).join("");
    $("suggestions").classList.remove("hidden");
    document.querySelectorAll(".suggestion").forEach(el => {
      el.onclick = () => {
        const name = el.dataset.name;
        const tailMatch = $("query").value.match(/\blast\s+\d+.*$/i);
        $("query").value = tailMatch ? `${name} ${tailMatch[0]}` : `${name} last 5 games`;
        hideSuggestions();
        runSearch();
      };
    });
  }catch(e){ hideSuggestions(); }
}

function hideSuggestions(){ $("suggestions").classList.add("hidden"); }

async function runSearch(){
  const q = $("query").value.trim();
  if(!q) return setStatus("Enter a player question first.");
  hideSuggestions();
  setStatus("Fetching exact game log...");
  $("results").classList.add("hidden");
  $("linksCard").classList.add("hidden");

  const params = new URLSearchParams({q, league:$("league").value, season:$("season").value});
  try{
    const res = await fetch(`/api/ask?${params}`);
    const data = await res.json();
    if(!data.ok){
      setStatus(data.error || "Could not fetch stats.");
      renderLinks(data.links || []);
      return;
    }
    renderResults(data);
    setStatus("");
  }catch(e){ setStatus("Browser could not reach backend: " + e.message); }
}

function renderResults(data){
  $("results").classList.remove("hidden");
  $("playerName").textContent = data.player.name;
  $("meta").textContent = `${data.league} · ${data.season} · Last ${data.last_n} games · Exact game log · Source: ${data.source}`;

  const lg = data.last_game || {};
  const lastStats = ["pts","fg3m","fgm","fga","reb","ast","stl","blk","turnover","plus_minus"];
  $("lastGame").innerHTML = lastStats.map(s => `
    <div class="lastStat ${s === "pts" ? "feature" : ""}">
      <strong>${fmt(lg[s])}</strong>
      <span>${data.display_names[s] || s}</span>
    </div>`).join("");

  $("summary").innerHTML = data.stats.map(s => `
    <div class="stat">
      <strong>${fmt(data.averages[s])}</strong>
      <span>${data.display_names[s] || s} avg</span><br>
      <span>High: ${fmt(data.highs[s])} · Total: ${fmt(data.totals[s])}</span>
    </div>`).join("");

  const labels = data.games.map(g => g.date || "").reverse();
  const chartStats = data.stats.filter(s => ["pts","fg3m","reb","ast","stl","blk","turnover"].includes(s));
  const datasets = chartStats.map(s => ({
    label: data.display_names[s] || s,
    data: data.games.map(g => Number(g[s] || 0)).reverse(),
    tension:.28
  }));

  if(chart) chart.destroy();
  chart = new Chart($("chart"),{
    type:"line",
    data:{labels,datasets},
    options:{responsive:true,plugins:{legend:{position:"bottom"}},scales:{y:{beginAtZero:true}}}
  });

  const cols = ["date","team","min","pts","fg3m","fgm","fga","reb","ast","stl","blk","turnover","plus_minus"];
  $("table").querySelector("thead").innerHTML =
    `<tr>${cols.map(c => `<th>${(data.display_names[c] || c).toUpperCase()}</th>`).join("")}</tr>`;
  $("table").querySelector("tbody").innerHTML = data.games.map(g =>
    `<tr>${cols.map(c => `<td>${fmt(g[c])}</td>`).join("")}</tr>`
  ).join("");

  renderLinks(data.links || []);
}

function renderLinks(links){
  if(!links.length) return;
  $("linksCard").classList.remove("hidden");
  $("links").innerHTML = links.map(l => `<a href="${l.url}" target="_blank">${l.label}</a>`).join("");
}

$("search").onclick = runSearch;
$("query").addEventListener("keydown", e => { if(e.key === "Enter") runSearch(); });
$("query").addEventListener("input", () => {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(fetchSuggestions, 250);
});
document.addEventListener("click", e => {
  if(!e.target.closest(".inputWrap")) hideSuggestions();
});
document.querySelectorAll(".ex").forEach(b => b.onclick = () => { $("query").value = b.textContent; fetchSuggestions(); });

$("league").addEventListener("change", () => { loadTodayGames(); hideSuggestions(); });

$("voice").onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SR) return setStatus("Voice search needs Chrome or Edge.");
  const rec = new SR();
  rec.lang = "en-US";
  rec.onstart = () => setStatus("Listening...");
  rec.onerror = e => setStatus("Voice error: " + e.error);
  rec.onresult = e => { $("query").value = e.results[0][0].transcript; fetchSuggestions(); runSearch(); };
  rec.start();
};

loadTodayGames();
