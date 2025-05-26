# schemas.py

from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class ChatRequest(BaseModel):
    input: str

class ChatResponse(BaseModel):
    intent: str
    result: str

class SignalEntry(BaseModel):
    user_id: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    created_at: datetime
