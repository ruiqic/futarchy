# Futarchy Python SDK
This unofficial Meta-DAO Futarchy Python SDK implements several basic functions for trading proposal markets. Currently supports minting, merging, buying, and selling conditional tokens.

Requires `python=3.10`. Clone and install:
```console
git clone https://github.com/ruiqic/futarchy.git
cd futarchy
pip install -e .
```

Donations appreciated to `C7NJhQmVpCQ9AgLoU4kWW62EApndJH1HoGYWejQJyr7`

## Example usage
Set up connection, wallet, and client
```python
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed
from anchorpy import Wallet
from futarchy.client import ProposalClient
from futarchy.keypair import load_keypair

connection_url = "https://api.mainnet-beta.solana.com"
connection = AsyncClient(connection_url, commitment=Confirmed)
keypair_file = "path/to/keypair.json"
keypair = load_keypair(keypair_file)
wallet = Wallet(keypair)
opts = TxOpts(skip_confirmation=False, skip_preflight=False, preflight_commitment=Confirmed)
proposal_pubkey = Pubkey.from_string("J57DcV2yQGiDpSetQHui6Piwjwsbet2ozXVPG77kTvTd")

client = ProposalClient(
    connection,
    wallet,
    proposal_pubkey,
    opts
)
```

Initialize client with relevant addresses and make token accounts
```python
await client.get_proposal_info()
await client.create_conditional_token_accounts()
```

Example mint, trade, and merge
```python
mint_ix = client.get_mint_quote_conditional_tokens_ix(10 * client.quote_precision)
await client.send_ix(mint_ix)

buy_ix = await client.get_buy_fail_ix(5 * client.quote_precision)
await client.send_ix(buy_ix)

merge_ix = client.get_merge_quote_conditional_tokens_ix(3 * client.quote_precision)
await client.send_ix(merge_ix)
```
