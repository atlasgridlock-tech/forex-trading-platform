"""
Server entry point for Uvicorn.

This module re-exports the FastAPI app from app.main for the supervisor to use.
"""
from app.main import app

__all__ = ["app"]
