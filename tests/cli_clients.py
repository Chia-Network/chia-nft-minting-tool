from pathlib import Path
from secrets import token_bytes
from typing import Any, Dict, List, Optional, Set

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

    # These are the only two methods we need
    async def select_coins(self, amount, wallet_id, excluded_coins=[]) -> List[Coin]:
        coins = await self.sim_client.get_coin_records_by_puzzle_hashes([ACS_PH], include_spent_coins=False)

        coin = [coin for coin in coins if coin not in excluded_coins + self.used_coins][0]
        self.used_coins.append(coin)
        return [coin.coin]
        # return [[coin.coin for coin in coins][0]]

    async def get_wallets(self, wallet_type: WalletType) -> List[Dict[str, int]]:
        return [{"id": wallet_type.value}]

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
            coins = await self.select_coins(None, None)
        conditions.append(Program.to([51, ACS_PH, sum(c.amount for c in coins) - (total_amount + fee)]))  # change
        coin_spends: List[CoinSpend] = [CoinSpend(coins[0], ACS, Program.to(conditions))]
        if len(coins) > 1:
            for coin in coins[1:]:
                coin_spends.append(CoinSpend(coin, ACS, Program.to([])))
        return TXMock(SpendBundle(coin_spends, G2Element()))

    async def nft_mint_from_did(
        self,
        wallet_id: int,
        metadata_list: List[Any],
        royalty_percentage: int,
        royalty_address: str,
        target_list: Optional[List[str]] = None,
        mint_number_start: Optional[int] = 1,
        mint_total: Optional[int] = None,
        xch_coins: Optional[Set[Coin]] = None,
        xch_change_target: Optional[str] = None,
        new_innerpuzhash: Optional[str] = None,
        did_coin: Optional[Dict] = None,
        did_lineage_parent: Optional[str] = None,
        mint_from_did: Optional[bool] = False,
        fee: Optional[int] = 0,
    ) -> Dict:
        spend_bundles = []
        # for i in range(len(metadata_list)):
        #  connstruct a spendbundle using xch coin and did coin, spending both back to themselves
        xch_coin = xch_coins
        xch_conds = [[51, bytes32.from_hexstr(xch_coins["puzzle_hash"]), int(xch_coins["amount"])]]  # type: ignore
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
    return client, WalletClientMock(client)


async def get_node_client(full_node_rpc_port: int):
    sim = await SpendSim.create(db_path=Path("./sim.db"))
    await sim.farm_block(ACS_PH)
    return FullNodeClientMock(sim)


def get_additional_data():
    return DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA
