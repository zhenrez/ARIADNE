"""Local ARIADNE control center and read-only progress projections."""
import json
from .acquisition import pointers, queue_manifest

ATTENTION = (
    "AUTH_REQUIRED",
    "PAYWALLED",
    "ROBOTS_BLOCKED",
    "UNSUPPORTED_FORMAT",
    "BANKED_DEPTH",
    "STORAGE_DEFERRED",
)


def submit_manifest(con, text):
    if not isinstance(text, str):
        raise ValueError("Paste a resource list as text")
    before = con.execute("SELECT COUNT(*) FROM acquisition_jobs").fetchone()[0]
    detected = len(pointers(text))
    queue_manifest(con, text)
    added = con.execute("SELECT COUNT(*) FROM acquisition_jobs").fetchone()[0] - before
    return dict(queued=added, detected=detected, existing=detected-added)


def progress_summary(con):
    """Counts describe persisted work, never a percentage of total knowledge."""
    counts = {r[0]: r[1] for r in con.execute(
        "SELECT status,COUNT(*) FROM acquisition_jobs GROUP BY status"
    )}
    sources = con.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    indexed = con.execute(
        """SELECT COUNT(DISTINCT p.source_id)
           FROM passages p JOIN sources s USING(source_id)
           WHERE s.text_extracted=1"""
    ).fetchone()[0]
    gaps = con.execute("SELECT COUNT(*) FROM sources WHERE text_extracted=0").fetchone()[0]
    pending = con.execute(
        """SELECT COUNT(*) FROM acquisition_jobs
           WHERE status='QUEUED' OR (status='FETCH_FAILED' AND attempts<3)"""
    ).fetchone()[0]
    failed = con.execute(
        """SELECT COUNT(*) FROM acquisition_jobs
           WHERE status='FETCH_FAILED' AND attempts>=3"""
    ).fetchone()[0]
    attention_jobs = failed + sum(counts.get(s, 0) for s in ATTENTION)
    jobs = []
    for r in con.execute(
        """SELECT url,status,attempts,detail FROM acquisition_jobs
           WHERE status IN ('FETCH_FAILED','AUTH_REQUIRED','PAYWALLED','ROBOTS_BLOCKED',
                            'UNSUPPORTED_FORMAT','BANKED_DEPTH','STORAGE_DEFERRED')
           ORDER BY CASE WHEN status='FETCH_FAILED' AND attempts<3 THEN 1 ELSE 0 END,
                    rowid DESC LIMIT 8"""
    ):
        try:
            detail = json.loads(r["detail"])
        except (ValueError, TypeError):
            detail = {}
        if not isinstance(detail, dict):
            detail = {}
        jobs.append(
            dict(
                url=r["url"],
                status=r["status"],
                attempts=r["attempts"],
                reason=detail.get("error") or detail.get("reason") or "",
                retrying=r["status"] == "FETCH_FAILED" and r["attempts"] < 3,
            )
        )
    recent = [
        dict(r)
        for r in con.execute(
            """SELECT s.original_name,s.text_extracted,s.source_id,
                      (s.text_extracted=1 AND EXISTS(
                         SELECT 1 FROM passages p WHERE p.source_id=s.source_id
                       )) AS indexed
               FROM sources s ORDER BY s.created_at DESC,s.rowid DESC LIMIT 8"""
        )
    ]
    return dict(
        sources=sources,
        indexed=indexed,
        extraction_gaps=gaps,
        queued=pending,
        attention_jobs=attention_jobs,
        acquired=sum(
            counts.get(s, 0)
            for s in ("CUSTODIED", "EXTRACTED", "NORMALIZED", "INDEXED", "LINKED", "UNSUPPORTED_FORMAT")
        ),
        linked=counts.get("LINKED", 0),
        total_pointers=sum(counts.values()),
        statuses=counts,
        jobs=jobs,
        recent=recent,
        findings=con.execute("SELECT COUNT(*) FROM active_findings").fetchone()[0],
        revision=con.execute("SELECT COALESCE(MAX(revision),0) FROM state_versions").fetchone()[0],
    )


PAGE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARIADNE · Control Center</title>
<style>
:root{color-scheme:dark;--bg:#10151c;--panel:#18212b;--panel2:#202b37;--line:#3a4a5a;--text:#edf3f8;--muted:#aebdca;--accent:#9fe0c8;--warn:#f2c078;--bad:#f19a9a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,Segoe UI,sans-serif}
main{max-width:1180px;margin:26px auto;padding:0 18px 40px}
header{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}
h1{margin:0;font-size:25px;letter-spacing:.08em}
h2{font-size:17px;margin:0 0 12px}
h3{font-size:14px;margin:0 0 8px}
.muted,small{color:var(--muted)}
.status{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.pill{border:1px solid var(--line);border-radius:999px;padding:5px 9px;font-size:12px;background:var(--panel)}
.pill.good{color:var(--accent)}.pill.warn{color:var(--warn)}.pill.bad{color:var(--bad)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:16px}
.controlbar{display:flex;gap:8px;flex-wrap:wrap}
button,select,input,textarea{font:inherit}
button{min-height:42px;border-radius:8px;border:1px solid var(--line);padding:8px 12px;background:var(--panel2);color:var(--text);cursor:pointer}
button.primary{background:var(--accent);color:#10271f;border-color:transparent}
button.warn{color:#2b210d;background:var(--warn);border-color:transparent}
button.danger{color:#2a1111;background:var(--bad);border-color:transparent}
button:disabled{opacity:.45;cursor:not-allowed}
button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,a:focus-visible{outline:3px solid #ffe4a2;outline-offset:3px}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.card{background:var(--panel2);padding:12px;border-radius:8px;min-width:0}.card strong{display:block;font-size:24px}.card span{font-size:12px;color:var(--muted)}
.storage-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:16px}
.meter{height:12px;background:#0c1117;border-radius:999px;overflow:hidden;border:1px solid var(--line);margin:8px 0}.meter>span{display:block;height:100%;background:var(--accent);width:0}
.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
label{display:block;color:var(--muted);font-size:13px}label input,label select{display:block;width:100%;margin-top:5px}
input,select,textarea{background:#0f161e;color:var(--text);border:1px solid var(--line);border-radius:7px;padding:9px;min-height:42px}
textarea{width:100%;min-height:94px;resize:vertical}
.drop{display:block;width:100%;border:1px dashed var(--accent);background:var(--panel2);color:var(--text);border-radius:10px;padding:20px;margin:10px 0;cursor:pointer;text-align:left}.drop.over{background:#253b39}
.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:9px}
a{color:var(--accent)}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:10px}
table{border-collapse:collapse;width:100%;min-width:760px;background:var(--panel2)}
th,td{text-align:left;vertical-align:top;padding:9px 10px;border-bottom:1px solid var(--line)}
th{position:sticky;top:0;background:#252f3a;font-size:12px;color:var(--muted)}
td{font-size:13px;overflow-wrap:anywhere}.row-actions{display:flex;gap:6px;flex-wrap:wrap}.row-actions button{min-height:34px;padding:5px 8px;font-size:12px}
.notice{border-left:4px solid var(--warn);padding:10px 12px;background:var(--panel2);margin-top:10px;white-space:pre-wrap}
.danger-note{border-left-color:var(--bad)}
details{margin-top:12px}summary{cursor:pointer}
@media(max-width:760px){.grid4{grid-template-columns:repeat(2,minmax(0,1fr))}.storage-grid,.formgrid{grid-template-columns:1fr}}
@media(max-width:420px){main{padding:0 12px 30px}.grid4{grid-template-columns:1fr 1fr}.controlbar button{flex:1 1 46%}}
</style>
</head>
<body>
<main>
<header>
  <div><h1>ARIADNE</h1><div class="muted">Local research control center</div></div>
  <div class="status"><span id="worker" class="pill">Connecting…</span><span id="downloads" class="pill">Downloads…</span></div>
</header>

<section class="panel">
  <h2>Runtime controls</h2>
  <div class="controlbar">
    <button id="pause">Pause Warden</button>
    <button id="resume">Resume Warden</button>
    <button id="pauseDownloads">Pause downloads</button>
    <button id="resumeDownloads">Resume downloads</button>
    <button id="stop" class="danger">Stop ARIADNE</button>
  </div>
  <div id="controlMessage" class="notice" hidden></div>
</section>

<section class="panel">
  <div class="grid4">
    <div class="card"><strong id="queued">—</strong><span>Queued links</span></div>
    <div class="card"><strong id="sources">—</strong><span>Sources recorded</span></div>
    <div class="card"><strong id="indexed">—</strong><span>Sources indexed</span></div>
    <div class="card"><strong id="findings">—</strong><span>Candidate findings</span></div>
  </div>
  <p id="progress" class="muted">Waiting for status.</p>
  <a href="/report" target="_blank" rel="noopener">View findings ↗</a>
</section>

<section class="panel">
  <h2>Storage governor</h2>
  <div class="storage-grid">
    <div>
      <div id="storageText">Calculating storage…</div>
      <div class="meter" aria-label="ARIADNE storage budget"><span id="storageMeter"></span></div>
      <div id="diskText" class="muted"></div>
      <div id="storageBreakdown" class="muted"></div>
      <div id="storageWarning" class="notice danger-note" hidden></div>
    </div>
    <div>
      <div class="formgrid">
        <label>Acquisition mode
          <select id="mode">
            <option value="metadata_first">Metadata first</option>
            <option value="selective">Selective</option>
            <option value="full">Full</option>
          </select>
        </label>
        <label>ARIADNE data budget (GB)
          <input id="budgetGb" inputmode="decimal" value="1">
        </label>
        <label>Keep free on drive (GB)
          <input id="reserveGb" inputmode="decimal" value="5">
        </label>
        <label style="display:flex;align-items:center;gap:8px;margin-top:21px;color:var(--text)">
          <input id="autoEvict" type="checkbox" style="width:auto;min-height:auto"> Auto-evict parsed G0 originals
        </label>
      </div>
      <div class="actions">
        <button id="saveStorage" class="primary">Save storage policy</button>
        <button data-clean="staging">Clear staging</button>
        <button data-clean="backups">Prune old backups</button>
        <button data-clean="snapshots">Prune old snapshots</button>
      </div>
    </div>
  </div>
</section>

<section class="panel">
  <h2>Add research material</h2>
  <button id="drop" class="drop" type="button"><strong>Drop files here</strong><br><span class="muted">or click to choose files</span></button>
  <input id="files" type="file" multiple hidden>
  <label for="manifest">Paste links, DOI/arXiv references, or a resource list</label>
  <textarea id="manifest"></textarea>
  <div class="actions"><button id="acquire" class="primary">Queue resources</button><span id="message" class="muted"></span></div>
</section>

<section class="panel">
  <h2>Acquisition queue</h2>
  <div class="tablewrap">
    <table><thead><tr><th>Status</th><th>URL</th><th>Reason</th><th>Controls</th></tr></thead><tbody id="queueBody"></tbody></table>
  </div>
</section>

<section class="panel">
  <h2>Stored sources</h2>
  <p class="muted">Evict removes the local original only. The source identity, hash, provenance, extracted passages and graph state remain. ARIADNE refuses eviction when a source is not safely reacquirable.</p>
  <div class="tablewrap">
    <table><thead><tr><th>Source</th><th>Size</th><th>Lane</th><th>Storage</th><th>Origin</th><th>Controls</th></tr></thead><tbody id="sourceBody"></tbody></table>
  </div>
</section>

<details class="panel">
  <summary>Needs attention</summary>
  <ul id="problems"></ul>
</details>
<p id="updated" class="muted"></p>
</main>

<script>
const token='__TOKEN__', $=id=>document.getElementById(id);
let uploading=false, refreshing=false, stopped=false;

function bytes(n){
  n=Number(n)||0;
  const units=['B','KB','MB','GB','TB']; let i=0;
  while(n>=1024&&i<units.length-1){n/=1024;i++}
  return (i? n.toFixed(n>=10?1:2):Math.round(n))+' '+units[i];
}
function gbToBytes(v){
  const n=Number(v);
  if(!Number.isFinite(n)||n<0)throw Error('Storage values must be non-negative numbers.');
  return Math.round(n*1024*1024*1024);
}
async function post(path,data){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-ARIADNE-Token':token},body:JSON.stringify(data)});
  const out=await r.json().catch(()=>({error:'Request failed'}));
  if(!r.ok)throw Error(out.error||'Request failed');
  return out;
}
function controlNotice(text,bad=false){
  const n=$('controlMessage');n.hidden=!text;n.textContent=text||'';n.classList.toggle('danger-note',!!bad);
}
async function action(path,data,msg){
  try{const r=await post(path,data);if(msg)controlNotice(msg);await refresh();return r}
  catch(e){controlNotice(e.message,true);throw e}
}
$('pause').onclick=()=>action('/api/control',{action:'pause'},'Warden paused.');
$('resume').onclick=()=>action('/api/control',{action:'resume'},'Warden resumed.');
$('pauseDownloads').onclick=()=>action('/api/control',{action:'pause_downloads'},'Network acquisition paused.');
$('resumeDownloads').onclick=()=>action('/api/control',{action:'resume_downloads'},'Network acquisition resumed.');
$('stop').onclick=async()=>{
  if(!confirm('Stop ARIADNE and its Warden worker cleanly?'))return;
  try{await post('/api/control',{action:'stop'});stopped=true;$('worker').textContent='Stopping…';controlNotice('ARIADNE is stopping. You may close this tab when it disconnects.')}
  catch(e){controlNotice(e.message,true)}
};

$('saveStorage').onclick=async()=>{
  try{
    await action('/api/storage/settings',{
      mode:$('mode').value,
      local_budget_bytes:gbToBytes($('budgetGb').value),
      free_space_reserve_bytes:gbToBytes($('reserveGb').value),
      auto_evict_g0_originals:$('autoEvict').checked
    },'Storage policy saved.');
  }catch(e){}
};
document.querySelectorAll('[data-clean]').forEach(b=>b.addEventListener('click',async()=>{
  try{const r=await post('/api/cleanup',{kind:b.dataset.clean});controlNotice('Cleanup freed '+bytes(r.freed_bytes)+' from '+r.removed_files+' files.');refresh()}
  catch(e){controlNotice(e.message,true)}
}));

async function upload(files,lane='AUTO'){
  if(uploading)return;
  const batch=Array.from(files);if(!batch.length)return;
  uploading=true;$('drop').disabled=true;let saved=0;const failures=[];
  try{
    for(const [i,file] of batch.entries()){
      $('message').textContent='Uploading '+(i+1)+' of '+batch.length+': '+file.name;
      try{
        if(file.size>25*1024*1024)throw Error('exceeds 25 MiB');
        const bytesArr=new Uint8Array(await file.arrayBuffer());let raw='';
        for(let j=0;j<bytesArr.length;j+=8192)raw+=String.fromCharCode(...bytesArr.subarray(j,j+8192));
        await post('/api/upload',{name:file.name,data:btoa(raw),lane});saved++;
      }catch(e){failures.push(file.name+': '+e.message)}
    }
    $('message').textContent=saved+' of '+batch.length+' files queued.'+(failures.length?' '+failures.join(' | '):'');
  }finally{uploading=false;$('drop').disabled=false;$('files').value='';refresh()}
}
$('drop').onclick=()=> $('files').click();
$('files').onchange=e=>upload(e.target.files);
const drop=$('drop');
drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');if(e.dataTransfer.files.length){upload(e.dataTransfer.files);return}const t=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');if(t)$('manifest').value=t};
$('acquire').onclick=async()=>{
  const text=$('manifest').value.trim();if(!text){$('message').textContent='Paste at least one resource first.';return}
  try{const r=await post('/api/acquire',{text});$('message').textContent=r.queued+' new links queued; '+r.existing+' already known.';refresh()}
  catch(e){$('message').textContent=e.message}
};

async function queueAction(job,act){try{await post('/api/queue',{job_id:job,action:act});refresh()}catch(e){controlNotice(e.message,true)}}
async function sourceAction(source,act){try{await post('/api/source',{source_id:source,action:act});refresh()}catch(e){controlNotice(e.message,true)}}

function renderQueue(rows){
  const body=$('queueBody');body.replaceChildren();
  if(!rows.length){const tr=document.createElement('tr');tr.innerHTML='<td colspan="4" class="muted">No queued or blocked acquisitions.</td>';body.append(tr);return}
  for(const q of rows){
    const tr=document.createElement('tr');
    const s=document.createElement('td');s.textContent=q.status;tr.append(s);
    const u=document.createElement('td');u.textContent=q.url;tr.append(u);
    const r=document.createElement('td');r.textContent=q.reason||'';tr.append(r);
    const a=document.createElement('td');a.className='row-actions';
    if(['QUEUED','FETCH_FAILED','STORAGE_DEFERRED'].includes(q.status)){const b=document.createElement('button');b.textContent='Cancel';b.onclick=()=>queueAction(q.job_id,'cancel');a.append(b)}
    if(q.status!=='QUEUED'){const b=document.createElement('button');b.textContent='Retry';b.onclick=()=>queueAction(q.job_id,'retry');a.append(b)}
    tr.append(a);body.append(tr);
  }
}
function renderSources(rows){
  const body=$('sourceBody');body.replaceChildren();
  if(!rows.length){const tr=document.createElement('tr');tr.innerHTML='<td colspan="6" class="muted">No sources recorded yet.</td>';body.append(tr);return}
  for(const s of rows){
    const tr=document.createElement('tr');
    const n=document.createElement('td');n.textContent=s.original_name+' · '+s.source_id;tr.append(n);
    const z=document.createElement('td');z.textContent=bytes(s.byte_size);tr.append(z);
    const l=document.createElement('td');l.textContent=s.lane;tr.append(l);
    const st=document.createElement('td');st.textContent=s.state+(s.pinned?' · PINNED':'');tr.append(st);
    const o=document.createElement('td');o.textContent=s.url||'local/user file';tr.append(o);
    const a=document.createElement('td');a.className='row-actions';
    const pin=document.createElement('button');pin.textContent=s.pinned?'Unpin':'Pin';pin.onclick=()=>sourceAction(s.source_id,s.pinned?'unpin':'pin');a.append(pin);
    const ev=document.createElement('button');ev.textContent='Evict original';ev.disabled=s.state!=='PRESENT'||s.pinned||(!s.reacquirable&&s.lane!=='G0');ev.title=ev.disabled?'Pinned or not safely reacquirable':'';ev.onclick=()=>sourceAction(s.source_id,'evict');a.append(ev);
    tr.append(a);body.append(tr);
  }
}

async function refresh(){
  if(refreshing||stopped)return;refreshing=true;
  try{
    const r=await fetch('/api/status');if(!r.ok)throw Error('Status unavailable');
    const d=await r.json(),p=d.progress,w=d.worker,st=d.storage,pol=d.storage_policy;
    $('worker').textContent=w.status||'UNKNOWN';$('worker').className='pill '+(w.status==='WAITING'?'good':w.status==='PAUSED'?'warn':w.status==='ERROR_RETRY'?'bad':'');
    $('downloads').textContent=w.downloads_paused?'Downloads paused':'Downloads active';$('downloads').className='pill '+(w.downloads_paused?'warn':'good');
    $('pause').disabled=!!w.paused;$('resume').disabled=!w.paused;$('pauseDownloads').disabled=!!w.downloads_paused;$('resumeDownloads').disabled=!w.downloads_paused;
    $('queued').textContent=p.queued;$('sources').textContent=p.sources;$('indexed').textContent=p.indexed;$('findings').textContent=p.findings;
    $('progress').textContent=p.acquired+' of '+p.total_pointers+' known pointers acquired · '+p.linked+' linked. Counts are recorded work, not total knowledge coverage.';

    const pct=st.budget_bytes?Math.min(100,(st.research_bytes/st.budget_bytes)*100):100;
    $('storageMeter').style.width=pct+'%';
    $('storageText').textContent=bytes(st.research_bytes)+' research data used of '+bytes(st.budget_bytes)+' budget · '+bytes(st.headroom_bytes)+' permitted headroom';
    $('diskText').textContent=bytes(st.disk_free_bytes)+' drive free · ARIADNE preserves at least '+bytes(st.reserve_bytes)+' free';
    $('storageBreakdown').textContent='DB '+bytes(st.categories.database)+' · custody '+bytes(st.categories.custody)+' · inbox '+bytes(st.categories.inbox)+' · artifacts '+bytes(st.categories.artifacts)+' · venv '+bytes(st.categories.venv);
    const warning=$('storageWarning');warning.hidden=st.downloads_allowed;warning.textContent=st.downloads_allowed?'':'New network acquisition is blocked by the storage budget or free-space reserve.';
    $('mode').value=pol.mode;$('budgetGb').value=(pol.local_budget_bytes/1073741824).toFixed(2).replace(/\.00$/,'');$('reserveGb').value=(pol.free_space_reserve_bytes/1073741824).toFixed(2).replace(/\.00$/,'');$('autoEvict').checked=!!pol.auto_evict_g0_originals;

    renderQueue(d.queue||[]);renderSources(d.sources||[]);
    const problems=$('problems');problems.replaceChildren();
    for(const job of p.jobs||[]){const li=document.createElement('li');li.textContent=job.status+' · '+job.url+(job.reason?' · '+job.reason:'');problems.append(li)}
    if(p.extraction_gaps){const li=document.createElement('li');li.textContent=p.extraction_gaps+' preserved sources have extraction gaps.';problems.append(li)}
    $('updated').textContent='Updated '+new Date().toLocaleTimeString()+' · state revision '+p.revision;
  }catch(e){
    $('worker').textContent=stopped?'Stopped':'Connection lost';$('worker').className='pill bad';$('updated').textContent=e.message;
  }finally{refreshing=false}
}
refresh();setInterval(refresh,5000);
</script>
</body>
</html>'''
