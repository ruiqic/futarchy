from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.instruction import Instruction
from solders.message import MessageV0
from solders.hash import Hash
from solders.signature import Signature
from solders.rpc.responses import SendTransactionResp
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Processed, Confirmed
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address, create_associated_token_account, close_account, CloseAccountParams
from anchorpy import Program, Context, Idl, Provider, Wallet
from pathlib import Path
from typing import Optional, Iterable, Union, Tuple
from enum import Enum

import futarchy
from futarchy.get_accounts import get_amm_account, get_conditional_vault_account, get_proposal_account    
from futarchy.constants import AMM_PROGRAM_ID, CONDITIONAL_VAULT_PROGRAM_ID, AUTOCRAT_PROGRAM_ID
from futarchy.types import Amm, ConditionalVault, Proposal, SwapArgs, SwapType
from futarchy.math import get_output_tokens_buy, get_output_tokens_sell

DEFAULT_TX_OPTIONS = TxOpts(skip_confirmation=False, skip_preflight=False, preflight_commitment=Processed)

class TokenType(Enum):
    BASE = 0
    QUOTE = 1

class OutcomeType(Enum):
    PASS = 0
    FAIL = 1

def get_program(idl_file: Path, program_id: Pubkey, provider: Provider):
    raw = idl_file.read_text()
    idl = Idl.from_json(raw)
    return Program(
        idl,
        program_id,
        provider,
    )


class ProposalClient:
    def __init__(
        self, 
        connection : AsyncClient, 
        wallet : Wallet, 
        proposal : Pubkey,
        opts: TxOpts = DEFAULT_TX_OPTIONS,
    ):
        self.connection = connection
        self.wallet = wallet
        self.authority = wallet.public_key
        self.proposal = proposal
        self.opts = opts
        provider = Provider(connection, wallet, opts)

        self.amm_program_id = AMM_PROGRAM_ID
        amm_file = Path(str(futarchy.__path__[0]) + "/idl/amm_v0.3.json")
        self.amm_program = get_program(amm_file, self.amm_program_id, provider)

        self.vault_program_id = CONDITIONAL_VAULT_PROGRAM_ID
        vault_file = Path(str(futarchy.__path__[0]) + "/idl/conditional_vault_v0.3.json")
        self.vault_program = get_program(vault_file, self.vault_program_id, provider)

        self.autocrat_program_id = AUTOCRAT_PROGRAM_ID
        autocrat_file = Path(str(futarchy.__path__[0]) + "/idl/autocrat_v0.3.json")
        self.autocrat_program = get_program(autocrat_file, self.autocrat_program_id, provider)

    async def get_proposal_info(self):
        self.proposal_account : Proposal = await get_proposal_account(self.autocrat_program, self.proposal)
        self.proposal_start_slot = self.proposal_account.slot_enqueued
        self.pass_amm = self.proposal_account.pass_amm
        self.fail_amm = self.proposal_account.fail_amm
        self.base_vault = self.proposal_account.base_vault
        self.quote_vault = self.proposal_account.quote_vault

        base_vault_account : ConditionalVault = await get_conditional_vault_account(self.vault_program, self.base_vault)
        self.base_underlying_token_mint = base_vault_account.underlying_token_mint
        self.base_pass_token_mint = base_vault_account.conditional_on_finalize_token_mint
        self.base_fail_token_mint = base_vault_account.conditional_on_revert_token_mint
        self.base_precision = 10 ** base_vault_account.decimals

        quote_vault_account : ConditionalVault = await get_conditional_vault_account(self.vault_program, self.quote_vault)
        self.quote_underlying_token_mint = quote_vault_account.underlying_token_mint
        self.quote_pass_token_mint = quote_vault_account.conditional_on_finalize_token_mint
        self.quote_fail_token_mint = quote_vault_account.conditional_on_revert_token_mint
        self.quote_precision = 10 ** quote_vault_account.decimals

    async def create_token_accounts(self):
        mints = [
            self.base_pass_token_mint,
            self.base_fail_token_mint,
            self.quote_pass_token_mint,
            self.quote_fail_token_mint,
            self.base_underlying_token_mint,
            self.quote_underlying_token_mint
        ]
        accounts = [get_associated_token_address(self.authority, mint) for mint in mints]
        account_statuses = await self.connection.get_multiple_accounts_json_parsed(accounts, commitment=Confirmed)
        ixs = []
        for i, status in enumerate(account_statuses.value):
            if status is None or status.data.parsed["info"]["state"] != "initialized":
                ixs.append(create_associated_token_account(
                    self.authority, 
                    self.authority, 
                    mints[i]
                ))
        if ixs:
            return await self.send_ix(ixs, compute_unit_limit=25_000 * len(ixs))
        
    async def close_conditional_token_accounts(self):
        mints = [
            self.base_pass_token_mint,
            self.base_fail_token_mint,
            self.quote_pass_token_mint,
            self.quote_fail_token_mint,
        ]
        accounts = [get_associated_token_address(self.authority, mint) for mint in mints]
        ixs = [self.get_redeem_base_conditional_tokens_ix(), self.get_redeem_quote_conditional_tokens_ix()]
        for account in accounts:
            ixs.append(close_account(CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID, 
                account=account,
                dest=self.authority,
                owner=self.authority
            )))
        return await self.send_ix(ixs, compute_unit_limit=150_000)

    def get_mint_conditional_tokens_ix(self, amount: int, token_type: TokenType) -> Instruction:
        accounts = self.get_accounts_for_vault_ix(token_type)
        ix = self.vault_program.instruction["mint_conditional_tokens"](
            amount,
            ctx=Context(accounts=accounts),
        )
        return ix

    def get_merge_conditional_tokens_ix(self, amount: int, token_type: TokenType) -> Instruction:
        accounts = self.get_accounts_for_vault_ix(token_type)
        ix = self.vault_program.instruction["merge_conditional_tokens_for_underlying_tokens"](
            amount,
            ctx=Context(accounts=accounts)
        )
        return ix
    
    def get_redeem_conditional_tokens_ix(self, token_type: TokenType) -> Instruction:
        accounts = self.get_accounts_for_vault_ix(token_type)
        ix = self.vault_program.instruction["redeem_conditional_tokens_for_underlying_tokens"](
            ctx=Context(accounts=accounts)
        )
        return ix

    def get_accounts_for_vault_ix(self, token_type: TokenType) -> dict:
        if token_type == TokenType.BASE:
            vault = self.base_vault
            pass_token_mint = self.base_pass_token_mint
            fail_token_mint = self.base_fail_token_mint
            vault_underlying_account = get_associated_token_address(vault, self.base_underlying_token_mint)
            user_pass_account = get_associated_token_address(self.authority, pass_token_mint)
            user_fail_account = get_associated_token_address(self.authority, fail_token_mint)
            user_underlying_account = get_associated_token_address(self.authority, self.base_underlying_token_mint)
        else:
            vault = self.quote_vault
            pass_token_mint = self.quote_pass_token_mint
            fail_token_mint = self.quote_fail_token_mint
            vault_underlying_account = get_associated_token_address(vault, self.quote_underlying_token_mint)
            user_pass_account = get_associated_token_address(self.authority, pass_token_mint)
            user_fail_account = get_associated_token_address(self.authority, fail_token_mint)
            user_underlying_account = get_associated_token_address(self.authority, self.quote_underlying_token_mint)
        accounts={
            "vault": vault,
            "conditional_on_finalize_token_mint": pass_token_mint,
            "conditional_on_revert_token_mint": fail_token_mint,
            "vault_underlying_token_account": vault_underlying_account,
            "authority": self.authority,
            "user_conditional_on_finalize_token_account": user_pass_account,
            "user_conditional_on_revert_token_account": user_fail_account,
            "user_underlying_token_account": user_underlying_account,
            "token_program": TOKEN_PROGRAM_ID,
        }
        return accounts
    
    def get_mint_base_conditional_tokens_ix(self, amount: int) -> Instruction:
        return self.get_mint_conditional_tokens_ix(amount, TokenType.BASE)
    
    def get_mint_quote_conditional_tokens_ix(self, amount: int) -> Instruction:
        return self.get_mint_conditional_tokens_ix(amount, TokenType.QUOTE)
    
    def get_merge_base_conditional_tokens_ix(self, amount: int) -> Instruction:
        return self.get_merge_conditional_tokens_ix(amount, TokenType.BASE)
    
    def get_merge_quote_conditional_tokens_ix(self, amount: int) -> Instruction:
        return self.get_merge_conditional_tokens_ix(amount, TokenType.QUOTE)
    
    def get_redeem_base_conditional_tokens_ix(self) -> Instruction:
        return self.get_redeem_conditional_tokens_ix(TokenType.BASE)
    
    def get_redeem_quote_conditional_tokens_ix(self) -> Instruction:
        return self.get_redeem_conditional_tokens_ix(TokenType.QUOTE)

    def get_buy_ix(
        self, 
        amount: int, 
        outcome_type: OutcomeType, 
        amm: Amm, 
        slippage_bps: int = 10,
        return_min_out: bool = False
    ) -> Union[Instruction, Tuple[Instruction, int]]:
        accounts = self.get_accounts_for_swap_ix(outcome_type, amm)
        min_output = get_output_tokens_buy(amount, amm, slippage_bps)
        swap_args = SwapArgs(SwapType.Buy(), amount, min_output)
        ix = self.amm_program.instruction["swap"](
            swap_args,
            ctx=Context(accounts=accounts)
        )
        if return_min_out:
            return ix, min_output
        return ix
    
    def get_sell_ix(
        self, 
        amount: int, 
        outcome_type: OutcomeType, 
        amm: Amm, 
        slippage_bps: int = 10,
        return_min_out: bool = False
    ) -> Union[Instruction, Tuple[Instruction, int]]:
        accounts = self.get_accounts_for_swap_ix(outcome_type, amm)
        min_output = get_output_tokens_sell(amount, amm, slippage_bps)
        swap_args = SwapArgs(SwapType.Sell(), amount, min_output)
        ix = self.amm_program.instruction["swap"](
            swap_args,
            ctx=Context(accounts=accounts)
        )
        if return_min_out:
            return ix, min_output
        return ix

    def get_accounts_for_swap_ix(self, outcome_type: OutcomeType, amm: Amm) -> dict:
        if outcome_type == OutcomeType.PASS:
            amm_pubkey = self.pass_amm
            assert(amm.base_mint == self.base_pass_token_mint)
            assert(amm.quote_mint == self.quote_pass_token_mint)
            user_base_account = get_associated_token_address(self.authority, amm.base_mint)
            user_quote_account = get_associated_token_address(self.authority, amm.quote_mint)
            vault_ata_base = get_associated_token_address(amm_pubkey, amm.base_mint)
            vault_ata_quote = get_associated_token_address(amm_pubkey, amm.quote_mint)
        else:
            amm_pubkey = self.fail_amm
            assert(amm.base_mint == self.base_fail_token_mint)
            assert(amm.quote_mint == self.quote_fail_token_mint)
            user_base_account = get_associated_token_address(self.authority, amm.base_mint)
            user_quote_account = get_associated_token_address(self.authority, amm.quote_mint)
            vault_ata_base = get_associated_token_address(amm_pubkey, amm.base_mint)
            vault_ata_quote = get_associated_token_address(amm_pubkey, amm.quote_mint)
        accounts={
            "user": self.authority,
            "amm": amm_pubkey,
            "user_base_account": user_base_account,
            "user_quote_account": user_quote_account,
            "vault_ata_base": vault_ata_base,
            "vault_ata_quote": vault_ata_quote,
            "token_program": TOKEN_PROGRAM_ID,
        }
        return accounts

    async def get_buy_pass_ix(
        self, amount: int, 
        amm: Optional[Amm] = None, 
        slippage_bps: int = 10, 
        return_min_out: bool = False
    ) -> Union[Instruction, Tuple[Instruction, int]]:
        if amm is None:
            amm = await get_amm_account(self.amm_program, self.pass_amm)
        return self.get_buy_ix(amount, OutcomeType.PASS, amm, slippage_bps, return_min_out)

    async def get_sell_pass_ix(
        self, amount: int, 
        amm: Optional[Amm] = None, 
        slippage_bps: int = 10, 
        return_min_out: bool = False
    ) -> Union[Instruction, Tuple[Instruction, int]]:
        if amm is None:
            amm = await get_amm_account(self.amm_program, self.pass_amm)
        return self.get_sell_ix(amount, OutcomeType.PASS, amm, slippage_bps, return_min_out)

    async def get_buy_fail_ix(
        self, amount: int, 
        amm: Optional[Amm] = None, 
        slippage_bps: int = 10, 
        return_min_out: bool = False
    ) -> Union[Instruction, Tuple[Instruction, int]]:
        if amm is None:
            amm = await get_amm_account(self.amm_program, self.fail_amm)
        return self.get_buy_ix(amount, OutcomeType.FAIL, amm, slippage_bps, return_min_out)

    async def get_sell_fail_ix(
        self, amount: int, 
        amm: Optional[Amm] = None, 
        slippage_bps: int = 10, 
        return_min_out: bool = False
    ) -> Union[Instruction, Tuple[Instruction, int]]:
        if amm is None:
            amm = await get_amm_account(self.amm_program, self.fail_amm)
        return self.get_sell_ix(amount, OutcomeType.FAIL, amm, slippage_bps, return_min_out)
    
    async def fetch_latest_blockhash(self) -> Hash:
        return (
            await self.connection.get_latest_blockhash(Confirmed)
        ).value.blockhash

    async def send_ix(
        self,
        ix : Union[Instruction, Iterable[Instruction]],
        compute_unit_price: int = 10_000,
        compute_unit_limit: int = 50_000,
    ) -> Signature:
        compute_price_ix = set_compute_unit_price(compute_unit_price)
        compute_limit_ix = set_compute_unit_limit(compute_unit_limit)
        if isinstance(ix, Instruction):
            ixs = [compute_limit_ix, compute_price_ix, ix]
        else:
            ixs = [compute_limit_ix, compute_price_ix] + list(ix)

        latest_blockhash = await self.fetch_latest_blockhash()
        msg = MessageV0.try_compile(
            self.authority, ixs, [], latest_blockhash
        )
        tx = VersionedTransaction(msg, [self.wallet.payer])
        body = self.connection._send_raw_transaction_body(bytes(tx), self.opts)
        resp = await self.connection._provider.make_request(body, SendTransactionResp)
        return resp.value
    
