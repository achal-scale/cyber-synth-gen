"""
main.py - FastAPI application entry point.
"""
from fastapi import FastAPI

from app import app as application

app: FastAPI = application
