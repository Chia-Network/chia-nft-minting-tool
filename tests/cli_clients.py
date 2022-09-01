from pathlib import Path
from secrets import token_bytes
from typing import Any, Dict, List, Optional

from blspy import G2Element
from chia.clvm.spend_sim import SimClient, SpendSim
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.types.announcement import Announcement
from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import Program
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_spend import CoinSpend
from chia.types.mempool_inclusion_status import MempoolInclusionStatus
from chia.types.spend_bundle import SpendBundle
from chia.util.bech32m import encode_puzzle_hash
from chia.util.ints import uint64
from chia.wallet.util.wallet_types import WalletType
from chia.wallet.wallet_info import WalletInfo

ACS = Program.to(1)
ACS_PH = ACS.get_tree_hash()


class FullNodeClientMock(SimClient):
    # We're just overriding the push_tx endpoint to return a dict and farm a block when done
    async def push_tx(self, spend_bundle: SpendBundle) -> Dict[str, Any]:  # type: ignore
        result = await super().push_tx(spend_bundle)
        if result[0] == MempoolInclusionStatus.SUCCESS:
            # await self.service.farm_block()
            return {"success": True, "status": MempoolInclusionStatus.SUCCESS.name}
        else:
            return {"success": False, "error": result[1]}

    async def get_all_mempool_items(self):
        result = await super().get_all_mempool_items()
        mempool_dict = {}
        for item in result.items():
            mempool_dict[item[0]] = item[1].to_json_dict()
        return mempool_dict

    async def get_mempool_item_by_tx_id(self, tx_id):
        result = await super().get_mempool_item_by_tx_id(tx_id)
        if result:
            await self.service.farm_block()

        return result

    def close(self):
        return

    async def await_closed(self):
        await self.service.close()


class TXMock:
    def __init__(self, bundle):
        self.spend_bundle = bundle


class WalletClientMock:
    def __init__(self, sim_client):
        self.sim_client = sim_client
        self.used_coins = []
        self.did_coin = None

    # These are the only two methods we need
    async def select_coins(self, amount, wallet_id, excluded_coins=[]) -> List[Coin]:
        if self.did_coin:
            excluded_coins.append(self.did_coin)
        coins = await self.sim_client.get_coin_records_by_puzzle_hashes([ACS_PH], include_spent_coins=False)
        coin = [coin for coin in coins if coin not in excluded_coins + self.used_coins][0]
        self.used_coins.append(coin)
        return [coin.coin]
        # return [[coin.coin for coin in coins][0]]

    async def _assign_wallets(self):
        self.wallets = [
            WalletInfo(1, "STD WALLET", WalletType.STANDARD_WALLET.value, ""),
            WalletInfo(2, "DID WALLET", WalletType.DECENTRALIZED_ID.value, ""),
            WalletInfo(3, "NFT WALLET 1", WalletType.NFT.value, ""),
            WalletInfo(4, "NFT WALLET 2", WalletType.NFT.value, ""),
        ]

    async def _assign_did(self):
        coins = await self.select_coins(1, 1)
        self.did_coin = coins[0]
        self.did_id = encode_puzzle_hash(self.did_coin.name(), "did:chia:")

    async def get_nft_wallet_did(self, wallet_id):
        did_addr = encode_puzzle_hash(self.did_coin.puzzle_hash, "did:chia:")
        return {"did_id": did_addr, "success": True}

    async def get_did_id(self, wallet_id):
        return {"coin_id": "0x" + self.did_coin.name().hex(), "my_did": self.did_id, "wallet_id": 2, "success": True}

    async def get_wallets(self, wallet_type: WalletType) -> List[Dict[str, int]]:
        return [wallet.to_json_dict() for wallet in self.wallets if wallet.type == wallet_type]

    async def get_next_address(self, wallet_id: int, new_address: bool) -> str:
        return encode_puzzle_hash(bytes32(token_bytes(32)), "xch")

    async def create_signed_transaction(
        self,
        additions: List[Dict],
        coins: Optional[List[Coin]] = None,
        fee=uint64(0),
        coin_announcements: Optional[List[Announcement]] = None,
    ) -> TXMock:
        total_amount: int = 0
        conditions: List[Program] = []
        for add in additions:
            total_amount += add["amount"]
            conditions.append(Program.to([51, add["puzzle_hash"], add["amount"]]))
        if coin_announcements is not None:
            for ca in coin_announcements:
                conditions.append(Program.to([61, ca.name()]))
        if coins is None:
            coins = await self.select_coins(None, None)  # type: ignore
        conditions.append(Program.to([51, ACS_PH, sum(c.amount for c in list(coins)) - (total_amount + fee)]))
        coin_spends: List[CoinSpend] = [CoinSpend(coins[0], ACS, Program.to(conditions))]  # type: ignore
        if len(coins) > 1:
            for coin in coins[1:]:
                coin_spends.append(CoinSpend(coin, ACS, Program.to([])))
        return TXMock(SpendBundle(coin_spends, G2Element()))

    async def nft_mint_bulk(
        self,
        wallet_id: int,
        metadata_list: List[Any],
        royalty_percentage: int,
        royalty_address: str,
        target_list: Optional[List[str]] = None,
        mint_number_start: Optional[int] = 1,
        mint_total: Optional[int] = None,
        xch_coins: Optional[List[Coin]] = None,
        xch_change_target: Optional[str] = None,
        new_innerpuzhash: Optional[str] = None,
        did_coin: Optional[Dict] = None,
        did_lineage_parent: Optional[str] = None,
        mint_from_did: Optional[bool] = False,
        fee: Optional[int] = 0,
    ) -> Dict:
        spend_bundles = []
        # construct a spendbundle using xch coin and did coin, spending both back to themselves
        assert isinstance(xch_coins, List)
        xch_coin = xch_coins[0]
        xch_conds = [[51, bytes32.from_hexstr(xch_coin["puzzle_hash"]), int(xch_coin["amount"])]]  # type: ignore
        xch_spend = CoinSpend(Coin.from_json_dict(xch_coin), ACS, Program.to(xch_conds))
        if mint_from_did:
            did_conds = [[51, bytes32.from_hexstr(did_coin["puzzle_hash"]), int(did_coin["amount"])]]  # type: ignore
            did_spend = CoinSpend(Coin.from_json_dict(did_coin), ACS, Program.to(did_conds))
            spend_bundles.append(SpendBundle([xch_spend, did_spend], G2Element()))
        else:
            spend_bundles.append(SpendBundle([xch_spend], G2Element()))
        return {"success": True, "spend_bundle": SpendBundle.aggregate(spend_bundles).to_json_dict()}

    def close(self):
        return

    async def await_closed(self):
        try:
            await self.sim_client.service.close()
        finally:
            return


async def get_node_and_wallet_clients(full_node_rpc_port: int, wallet_rpc_port: int, fingerprint: int):
    sim = await SpendSim.create(db_path=Path("./sim.db"))
    for i in range(2):
        await sim.farm_block(ACS_PH)
    client = FullNodeClientMock(sim)
    wallet_client = WalletClientMock(client)
    await wallet_client._assign_wallets()
    await wallet_client._assign_did()
    return client, wallet_client


async def get_node_client(full_node_rpc_port: int):
    sim = await SpendSim.create(db_path=Path("./sim.db"))
    await sim.farm_block(ACS_PH)
    return FullNodeClientMock(sim)


def get_additional_data():
    return DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA
