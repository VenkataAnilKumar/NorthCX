export const WIDGET_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NorthCX chat</title>
<style>
body{font:16px system-ui,sans-serif;margin:0;background:#f5f7fa;color:#111}
main{max-width:640px;margin:0 auto;padding:16px;display:flex;flex-direction:column;height:100vh;box-sizing:border-box}
#log{flex:1;overflow:auto;display:flex;flex-direction:column;gap:8px}
.m{padding:8px 12px;border-radius:12px;max-width:80%;white-space:pre-wrap}
.u{align-self:flex-end;background:#0b3d91;color:#fff}.a{align-self:flex-start;background:#fff;border:1px solid #d0d7e2}
.s{align-self:center;font-size:13px;color:#555}
form{display:flex;gap:8px;margin-top:8px}input{flex:1;padding:10px;border:1px solid #b8c2d1;border-radius:8px;font:inherit}
button{padding:10px 16px;border:0;border-radius:8px;background:#0b3d91;color:#fff;font:inherit;cursor:pointer}
</style></head><body><main>
<h1>NorthCX</h1><div id="log" aria-live="polite"></div>
<form id="f"><input id="i" aria-label="Message" autocomplete="off" required><button>Send</button></form></main>
<script>
const sid=crypto.randomUUID(),log=document.getElementById('log');
function add(t,c){const d=document.createElement('div');d.className='m '+c;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();const i=document.getElementById('i'),m=i.value.trim();if(!m)return;i.value='';add(m,'u');
try{const r=await fetch('/v1/agents/support/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({sessionId:sid,message:m})});
const j=await r.json();if(!r.ok){add(j.error?.message||'Error','s');return}add(j.reply,'a');if(j.status!=='completed')add('Status: '+j.status,'s')}catch{add('Network error','s')}};
</script></body></html>`;
