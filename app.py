\
# AI Interviewer — Full version (Face + Tab/App + Voice detection + PDF report)
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import base64, io, os, tempfile, threading, webbrowser, json
from datetime import datetime
from collections import defaultdict
from PIL import Image
import numpy as np

# Optional heavy libs
HAS_LIBROSA = False
try:
    import librosa, soundfile as sf
    HAS_LIBROSA = True
except Exception:
    HAS_LIBROSA = False

HAS_CV2 = False
try:
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

HAS_REPORTLAB = False
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = 'bindu-full-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Stores
USERS = {}            # name -> {'image_data':..., 'voice_mfcc':..., 'registered_at':...}
ACTIVE_CALLS = {}     # call_id -> state
LOGS = defaultdict(list)

# Config
WARNING_LIMIT = 3        # terminate when violations >= WARNING_LIMIT
FRAME_INTERVAL_MS = 600
VOICE_SIM_THRESHOLD = 0.60
LOOK_AWAY_FRAMES_THRESHOLD = 12
OUT_OF_FRAME_THRESHOLD = 12

def nowts():
    return datetime.utcnow().isoformat() + "Z"

def log_event(call_id, event):
    LOGS[call_id].append({'ts': nowts(), 'event': event})
    print(f"[{nowts()}] [{call_id}] {event}")

def decode_image_from_dataurl(data_url):
    try:
        head,b64 = data_url.split(',',1)
    except Exception:
        b64 = data_url
    b = base64.b64decode(b64)
    img = Image.open(io.BytesIO(b)).convert('RGB')
    arr = np.array(img)  # RGB
    return arr

def mfcc_from_bytes(wav_bytes, sr_target=16000, n_mfcc=20):
    if not HAS_LIBROSA:
        raise RuntimeError("librosa not installed")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    try:
        tmp.write(wav_bytes); tmp.close()
        y, sr = librosa.load(tmp.name, sr=sr_target, mono=True)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
        return mfcc.mean(axis=1)
    finally:
        try: os.unlink(tmp.name)
        except: pass

def cosine_sim(a,b):
    a = np.array(a); b = np.array(b)
    denom = (np.linalg.norm(a)*np.linalg.norm(b) + 1e-9)
    return float(np.dot(a,b)/denom)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/questions')
def questions():
    return jsonify({'questions': [
        "Tell me about yourself.",
        "Explain a project you are proud of.",
        "What are your strengths and weaknesses?",
        "Explain TCP vs UDP."
    ]})

@app.route('/register', methods=['POST'])
def register():
    payload = request.get_json(force=True)
    name = payload.get('name')
    image_data = payload.get('image_data')
    if not name or not image_data:
        return jsonify({'ok': False, 'error': 'name and image required'}), 400
    USERS[name] = USERS.get(name, {})
    USERS[name]['image_data'] = image_data
    USERS[name]['registered_at'] = nowts()
    log_event('system', f'registered face for {name}')
    return jsonify({'ok': True, 'msg': f'registered face for {name}'})

@app.route('/register_voice', methods=['POST'])
def register_voice():
    if not HAS_LIBROSA:
        return jsonify({'ok': False, 'error': 'server missing audio libs (librosa)'}), 500
    payload = request.get_json(force=True)
    name = payload.get('name')
    audio_data = payload.get('audio_data')
    if not name or not audio_data:
        return jsonify({'ok': False, 'error': 'name and audio required'}), 400
    head,b64 = (audio_data.split(',',1) if ',' in audio_data else (None,audio_data))
    wav_bytes = base64.b64decode(b64)
    try:
        mfcc = mfcc_from_bytes(wav_bytes)
        USERS[name] = USERS.get(name, {})
        USERS[name]['voice_mfcc'] = mfcc.tolist()
        USERS[name]['voice_registered_at'] = nowts()
        log_event('system', f'registered voice for {name}')
        return jsonify({'ok': True, 'msg': f'registered voice for {name}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/report/<call_id>')
def report(call_id):
    if call_id not in LOGS:
        return "No logs", 404
    fname = f"report_{call_id}.txt"
    with open(fname,'w') as f:
        f.write(f"AI Interview Report\nCall ID: {call_id}\nGenerated: {nowts()}\n\n")
        for it in LOGS[call_id]:
            f.write(f"[{it['ts']}] {it['event']}\n")
    return send_file(fname, as_attachment=True)

@app.route('/report_pdf/<call_id>')
def report_pdf(call_id):
    if not HAS_REPORTLAB:
        return jsonify({'ok': False, 'error': 'reportlab not installed'}), 500
    if call_id not in LOGS:
        return jsonify({'ok': False, 'error': 'no logs'}), 404

    fname = f"report_{call_id}.pdf"
    c = canvas.Canvas(fname, pagesize=letter)
    t = c.beginText(40, 750)
    t.setFont("Helvetica", 11)
    t.textLine("AI Interview Report")
    t.textLine(f"Call ID: {call_id}")
    t.textLine(f"Generated: {nowts()}")
    t.textLine("")
    for it in LOGS[call_id]:
        t.textLine(f"[{it['ts']}] {it['event']}")
    c.drawText(t)
    c.save()
    return send_file(fname, as_attachment=True)


# Socket handlers
@socketio.on('start_call')
def start_call(data):
    call_id = data.get('call_id')
    user = data.get('user_name','unknown')
    if not call_id:
        emit('error', {'msg':'call_id required'}); return
    ACTIVE_CALLS[call_id] = {
        'user_name': user,
        'warnings': 0,
        'violations': 0,
        'looking_away_count': 0,
        'out_of_frame_count': 0,
        'terminated': False,
        'termination_reason': None,
        'start_ts': nowts()
    }
    log_event(call_id, f'call started by {user}')
    emit('call_started', {'ok': True})

@socketio.on('frame')
def on_frame(data):
    call_id = data.get('call_id'); image = data.get('image')
    if not call_id or call_id not in ACTIVE_CALLS or not image: return
    state = ACTIVE_CALLS[call_id]
    if state['terminated']:
        emit('terminated', {'msg': state['termination_reason']}); return
    try:
        arr = decode_image_from_dataurl(image)  # RGB
    except Exception as e:
        log_event(call_id, f'image decode error: {e}'); return
    h,w = arr.shape[:2]
    face_count = 0; centers = []
    if HAS_CV2:
        try:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30,30))
            face_count = len(faces)
            for (x,y,fw,fh) in faces: centers.append((x+fw/2, y+fh/2))
        except Exception as e:
            log_event(call_id, f'cv2 face error: {e}'); face_count = 0
    else:
        # fallback assume one centered face to avoid false positives
        face_count = 1; centers.append((w/2, h/2))

    # Intruder
    if face_count > 1:
        state['warnings'] += 1; state['violations'] += 1
        log_event(call_id, f'intruder faces={face_count}'); emit('violation', {'type':'intruder','warnings':state['warnings']})

    # Out of frame
    if face_count == 0:
        state['out_of_frame_count'] += 1
    else:
        state['out_of_frame_count'] = 0
    if state['out_of_frame_count'] > OUT_OF_FRAME_THRESHOLD:
        state['warnings'] += 1; state['violations'] += 1
        log_event(call_id, 'out_of_frame'); emit('violation', {'type':'out_of_frame','warnings':state['warnings']})

    # Looking away
    if centers:
        cx,cy = centers[0]; dx = abs(cx - w/2)/(w/2); dy = abs(cy - h/2)/(h/2)
        if dx > 0.35 or dy > 0.35:
            state['looking_away_count'] += 1
        else:
            state['looking_away_count'] = 0
        if state['looking_away_count'] > LOOK_AWAY_FRAMES_THRESHOLD:
            state['warnings'] += 1; state['violations'] += 1
            log_event(call_id, 'looking_away'); emit('violation', {'type':'looking_away','warnings':state['warnings']})

    # Terminate if violations reached
    if state['violations'] >= WARNING_LIMIT:
        state['terminated'] = True; state['termination_reason'] = 'repeated_violations'
        log_event(call_id, f'terminated due to {state["termination_reason"]}')
        # auto-generate PDF if possible
        if HAS_REPORTLAB:
            try:
                fname = f"report_{call_id}_auto.pdf"
                c = canvas.Canvas(fname, pagesize=letter)
                t = c.beginText(40, 750); t.setFont("Helvetica",11)
                t.textLine("AI Interview Termination Report")
                t.textLine(f"Call ID: {call_id}")
                t.textLine(f"Reason: {state['termination_reason']}")
                t.textLine(f"Generated: {nowts()}"); t.textLine("")
                for it in LOGS[call_id]:
                    t.textLine(f"[{it['ts']}] {it['event']}")
                c.drawText(t); c.save()
                log_event(call_id, f'PDF auto-generated: {fname}')
            except Exception as e:
                log_event(call_id, f'pdf gen error: {e}')
        emit('terminated', {'msg': state['termination_reason']}); return

    emit('status', {'face_count': face_count, 'warnings': state['warnings'], 'violations': state['violations']})

@socketio.on('audio_chunk')
def on_audio_chunk(data):
    call_id = data.get('call_id'); audio = data.get('audio')
    if not call_id or call_id not in ACTIVE_CALLS: return
    state = ACTIVE_CALLS[call_id]
    if not HAS_LIBROSA:
        log_event(call_id, 'audio_chunk received (librosa not installed)'); return
    try:
        head,b64 = (audio.split(',',1) if ',' in audio else (None,audio))
        wav_bytes = base64.b64decode(b64)
    except Exception as e:
        log_event(call_id, f'audio decode error: {e}'); return
    try:
        mfcc = mfcc_from_bytes(wav_bytes)
    except Exception as e:
        log_event(call_id, f'mfcc error: {e}'); return
    reg = USERS.get(state['user_name'], {}).get('voice_mfcc')
    if reg is not None:
        sim = cosine_sim(mfcc, reg)
        if sim < VOICE_SIM_THRESHOLD:
            state['warnings'] += 1; state['violations'] += 1
            log_event(call_id, f'voice_mismatch sim={sim:.3f}')
            emit('violation', {'type':'voice_mismatch','sim': sim, 'warnings': state['warnings']})
    else:
        log_event(call_id, 'audio processed (no registered voice)')

@socketio.on('client_alert')
def on_client_alert(data):
    call_id = data.get('call_id'); typ = data.get('type'); detail = data.get('detail','')
    if not call_id or call_id not in ACTIVE_CALLS: return
    state = ACTIVE_CALLS[call_id]
    state['warnings'] += 1; state['violations'] += 1
    log_event(call_id, f'client_alert: {typ} detail={detail}'); emit('violation', {'type':typ,'detail':detail,'warnings':state['warnings']})
    if state['violations'] >= WARNING_LIMIT:
        state['terminated'] = True; state['termination_reason'] = typ
        log_event(call_id, f'terminated due to {typ}'); emit('terminated', {'msg': typ}); return

@socketio.on('transcript')
def on_transcript(data):
    call_id = data.get('call_id'); text = data.get('text')
    if call_id: LOGS[call_id].append({'ts': nowts(), 'event': f'transcript: {text}'})

@socketio.on('end_call')
def on_end(data):
    call_id = data.get('call_id')
    if call_id in ACTIVE_CALLS:
        log_event(call_id, 'call ended by client'); ACTIVE_CALLS.pop(call_id, None); emit('call_ended', {'ok': True})

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5050")

if __name__ == '__main__':
    threading.Timer(1.0, open_browser).start()
    socketio.run(app, host='0.0.0.0', port=5050, debug=True)