let chart, timer; const $=id=>document.getElementById(id);
const fmt=v=>(v===null||v===undefined||v==="")?"-":v;
function status(m){$("status").textContent=m||""}
function hideSug(){$("suggestions").classList.add("hidden")}
function seq(values){return (values||[]).map(v=>Number(v).toString().replace(".0","")).join(" · ")}

async function suggest(){
  const raw=$("query").value.trim();
  const name=raw.replace(/\blast\s+\d+.*$/i,"").trim();
  if(name.length<2){hideSug();return}
  try{
    const r=await fetch(`/api/suggest?league=${$("league").value}&q=${encodeURIComponent(name)}`);
    const d=await r.json();
    if(!d.suggestions||!d.suggestions.length){hideSug();return}
    $("suggestions").innerHTML=d.suggestions.map(s=>`<div class="suggestion" data-name="${s.name}" data-league="${s.league||$("league").value}"><div class="miniAvatar">${s.initials||"P"}</div><div><b>${s.name}</b><small>${(s.league||"").toUpperCase()} ${s.team_abbr||""} ${s.source==="quick"?"· quick":""}</small></div></div>`).join("");
    $("suggestions").classList.remove("hidden");
    document.querySelectorAll(".suggestion").forEach(el=>el.onclick=()=>{
      $("league").value = el.dataset.league === "wnba" ? "wnba" : "nba";
      $("query").value = `${el.dataset.name} last 6 games`;
      hideSug(); search();
    });
  }catch(e){hideSug()}
}

async function search(){
  const q=$("query").value.trim(); if(!q)return;
  hideSug(); status("Fetching last 6 betting stats...");
  $("results").classList.add("hidden");
  try{
    const r=await fetch(`/api/ask?league=${$("league").value}&q=${encodeURIComponent(q)}`);
    const d=await r.json();
    if(!d.ok){status(d.error);return}
    render(d); status("");
    document.getElementById("results").scrollIntoView({behavior:"smooth", block:"start"});
  }catch(e){status("Error: "+e.message)}
}

function render(d){
  saveRecentSearch(d.player.name);
  $("results").classList.remove("hidden");
  $("playerName").textContent=d.player.name;
  $("avatar").textContent=d.player.initials||"P";
  $("meta").textContent=`${d.league} · ${d.season} · Last ${d.last_n} games`;
  const lg=d.last_game||{};
  const lastStats=["pts","reb","ast","fg3m","fg3a","stl","blk","min"];
  $("lastGame").innerHTML=lastStats.map(s=>`<div class="stat"><strong>${fmt(lg[s])}</strong><span>${d.display_names[s]||s}</span></div>`).join("");
  $("hitCards").innerHTML=(d.hit_cards||[]).map(h=>`<div class="hit ${(h.pct||0)>=60?"good":((h.pct||0)<=33?"bad":"")}"><strong>${h.hits}/${h.total}</strong><span>${h.label}</span><div class="seq">${h.pct}% hit</div></div>`).join("");
  const summary=["pts","reb","ast","fg3m","fg3a","stl","blk"];
  $("summary").innerHTML=summary.map(s=>`<div class="stat"><strong>${fmt(d.averages[s])}</strong><span>${d.display_names[s]||s} avg · high ${fmt(d.highs[s])}</span><div class="seq">${seq(d.sequences[s])}</div></div>`).join("");
  const labels=d.games.map(g=>g.date).reverse();
  const chartStats=["pts","reb","ast","fg3m","stl","blk"];
  if(chart)chart.destroy();
  chart=new Chart($("chart"),{type:"line",data:{labels,datasets:chartStats.map(s=>({label:d.display_names[s]||s,data:d.games.map(g=>Number(g[s]||0)).reverse(),tension:.25}))},options:{plugins:{legend:{position:"bottom"}},scales:{y:{beginAtZero:true}}}});
  const cols=d.table_stats;
  $("table").querySelector("thead").innerHTML=`<tr>${cols.map(c=>`<th>${d.display_names[c]||c}</th>`).join("")}</tr>`;
  $("table").querySelector("tbody").innerHTML=d.games.map(g=>`<tr>${cols.map(c=>`<td>${fmt(g[c])}</td>`).join("")}</tr>`).join("");
}

async function loadGames(league){
  $("gamesMeta").textContent=`Loading ${league.toUpperCase()} yesterday/today/tomorrow...`;
  try{
    const r=await fetch(`/api/games3?league=${league}`);
    const d=await r.json();
    $("gamesMeta").textContent = d.ok ? `${d.league}: ${d.dates.join(" · ")}` : d.error;
    if(!d.ok)return;
    if(!d.games.length){$("gamesBoard").innerHTML=`<div class="gameCard">No games found.</div>`;return}
    $("gamesBoard").innerHTML=d.games.map(g=>`<div class="gameCard"><div class="gameTop"><span>${g.date}</span><span>${g.status||"scheduled"}</span></div><div class="team"><span>${g.visitor_abbr}</span><span>${fmt(g.visitor_score)}</span></div><div class="team"><span>${g.home_abbr}</span><span>${fmt(g.home_score)}</span></div></div>`).join("");
    $("chipTitle").classList.remove("hidden");
    $("gamePlayerChips").innerHTML=(d.chips||[]).map(c=>`<button class="playerChip" data-league="${c.league}" data-name="${c.name}">${c.initials} · ${c.name}</button>`).join("");
    document.querySelectorAll(".playerChip").forEach(b=>b.onclick=()=>{$("league").value=b.dataset.league;$("query").value=`${b.dataset.name} last 6 games`;search()});
  }catch(e){$("gamesMeta").textContent=e.message}
}


async function loadPriority(){
  const box = $("priorityChips");
  if(!box) return;
  box.innerHTML = `<span class="loadingText">Loading priority players...</span>`;
  try{
    const r = await fetch(`/api/priority?league=nba`);
    const d = await r.json();
    if(!d.ok){ box.innerHTML = "Could not load player pool."; return; }
    box.innerHTML = d.players.map(p => `<button class="priorityChip" data-league="${p.league}" data-name="${p.name}">${p.initials} · ${p.name}</button>`).join("");
    document.querySelectorAll(".priorityChip").forEach(b => b.onclick = () => {
      $("league").value = b.dataset.league === "wnba" ? "wnba" : "nba";
      $("query").value = `${b.dataset.name} last 6 games`;
      search();
    });
  }catch(e){
    box.innerHTML = e.message;
  }
}

function saveRecentSearch(name){
  const clean = (name || "").replace(/\s+last\s+\d+\s+games/i, "").trim();
  if(!clean) return;
  let recent = JSON.parse(localStorage.getItem("recent_v51") || "[]");
  recent = [clean, ...recent.filter(x => x.toLowerCase() !== clean.toLowerCase())].slice(0, 8);
  localStorage.setItem("recent_v51", JSON.stringify(recent));
  renderRecentSearches();
if($("loadPriority")) $("loadPriority").onclick=loadPriority;
}
function renderRecentSearches(){
  const box = $("recentSearches");
  if(!box) return;
  const recent = JSON.parse(localStorage.getItem("recent_v51") || "[]");
  if(!recent.length){
    box.innerHTML = `<button class="recentChip" data-name="Cade Cunningham">Cade Cunningham</button><button class="recentChip" data-name="Caitlin Clark">Caitlin Clark</button>`;
  } else {
    box.innerHTML = recent.map(n => `<button class="recentChip" data-name="${n}">${n}</button>`).join("");
  }
  document.querySelectorAll(".recentChip").forEach(b => b.onclick = () => {
    $("query").value = `${b.dataset.name} last 6 games`;
    search();
  });
}


$("query").addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(suggest,450)});
$("query").addEventListener("keydown",e=>{if(e.key==="Enter")search()});
document.querySelectorAll(".ex").forEach(b=>b.onclick=()=>{$("query").value=b.textContent;suggest()});
$("loadNba").onclick=()=>loadGames("nba");
$("loadWnba").onclick=()=>loadGames("wnba");
$("voice").onclick=()=>{const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return status("Voice needs Chrome/Edge.");const r=new SR();r.lang="en-US";r.onstart=()=>status("Listening...");r.onerror=e=>status("Voice error: "+e.error);r.onresult=e=>{$("query").value=e.results[0][0].transcript;search()};r.start()};
$("xNba").onclick=()=>window.open("https://twitter.com/search?q=NBA%20injury%20lineup%20props&f=live","_blank");
$("xWnba").onclick=()=>window.open("https://twitter.com/search?q=WNBA%20injury%20lineup%20props&f=live","_blank");
$("injury").onclick=()=>window.open("https://official.nba.com/nba-injury-report-2024-25-season/","_blank");
$("rotowire").onclick=()=>window.open("https://www.rotowire.com/basketball/nba-lineups.php","_blank");
$("google").onclick=()=>window.open("https://news.google.com/search?q=NBA%20WNBA%20injury%20props","_blank");
$("espn").onclick=()=>window.open("https://www.espn.com/search/_/q/nba%20wnba%20injury","_blank");
renderRecentSearches();
if($("loadPriority")) $("loadPriority").onclick=loadPriority;
