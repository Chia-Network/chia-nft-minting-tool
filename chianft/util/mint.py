from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Any, Optional

from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.rpc.wallet_request_types import NFTMintBulkResponse
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import INFINITE_COST
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_record import CoinRecord
from chia.types.spend_bundle import SpendBundle
from chia.util.byte_types import hexstr_to_bytes
from chia.util.ints import uint64
from chia.wallet.singleton import SINGLETON_LAUNCHER_PUZZLE_HASH
from chia.wallet.util.tx_config import DEFAULT_COIN_SELECTION_CONFIG, DEFAULT_TX_CONFIG
from chia.wallet.util.wallet_types import WalletType


class Minter:
    def __init__(
        self,
        wallet_client: WalletRpcClient,
        node_client: FullNodeRpcClient,
    ) -> None:
        self.wallet_client = wallet_client
        self.node_client = node_client

    async def get_wallet_ids(
        self,
        nft_wallet_id: Optional[int] = None,
    ) -> None:
        nft_wallets = await self.wallet_client.get_wallets(wallet_type=WalletType.NFT)
        if nft_wallet_id is not None:
            if len(nft_wallets) > 1:
                self.non_did_nft_wallet_ids = [wallet["id"] for wallet in nft_wallets if wallet["id"] != nft_wallet_id]
            self.nft_wallet_id = nft_wallet_id
            self.did_coin_id = None
            self.did_wallet_id: int = 0

            did_id_for_nft = (await self.wallet_client.get_nft_wallet_did(wallet_id=nft_wallet_id))["did_id"]
            did_wallets = await self.wallet_client.get_wallets(wallet_type=WalletType.DECENTRALIZED_ID)
            for wallet in did_wallets:
                did_info = await self.wallet_client.get_did_id(wallet_id=wallet["id"])
                if did_info["my_did"] == did_id_for_nft:
                    self.did_coin_id = bytes32.from_hexstr(did_info["coin_id"])
                    self.did_wallet_id = wallet["id"]
                    break
        else:
            self.non_did_nft_wallet_ids = []
            for wallet in nft_wallets:
                did_id = (await self.wallet_client.get_nft_wallet_did(wallet_id=wallet["id"]))["did_id"]
                if did_id is None:
                    self.non_did_nft_wallet_ids.append(wallet["id"])
                else:
                    self.nft_wallet_id = wallet["id"]

        xch_wallets = await self.wallet_client.get_wallets(wallet_type=WalletType.STANDARD_WALLET)
        self.xch_wallet_id = xch_wallets[0]["id"]

    async def get_funding_coin(self, amount: int) -> Coin:
        coins = await self.wallet_client.select_coins(
            amount=amount,
            wallet_id=self.xch_wallet_id,
            coin_selection_config=DEFAULT_COIN_SELECTION_CONFIG,
        )
        if len(coins) > 1:
            raise ValueError(f"Bulk minting requires a single coin with value greater than {amount}")
        return coins[0]

    async def get_tx_from_mempool(self, sb_name: bytes32) -> tuple[bool, Optional[bytes32]]:
        mempool_items = await self.node_client.get_all_mempool_items()
        for item in mempool_items.items():
            if bytes32(hexstr_to_bytes(item[1]["spend_bundle_name"])) == sb_name:
                return True, item[0]
        return False, None

    async def create_spend_bundles(
        self,
        metadata_input: Path,
        bundle_output: Path,
        wallet_id: int,
        mint_from_did: Optional[bool] = False,
        royalty_address: Optional[str] = "",
        royalty_percentage: Optional[int] = 0,
        has_targets: Optional[bool] = True,
        chunk: Optional[int] = 25,
    ) -> list[bytes]:
        await self.get_wallet_ids(wallet_id)
        metadata_list, target_list = read_metadata_csv(metadata_input, has_header=True, has_targets=has_targets)
        mint_total = len(metadata_list)
        funding_coin: Coin = await self.get_funding_coin(mint_total)
        next_coin = funding_coin
        spend_bundles = []
        if mint_from_did:
            did = await self.wallet_client.get_did_id(wallet_id=self.did_wallet_id)
            did_cr = await self.wallet_client.get_did_info(coin_id=did["coin_id"], latest=True)
            did_coin_record: Optional[CoinRecord] = await self.node_client.get_coin_record_by_name(
                bytes32.from_hexstr(did_cr["latest_coin"])
            )
            assert did_coin_record is not None
            did_coin = did_coin_record.coin
            assert did_coin is not None
            did_coin_dict: Optional[dict[str, Any]] = did_coin.to_json_dict()
        else:
            did_coin = None
            did_coin_dict = None
        did_lineage_parent = None
        assert chunk is not None
        assert royalty_percentage is not None
        assert royalty_address is not None
        for i in range(0, mint_total, chunk):
            resp: NFTMintBulkResponse = await self.wallet_client.nft_mint_bulk(
                wallet_id=self.nft_wallet_id,
                metadata_list=metadata_list[i : i + chunk],
                target_list=target_list[i : i + chunk],
                royalty_percentage=royalty_percentage,
                royalty_address=royalty_address,
                mint_number_start=i + 1,
                mint_total=mint_total,
                xch_coins=[next_coin.to_json_dict()],
                xch_change_target=next_coin.to_json_dict()["puzzle_hash"],
                did_coin=did_coin_dict,
                did_lineage_parent=did_lineage_parent,
                mint_from_did=mint_from_did,
                tx_config=DEFAULT_TX_CONFIG,
            )
            if not resp:
                raise ValueError(f"SpendBundle could not be created for metadata rows: {i} to {i + chunk}")
            sb = resp.spend_bundle
            spend_bundles.append(bytes(sb))
            next_coin = next(c for c in sb.additions() if c.puzzle_hash == funding_coin.puzzle_hash)
            if mint_from_did:
                assert did_coin is not None
                did_lineage_parent = next(
                    c for c in sb.removals() if c.name() == did_coin.name()
                ).parent_coin_info.hex()
                did_coin = next(
                    c
                    for c in sb.additions()
                    if (c.parent_coin_info == did_coin.name()) and (c.amount == did_coin.amount)
                )
                assert did_coin is not None
                did_coin_dict = did_coin.to_json_dict()
        return spend_bundles

    def spend_cost(self, spend_bundle: SpendBundle) -> int:
        sb_cost = 0
        for spend in spend_bundle.coin_spends:
            cost, _ = spend.puzzle_reveal.run_with_cost(INFINITE_COST, spend.solution)
            sb_cost += cost
        return sb_cost

    async def is_mempool_full(self, sb_cost: int) -> bool:
        mempool_items = await self.node_client.get_all_mempool_items()
        costs = 0
        for key, val in mempool_items.items():
            costs += val["cost"]
        if costs + sb_cost >= DEFAULT_CONSTANTS.MAX_BLOCK_COST_CLVM:
            return True
        return False

    async def add_fee_to_spend(
        self,
        spend: SpendBundle,
        fee_coin: Coin,
        attempt: int,
        max_fee: Optional[int],
    ) -> tuple[SpendBundle, int]:
        if max_fee:
            total_fee = max_fee
        else:
            mempool_items = await self.node_client.get_all_mempool_items()
            costs = []
            fees = []
            fee_per_costs = []
            for key, val in mempool_items.items():
                costs.append(val["cost"])
                fees.append(val["fee"])
                if val["cost"] > 0:
                    fee_per_costs.append(val["fee"] / val["cost"])
            sb_cost = self.spend_cost(spend)
            if await self.is_mempool_full(sb_cost):
                fee_to_replace = min(fee_per_costs)
                if fee_to_replace < 5:
                    fee_per_cost = 5
                else:
                    fee_per_cost = int(fee_to_replace) + 5
            else:
                # No fee required
                return spend, 0
            total_fee = sb_cost * (fee_per_cost * attempt)
        print(f"Fee for inclusion: {total_fee}")
        fee_tx = await self.wallet_client.create_signed_transactions(
            additions=[
                {
                    "amount": fee_coin.amount - total_fee,
                    "puzzle_hash": fee_coin.puzzle_hash,
                }
            ],
            coins=[fee_coin],
            fee=uint64(total_fee),
            tx_config=DEFAULT_TX_CONFIG,
        )
        assert fee_tx.signed_tx.spend_bundle is not None
        spend_with_fee = SpendBundle.aggregate([fee_tx.signed_tx.spend_bundle, spend])
        return spend_with_fee, total_fee

    async def sb_in_mempool(self, sb_name: bytes32) -> bool:
        mempool_items = await self.node_client.get_all_mempool_items()
        for item in mempool_items.items():
            if bytes32(hexstr_to_bytes(item[1]["spend_bundle_name"])) == sb_name:
                return True
        return False

    async def tx_confirmed(self, sb: SpendBundle) -> bool:
        # grab the NFT coins from the spend and check if they are visible to the node_client
        # we can't check against wallet client b/c they might be transferred during the mint spend
        removal_ids = [coin.name() for coin in sb.removals() if coin.amount == 0]
        nft_list = [coin for coin in sb.additions() if coin.amount == 1 and coin.parent_coin_info in removal_ids]
        confirmed_nfts = 0
        for nft in nft_list:
            # Retry up to 10 times to find NFTs on node
            for j in range(10):
                record = await self.node_client.get_coin_record_by_name(nft.name())
                if not record:
                    await asyncio.sleep(1)
                    continue
                else:
                    confirmed_nfts += 1
                    break
        if confirmed_nfts == len(nft_list):
            return True
        else:
            print(f"Only found {confirmed_nfts} of {len(nft_list)} confirmed nfts")
            return False

    async def monitor_mempool(self, sb: SpendBundle) -> bool:
        while True:
            # make sure we find the spend in mempool before going on to check
            is_in = await self.sb_in_mempool(sb.name())
            if is_in:
                break
            else:
                # If testing with the sim autofarming
                confirmed = await self.tx_confirmed(sb)
                if confirmed:
                    break
        while True:
            if await self.sb_in_mempool(sb.name()):
                # Tx is still in mempool so keep waiting
                await asyncio.sleep(5)
                continue
            elif await self.tx_confirmed(sb):
                # Tx has exited mempool and tx is confirmed so return
                return True
            else:
                # Tx has exited mempool but is not confirmed

                return False

    async def submit_spend(
        self,
        i: int,
        sb: SpendBundle,
        fee_coin: Coin,
        max_fee: Optional[int],
    ) -> SpendBundle:
        max_retries = 10
        for j in range(max_retries):
            final_sb, _total_fee = await self.add_fee_to_spend(sb, fee_coin, j + 1, max_fee)
            print(f"Submitting SB: {final_sb.name()}")
            try:
                resp = await self.node_client.push_tx(final_sb)
                if resp["success"]:
                    # Monitor the progress of tx through the mempool
                    print("Spend successfully submitted. Waiting for confirmation")
                    tx_confirmed = await self.monitor_mempool(final_sb)
                    if tx_confirmed:
                        return final_sb
                    else:
                        print(f"Spend was kicked from mempool. Retrying {j} of {max_retries}")
                        continue
            except ValueError as err:
                error_msg = err.args[0]["error"]
                if "DOUBLE_SPEND" in error_msg:
                    print("SpendBundle was already submitted, skipping")
                    break
                print(error_msg)
                print("retrying in 20 seconds")
                await asyncio.sleep(20)

        raise ValueError("Submit spend failed. Wait for a few blocks and retry")

    async def get_unspent_spend_bundle(self, spend_bundles: list[SpendBundle]) -> tuple[Coin, int]:
        for i, sb in enumerate(spend_bundles):
            xch_coin_to_spend = next(coin for coin in sb.removals() if coin.amount > 1)
            coin_record = await self.node_client.get_coin_record_by_name(xch_coin_to_spend.name())
            assert coin_record is not None
            if coin_record.spent_block_index == 0:
                starting_spend_index: int = i
                return xch_coin_to_spend, starting_spend_index
        raise ValueError("All spend bundles have been spent")

    async def create_offer(self, launcher_ids: list[str], create_sell_offer: int) -> None:
        assert self.wallet_client is not None
        for launcher_id in launcher_ids:
            offer_dict = {
                launcher_id: -1,
                self.xch_wallet_id: int(create_sell_offer),
            }
            for i in range(10):
                try:
                    offer_resp = await self.wallet_client.create_offer_for_ids(
                        offer_dict,
                        fee=0,
                        tx_config=DEFAULT_TX_CONFIG,
                    )
                    offer = offer_resp.offer
                    filepath = f"offers/{launcher_id}.offer"
                    assert offer is not None
                    with open(Path(filepath), "w") as file:
                        file.write(offer.to_bech32())
                    break
                except ValueError as err:
                    print(err)
                    print("Retrying offer creation in 5 seconds")
                    await asyncio.sleep(5)
                    continue

    async def coin_in_mempool(self, funding_coin: Coin) -> Optional[SpendBundle]:
        # the raw spend bundle won't be included in mempool if it has fee added, so we have to check
        # for matching funding coin name in the parent ids of the additions
        mempool_items = await self.node_client.get_all_mempool_items()
        for item in mempool_items.items():
            for coin in item[1]["additions"]:
                if bytes32.from_hexstr(coin["parent_coin_info"]) == funding_coin.name():
                    return SpendBundle.from_json_dict(item[1]["spend_bundle"])
        return None

    async def submit_spend_bundles(
        self,
        spend_bundles: list[SpendBundle],
        fee: Optional[int] = None,
        create_sell_offer: Optional[int] = None,
    ) -> None:
        await self.get_wallet_ids()
        funding_coin, sb_index = await self.get_unspent_spend_bundle(spend_bundles)
        if sb_index > 0:
            print(f"Resuming from spend bundle: {sb_index}")

        # setup a directory for offers if needed
        if create_sell_offer:
            Path("offers").mkdir(parents=True, exist_ok=True)

        # select a coin to use for fees
        if fee:
            estimated_max_fee = len(spend_bundles) * fee
        else:
            estimated_max_fee = len(spend_bundles) * self.spend_cost(spend_bundles[0]) * 5
        csc = DEFAULT_COIN_SELECTION_CONFIG.override(excluded_coin_ids=[funding_coin.name()])
        fee_coin = (
            await self.wallet_client.select_coins(
                amount=estimated_max_fee,
                wallet_id=self.xch_wallet_id,
                coin_selection_config=csc,
            )
        )[0]

        # check current sb is not in mempool, and if it is wait for it to confirm and adjust sb_index
        last_sb = await self.coin_in_mempool(funding_coin)
        if last_sb:
            print("Previous tx is not yet confirmed. Wait a few blocks and restart")
            return None

        # Loop through the unspent bundles and try to submit them
        print(f"Submitting a total of {len(spend_bundles[sb_index:])} spend bundles")
        for i, sb in enumerate(spend_bundles[sb_index:]):
            final_sb = await self.submit_spend(i, sb, fee_coin, fee)

            fee_coin_list = [coin for coin in final_sb.additions() if coin.parent_coin_info == fee_coin.name()]
            if fee_coin_list:
                fee_coin = fee_coin_list[0]

            launcher_ids = [
                coin.name().hex() for coin in sb.removals() if coin.puzzle_hash == SINGLETON_LAUNCHER_PUZZLE_HASH
            ]
            if create_sell_offer:
                await self.create_offer(launcher_ids, create_sell_offer)
            print(f"Spendbundle {sb_index + i} Confirmed")
            bs = await self.node_client.get_blockchain_state()
            mempool_pc = bs["mempool_cost"] / bs["mempool_max_total_cost"]
            print(f"Mempool utilization: {mempool_pc:.0%}")


def read_metadata_csv(
    file_path: Path,
    has_header: Optional[bool] = False,
    has_targets: Optional[bool] = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    with open(file_path) as f:
        csv_reader = csv.reader(f)
        bulk_data = list(csv_reader)
    metadata_list: list[dict[str, Any]] = []
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
            "edition_total",
        ]
        if has_targets:
            header_row.append("target")
        rows = bulk_data
    list_headers = ["uris", "meta_uris", "license_uris"]
    targets = []
    for row in rows:
        meta_dict: dict[str, Any] = {list_headers[i]: [] for i in range(len(list_headers))}
        for i, header in enumerate(header_row):
            if header in list_headers:
                meta_dict[header].append(row[i])
            elif header == "target":
                targets.append(row[i])
            else:
                meta_dict[header] = row[i]
        metadata_list.append(meta_dict)
    return metadata_list, targets
