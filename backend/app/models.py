from pydantic import BaseModel, Field


class Geometry(BaseModel):
    x: float
    y: float
    width: float
    height: float


class RecognizedState(BaseModel):
    id: str
    name: str
    geometry: Geometry
    confidence: float = Field(ge=0, le=1)
    initial: bool = False
    final: bool = False


class RecognizedTransition(BaseModel):
    id: str
    from_state: str = Field(alias="from")
    to: str
    event: str
    geometry: Geometry
    confidence: float = Field(ge=0, le=1)
    direction_confirmed: bool = False

    model_config = {"populate_by_name": True}


class RecognitionResult(BaseModel):
    states: list[RecognizedState]
    transitions: list[RecognizedTransition]
    warnings: list[str]
    processing_ms: float


class RefineRegionIn(BaseModel):
    id: str
    kind: str  # "state" | "transition"
    x: float
    y: float
    width: float
    height: float


class RefineRequest(BaseModel):
    regions: list[RefineRegionIn]


class RefineItemOut(BaseModel):
    id: str
    text: str
    confidence: float = Field(ge=0, le=1)


class RefineResultOut(BaseModel):
    items: list[RefineItemOut]
    processing_ms: float
    timed_out: bool = False
    attempted: int = 0
