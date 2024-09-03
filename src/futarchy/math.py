from futarchy.types import Amm

MAX_BPS = 100 * 100
FEE_BPS = 100

def get_output_tokens_buy(in_quote_amount: int, amm: Amm, slippage_bps: int = 30):
    input_amount = in_quote_amount / 10 ** amm.quote_mint_decimals
    input_reserves = amm.quote_amount / 10 ** amm.quote_mint_decimals
    output_reserves = amm.base_amount / 10 ** amm.base_mint_decimals
    min_output = calculate_amm_output(input_amount, slippage_bps, input_reserves, output_reserves)
    return int(min_output * 10 ** amm.base_mint_decimals)

def get_output_tokens_sell(in_base_amount: int, amm: Amm, slippage_bps: int = 30):
    input_amount = in_base_amount / 10 ** amm.base_mint_decimals
    input_reserves = amm.base_amount / 10 ** amm.base_mint_decimals
    output_reserves = amm.quote_amount / 10 ** amm.quote_mint_decimals
    min_output = calculate_amm_output(input_amount, slippage_bps, input_reserves, output_reserves)
    return int(min_output * 10 ** amm.quote_mint_decimals)

def calculate_amm_output(in_base_amount, slippage_bps, input_reserves, output_reserves):
    input_amount_with_fee = in_base_amount * (MAX_BPS - FEE_BPS) / MAX_BPS
    numerator = input_amount_with_fee * output_reserves
    denominator = input_reserves + input_amount_with_fee
    expected_out = numerator / denominator
    min_expected_out = expected_out * (MAX_BPS - slippage_bps) / MAX_BPS
    return min_expected_out