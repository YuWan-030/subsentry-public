"""Legacy Flask entrypoint removed.
Use `uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 4399`.
"""
from backend.app.main import app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=4399, reload=False)

