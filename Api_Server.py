from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Interviewer API")

# Allow your frontend to call it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>✅ FastAPI is running successfully!</h1><p>Visit /docs for API docs.</p>"

@app.get("/status")
async def status():
    return {"status": "ok", "framework": "FastAPI"}
