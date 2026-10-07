const keyInput=document.querySelector('#api-key');
const headers=()=>{const value=keyInput.value.trim();return value?{'Authorization':`Bearer ${value}`}:{}};
async function api(path,options={}){const response=await fetch(path,{...options,headers:{...headers(),'Content-Type':'application/json',...(options.headers||{})}});if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||`Request failed (${response.status})`)}return response.status===204?null:response.json()}
function date(value){return value?new Date(value).toLocaleString():'—'}
async function refresh(){
  const summary=await api('/api/v1/dashboard/summary');
  const counts=summary.runs_by_status||{};
  document.querySelector('#metrics').innerHTML=[summary.total_runs,counts.queued||0,counts.completed||0,counts.failed||0,summary.active_schedules].map((value,index)=>`<article><strong>${value}</strong><span>${['All runs','Queued','Completed','Failed','Schedules'][index]}</span></article>`).join('');
  const rows=summary.recent_runs||[];
  document.querySelector('#runs').innerHTML=rows.length?rows.map(run=>{
    const active=run.status==='queued'||run.status==='running';
    const actions=active
      ? '<span class="action-muted">In progress</span>'
      : `<a class="action-link" href="/api/v1/dashboard/runs/${run.id}">View</a>
         <button class="table-action" data-rerun="${run.id}" title="Run this repository again">Reanalyze</button>
         <button class="table-action danger" data-delete-run="${run.id}" title="Delete this run">Delete</button>`;
    return `<tr>
      <td><a href="${run.repository_url}" target="_blank" rel="noopener">${run.repository_url.replace('https://github.com/','')}</a></td>
      <td><span class="pill">${run.status}</span></td>
      <td>${run.outcome||'—'}</td>
      <td>${date(run.created_at)}</td>
      <td><a href="/api/v1/dashboard/runs/${run.id}">${run.id.slice(0,8)}…</a></td>
      <td class="run-actions">${actions}</td>
    </tr>`;
  }).join(''):'<tr><td colspan="6">No runs yet. Queue your first repository check above.</td></tr>';
  const schedules=await api('/api/v1/schedules');
  document.querySelector('#schedules').innerHTML=schedules.length?schedules.map(item=>`<div class="schedule-row"><span>${item.repository_url} · every ${item.interval_minutes} min · next ${date(item.next_run_at)}</span><button class="delete" data-delete="${item.id}">Remove</button></div>`).join(''):'No recurring checks configured.';
}
document.querySelector('#refresh').addEventListener('click',()=>refresh().catch(showError));
document.querySelector('#run-form').addEventListener('submit',async event=>{event.preventDefault();const message=document.querySelector('#message');message.textContent='Queueing…';try{const result=await api('/api/v1/test-runs',{method:'POST',body:JSON.stringify({repository_url:document.querySelector('#repository').value})});message.textContent=`Run ${result.id} queued.`;event.target.reset();await refresh()}catch(error){message.textContent=error.message}});
document.querySelector('#schedule-form').addEventListener('submit',async event=>{event.preventDefault();try{await api('/api/v1/schedules',{method:'POST',body:JSON.stringify({repository_url:document.querySelector('#schedule-repository').value,interval_minutes:Number(document.querySelector('#interval').value)})});event.target.reset();await refresh()}catch(error){showError(error)}});
document.querySelector('#schedules').addEventListener('click',async event=>{const id=event.target.dataset.delete;if(id){try{await api(`/api/v1/schedules/${id}`,{method:'DELETE'});await refresh()}catch(error){showError(error)}}});
document.querySelector('#runs').addEventListener('click',async event=>{
  const rerunId=event.target.dataset.rerun;
  const deleteId=event.target.dataset.deleteRun;
  if(rerunId){
    if(!confirm('Reanalyze this repository now?')) return;
    try{const result=await api(`/api/v1/dashboard/runs/${rerunId}/rerun`,{method:'POST'});document.querySelector('#message').textContent=`Reanalysis ${result.id.slice(0,8)}… queued.`;await refresh()}catch(error){showError(error)}
  }
  if(deleteId){
    if(!confirm('Delete this run and remove it from Recent runs?')) return;
    try{await api(`/api/v1/dashboard/runs/${deleteId}`,{method:'DELETE'});document.querySelector('#message').textContent='Run deleted.';await refresh()}catch(error){showError(error)}
  }
});
function showError(error){document.querySelector('#message').textContent=error.message}
refresh().catch(showError);
