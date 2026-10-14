from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from pathlib import Path
import asyncio, re, shutil, subprocess, sys

app = FastAPI(title="Sherlock Web", version="1.0.0")
INDEX = Path(__file__).parent / "static" / "index.html"
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,39}$")
SITE_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,80}$")
MAX_CONCURRENT = 2
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

class SearchRequest(BaseModel):
    username: str = Field(min_length=1, max_length=39)
    timeout: int = Field(default=15, ge=5, le=60)
    sites: list[str] = Field(default_factory=list, max_length=30)

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX.read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "sherlock-project"}

@app.post("/api/search")
async def search(req: SearchRequest):
    username = req.username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(400, "Use letras, números, ponto, hífen ou sublinhado (até 39 caracteres).")
    if any(not SITE_RE.fullmatch(site) for site in req.sites):
        raise HTTPException(400, "Nome de plataforma inválido.")
    executable = shutil.which("sherlock")
    cmd = ([executable] if executable else [sys.executable, "-m", "sherlock_project"])
    cmd += [username, "--timeout", str(req.timeout), "--print-found", "--no-color"]
    for site in req.sites:
        cmd += ["--site", site]
    async with semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            try:
                output, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise HTTPException(504, "A busca excedeu o limite de tempo.")
        except FileNotFoundError:
            raise HTTPException(500, "O mecanismo Sherlock não está instalado.")
    text = output.decode("utf-8", "replace")
    results = []
    for line in text.splitlines():
        match = re.search(r"\[\+\]\s*([^:]+):\s*(https?://\S+)", line)
        if match:
            results.append({"site": match.group(1).strip(), "url": match.group(2).rstrip(".,")})
    return {"username": username, "status": "completed" if proc.returncode == 0 else "finished_with_warnings",
            "returncode": proc.returncode, "results": results, "log": text[-12000:]}

