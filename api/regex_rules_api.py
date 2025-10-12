# api/regex_rules_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from .regex_rules import load_rules, save_rules, debug_apply

router = APIRouter(prefix="", tags=["regex-rules"])

class RulesPayload(BaseModel):
    __root__: List[Dict[str, Any]]

class TestPayload(BaseModel):
    path: str

@router.get("/regex-rules")
def get_rules():
    return load_rules()

@router.post("/regex-rules")
def post_rules(payload: RulesPayload):
    rules = payload.__root__
    if not isinstance(rules, list):
        raise HTTPException(400, "payload deve essere un array di regole")
    save_rules(rules)
    return {"ok": True, "count": len(rules)}

@router.post("/regex-rules/test")
def post_test(payload: TestPayload):
    if not payload.path:
        raise HTTPException(400, "path mancante")
    return debug_apply(payload.path)