let chart, timer; const $=id=>document.getElementById(id);
const fmt=v=>(v===null||v===undefined||v==="")?"-":v;
function status(m){$("status").textContent=m||""}
function hideSug(){$("suggestions").classList.add("hidden")}

async function suggest(){
  const raw=$("query").value.trim();
  const name=raw.replace(/\blast\s+\d+.*$/i,"").trim();
  if(name.length<3){hideSug();return}
  try{
    const r=await fetch(`/api/suggest?league=${$("league").value}&q=${encodeURIComponent(name)}`);
    const d=await r.json();
    if(!d.suggestions||!d.suggestions.length){hideSug();return}
    $("suggestions").innerHTML=d.suggestions.map(s=>`<div class="suggestion" data-name="${s.name}" data-league="${s.league||$("league").value}"><div class="miniAvatar">${s.initials||"P"}</div><div><b>${s.name}</b><small>${(s.league||"").toUpperCase()} ${s.team_abbr||""} ${s.source==="local"?"· quick":""}</small></div></div>`).join("");
    $("suggestions").classList.remove("hidden");
    document.querySelectorAll(".suggestion").forEach(el=>el.onclick=()=>{
      const tail=$("query").value.match(/\blast\s+\d+.*$/i);
      $("league").value = el.dataset.league === "wnba" ? "wnba" : "nba";
      $("query").value = tail ? `${el.dataset.name} ${tail[0]}` : `${el.dataset.name} last 6 games`;
      hideSug(); search();
    });
  }catch(e){hideSug()}
}

async function search(){
  const q=$("query").value.trim(); if(!q)return;
  hideSug(); status("Fetching last 6 games...");
  $("results").classList.add("hidden");
  try{
    const r=await fetch(`/api/ask?league=${$("league").value}&q=${encodeURIComponent(q)}`);
    const d=await r.json();
    if(!d.ok){status(d.error);return}
    render(d); status("");
  }catch(e){status("Error: "+e.message)}
}

function render(d){
  $("results").classList.remove("hidden");
  $("playerName").textContent=d.player.name;
  $("avatar").textContent=d.player.initials||"P";
  $("meta").textContent=`${d.league} · ${d.season} · Last ${d.last_n} games`;
  const lg=d.last_game||{};
  const lastStats=["pts","reb","ast","fg3m","fgm","fga","plus_minus","min"];
  $("lastGame").innerHTML=lastStats.map(s=>`<div class="stat"><strong>${fmt(lg[s])}</strong><span>${d.display_names[s]||s}</span></div>`).join("");
  const summary=["pts","reb","ast","fg3m","stl","blk","turnover","plus_minus"];
  $("summary").innerHTML=summary.map(s=>`<div class="stat"><strong>${fmt(d.averages[s])}</strong><span>${d.display_names[s]||s} avg · high ${fmt(d.highs[s])}</span></div>`).join("");
  const labels=d.games.map(g=>g.date).reverse();
  const chartStats=["pts","reb","ast","fg3m"];
  if(chart)chart.destroy();
  chart=new Chart($("chart"),{type:"line",data:{labels,datasets:chartStats.map(s=>({label:d.display_names[s]||s,data:d.games.map(g=>Number(g[s]||0)).reverse(),tension:.25}))},options:{plugins:{legend:{position:"bottom"}},scales:{y:{beginAtZero:true}}}});
  const cols=["date","team","min","pts","reb","ast","fg3m","fgm","fga","stl","blk","turnover","plus_minus"];
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
  }catch(e){$("gamesMeta").textContent=e.message}
}

$("query").addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(suggest,500)});
$("query").addEventListener("keydown",e=>{if(e.key==="Enter")search()});
$("search").onclick=search;
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
