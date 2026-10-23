from pydantic import BaseModel


class DemoStartRequest(BaseModel):
    scenario: str = "main_demo"


class DemoStatusResponse(BaseModel):
    enabled: bool
    active: bool
    scenario: str | None = None
    case_count: int
    active_cctv_count: int
    active_alert_count: int


class DemoStopRequest(BaseModel):
    scenario: str = "main_demo"


class DemoStopResponse(BaseModel):
    scenario: str
    stopped: bool
    case_count: int
    stopped_cctv_count: int
    ended_alert_count: int


class DemoScenarioResponse(BaseModel):
    scenario: str
    case_count: int


class DemoResolvedCctv(BaseModel):
    id: int
    provider: str
    external_cctv_id: str
    name: str
    region_code: str | None = None


class DemoStartResponse(BaseModel):
    scenario: str
    ready: bool
    started: bool
    case_count: int
    resolved_cctv_count: int
    fake_alert_count: int
    cctvs: list[DemoResolvedCctv]
