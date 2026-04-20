import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pipeline import run_analytics_pipeline

load_dotenv()

app = FastAPI(
    title="GitHub Candidate Intelligence API",
    description=(
        "Automated Technical Candidate Intelligence System — "
        "5-phase pipeline: Ingest → Prune → Assemble → Evaluate → Report"
    ),
    version="1.0.0",
)

# Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProfileRequest(BaseModel):
    github_id: str   # accepts either a full URL or a bare username


@app.get("/")
async def health_check():
    """Simple health-check so you can confirm the server is running."""
    token_set = bool(os.getenv("GITHUB_TOKEN", ""))
    return {
        "status": "ok",
        "github_token_configured": token_set,
        "warning": (
            None if token_set
            else "GITHUB_TOKEN not set — you will hit the 60 req/hr unauthenticated rate limit quickly."
        ),
    }


@app.post("/api/analyze")
async def analyze_profile(req: ProfileRequest):
    """
    FR1  — Input Acceptance: accepts a full GitHub URL or a bare username.
    FR2  — Profile validation: 400 is returned for invalid / not-found users.
    FR3  — Returns a structured JSON score report on success.
    """
    # Normalise: strip URL prefix if the user pasted a full GitHub URL
    raw_input = req.github_id.strip().rstrip("/")
    if "github.com" in raw_input:
        username = raw_input.split("github.com/")[-1].split("/")[0]
    else:
        username = raw_input

    if not username:
        raise HTTPException(status_code=422, detail="github_id must not be empty.")

    result = run_analytics_pipeline(username)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)