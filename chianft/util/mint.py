import asyncio
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.spend_bundle import SpendBundle
from chia.util.bech32m import decode_puzzle_hash
from chia.util.byte_types import hexstr_to_bytes
from chia.util.config import load_config
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.ints import uint16, uint64
from chia.wallet.did_wallet.did_wallet_puzzles import LAUNCHER_PUZZLE_HASH
from chia.wallet.nft_wallet.nft_info import NFTInfo
from chia.wallet.trading.offer import Offer
from chia.wallet.transaction_record import TransactionRecord
from chia.wallet.util.wallet_types import WalletType

chunk = 25


class Minter:
    def __init__(
        self,
        wallet_client: Optional[WalletRpcClient] = None,
        node_client: Optional[FullNodeRpcClient] = None,
    ) -> None:
        self.wallet_client = wallet_client
        self.node_client = node_client

    async def connect(self, fingerprint: Optional[int] = None) -> None:
        config = load_config(Path(DEFAULT_ROOT_PATH), "config.yaml")
        rpc_host = config["self_hostname"]
        full_node_rpc_port = config["full_node"]["rpc_port"]
        wallet_rpc_port = config["wallet"]["rpc_port"]
        if not self.node_client:
            self.node_client = await FullNodeRpcClient.create(
                rpc_host, uint16(full_node_rpc_port), Path(DEFAULT_ROOT_PATH), config
            )
        if not self.wallet_client:
            self.wallet_client = await WalletRpcClient.create(
                rpc_host, uint16(wallet_rpc_port), Path(DEFAULT_ROOT_PATH), config
            )
        assert isinstance(self.wallet_client, WalletRpcClient)
        if fingerprint:
            await self.wallet_client.log_in(fingerprint)
        xch_wallets = await self.wallet_client.get_wallets(wallet_type=WalletType.STANDARD_WALLET)
        did_wallets = await self.wallet_client.get_wallets(wallet_type=WalletType.DECENTRALIZED_ID)
        nft_wallets = await self.wallet_client.get_wallets(wallet_type=WalletType.NFT)
        self.xch_wallet_id = xch_wallets[0]["id"]
        self.did_wallet_id = did_wallets[0]["id"]
        self.nft_wallet_id = nft_wallets[0]["id"]

    async def close(self) -> None:
        if self.node_client:
            self.node_client.close()

        if self.wallet_client:
            self.wallet_client.close()

    async def get_funding_coin(self, amount: int) -> Coin:
        assert isinstance(self.wallet_client, WalletRpcClient)
        coins = await self.wallet_client.select_coins(amount=amount, wallet_id=self.xch_wallet_id)
        if len(coins) > 1:
            raise ValueError("Bulk minting requires a single coin with value greater than %s" % amount)
        return coins[0]

    async def get_did_coin(self) -> Coin:
        assert isinstance(self.wallet_client, WalletRpcClient)
        coins = await self.wallet_client.select_coins(amount=1, wallet_id=self.did_wallet_id)
        return coins[0]

    async def get_mempool_cost(self) -> uint64:
        assert isinstance(self.node_client, FullNodeRpcClient)
        mempool_items = await self.node_client.get_all_mempool_items()
        cost = 0
        for item in mempool_items.values():
            cost += item["cost"]
        return uint64(cost)

    async def get_tx_from_mempool(self, sb_name: bytes32) -> Tuple[bool, Optional[bytes32]]:
        assert isinstance(self.node_client, FullNodeRpcClient)
        mempool_items = await self.node_client.get_all_mempool_items()
        for item in mempool_items.items():
            if bytes32(hexstr_to_bytes(item[1]["spend_bundle_name"])) == sb_name:
                return True, item[0]
        return False, None

    async def wait_tx_confirmed(self, tx_id: bytes32) -> bool:
        assert isinstance(self.node_client, FullNodeRpcClient)
        while True:
            item = await self.node_client.get_mempool_item_by_tx_id(tx_id)
            if item is None:
                return True
            else:
                await asyncio.sleep(1)

    async def create_fee_tx(self, fee: int, spent_coins: List[Coin]) -> TransactionRecord:
        xch_coins = [coin.to_json_dict() for coin in spent_coins if coin.amount > 1]
        assert isinstance(self.wallet_client, WalletRpcClient)
        address = await self.wallet_client.get_next_address(self.xch_wallet_id, new_address=True)
        ph = decode_puzzle_hash(address)
        fee_coins = await self.wallet_client.select_coins(amount=fee, wallet_id=self.xch_wallet_id, exclude=xch_coins)
        assert fee_coins is not None
        if any(item in xch_coins for item in fee_coins):
            raise ValueError("Selected coin for fee conflicts with funding coin. Select a different coin")
        fee_tx = await self.wallet_client.create_signed_transaction(
            additions=[{"amount": 0, "puzzle_hash": ph}],
            coins=fee_coins,
            fee=uint64(fee),
        )
        return fee_tx

    async def create_spend_bundles(
        self,
        metadata_input: Path,
        bundle_output: Path,
        wallet_id: int,
        royalty_address: Optional[str] = None,
        royalty_percentage: Optional[int] = 0,
        has_targets: Optional[bool] = True,
    ) -> List[bytes]:
        metadata_list, target_list = read_metadata_csv(metadata_input, has_header=True, has_targets=has_targets)
        n = len(metadata_list)
        funding_coin: Coin = await self.get_funding_coin(n)
        did_coin: Coin = await self.get_did_coin()
        did_lineage_parent = None
        next_coin = funding_coin
        spend_bundles = []
        assert isinstance(self.wallet_client, WalletRpcClient)
        for i in range(0, n, chunk):
            resp = await self.wallet_client.did_mint_nfts(
                wallet_id=self.did_wallet_id,
                metadata_list=metadata_list[i : i + chunk],
                target_list=target_list[i : i + chunk],
                royalty_percentage=royalty_percentage,  # type: ignore
                royalty_address=royalty_address,  # type: ignore
                starting_num=i + 1,
                max_num=n,
                xch_coins=next_coin.to_json_dict(),
                xch_change_ph=next_coin.to_json_dict()["puzzle_hash"],
                did_coin=did_coin.to_json_dict(),
                did_lineage_parent=did_lineage_parent,
            )
            if not resp["success"]:
                raise ValueError("SpendBundle was not able to be created for metadata rows: %s to %s" % (i, i + chunk))
            sb = SpendBundle.from_json_dict(resp["spend_bundle"])
            spend_bundles.append(bytes(sb))
            next_coin = [c for c in sb.additions() if c.puzzle_hash == funding_coin.puzzle_hash][0]
            did_lineage_parent = [c for c in sb.removals() if c.name() == did_coin.name()][0].parent_coin_info.hex()
            did_coin = [c for c in sb.additions() if (c.parent_coin_info == did_coin.name()) and (c.amount == 1)][0]
        return spend_bundles

    async def submit_spend_bundles(
        self,
        spend_bundles: List[SpendBundle],
        fee_per_cost: Optional[int] = 0,
        create_sell_offer: Optional[int] = None,
    ) -> None:
        MAX_COST = 11000000000
        if create_sell_offer:
            Path("offers").mkdir(parents=True, exist_ok=True)

        for i, sb in enumerate(spend_bundles):
            complete = i
            queued = len(spend_bundles) - complete
            sb_cost = 0
            for spend in sb.coin_spends:
                cost, _ = spend.puzzle_reveal.to_program().run_with_cost(MAX_COST, spend.solution.to_program())
                sb_cost += cost
            fee_per_cost = int(fee_per_cost)  # type: ignore
            assert isinstance(fee_per_cost, int)
            fee = sb_cost * fee_per_cost
            fee_tx = await self.create_fee_tx(fee, sb.removals())
            final_sb = SpendBundle.aggregate([fee_tx.spend_bundle, sb])
            launchers = [coin for coin in sb.removals() if coin.puzzle_hash == LAUNCHER_PUZZLE_HASH]
            assert isinstance(self.node_client, FullNodeRpcClient)
            try:
                resp = await self.node_client.push_tx(final_sb)
            except ValueError as err:
                if "DOUBLE_SPEND" in err.args[0]["error"]:
                    print("SpendBundle was already submitted, skipping")
                    continue
                else:
                    print(err)
                    return

            assert resp["success"]

            while True:
                in_mempool, tx_id = await self.get_tx_from_mempool(final_sb.name())
                if in_mempool:
                    print("Queued: %s Mempool: %s Complete: %s" % (chunk * (queued - 1), chunk, chunk * complete))
                    break
            assert isinstance(tx_id, bytes32)
            await self.wait_tx_confirmed(tx_id)
            await asyncio.sleep(2)

            if create_sell_offer:
                assert isinstance(self.wallet_client, WalletRpcClient)
                for launcher in launchers:
                    info = NFTInfo.from_json_dict(
                        (await self.wallet_client.get_nft_info(launcher.name().hex()))["nft_info"]
                    )
                    offer_dict = {info.launcher_id.hex(): -1, self.xch_wallet_id: int(create_sell_offer)}
                    offer, tr = await self.wallet_client.create_offer_for_ids(offer_dict, fee=0)
                    filepath = "offers/{}.offer".format(launcher.name().hex())
                    assert isinstance(offer, Offer)
                    with open(Path(filepath), "w") as file:
                        file.write(offer.to_bech32())


def read_metadata_csv(
    file_path: Path,
    has_header: Optional[bool] = False,
    has_targets: Optional[bool] = False,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    with open(file_path, "r") as f:
        csv_reader = csv.reader(f)
        bulk_data = list(csv_reader)
    metadata_list = []
    if has_header:
        header_row = bulk_data[0]
        rows = bulk_data[1:]
    else:
        header_row = [
            "hash",
            "uris",
            "meta_hash",
            "meta_uris",
            "license_hash",
            "license_uris",
            "edition_number",
            "edition_count",
        ]
        if has_targets:
            header_row.append("target")
        rows = bulk_data
    list_headers = ["uris", "meta_uris", "license_uris"]
    targets = []
    for row in rows:
        meta_dict: Dict[str, Any] = {list_headers[i]: [] for i in range(len(list_headers))}
        for i, header in enumerate(header_row):
            if header in list_headers:
                meta_dict[header].append(row[i])
            elif header == "target":
                targets.append(row[i])
            else:
                meta_dict[header] = row[i]
        metadata_list.append(meta_dict)
    return metadata_list, targets
