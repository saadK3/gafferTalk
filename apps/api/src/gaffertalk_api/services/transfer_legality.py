"""Deterministic validation for normal FPL transfers.

This service deliberately does not infer private in-progress team state. Callers
must provide the manager-confirmed bank, free transfers, and selling prices
needed to determine an exact result.
"""

from collections import Counter

from gaffertalk_api.domain.models import FplCatalogue, Money, SquadSnapshot
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityResult,
    TransferLegalityStatus,
    TransferPlanningState,
    TransferRejection,
    TransferRejectionCode,
)

POINTS_PER_EXTRA_TRANSFER = 4


class TransferLegalityService:
    """Validate proposed normal transfers without language-model judgment."""

    def validate(
        self,
        *,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        state: TransferPlanningState,
        transfers: tuple[ProposedTransfer, ...],
    ) -> TransferLegalityResult:
        if state.active_chip is not None:
            return self._unsupported_chip(transfers, state.active_chip)

        source_player_ids = {pick.player.id for pick in snapshot.picks}
        rejections = self._validate_transfer_references(transfers, source_player_ids, catalogue)
        if rejections:
            return self._rejected(
                TransferLegalityStatus.ILLEGAL,
                transfers,
                rejections,
            )

        final_player_ids = (source_player_ids - {item.outgoing_player_id for item in transfers}) | {
            item.incoming_player_id for item in transfers
        }
        rejections = self._validate_final_squad(final_player_ids, catalogue)
        if rejections:
            return self._rejected(
                TransferLegalityStatus.ILLEGAL,
                transfers,
                rejections,
            )

        missing_state = self._missing_financial_state(transfers, state)
        if missing_state:
            return self._rejected(
                TransferLegalityStatus.MISSING_STATE,
                transfers,
                missing_state,
            )

        assert state.bank is not None
        assert state.free_transfers is not None
        outgoing_total = sum(
            state.selling_prices[item.outgoing_player_id].tenths for item in transfers
        )
        incoming_total = sum(
            catalogue.players[item.incoming_player_id].current_price.tenths for item in transfers
        )
        remaining_tenths = state.bank.tenths + outgoing_total - incoming_total
        if remaining_tenths < 0:
            return self._rejected(
                TransferLegalityStatus.ILLEGAL,
                transfers,
                (
                    TransferRejection(
                        code=TransferRejectionCode.INSUFFICIENT_FUNDS,
                        detail=(
                            "The confirmed bank and selling prices do not cover "
                            "the incoming players."
                        ),
                    ),
                ),
                free_transfers=state.free_transfers,
            )

        paid_transfers = max(0, len(transfers) - state.free_transfers)
        return TransferLegalityResult(
            status=TransferLegalityStatus.LEGAL,
            transfers_requested=len(transfers),
            free_transfers_used=min(len(transfers), state.free_transfers),
            paid_transfers=paid_transfers,
            points_hit=paid_transfers * POINTS_PER_EXTRA_TRANSFER,
            remaining_bank=Money(tenths=remaining_tenths),
            assumptions=(
                "Validated as normal transfers; Wildcard and Free Hit are not supported.",
                "Each transfer beyond the confirmed free-transfer count costs "
                f"{POINTS_PER_EXTRA_TRANSFER} points.",
            ),
        )

    @staticmethod
    def _validate_transfer_references(
        transfers: tuple[ProposedTransfer, ...],
        source_player_ids: set[int],
        catalogue: FplCatalogue,
    ) -> tuple[TransferRejection, ...]:
        rejections: list[TransferRejection] = []
        outgoing_counts = Counter(item.outgoing_player_id for item in transfers)
        incoming_counts = Counter(item.incoming_player_id for item in transfers)
        for item in transfers:
            if item.outgoing_player_id not in source_player_ids:
                rejections.append(
                    TransferRejection(
                        code=TransferRejectionCode.OUTGOING_PLAYER_NOT_IN_SQUAD,
                        detail="The outgoing player is not in the loaded squad.",
                        player_id=item.outgoing_player_id,
                    )
                )
            elif outgoing_counts[item.outgoing_player_id] > 1:
                rejections.append(
                    TransferRejection(
                        code=TransferRejectionCode.DUPLICATE_OUTGOING_PLAYER,
                        detail="A player can only be transferred out once in a request.",
                        player_id=item.outgoing_player_id,
                    )
                )
            if item.incoming_player_id not in catalogue.players:
                rejections.append(
                    TransferRejection(
                        code=TransferRejectionCode.UNKNOWN_INCOMING_PLAYER,
                        detail="The incoming player is not in the current FPL catalogue.",
                        player_id=item.incoming_player_id,
                    )
                )
            elif item.incoming_player_id in source_player_ids:
                rejections.append(
                    TransferRejection(
                        code=TransferRejectionCode.INCOMING_PLAYER_ALREADY_IN_SQUAD,
                        detail="The incoming player is already in the loaded squad.",
                        player_id=item.incoming_player_id,
                    )
                )
            elif incoming_counts[item.incoming_player_id] > 1:
                rejections.append(
                    TransferRejection(
                        code=TransferRejectionCode.DUPLICATE_INCOMING_PLAYER,
                        detail="A player can only be transferred in once in a request.",
                        player_id=item.incoming_player_id,
                    )
                )
        return tuple(dict.fromkeys(rejections))

    @staticmethod
    def _validate_final_squad(
        player_ids: set[int],
        catalogue: FplCatalogue,
    ) -> tuple[TransferRejection, ...]:
        players = tuple(catalogue.players[player_id] for player_id in player_ids)
        rejections: list[TransferRejection] = []
        if len(players) != catalogue.rules.squad_size:
            rejections.append(
                TransferRejection(
                    code=TransferRejectionCode.SQUAD_SIZE,
                    detail=f"A squad must contain exactly {catalogue.rules.squad_size} players.",
                )
            )
        position_counts = Counter(player.position for player in players)
        if position_counts != catalogue.rules.squad_size_by_position:
            rejections.append(
                TransferRejection(
                    code=TransferRejectionCode.POSITION_COMPOSITION,
                    detail=(
                        "The transfers do not preserve FPL's required squad position composition."
                    ),
                )
            )
        club_counts = Counter(player.club.id for player in players)
        if any(count > catalogue.rules.club_limit for count in club_counts.values()):
            rejections.append(
                TransferRejection(
                    code=TransferRejectionCode.CLUB_LIMIT,
                    detail=(
                        "A squad may contain at most "
                        f"{catalogue.rules.club_limit} players per club."
                    ),
                )
            )
        return tuple(rejections)

    @staticmethod
    def _missing_financial_state(
        transfers: tuple[ProposedTransfer, ...],
        state: TransferPlanningState,
    ) -> tuple[TransferRejection, ...]:
        rejections: list[TransferRejection] = []
        if state.bank is None:
            rejections.append(
                TransferRejection(
                    code=TransferRejectionCode.MISSING_BANK,
                    detail="Confirm current bank before calculating exact transfer legality.",
                )
            )
        if state.free_transfers is None:
            rejections.append(
                TransferRejection(
                    code=TransferRejectionCode.MISSING_FREE_TRANSFERS,
                    detail="Confirm available free transfers before calculating any points hit.",
                )
            )
        for transfer in transfers:
            if transfer.outgoing_player_id not in state.selling_prices:
                rejections.append(
                    TransferRejection(
                        code=TransferRejectionCode.MISSING_SELLING_PRICE,
                        detail=(
                            "Confirm the outgoing player's selling price before calculating budget."
                        ),
                        player_id=transfer.outgoing_player_id,
                    )
                )
        return tuple(rejections)

    @staticmethod
    def _unsupported_chip(
        transfers: tuple[ProposedTransfer, ...],
        active_chip: str,
    ) -> TransferLegalityResult:
        return TransferLegalityResult(
            status=TransferLegalityStatus.UNSUPPORTED,
            transfers_requested=len(transfers),
            free_transfers_used=0,
            paid_transfers=0,
            points_hit=0,
            rejections=(
                TransferRejection(
                    code=TransferRejectionCode.UNSUPPORTED_CHIP,
                    detail=(
                        f"{active_chip} is not supported by normal-transfer validation; "
                        "do not use this result for chip planning."
                    ),
                ),
            ),
        )

    @staticmethod
    def _rejected(
        status: TransferLegalityStatus,
        transfers: tuple[ProposedTransfer, ...],
        rejections: tuple[TransferRejection, ...],
        *,
        free_transfers: int | None = None,
    ) -> TransferLegalityResult:
        paid_transfers = max(0, len(transfers) - free_transfers) if free_transfers else 0
        return TransferLegalityResult(
            status=status,
            transfers_requested=len(transfers),
            free_transfers_used=min(len(transfers), free_transfers) if free_transfers else 0,
            paid_transfers=paid_transfers,
            points_hit=paid_transfers * POINTS_PER_EXTRA_TRANSFER,
            rejections=rejections,
        )
