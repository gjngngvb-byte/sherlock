from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from pathlib import Path
import asyncio, json, os, re, shutil, subprocess, sys

app = FastAPI(title="Sherlock Web", version="1.1.0")
INDEX = Path(__file__).parent / "static" / "index.html"
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,39}$")
SITE_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,80}$")
MAX_CONCURRENT = 2
semaphore = asyncio.Semaphore(MAX_CONCURRENT)
FOUND_RE = re.compile(r"^\[\+\]\s*(.+?):\s*(https?://\S+)")
OTHER_RE = re.compile(r"^\[-\]\s*(.+?):\s*(.*)$")


class SearchRequest(BaseModel):
    username: str = Field(min_length=1, max_length=39)
    timeout: int = Field(default=15, ge=5, le=60)
    sites: list[str] = Field(default_factory=list, max_length=30)


def validate_request(req: SearchRequest) -> str:
    username = req.username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(400, "Use letras, números, ponto, hífen ou sublinhado (até 39 caracteres).")
    if any(not SITE_RE.fullmatch(site) for site in req.sites):
        raise HTTPException(400, "Nome de plataforma inválido.")
    return username


def event(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False) + "\n"


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX.read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "sherlock-project", "version": "0.16.2"}


@app.post("/api/search/stream")
async def search_stream(req: SearchRequest):
    username = validate_request(req)

    async def generate():
        async with semaphore:
            try:
                from sherlock_project.sites import SitesInformation
                sites_info = await asyncio.to_thread(SitesInformation)
                sites_info.remove_nsfw_sites(do_not_remove=req.sites)
                names = sorted(sites_info.sites.keys(), key=str.casefold)
                if req.sites:
                    requested = {s.casefold() for s in req.sites}
                    names = [n for n in names if n.casefold() in requested]
                yield event({"type": "start", "username": username, "timeout": req.timeout,
                             "sites": names, "total": len(names), "engine_version": "0.16.2"})
            except Exception as exc:
                yield event({"type": "error", "message": "Não foi possível carregar a lista atual de sites do Sherlock: " + str(exc)[:300]})
                return

            executable = shutil.which("sherlock")
            cmd = ([executable] if executable else [sys.executable, "-u", "-m", "sherlock_project"])
            cmd += [username, "--timeout", str(req.timeout), "--print-all", "--no-color"]
            for site in req.sites:
                cmd += ["--site", site]

            output_lines = []
            processed = set()
            found = []
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                yield event({"type": "running", "pid": proc.pid})
                while True:
                    raw = await proc.stdout.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    output_lines.append(line)
                    output_lines = output_lines[-250:]

                    match = FOUND_RE.search(line)
                    if match:
                        site, url = match.group(1).strip(), match.group(2).rstrip(".,")
                        processed.add(site.casefold())
                        result = {"site": site, "url": url, "status": "found"}
                        found.append(result)
                        yield event({"type": "site", **result, "processed": len(processed)})
                        continue

                    match = OTHER_RE.search(line)
                    if match:
                        site, detail = match.group(1).strip(), match.group(2).strip()
                        processed.add(site.casefold())
                        lowered = detail.casefold()
                        if "not found" in lowered:
                            status = "not_found"
                        elif "blocked" in lowered or "waf" in lowered or "bot detection" in lowered:
                            status = "blocked"
                        elif "illegal username" in lowered:
                            status = "skipped"
                        else:
                            status = "error"
                        yield event({"type": "site", "site": site, "status": status,
                                     "detail": detail[:240], "processed": len(processed)})

                returncode = await proc.wait()
                yield event({"type": "finish", "returncode": returncode,
                             "processed": len(processed), "total": len(names),
                             "results": found, "log": "\n".join(output_lines[-40:])})
            except FileNotFoundError:
                yield event({"type": "error", "message": "O mecanismo Sherlock não está instalado no servidor."})
            except Exception as exc:
                yield event({"type": "error", "message": "Falha durante a pesquisa: " + str(exc)[:300]})

    return StreamingResponse(generate(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@app.post("/api/search")
async def search(req: SearchRequest):
    username = validate_request(req)
    executable = shutil.which("sherlock")
    cmd = ([executable] if executable else [sys.executable, "-u", "-m", "sherlock_project"])
    cmd += [username, "--timeout", str(req.timeout), "--print-found", "--no-color"]
    for site in req.sites:
        cmd += ["--site", site]
    async with semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
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
        match = FOUND_RE.search(line)
        if match:
            results.append({"site": match.group(1).strip(), "url": match.group(2).rstrip(".,")})
    return {"username": username, "status": "completed" if proc.returncode == 0 else "finished_with_warnings",
            "returncode": proc.returncode, "results": results, "log": text[-12000:]}
