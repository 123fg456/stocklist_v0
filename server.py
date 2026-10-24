import json, os, subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from zoneinfo import ZoneInfo
app=Flask(__name__)
BASE=Path(__file__).parent
state={'running':False,'last_started':None,'last_finished':None,'last_exit_code':None,'last_error':None,'last_request_monotonic':-100000.0}
lock=threading.Lock()
def worker():
    try:
        limit=max(1,min(int(os.environ.get('ANALYSIS_LIMIT','20')),3000))
        p=subprocess.run([sys.executable,str(BASE/'analyze.py'),'--limit',str(limit)],cwd=BASE,capture_output=True,text=True,timeout=1800)
        with lock:
            state['last_exit_code']=p.returncode
            state['last_error']=(p.stderr or p.stdout)[-1200:] if p.returncode else None
    except Exception as e:
        with lock: state['last_error']=str(e)
    finally:
        with lock:
            state['running']=False
            state['last_finished']=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
@app.get('/')
def home(): return send_from_directory(BASE,'index.html')
@app.get('/api/status')
def status():
    with lock: s=dict(state)
    try: s['report']=json.loads((BASE/'report.json').read_text(encoding='utf8'))
    except Exception: s['report']={}
    return jsonify(s)
@app.post('/api/run')
def run():
    with lock:
        if state['running']: return jsonify({'error':'이미 분석 중입니다.'}),409
        if time.monotonic()-state['last_request_monotonic']<600: return jsonify({'error':'반복 실행 제한: 마지막 요청 후 10분이 지나야 합니다.'}),429
        state['last_request_monotonic']=time.monotonic()
        state.update(running=True,last_started=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),last_error=None)
    threading.Thread(target=worker,daemon=True).start()
    return jsonify({'message':'수집 작업을 시작했습니다.'}),202
@app.get('/health')
def health():return {'ok':True}
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))
