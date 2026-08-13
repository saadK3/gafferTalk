from pydantic import Field

from gaffertalk_api.domain.models import DomainModel


class TransferIntent(DomainModel):
    outgoing_player_id: int = Field(gt=0)
    interpretation: str = Field(min_length=1, max_length=240)
