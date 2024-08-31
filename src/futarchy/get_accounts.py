from typing import cast, Optional, Callable
from solders.pubkey import Pubkey
from anchorpy import Program, ProgramAccount
from solana.rpc.commitment import Commitment, Processed

from futarchy.types import *

async def get_account_data_and_slot(
    address: Pubkey,
    program: Program,
    commitment: Commitment = Processed,
    decode: Optional[Callable[[bytes], T]] = None,
) -> Optional[DataAndSlot[T]]:
    account_info = await program.provider.connection.get_account_info(
        address,
        encoding="base64",
        commitment=commitment,
    )

    if not account_info.value:
        return None

    slot = account_info.context.slot
    data = account_info.value.data

    decoded_data = (
        decode(data) if decode is not None else program.coder.accounts.decode(data)
    )

    return DataAndSlot(slot, decoded_data)


async def get_amm_account(
    program: Program,
    amm_account_pubkey: Pubkey,
) -> Amm:
    data_and_slot = await get_account_data_and_slot(amm_account_pubkey, program)
    return cast(Amm, data_and_slot.data)


async def get_conditional_vault_account(
    program: Program,
    conditional_vault_pubkey: Pubkey,
) -> ConditionalVault:
    data_and_slot = await get_account_data_and_slot(conditional_vault_pubkey, program)
    return cast(ConditionalVault, data_and_slot.data)


async def get_proposal_account(
    program: Program,
    proposal_pubkey: Pubkey,
) -> Proposal:
    data_and_slot = await get_account_data_and_slot(proposal_pubkey, program)
    return cast(Proposal, data_and_slot.data)


async def get_dao_account(
    program: Program,
    dao_pubkey: Pubkey,
) -> Dao:
    data_and_slot = await get_account_data_and_slot(dao_pubkey, program)
    return cast(Dao, data_and_slot.data)
