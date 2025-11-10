
// Full client logic for AI Interviewer — sends frames, audio chunks, tab/app detection, transcript
const socket = io();
let localStream = null;
let regVideoEl = null;
let callVideoEl = null;
let callId = '';
let sendingFrames = false;
let audioRecorder = null, audioStream = null;
let transcriptRecognizer = null;

function el(id){ return document.getElementById(id); }
function toast(msg, t=3000){ const d=el('toast'); d.innerText = msg; d.style.display='block'; setTimeout(()=>d.style.display='none',t); }
function log(msg){ const l=el('log'); l.innerText = `[${new Date().toLocaleTimeString()}] ${msg}\n` + l.innerText; console.log(msg); }

// clock
setInterval(()=> el('clock').innerText = new Date().toLocaleString(), 1000);

// start media
async function startMedia(){
  try{
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    regVideoEl = el('reg_video');
    callVideoEl = el('call_video');
    regVideoEl.srcObject = localStream;
    callVideoEl.srcObject = localStream;
    log('Camera & mic started');
  } catch(e){
    alert('Camera/Microphone error: ' + e.message);
  }
}
startMedia();

// register face
el('capture_reg').onclick = async () => {
  const name = el('reg_name').value || 'unknown';
  const canvas = document.createElement('canvas');
  canvas.width = regVideoEl.videoWidth;
  canvas.height = regVideoEl.videoHeight;
  canvas.getContext('2d').drawImage(regVideoEl, 0, 0);
  const data = canvas.toDataURL('image/jpeg', 0.9);
  const res = await fetch('/register', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, image_data: data})});
  const j = await res.json();
  el('reg_msg').innerText = JSON.stringify(j);
  log('Registered face: ' + JSON.stringify(j));
  toast('Registered face: ' + (j.msg || j.error));
};

// register voice (3s)
el('record_voice').onclick = async () => {
  if (!localStream) { toast('Start camera first'); return; }
  const name = el('reg_name').value || 'unknown';
  const stream = await navigator.mediaDevices.getUserMedia({ audio:true });
  const mr = new MediaRecorder(stream);
  const chunks = [];
  mr.ondataavailable = e => chunks.push(e.data);
  mr.onstop = async () => {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    const ab = await blob.arrayBuffer();
    const b64 = btoa(String.fromCharCode(...new Uint8Array(ab)));
    const dataUrl = 'data:audio/webm;base64,' + b64;
    const res = await fetch('/register_voice', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, audio_data: dataUrl})});
    const j = await res.json();
    log('Registered voice: ' + JSON.stringify(j));
    toast('Voice registered: ' + (j.msg || j.error));
    stream.getTracks().forEach(t=>t.stop());
  };
  mr.start();
  toast('Recording voice for 3s...');
  setTimeout(()=> mr.stop(), 3000);
};

// load questions
(async ()=> {
  const r = await fetch('/questions'); const j = await r.json();
  const qdiv = el('questions'); qdiv.innerHTML='';
  j.questions.forEach((q,i)=> qdiv.innerHTML += `<div><b>Q${i+1}:</b> ${q}</div>`);
})();

// start call
el('start_call').onclick = () => {
  const user = el('call_user').value || el('reg_name').value || 'anon';
  callId = el('call_id').value || ('call_'+Date.now());
  socket.emit('start_call', { call_id: callId, user_name: user });
  sendingFrames = true;
  startFrameLoop();
  startAudioChunking();
  startClientVAD();
  log('Call started: ' + callId);
  toast('Call started');
};

// end call
el('end_call').onclick = () => {
  sendingFrames = false;
  stopAudioChunking();
  stopClientVAD();
  socket.emit('end_call', { call_id: callId });
  log('Call ended: ' + callId);
  toast('Call ended');
};

// send frames
async function startFrameLoop(){
  const video = callVideoEl;
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext('2d');
  while(sendingFrames){
    ctx.drawImage(video,0,0,canvas.width,canvas.height);
    const data = canvas.toDataURL('image/jpeg', 0.6);
    socket.emit('frame', { call_id: callId, image: data });
    await new Promise(r=>setTimeout(r, 600));
  }
}

// audio chunking
function startAudioChunking(){
  navigator.mediaDevices.getUserMedia({ audio:true }).then(stream => {
    audioStream = stream;
    audioRecorder = new MediaRecorder(stream);
    audioRecorder.ondataavailable = async (ev) => {
      if (ev.data && ev.data.size > 0){
        const ab = await ev.data.arrayBuffer();
        const b64 = btoa(String.fromCharCode(...new Uint8Array(ab)));
        socket.emit('audio_chunk', { call_id: callId, audio: 'data:audio/webm;base64,' + b64 });
      }
    };
    audioRecorder.start(1000);
  }).catch(e => log('audioChunk err: ' + e));
}
function stopAudioChunking(){ if (audioRecorder && audioRecorder.state !== 'inactive') audioRecorder.stop(); if (audioStream) audioStream.getTracks().forEach(t=>t.stop()); audioRecorder=null; audioStream=null; }

// simple client VAD for multiple-voice detection
let audioCtx=null, sourceNode=null, analyser=null, vadInterval=null;
function startClientVAD(){
  try{
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    navigator.mediaDevices.getUserMedia({ audio:true }).then(s=>{
      sourceNode = audioCtx.createMediaStreamSource(s);
      analyser = audioCtx.createAnalyser(); analyser.fftSize = 1024;
      sourceNode.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      vadInterval = setInterval(()=>{
        analyser.getByteTimeDomainData(data);
        let sum=0;
        for (let i=0;i<data.length;i++){ const v=(data[i]-128)/128; sum+=v*v; }
        const rms = Math.sqrt(sum/data.length);
        if (rms > 0.03) { // when loud while muted possible other voice
          socket.emit('client_alert', { call_id: callId, type: 'multiple_voice_detected', detail: `rms=${rms.toFixed(3)}` });
          log('Client VAD: multiple_voice_detected rms=' + rms.toFixed(3));
        }
      }, 700);
    });
  }catch(e){ log('VAD start error: ' + e); }
}
function stopClientVAD(){ if (vadInterval) clearInterval(vadInterval); if (sourceNode) sourceNode.disconnect(); sourceNode=null; }

// tab / visibility detection
document.addEventListener('visibilitychange', ()=> {
  if (document.hidden) {
    socket.emit('client_alert', { call_id: callId, type: 'page_hidden' });
    log('Tab hidden');
  }
});
window.addEventListener('blur', ()=> { socket.emit('client_alert', { call_id: callId, type: 'window_blur' }); log('Window blur'); });

// transcript (Web Speech API)
el('start_transcript').onclick = () => {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) { toast('No SpeechRecognition'); return; }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  transcriptRecognizer = new SR();
  transcriptRecognizer.continuous = true; transcriptRecognizer.interimResults = true;
  transcriptRecognizer.onresult = (ev) => {
    let final = '';
    for (let i=0;i<ev.results.length;i++){
      if (ev.results[i].isFinal) final += ev.results[i][0].transcript + ' ';
    }
    if (final.trim().length){
      el('transcript_area').innerText += final + '\n';
      socket.emit('transcript', { call_id: callId, text: final });
      log('Transcript chunk:' + final.trim());
    }
  };
  transcriptRecognizer.start(); toast('Transcript started');
};
el('stop_transcript').onclick = ()=> { if (transcriptRecognizer) transcriptRecognizer.stop(); toast('Transcript stopped'); transcriptRecognizer=null; };

// socket events
socket.on('status', s => { el('hud').innerText = `Faces: ${s.face_count} | Warnings: ${s.warnings} | Violations: ${s.violations}`; log('Status: ' + JSON.stringify(s)); });
socket.on('violation', v => { log('Violation: ' + JSON.stringify(v)); toast('Violation: ' + v.type); });
socket.on('terminated', t => { log('Terminated: ' + (t.msg || '')); toast('Terminated: ' + (t.msg || ''), 5000); sendingFrames=false; stopAudioChunking(); stopClientVAD(); if (localStream) { localStream.getTracks().forEach(track => track.stop()); } alert('Interview terminated: ' + (t.msg || '')); });
socket.on('call_started', c => log('call_started') );
socket.on('call_ended', c => log('call_ended') );

// generate report button
el('generate_report').onclick = async ()=>{
  if (!callId) { toast('No call id'); return; }
  // try PDF
  const res = await fetch('/report_pdf/' + callId);
  if (res.ok){ const blob = await res.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'report_' + callId + '.pdf'; a.click(); toast('PDF downloaded'); return; }
  const r2 = await fetch('/report/' + callId); if (r2.ok){ const blob = await r2.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'report_' + callId + '.txt'; a.click(); toast('Text downloaded'); } else { toast('No report available yet'); }
};
