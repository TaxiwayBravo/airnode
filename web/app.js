'use strict';
const $ = id => document.getElementById(id);
let csrf = '', configured = false, config = null, status = null, aircraft = null, lastSample = null, polling = false, confirmation = null, map = null, mapMarkers = new Map(), leafletReady = null;
let providers = [], selectedProvider = null, aggregatorPolling = false;
function setupTheme(){if(document.getElementById('theme-toggle'))return;const b=document.createElement('button');b.id='theme-toggle';b.type='button';b.textContent=localStorage.getItem('airnode-theme')==='dark'?'Light mode':'Dark mode';b.title='Toggle dark mode';b.addEventListener('click',()=>{const dark=document.body.classList.toggle('dark-mode');localStorage.setItem('airnode-theme',dark?'dark':'light');b.textContent=dark?'Light mode':'Dark mode';});document.querySelector('.header-right')?.appendChild(b);if(localStorage.getItem('airnode-theme')==='dark')document.body.classList.add('dark-mode');const style=document.createElement('style');style.textContent='.dark-mode{--ink:#e5f0f2;--muted:#9bb0b8;--line:#29434e;--bg:#0b1b25}.dark-mode .card,.dark-mode .metric,.dark-mode input,.dark-mode select,.dark-mode dialog{background:#122a36;color:var(--ink);border-color:#29434e}.dark-mode th{background:#10232d;color:#9bb0b8}.dark-mode td{color:#c0d1d5;border-color:#29434e}.dark-mode .radar-wrap,.dark-mode .aircraft-map{background:#112832}.dark-mode button{background:#173440;color:var(--ink);border-color:#31515d}.dark-mode .primary{background:#117f79;color:#fff}#theme-toggle{padding:7px 11px;font-size:11px}';document.head.appendChild(style);}
async function loadInstallation(){try{const p=await api('installation');if(!configured||!csrf){$('auth-description').textContent=p.state==='ready'?'Your receiver is ready. Claim it to continue.':`${p.step} (${p.progress}%)`;}}catch{}}
function setupWifiFields(){if($('setup-wifi'))return;const box=document.createElement('div');box.id='setup-wifi';box.className='setup-note';box.innerHTML='<strong>Connect this Pi to your Wi-Fi</strong><p>Choose the same network your phone or computer uses. AirNode will connect after you create the owner password.</p><label>Home Wi-Fi<input id="setup-ssid" list="setup-networks" autocomplete="off" maxlength="32" placeholder="Select or type network name"><datalist id="setup-networks"></datalist></label><label>Wi-Fi password<input id="setup-wifi-password" type="password" autocomplete="off" maxlength="64"></label><label>Country code<input id="setup-country" value="GB" pattern="[A-Z]{2}" maxlength="2"></label><button type="button" id="setup-scan">Scan for Wi-Fi</button><small id="setup-wifi-status">Scanning…</small>';const form=$('auth-form');form.insertBefore(box,$('login-password').parentElement);$('setup-scan').addEventListener('click',loadSetupWifi);loadSetupWifi();}
async function loadSetupWifi(){try{const w=await api('onboarding/wifi');$('setup-wifi-status').textContent=w.message||'Choose your home network';$('setup-networks').innerHTML=(w.networks||[]).map(n=>`<option value="${escapeHTML(n.ssid)}">${escapeHTML(n.signal)}% · ${escapeHTML(n.security)}</option>`).join('');}catch(e){$('setup-wifi-status').textContent='Enter your network name manually.';}}
const escapeHTML = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function ensureMapContainer(){let box=$('aircraft-map');if(box)return box;const target=$('overview')||$('sky');if(!target)return null;box=document.createElement('div');box.id='aircraft-map';box.className='aircraft-map';box.setAttribute('role','application');box.setAttribute('aria-label','Live aircraft map');box.innerHTML='<div class="map-message">Waiting for a station location and live aircraft positions.</div>';const radar=target.querySelector('.radar-wrap');if(radar)radar.parentElement.insertBefore(box,radar);if(!document.getElementById('airnode-map-style')){const style=document.createElement('style');style.id='airnode-map-style';style.textContent='.aircraft-map{height:420px;margin:0 20px 20px;border-radius:8px;overflow:hidden;background:#edf4f3;position:relative}.aircraft-map .map-message{position:absolute;z-index:500;inset:0;display:grid;place-items:center;color:#6d858e;font-size:13px;padding:20px;text-align:center;pointer-events:none}.leaflet-container{font:12px Inter,ui-sans-serif,sans-serif}';document.head.appendChild(style);}return box;}
function loadLeaflet(){if(window.L)return Promise.resolve(window.L);if(leafletReady)return leafletReady;leafletReady=new Promise((resolve,reject)=>{const css=document.createElement('link');css.rel='stylesheet';css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.appendChild(css);const script=document.createElement('script');script.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';script.onload=()=>resolve(window.L);script.onerror=reject;document.head.appendChild(script);});return leafletReady;}
async function updateAircraftMap(){const box=ensureMapContainer();if(!box)return;const positions=(aircraft&&!aircraft.stale?aircraft.aircraft:[]).filter(a=>Number.isFinite(a.lat)&&Number.isFinite(a.lon)&&a.seen_pos<60);const center=config?.receiver;try{const L=await loadLeaflet();if(!map){const lat=Number.isFinite(center?.latitude)?center.latitude:(positions[0]?.lat||51.5),lon=Number.isFinite(center?.longitude)?center.longitude:(positions[0]?.lon||-0.1);map=L.map(box,{worldCopyJump:true}).setView([lat,lon],Number.isFinite(center?.latitude)?8:4);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap contributors'}).addTo(map);const msg=box.querySelector('.map-message');if(msg)msg.remove();}const seen=new Set;positions.forEach(a=>{seen.add(a.hex);let marker=mapMarkers.get(a.hex);if(!marker){marker=L.circleMarker([a.lat,a.lon],{radius:7,color:'#fff',weight:2,fillColor:'#117f79',fillOpacity:.95}).addTo(map);mapMarkers.set(a.hex,marker);}marker.setLatLng([a.lat,a.lon]).bindPopup('<strong>'+escapeHTML((a.flight||a.hex).trim())+'</strong><br>'+escapeHTML(a.desc||a.t||'Aircraft type unavailable')+'<br>'+escapeHTML(a.alt_baro==null?'Altitude unavailable':String(a.alt_baro)+' ft'));});mapMarkers.forEach((marker,key)=>{if(!seen.has(key)){map.removeLayer(marker);mapMarkers.delete(key);}});if(!positions.length){const msg=box.querySelector('.map-message');if(msg)msg.textContent=aircraft?.stale?'Receiver data unavailable or stale.':'Map ready. Waiting for fresh aircraft positions.';}}catch{const msg=box.querySelector('.map-message');if(msg)msg.textContent='Map tiles are unavailable. Use the aircraft links below or connect the Pi to the internet.';}}
async function api(path, data) {
  const res = await fetch('/api/' + path, {method:data === undefined ? 'GET' : 'POST', headers:data === undefined ? {} : {'Content-Type':'application/json','X-CSRF-Token':csrf}, body:data === undefined ? undefined : JSON.stringify(data)});
  const result = await res.json();
  if (!res.ok) {
    if (res.status === 401 && !['login','setup'].includes(path)) { $('shell').hidden = true; $('auth').hidden = false; }
    throw new Error(result.error || `Request failed (${res.status})`);
  }
  return result;
}
function notice(text, error=false) { $('notice').textContent=text; $('notice').classList.toggle('error',error); $('notice').hidden=false; }
async function action(work) { try { await work(); } catch(e) { notice(e.message,true); } }
function view() {
  const name = location.hash.slice(1) || 'overview';
  const valid = ['overview','sky','receiver','feeders','aggregators','system','logs'].includes(name) ? name : 'overview';
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== valid);
  document.querySelectorAll('nav a').forEach(el => el.classList.toggle('active', el.dataset.view === valid));
  $('crumb').textContent = valid.toUpperCase();
  if (valid === 'logs' && csrf) action(loadLogs);
  if (valid === 'aggregators' && csrf) action(loadAggregators);
  if (valid === 'system' && csrf) action(loadDeviceSetup);
  requestAnimationFrame(()=>{drawRadars();if(valid==='sky'&&map)map.invalidateSize();if(valid==='sky')updateAircraftMap();});
}
async function boot() {
  try {
    await loadInstallation();
    const session=await api('session'); configured=session.configured; csrf=session.csrf || '';
    $('shell').hidden=!session.authenticated; $('auth').hidden=session.authenticated;if(!session.configured)setupWifiFields();
    if(session.authenticated)setupTheme();
    $('auth-title').textContent=configured?'Sign in to your station':'Claim your AirNode';
    $('auth-submit').textContent=configured?'Sign in →':'Create owner account →';
    $('auth-demo').textContent=session.demo?'Demo mode · synthetic aircraft · no host changes':session.local_preview?'Hardware preview · no Pi connected':'';
    if(session.authenticated){ await loadConfig(); await refresh(); view(); }
  } catch(e) { $('auth').hidden=false; $('auth-error').textContent=e.message; }
}
$('auth-form').addEventListener('submit',async e=>{e.preventDefault();$('auth-submit').disabled=true;const firstSetup=!configured;try{const setupWifi=firstSetup&&$('setup-ssid')?.value;const response=await api(firstSetup?'setup':'login',{password:$('login-password').value});csrf=response.csrf;$('login-password').value='';$('auth-error').textContent='';if(firstSetup&&setupWifi){await api('wifi/connect',{ssid:setupWifi,password:$('setup-wifi-password').value,country:$('setup-country').value.toUpperCase()});$('setup-wifi-password').value='';}if(firstSetup)location.hash='system';await boot();}catch(err){$('auth-error').textContent=err.message;}finally{$('auth-submit').disabled=false;}});
$('logout').addEventListener('click',()=>action(async()=>{await api('logout',{});csrf='';await boot();}));
async function loadConfig(){
  config=await api('config'); const r=config.receiver;
  $('station-name').value=config.name;$('sdr-device').value=r.device;$('sdr-gain').value=r.gain;$('sdr-ppm').value=r.ppm;
  $('latitude').value=r.latitude??'';$('longitude').value=r.longitude??'';$('lan-output').checked=r.lan_output;
  renderFeeds();
}
async function refresh(){
  if(polling || !csrf || $('shell').hidden)return;polling=true;
  try{
    [status,aircraft]=await Promise.all([api('status'),api('aircraft')]);
    $('demo-pill').hidden=!(status.demo||status.local_preview);$('demo-pill').textContent=status.local_preview?'NO PI CONNECTED':'DEMO DATA';$('side-name').textContent=status.station;$('side-host').textContent=status.hostname;
    $('metric-aircraft').textContent=status.aircraft;$('metric-position').textContent=status.positioned;
    $('metric-temp').textContent=status.temperature??'—';$('metric-storage').textContent=status.disk_percent==null?'No Pi connected':`${status.disk_percent}% storage used`;
    const receiver=status.services['airnode-receiver']; const healthy=!status.stale && receiver?.ActiveState==='active';
    $('health-banner').classList.toggle('warning',!healthy);$('health-title').textContent=healthy?'Your station is receiving':'Your station needs attention';
    $('health-description').textContent=healthy?(status.demo?'Demo mode is showing simulated traffic.':'Fresh receiver data is reaching AirNode. Your local sky is up to date.'):(status.error||'No fresh decoder data. Check the USB SDR, receiver service and logs.');
    $('health-badge').textContent=healthy?'RECEIVING':'CHECK RECEIVER';
    $('receiver-state').textContent=receiver?.ActiveState||'unavailable';$('receiver-gain').textContent=config.receiver.gain==='auto'?'Automatic':`${config.receiver.gain} dB`;
    $('receiver-age').textContent=status.data_age===null?'No data':`${status.data_age}s ago${status.stale?' · stale':''}`;
    $('usb-inventory').textContent=status.usb||'No USB devices reported';
    if(document.activeElement!==$('hostname'))$('hostname').value=status.hostname;
    const access=status.access;
    $('access-description').textContent=(status.demo||status.local_preview)?'This preview runs on your computer. The installed Pi will show its own network addresses here.':'Open one of these addresses on a computer connected to the same LAN. Your Pi hosts the dashboard.';
    const links=access&&!access.demo?[...(access.hostname_url?[{url:access.hostname_url,interface:'Local hostname'}]:[]),...access.addresses]:[];
    $('access-links').innerHTML=links.map(item=>`<a href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(item.url)}<small>${escapeHTML(item.interface)}</small></a>`).join('')||((status.demo||status.local_preview)?'<p>No Pi LAN address available in this preview.</p>':'<p>Waiting for a network address. Check the Ethernet cable or Wi-Fi connection.</p>');

    try{const nets=JSON.parse(status.network);$('network-info').textContent=nets.flatMap(n=>(n.addr_info||[]).filter(a=>a.scope==='global').map(a=>`${n.ifname}  ${a.local}/${a.prefixlen}`)).join('\n')||'No active Pi network addresses reported';}catch{$('network-info').textContent='Network status unavailable';}
    $('update-state').textContent=status.update||'Unavailable';$('version').textContent=status.version;
    $('last-sync').textContent=`Last sync ${new Date().toLocaleTimeString()}`;
    let rate='—';if(lastSample&&!aircraft.stale){const dt=aircraft.now-lastSample.now,delta=aircraft.messages-lastSample.messages;if(dt>0&&delta>=0)rate=Math.round(delta/dt).toLocaleString();}
    lastSample=aircraft.stale?null:{now:aircraft.now,messages:aircraft.messages};$('metric-rate').textContent=rate;
    renderAircraft();renderServices();drawRadars();
  }catch(e){notice(`Connection interrupted: ${e.message}`,true);$('health-title').textContent='Station connection interrupted';$('health-banner').classList.add('warning');$('health-description').textContent='Live aircraft are hidden until the station reconnects.';$('health-badge').textContent='DISCONNECTED';if(aircraft)aircraft.stale=true;lastSample=null;for(const id of ['metric-aircraft','metric-position','metric-rate'])$(id).textContent='—';renderAircraft();drawRadars();}
  finally{polling=false;}
}
function rows(list,map=false){
  return list.map(a=>{const callsign=(a.flight||'').trim()||'Unknown callsign';const type=a.desc||a.t||a.category||'Type unavailable';return `<tr><td><span class="plane-icon">✈</span><strong>${escapeHTML(callsign)}</strong><small>${escapeHTML(a.hex)} · ${escapeHTML(type)}</small></td><td>${typeof a.alt_baro==='number'?a.alt_baro.toLocaleString()+' ft':escapeHTML(a.alt_baro)}</td><td>${a.gs==null?'—':escapeHTML(Math.round(a.gs))+' kt'}</td><td>${a.rssi==null?'—':escapeHTML(a.rssi)+' dBFS'}</td><td>${escapeHTML(a.seen)}s</td>${map?`<td>${Number.isFinite(a.lat)&&Number.isFinite(a.lon)&&a.seen_pos<60?`<a target="_blank" rel="noopener noreferrer" href="https://www.openstreetmap.org/?mlat=${encodeURIComponent(a.lat)}&mlon=${encodeURIComponent(a.lon)}#map=9/${encodeURIComponent(a.lat)}/${encodeURIComponent(a.lon)}">Map ↗</a>`:'—'}</td>`:''}</tr>`;}).join('')||`<tr><td class="empty" colspan="${map?6:5}">${aircraft?.stale?'Receiver data unavailable or stale.':'No aircraft heard yet. Give your antenna a clear view of the sky.'}</td></tr>`;
}
function liveAircraft(){return aircraft&&!aircraft.stale?aircraft.aircraft.filter(a=>a.seen<60):[];}
function renderAircraft(){const live=liveAircraft();$('overview-aircraft').innerHTML=rows(live.slice(0,5));const search=$('aircraft-search').value.toLowerCase();$('sky-aircraft').innerHTML=rows(live.filter(a=>`${a.flight} ${a.hex}`.toLowerCase().includes(search)),true);$('sky-caption').textContent=`${live.filter(a=>a.lat!=null&&a.seen_pos<60).length} aircraft with fresh positions`;updateAircraftMap();}
$('aircraft-search').addEventListener('input',renderAircraft);
function drawRadars(){
  for(const id of ['overview-radar','sky-radar']){
    const canvas=$(id),rect=canvas.getBoundingClientRect();if(!rect.width)continue;
    const dpr=window.devicePixelRatio||1;canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;const c=canvas.getContext('2d');c.scale(dpr,dpr);
    const w=rect.width,h=rect.height,x=w/2,y=h/2,r=Math.min(w/2-32,h/2-35);c.fillStyle='#f3f8f8';c.fillRect(0,0,w,h);
    c.strokeStyle='#dce8e9';c.lineWidth=1;for(let i=1;i<=4;i++){c.beginPath();c.arc(x,y,r*i/4,0,Math.PI*2);c.stroke();}
    c.setLineDash([3,5]);c.beginPath();c.moveTo(x,18);c.lineTo(x,h-25);c.moveTo(20,y);c.lineTo(w-20,y);c.stroke();c.setLineDash([]);
    c.fillStyle='#8ca4ad';c.font='9px system-ui';c.textAlign='center';c.fillText('N',x,15);c.fillText('50',x+8,y-r/4+10);c.fillText('100',x+8,y-r/2+10);c.fillText('200 NM',x,y+r+16);
    const center=config?.receiver; if(center?.latitude==null){c.fillStyle='#597b88';c.font='12px system-ui';c.fillText('Set receiver coordinates to plot your local sky',x,y+30);}
    else{
      for(const a of liveAircraft()){
        if(!Number.isFinite(a.lat)||!Number.isFinite(a.lon)||a.seen_pos>=60)continue;
        const rad=Math.PI/180,lat1=center.latitude*rad,lat2=a.lat*rad,dl=(a.lon-center.longitude)*rad;
        const hav=Math.sin((lat2-lat1)/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dl/2)**2;
        const distance=3440.065*2*Math.atan2(Math.sqrt(Math.min(1,hav)),Math.sqrt(Math.max(0,1-hav)));
        if(distance>200)continue;
        const bearing=Math.atan2(Math.sin(dl)*Math.cos(lat2),Math.cos(lat1)*Math.sin(lat2)-Math.sin(lat1)*Math.cos(lat2)*Math.cos(dl));
        const px=x+Math.sin(bearing)*distance/200*r,py=y-Math.cos(bearing)*distance/200*r;
        c.save();c.translate(px,py);c.rotate((a.track||0)*rad);c.beginPath();c.moveTo(0,-7);c.lineTo(3,-1);c.lineTo(8,3);c.lineTo(8,5);c.lineTo(2,3);c.lineTo(2,7);c.lineTo(-2,7);c.lineTo(-2,3);c.lineTo(-8,5);c.lineTo(-8,3);c.lineTo(-3,-1);c.closePath();c.fillStyle='#248f87';c.fill();c.restore();
        if(id==='sky-radar'){c.fillStyle='#5a7f88';c.font='8px system-ui';c.fillText((a.flight||a.hex).trim(),px,py+19);}
      }
    }
    c.beginPath();c.arc(x,y,6,0,Math.PI*2);c.fillStyle='#fff';c.fill();c.strokeStyle='#247d7c';c.stroke();c.beginPath();c.arc(x,y,2,0,Math.PI*2);c.fillStyle='#247d7c';c.fill();
  }
}
window.addEventListener('resize',drawRadars);window.addEventListener('hashchange',view);
$('receiver-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{const next=structuredClone(config);next.name=$('station-name').value;next.receiver={device:$('sdr-device').value,gain:$('sdr-gain').value==='auto'?'auto':Number($('sdr-gain').value),ppm:Number($('sdr-ppm').value),latitude:$('latitude').value===''?null:Number($('latitude').value),longitude:$('longitude').value===''?null:Number($('longitude').value),lan_output:$('lan-output').checked};await saveConfig(next);notice('Receiver settings saved. Check service health after the restart.');});});
async function saveConfig(next){await api('config',next);await loadConfig();await refresh();}
function renderFeeds(){
  $('feeder-list').innerHTML=config.feeders.map(f=>`<div class="feed-row"><div><strong>${escapeHTML(f.id)}</strong><small>${escapeHTML(f.host)}:${f.port}</small></div><span class="pill ${f.enabled?'mint':''}">${f.enabled?'ENABLED':'DISABLED'}</span><button data-feed="${f.id}" data-feed-action="toggle">${f.enabled?'Disable':'Enable'}</button><button data-feed="${f.id}" data-feed-action="remove">Remove</button></div>`).join('')||'<p class="footnote">No feed destinations. Your data stays on your station.</p>';
  const selected=$('log-unit').value;$('log-unit').innerHTML='<option value="airnode-receiver">Receiver</option><option value="airnode-update">OS updates</option>'+config.feeders.map(f=>`<option value="airnode-feeder@${f.id}">Feed · ${f.id}</option>`).join('');if([...$('log-unit').options].some(o=>o.value===selected))$('log-unit').value=selected;
}
function renderServices(){ $('service-list').innerHTML=Object.entries(status.services).map(([name,s])=>`<div class="service-row"><div><strong>${escapeHTML(name.replace('airnode-',''))}</strong><small>${escapeHTML(s.SubState)}</small></div><span class="pill ${s.ActiveState==='active'?'mint':'amber'}">${escapeHTML(s.ActiveState)}</span><div class="actions"><button data-service="${escapeHTML(name)}" data-action="start">Start</button><button data-service="${escapeHTML(name)}" data-action="stop">Stop</button><button data-service="${escapeHTML(name)}" data-action="restart">Restart</button></div></div>`).join('')||'<p>Service status unavailable.</p>'; }
$('feeder-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{const next=structuredClone(config);next.feeders.push({id:$('feed-id').value,host:$('feed-host').value,port:Number($('feed-port').value),enabled:false});await saveConfig(next);$('feeder-form').reset();notice('Destination added. Enable it when you are ready to share.');});});
document.addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.service)action(async()=>{await api('service',{unit:b.dataset.service,action:b.dataset.action});await refresh();notice('Service action completed.');});
  if(b.dataset.feed)action(async()=>{const next=structuredClone(config),f=next.feeders.find(f=>f.id===b.dataset.feed);if(b.dataset.feedAction==='remove'){if(!confirm(`Remove destination ${f.id}?`))return;next.feeders=next.feeders.filter(x=>x.id!==f.id);}else{if(!f.enabled&&!confirm(`Send raw aircraft data to ${f.host}:${f.port}?`))return;f.enabled=!f.enabled;}await saveConfig(next);notice('Feed settings applied.');});
  if(b.dataset.power)ask('power',{action:b.dataset.power},b.dataset.power==='reboot'?'Reboot your station?':'Shut down your station?','This will disconnect the station in one minute.');
});
$('hostname-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{const result=await api('hostname',{hostname:$('hostname').value});notice(result.message||'Hostname updated.');});});
$('password-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{await api('password',{current:$('current-password').value,password:$('new-password').value});$('password-form').reset();csrf='';await boot();});});
function ask(path,data,title,description){confirmation={path,data};$('confirm-title').textContent=title;$('confirm-description').textContent=description;$('confirm-password').value='';$('confirm-error').textContent='';$('confirm-dialog').showModal();}
$('update-button').addEventListener('click',()=>ask('update',{},'Install operating system updates?','This uses the configured signed package repositories. Keep the station powered on and follow the update log.'));
$('confirm-cancel').addEventListener('click',()=>$('confirm-dialog').close());
$('confirm-form').addEventListener('submit',async e=>{e.preventDefault();try{const result=await api(confirmation.path,{...confirmation.data,password:$('confirm-password').value});$('confirm-dialog').close();notice(result.message||'Action accepted.');$('confirm-password').value='';await refresh();}catch(err){$('confirm-error').textContent=err.message;}});
async function loadLogs(){const data=await api('logs?unit='+encodeURIComponent($('log-unit').value));$('log-output').textContent=data.text||'No journal entries yet.';}
$('refresh-logs').addEventListener('click',()=>action(loadLogs));$('log-unit').addEventListener('change',()=>action(loadLogs));$('update-log-link').addEventListener('click',()=>{$('log-unit').value='airnode-update';action(loadLogs);});
async function loadAggregators(){
  if(aggregatorPolling)return;aggregatorPolling=true;
  try{const data=await api('aggregators');providers=data.providers;renderAggregators();}
  finally{aggregatorPolling=false;}
}
function renderAggregators(){
  $('aggregator-enabled').textContent=providers.filter(p=>p.enabled).length;
  $('aggregator-cards').innerHTML=providers.map(p=>`<article class="card aggregator-card" data-provider-card="${p.id}">
    <div class="aggregator-top"><div class="provider-mark provider-${p.id}">${escapeHTML(p.mark)}</div><span class="pill ${p.enabled?'mint':!p.installed?'amber':''}">${escapeHTML(p.state)}</span></div>
    <h2>${escapeHTML(p.name)}</h2><p class="provider-description">${escapeHTML(p.description)}</p>
    <div class="provider-meta"><span>${p.kind==='readsb'?'AirNode feed client':'Local '+(p.id==='flightaware'?'PiAware':'FR24')+' client'}</span><span>${p.demo?'DEMO':p.installed?'Installed':'Installation needed'}</span></div>
    <p class="provider-state">${escapeHTML(p.detail)}</p>
    <div class="provider-links"><a href="${escapeHTML(p.setup_url)}" target="_blank" rel="noopener noreferrer">${p.kind==='native'?'Account / registration':'Provider guide'} ↗</a><a href="${escapeHTML(p.status_url)}" target="_blank" rel="noopener noreferrer">Provider status ↗</a>${p.claim_url?`<a href="${escapeHTML(p.claim_url)}" target="_blank" rel="noopener noreferrer">Claim receiver ↗</a>`:''}</div>
    <div class="aggregator-actions"><button class="primary" data-aggregator="${p.id}" data-aggregator-action="configure">${p.configured?'Settings':'Set up'}</button>${p.enabled?`<button data-aggregator="${p.id}" data-aggregator-action="disable">Disable</button><button data-aggregator="${p.id}" data-aggregator-action="restart">Restart</button>`:''}<button data-aggregator="${p.id}" data-aggregator-action="logs">Logs</button></div>
    <div class="software-panel"><div class="software-heading"><strong>Feeder software</strong><span class="pill ${p.software?.result==='Failed'?'amber':''}">${escapeHTML(p.software?.result||'Ready')}</span></div>
    <p>${p.kind==='readsb'?'Included with AirNode. Checks use the version approved for this AirNode release.':'AirNode installs the official client and its dependencies on this Pi.'}</p>
    <small>${p.software?.version?'Version '+escapeHTML(p.software.version):'Not installed'} · ${p.software?.automatic?'Daily updates on':'Daily updates off'}</small>
    <div class="aggregator-actions"><button data-aggregator="${p.id}" data-aggregator-action="${p.installed?'update':'install'}" ${p.software?.busy?'disabled':''}>${p.software?.busy?'Working…':p.installed?'Check & update':'Install software'}</button><button data-aggregator="${p.id}" data-aggregator-action="${p.software?.automatic?'auto-off':'auto-on'}" ${!p.installed||p.software?.busy?'disabled':''}>${p.software?.automatic?'Turn off daily updates':'Keep updated daily'}</button><button data-aggregator="${p.id}" data-aggregator-action="install-logs">Installation log</button></div></div>
    ${p.credential_set?`<small class="credential-stored">${p.id==='flightradar24'?'Sharing key saved privately on this Pi':'Station identifier saved on this Pi'}</small>`:''}
  </article>`).join('');
}
function configureAggregator(p){
  selectedProvider=p;$('aggregator-title').textContent=`Connect ${p.name}`;$('aggregator-description').textContent=p.description;
  $('aggregator-credential-label').textContent=p.credential_label;$('aggregator-credential').type=p.id==='flightradar24'?'password':'text';
  $('aggregator-credential').value=p.identifier||'';$('aggregator-credential').placeholder=p.id==='flightradar24'?(p.credential_set?'Saved key — leave blank to keep':'16-character sharing key'):'Leave blank for a new station';
  $('aggregator-credential-help').textContent=p.kind==='readsb'?'A unique station UUID is generated locally if left blank. Keep it when reinstalling to preserve your provider identity.':p.id==='flightaware'?'For a new site, leave blank: PiAware registers its own ID. For an existing site, paste its feeder UUID. Claim the receiver on FlightAware after it connects.':p.credential_set?'Your saved key is never returned to this browser. Leave blank to keep it, or enter a replacement.':'Obtain your sharing key from Flightradar24. It is stored on this Pi and used only by the local FR24 client.';
  $('aggregator-requirement').textContent=p.demo?'Demo mode: every action is simulated. No provider receives data.':p.kind==='readsb'?'Uses the included readsb client. It reads your local receiver and opens an outbound connection; LAN raw-feed sharing can stay off.':p.installed?'Installed client detected. Enabling configures it for AirNode’s local receiver, disables MLAT and starts it. Existing provider configuration is backed up before the first change.':'Close this form and choose Install software. AirNode prepares the official client on your Pi. Return here to enable sharing after installation finishes. Account registration remains with the provider.';
  $('aggregator-sharing').checked=p.enabled;$('aggregator-sharing').disabled=!p.installed;
  $('aggregator-consent').checked=false;$('aggregator-error').textContent='';syncAggregatorConsent();$('aggregator-dialog').showModal();
}
function syncAggregatorConsent(){const on=$('aggregator-sharing').checked;$('aggregator-consent-label').hidden=!on;$('aggregator-consent').required=on;}
$('aggregator-sharing').addEventListener('change',syncAggregatorConsent);
$('aggregator-cancel').addEventListener('click',()=>$('aggregator-dialog').close());
$('aggregator-log-close').addEventListener('click',()=>$('aggregator-log-dialog').close());
$('refresh-aggregators').addEventListener('click',()=>action(loadAggregators));
document.addEventListener('click',e=>{
  const b=e.target.closest('button[data-aggregator]');if(!b)return;
  const p=providers.find(p=>p.id===b.dataset.aggregator);if(!p)return;
  if(b.dataset.aggregatorAction==='configure'){configureAggregator(p);return;}
  action(async()=>{b.disabled=true;try{
    if(['logs','install-logs'].includes(b.dataset.aggregatorAction)){
      const data=await api('aggregators/action',{provider:p.id,action:'logs'});$('aggregator-log-title').textContent=p.name+' · Local log';$('aggregator-log-output').textContent=data.text||'No journal entries yet.';$('aggregator-log-dialog').showModal();
    }else{
      const result=b.dataset.aggregatorAction==='disable'?await api('aggregators/config',{provider:p.id,enabled:false}):await api('aggregators/action',{provider:p.id,action:b.dataset.aggregatorAction});
      notice(result.message);await loadAggregators();
    }
  }finally{b.disabled=false;}});
});
$('aggregator-form').addEventListener('submit',async e=>{
  e.preventDefault();$('aggregator-save').disabled=true;
  try{const result=await api('aggregators/config',{provider:selectedProvider.id,enabled:$('aggregator-sharing').checked,credential:$('aggregator-credential').value.trim(),consent:$('aggregator-consent').checked});
    $('aggregator-credential').value='';$('aggregator-dialog').close();notice(result.message);await loadAggregators();
  }catch(e){$('aggregator-error').textContent=e.message;}
  finally{$('aggregator-save').disabled=false;}
});
setInterval(()=>{if(csrf&&!$('shell').hidden&&location.hash==='#aggregators')action(loadAggregators);},10000);
async function loadDeviceSetup(){
  const [wifi,release]=await Promise.all([api('wifi'),api('releases')]);
  $('wifi-state').textContent=wifi.message+(wifi.hotspot?' Network: '+wifi.hotspot_ssid+' · '+wifi.setup_url:'');
  $('wifi-networks').innerHTML=(wifi.networks||[]).map(n=>`<option value="${escapeHTML(n.ssid)}">${escapeHTML(n.signal)}% · ${escapeHTML(n.security)}</option>`).join('');
  $('wifi-connect').disabled=!wifi.available;
  if(document.activeElement!==$('release-channel'))$('release-channel').value=release.channel;
  $('release-state').textContent=`${release.state} · Installed ${release.current}. ${release.message}`;
  $('release-install').disabled=release.state!=='Available'&&!release.demo;
}
$('wifi-refresh').addEventListener('click',()=>action(loadDeviceSetup));
$('wifi-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  const result=await api('wifi/connect',{ssid:$('wifi-ssid').value,password:$('wifi-password').value,country:$('wifi-country').value.toUpperCase()});
  $('wifi-password').value='';notice(result.message);
});});
$('release-check').addEventListener('click',()=>action(async()=>{notice((await api('releases/action',{action:'check'})).message);await loadDeviceSetup();}));
$('release-channel').addEventListener('change',()=>action(async()=>{notice((await api('releases/action',{action:'channel',channel:$('release-channel').value})).message);await loadDeviceSetup();}));
$('release-install').addEventListener('click',()=>ask('releases/action',{action:'install'},'Install AirNode update?','This installs a signed GitHub release on your Pi. Keep it powered on. The dashboard briefly disconnects.'));
setInterval(()=>{if(csrf&&!$('shell').hidden&&location.hash==='#system')action(loadDeviceSetup);},10000);
setInterval(refresh,5000);boot();
