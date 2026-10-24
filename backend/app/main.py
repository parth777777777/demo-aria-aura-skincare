"""Minimal FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Aura Skincare API")


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the API process is healthy."""
    return {"status": "healthy"}
