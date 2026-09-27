"""Optional server entrypoint. No routes, DB connection, authentication or services."""
from fastapi import FastAPI

app = FastAPI(title="OCTV - backend TODO", version="0.1.0")
