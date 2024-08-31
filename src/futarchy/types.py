from dataclasses import dataclass
from typing import TypeVar, Generic, List, Optional
from solders.pubkey import Pubkey
from borsh_construct.enum import _rust_enum
from sumtypes import constructor

def is_variant(enum, type: str) -> bool:
    return type in str(enum)

def is_one_of_variant(enum, types):
    return any(type in str(enum) for type in types)

T = TypeVar("T")

@dataclass
class DataAndSlot(Generic[T]):
    slot: int
    data: T

# AMM types
@_rust_enum
class SwapType:
    Buy = constructor()
    Sell = constructor()

@dataclass
class TwapOracle:
    last_updated_slot: int
    last_price: int
    last_observation: int
    aggregator: int
    max_observation_change_per_update: int
    initial_observation: int

@dataclass
class Amm:
    bump: int
    created_at_slot: int
    lp_mint: Pubkey
    base_mint: Pubkey
    quote_mint: Pubkey
    base_mint_decimals: int
    quote_mint_decimals: int
    base_amount: int
    quote_amount: int
    oracle: TwapOracle

@dataclass
class CreateAmmArgs:
    twap_initial_observation: int
    twap_max_observation_change_per_update: int

@dataclass
class AddLiquidityArgs:
    quote_amount: int
    max_base_amount: int
    min_lp_tokens: int

@dataclass
class RemoveLiquidityArgs:
    lp_tokens_to_burn: int
    min_quote_amount: int
    min_base_amount: int

@dataclass
class SwapArgs:
    swap_type: SwapType
    input_amount: int
    output_amount_min: int

# Conditional Vault types
@_rust_enum
class VaultStatus:
    Active = constructor()
    Finalized = constructor()
    Reverted = constructor()

@dataclass
class ConditionalVault:
    status: VaultStatus
    settlement_authority: Pubkey
    underlying_token_mint: Pubkey
    underlying_token_account: Pubkey
    conditional_on_finalize_token_mint: Pubkey
    conditional_on_revert_token_mint: Pubkey
    pda_bump: int
    decimals: int

@dataclass
class InitializeConditionalVaultArgs:
    settlement_authority: Pubkey

@dataclass
class AddMetadataToConditionalTokensArgs:
    proposal_number: int
    on_finalize_uri: str
    on_revert_uri: str

# Autocrat types
@_rust_enum
class ProposalState:
    Pending = constructor()
    Passed = constructor()
    Failed = constructor()
    Executed = constructor()

@dataclass
class ProposalAccount:
    pubkey: Pubkey
    is_signer: bool
    is_writable: bool

@dataclass
class ProposalInstruction:
    program_id: Pubkey
    accounts: List[ProposalAccount]
    data: bytes

@dataclass
class InitializeDaoParams:
    twap_initial_observation: int
    twap_max_observation_change_per_update: int
    min_quote_futarchic_liquidity: int
    min_base_futarchic_liquidity: int
    pass_threshold_bps: Optional[int]
    slots_per_proposal: Optional[int]

@dataclass
class InitializeProposalParams:
    description_url: str
    instruction: ProposalInstruction
    pass_lp_tokens_to_lock: int
    fail_lp_tokens_to_lock: int
    nonce: int

@dataclass
class UpdateDaoParams:
    pass_threshold_bps: Optional[int]
    slots_per_proposal: Optional[int]
    twap_initial_observation: Optional[int]
    twap_max_observation_change_per_update: Optional[int]
    min_quote_futarchic_liquidity: Optional[int]
    min_base_futarchic_liquidity: Optional[int]

@dataclass
class Dao:
    treasury_pda_bump: int
    treasury: Pubkey
    token_mint: Pubkey
    usdc_mint: Pubkey
    proposal_count: int
    pass_threshold_bps: int
    slots_per_proposal: int
    twap_initial_observation: int
    twap_max_observation_change_per_update: int
    min_quote_futarchic_liquidity: int
    min_base_futarchic_liquidity: int

@dataclass
class Proposal:
    number: int
    proposer: Pubkey
    description_url: str
    slot_enqueued: int
    state: ProposalState
    instruction: ProposalInstruction
    pass_amm: Pubkey
    fail_amm: Pubkey
    base_vault: Pubkey
    quote_vault: Pubkey
    dao: Pubkey
    pass_lp_tokens_locked: int
    fail_lp_tokens_locked: int
    nonce: int
    pda_bump: int