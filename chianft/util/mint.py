import asyncio
import csv
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_record import CoinRecord
from chia.types.spend_bundle import SpendBundle
from chia.util.byte_types import hexstr_to_bytes
from chia.util.ints import uint64
from chia.wallet.did_wallet.did_wallet_puzzles import LAUNCHER_PUZZLE_HASH
from chia.wallet.trading.offer import Offer
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
                self.non_did_nft_wallet_ids = [
                    wallet["id"]
                    for wallet in nft_wallets
                    if wallet["id"] != nft_wallet_id
                ]
            self.nft_wallet_id = nft_wallet_id
            self.did_coin_id = None
            self.did_wallet_id: int = 0

            did_id_for_nft = (
                await self.wallet_client.get_nft_wallet_did(wallet_id=nft_wallet_id)
            )["did_id"]
            did_wallets = await self.wallet_client.get_wallets(
                wallet_type=WalletType.DECENTRALIZED_ID
            )
            for wallet in did_wallets:
                did_info = await self.wallet_client.get_did_id(wallet_id=wallet["id"])
                if did_info["my_did"] == did_id_for_nft:
                    self.did_coin_id = bytes32.from_hexstr(did_info["coin_id"])
                    self.did_wallet_id = wallet["id"]
                    break
        else:
            self.non_did_nft_wallet_ids = []
            for wallet in nft_wallets:
                did_id = (
                    await self.wallet_client.get_nft_wallet_did(wallet_id=wallet["id"])
                )["did_id"]
                if did_id is None:
                    self.non_did_nft_wallet_ids.append(wallet["id"])
                else:
                    self.nft_wallet_id = wallet["id"]

        xch_wallets = await self.wallet_client.get_wallets(
            wallet_type=WalletType.STANDARD_WALLET
        )
        self.xch_wallet_id = xch_wallets[0]["id"]

    async def get_funding_coin(self, amount: int) -> Coin:
        coins = await self.wallet_client.select_coins(amount=amount, wallet_id=self.xch_wallet_id)  # type: ignore
        if len(coins) > 1:
            raise ValueError(
                "Bulk minting requires a single coin with value greater than %s"
                % amount
            )
        return coins[0]

    async def get_tx_from_mempool(
        self, sb_name: bytes32
    ) -> Tuple[bool, Optional[bytes32]]:
        mempool_items = await self.node_client.get_all_mempool_items()  # type: ignore
        for item in mempool_items.items():
            if bytes32(hexstr_to_bytes(item[1]["spend_bundle_name"])) == sb_name:
                return True, item[0]
        return False, None

    async def wait_tx_confirmed(self, tx_id: bytes32) -> bool:
        while True:
            item = await self.node_client.get_mempool_item_by_tx_id(tx_id)  # type: ignore
            if item is None:
                return True
            else:
                await asyncio.sleep(1)

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
    ) -> List[bytes]:
        await self.get_wallet_ids(wallet_id)
        metadata_list, target_list = read_metadata_csv(
            metadata_input, has_header=True, has_targets=has_targets
        )
        mint_total = len(metadata_list)
        funding_coin: Coin = await self.get_funding_coin(mint_total)
        next_coin = funding_coin
        spend_bundles = []
        if mint_from_did:
            did = await self.wallet_client.get_did_id(wallet_id=self.did_wallet_id)
            did_coin_record: Optional[
                CoinRecord
            ] = await self.node_client.get_coin_record_by_name(
                bytes32.from_hexstr(did["coin_id"])
            )
            assert isinstance(did_coin_record, CoinRecord)
            did_coin = did_coin_record.coin
            assert isinstance(did_coin, Coin)
            did_coin_dict: Optional[Dict] = did_coin.to_json_dict()
        else:
            did_coin = None
            did_coin_dict = None
        did_lineage_parent = None
        assert isinstance(chunk, int)
        assert isinstance(royalty_percentage, int)
        assert isinstance(royalty_address, str)
        for i in range(0, mint_total, chunk):
            resp = await self.wallet_client.nft_mint_bulk(
                wallet_id=self.nft_wallet_id,
                metadata_list=metadata_list[i:i + chunk],
                target_list=target_list[i:i + chunk],
                royalty_percentage=royalty_percentage,
                royalty_address=royalty_address,
                mint_number_start=i + 1,
                mint_total=mint_total,
                xch_coins=[next_coin.to_json_dict()],
                xch_change_target=next_coin.to_json_dict()["puzzle_hash"],
                did_coin=did_coin_dict,
                did_lineage_parent=did_lineage_parent,
                mint_from_did=mint_from_did,
            )
            if not resp["success"]:
                raise ValueError(
                    "SpendBundle could not be created for metadata rows: %s to %s"
                    % (i, i + chunk)
                )
            sb = SpendBundle.from_json_dict(resp["spend_bundle"])
            spend_bundles.append(bytes(sb))
            next_coin = [
                c for c in sb.additions() if c.puzzle_hash == funding_coin.puzzle_hash
            ][0]
            if mint_from_did:
                assert isinstance(did_coin, Coin)
                did_lineage_parent = [
                    c for c in sb.removals() if c.name() == did_coin.name()
                ][0].parent_coin_info.hex()
                did_coin = [
                    c
                    for c in sb.additions()
                    if (c.parent_coin_info == did_coin.name())
                    and (c.amount == did_coin.amount)
                ][0]
                assert isinstance(did_coin, Coin)
                did_coin_dict = did_coin.to_json_dict()
        return spend_bundles

    async def submit_spend_bundles(
        self,
        spend_bundles: List[SpendBundle],
        fee: Optional[int] = 0,
        create_sell_offer: Optional[int] = None,
        list_coins: Optional[str] = None,
    ) -> None:
        await self.get_wallet_ids()
        # Get first unspent spendbundle so we can restart efficiently
        for i, sb in enumerate(spend_bundles):
            xch_coin_to_spend = [coin for coin in sb.removals() if coin.amount > 1][0]
            coin_record = await self.node_client.get_coin_record_by_name(
                xch_coin_to_spend.name()
            )
            assert isinstance(coin_record, CoinRecord)
            if coin_record.spent_block_index == 0:
                starting_spend_index = i
                if starting_spend_index > 0:
                    print(
                        "Restarting submit from spend bundle: {}".format(
                            starting_spend_index
                        )
                    )
                break
        else:
            raise ValueError("All spend bundles have been spent")

        # make sure we have a dir for offers if needed
        if create_sell_offer:
            Path("offers").mkdir(parents=True, exist_ok=True)
        if list_coins:
            Path("coins_list").mkdir(parents=True, exist_ok=True)

        # select a coin to use for fees
        assert isinstance(fee, int)
        total_fee_to_pay = len(spend_bundles) * fee
        if total_fee_to_pay > 0:
            fee_coins = await self.wallet_client.select_coins(  # type: ignore
                amount=total_fee_to_pay,
                wallet_id=self.xch_wallet_id,
                excluded_coins=[xch_coin_to_spend],
            )
            fee_coin = fee_coins[0]

        offer_time: float = 0.0
        # start submit loop
        for i, sb in enumerate(spend_bundles[starting_spend_index:]):
            # nfts_in_sb_count = len(sb.additions()) - len(sb.removals())
            start = time.monotonic()
            # TODO: Add dynamic fee estimation
            assert isinstance(fee, int)
            fee_time_start = time.monotonic()
            # Create a tx for the fee and add to the spend bundle
            if fee > 0:
                fee_tx = await self.wallet_client.create_signed_transaction(  # type: ignore
                    additions=[
                        {
                            "amount": fee_coin.amount - fee,
                            "puzzle_hash": fee_coin.puzzle_hash,
                        }
                    ],
                    coins=[fee_coin],
                    fee=uint64(fee),
                )
                final_sb = SpendBundle.aggregate([fee_tx.spend_bundle, sb])
                # Setup the next fee coin for the next spend bundle
                fee_coin = [
                    coin
                    for coin in final_sb.additions()
                    if coin.parent_coin_info == fee_coin.name()
                ][0]
            else:
                final_sb = sb

            fee_time_end = time.monotonic()

            # Keep the launcher coins for creating offers
            launcher_ids = [
                coin.name().hex()
                for coin in sb.removals()
                if coin.puzzle_hash == LAUNCHER_PUZZLE_HASH
            ]

            # Submit the final spend bundle
            tx_time_start = time.monotonic()
            try:
                resp = await self.node_client.push_tx(final_sb)
                assert resp["success"]
            except ValueError as err:
                # if the spend was already submitted, skip to the next one
                # Need this in case user stops and restarts submitting before the last tx is confirmed
                if "DOUBLE_SPEND" in err.args[0]["error"]:
                    print("SpendBundle was already submitted, skipping")
                    continue
                elif "INVALID_FEE_TOO_CLOSE_TO_ZERO" in err.args[0]["error"]:
                    print(
                        "A higher fee than {} mojo is needed for inclusion into mempool.".format(
                            fee
                        )
                    )
                else:
                    print(err)
                    return

            # use a timer in case restart happens between tx in mempool and confirmation
            exception_timer = 10
            while True:
                in_mempool, tx_id = await self.get_tx_from_mempool(final_sb.name())
                if in_mempool:
                    break
                elif exception_timer > 0:
                    await asyncio.sleep(1)
                    exception_timer -= 1
                elif exception_timer == 0:
                    raise ValueError(
                        "Couldn't find tx in mempool after 10 seconds. Retry in a minute"
                    )

            # Wait until the TX is confirmed
            assert isinstance(tx_id, bytes32)
            await self.wait_tx_confirmed(tx_id)
            tx_time_end = time.monotonic()

            # Need to wait for the NFT wallet to catch up.
            # If offer creation is running slow, add an extra 20s wait
            if i > 0 and offer_time > 30:
                await asyncio.sleep(30)
            else:
                await asyncio.sleep(10)

            if create_sell_offer:
                offer_time_start = time.monotonic()
                assert isinstance(self.wallet_client, WalletRpcClient)
                for launcher_id in launcher_ids:
                    offer_dict = {
                        launcher_id: -1,
                        self.xch_wallet_id: int(create_sell_offer),
                    }
                    try:
                        offer, tr = await self.wallet_client.create_offer_for_ids(
                            offer_dict, fee=0
                        )
                    except ValueError as err:
                        print("Failed to include offer for NFT: {}".format(launcher_id))
                        print("Effor creating offer: {}".format(err))
                        await asyncio.sleep(5)
                        continue
                    filepath = "offers/{}.offer".format(launcher_id)
                    assert isinstance(offer, Offer)
                    with open(Path(filepath), "w") as file:
                        file.write(offer.to_bech32())
                offer_time_end = time.monotonic()
                offer_time = offer_time_end - offer_time_start

            if list_coins:
                id_file = open(Path("coins_list/" + list_coins), "a+")
                for launcher_id in launcher_ids:
                    id_file.write(launcher_id + "\n")

            end = time.monotonic()
            tx_time = tx_time_end - tx_time_start
            fee_time = fee_time_end - fee_time_start
            total_time = end - start
            print(
                "SUBMITTED: {}/{}\tTX: {:.2f}s\tFEE: {:.2f}s\tOFFER: {:.2f}s\tTOTAL: {:.2f}s".format(
                    i + starting_spend_index + 1,
                    len(spend_bundles),
                    tx_time,
                    fee_time,
                    offer_time,
                    total_time,
                )
            )


def read_metadata_csv(
    file_path: Path,
    has_header: Optional[bool] = False,
    has_targets: Optional[bool] = False,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    with open(file_path, "r") as f:
        csv_reader = csv.reader(f)
        bulk_data = list(csv_reader)
    metadata_list: List[Dict[str, Any]] = []
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
        meta_dict: Dict[str, Any] = {
            list_headers[i]: [] for i in range(len(list_headers))
        }
        for i, header in enumerate(header_row):
            if header in list_headers:
                meta_dict[header].append(row[i])
            elif header == "target":
                targets.append(row[i])
            else:
                meta_dict[header] = row[i]
        metadata_list.append(meta_dict)
    return metadata_list, targets
