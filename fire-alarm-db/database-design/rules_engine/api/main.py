from fastapi import FastAPI
from core.engine import run_fire_alarm_engine

app = FastAPI()

@app.post("/run-engine")
def run_engine(rooms: list[dict]):
    return run_fire_alarm_engine(rooms)