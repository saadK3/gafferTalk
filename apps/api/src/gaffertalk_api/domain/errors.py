class GafferTalkError(Exception):
    """Base class for expected application failures."""


class InvalidTeamIdError(GafferTalkError):
    def __init__(self, team_id: int) -> None:
        super().__init__(f"FPL Team ID {team_id} was not found")
        self.team_id = team_id


class UpstreamFplError(GafferTalkError):
    """Base class for failures talking to the FPL service."""


class UpstreamFplNotFoundError(UpstreamFplError):
    def __init__(self, resource: str, detail: str) -> None:
        super().__init__(detail)
        self.resource = resource
        self.detail = detail


class UpstreamFplTimeoutError(UpstreamFplError):
    pass


class UpstreamFplUnavailableError(UpstreamFplError):
    def __init__(self, status_code: int | None, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class InvalidUpstreamFplResponseError(UpstreamFplError):
    pass
