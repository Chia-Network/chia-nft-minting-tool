import csv
import pickle
from secrets import token_bytes
from typing import Any, List

import pytest
from chia.consensus.block_rewards import calculate_base_farmer_reward, calculate_pool_reward
from chia.full_node.mempool_manager import MempoolManager
from chia.rpc.full_node_rpc_api import FullNodeRpcApi
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.rpc.rpc_server import start_rpc_server
from chia.rpc.wallet_rpc_api import WalletRpcApi
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.simulator.full_node_simulator import FullNodeSimulator
from chia.simulator.simulator_protocol import FarmNewBlockProtocol
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.peer_info import PeerInfo
from chia.types.spend_bundle import SpendBundle
from chia.util.bech32m import encode_puzzle_hash
from chia.util.ints import uint16, uint32, uint64
from chia.wallet.did_wallet.did_info import DID_HRP
from chia.wallet.did_wallet.did_wallet import DIDWallet
from chia.wallet.did_wallet.did_wallet_puzzles import LAUNCHER_PUZZLE_HASH
from chia.wallet.nft_wallet.nft_info import NFTInfo

from chianft.util.mint import Minter
from tests.time_out_assert import time_out_assert, time_out_assert_not_none


async def tx_in_pool(mempool: MempoolManager, tx_id: bytes32) -> bool:
    tx = mempool.get_spendbundle(tx_id)
    if tx is None:
        return False
    return True


@pytest.mark.parametrize(
    "trusted",
    [True],
)
@pytest.mark.asyncio
async def test_nft_mint_and_transfer(tmp_path, two_wallet_nodes: Any, trusted: Any, self_hostname) -> None:
    num_blocks = 5
    full_nodes, wallets = two_wallet_nodes
    full_node_api: FullNodeSimulator = full_nodes[0]
    bt = full_node_api.bt
    full_node_server = full_node_api.server
    wallet_node_maker, server_0 = wallets[0]
    wallet_node_taker, server_1 = wallets[1]
    wallet_maker = wallet_node_maker.wallet_state_manager.main_wallet
    wallet_taker = wallet_node_taker.wallet_state_manager.main_wallet

    ph_maker = await wallet_maker.get_new_puzzlehash()
    ph_taker = await wallet_taker.get_new_puzzlehash()
    ph_token = bytes32(token_bytes())

    if trusted:
        wallet_node_maker.config["trusted_peers"] = {
            full_node_api.full_node.server.node_id.hex(): full_node_api.full_node.server.node_id.hex()
        }
        wallet_node_taker.config["trusted_peers"] = {
            full_node_api.full_node.server.node_id.hex(): full_node_api.full_node.server.node_id.hex()
        }
    else:
        wallet_node_maker.config["trusted_peers"] = {}
        wallet_node_taker.config["trusted_peers"] = {}

    await server_0.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
    await server_1.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)

    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_maker))
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_taker))
    await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    funds = sum(
        [calculate_pool_reward(uint32(i)) + calculate_base_farmer_reward(uint32(i)) for i in range(1, num_blocks)]
    )

    await time_out_assert(10, wallet_maker.get_unconfirmed_balance, funds)
    await time_out_assert(10, wallet_maker.get_confirmed_balance, funds)
    await time_out_assert(10, wallet_taker.get_unconfirmed_balance, funds)
    await time_out_assert(10, wallet_taker.get_confirmed_balance, funds)

    api_maker = WalletRpcApi(wallet_node_maker)
    api_taker = WalletRpcApi(wallet_node_taker)
    config = bt.config
    daemon_port = config["daemon_port"]

    def stop_node_cb():
        pass

    full_node_rpc_api = FullNodeRpcApi(full_node_api.full_node)

    rpc_cleanup_node, test_rpc_port_node = await start_rpc_server(
        full_node_rpc_api,
        self_hostname,
        daemon_port,
        uint16(0),
        stop_node_cb,
        bt.root_path,
        config,
        connect_to_daemon=False,
    )

    rpc_cleanup, test_rpc_port = await start_rpc_server(
        api_maker,
        self_hostname,
        daemon_port,
        uint16(0),
        lambda x: None,  # type: ignore
        bt.root_path,
        config,
        connect_to_daemon=False,
    )

    wallet_client = await WalletRpcClient.create(self_hostname, test_rpc_port, bt.root_path, config)

    node_client = await FullNodeRpcClient.create(self_hostname, test_rpc_port_node, bt.root_path, config)

    did_wallet_maker: DIDWallet = await DIDWallet.create_new_did_wallet(
        wallet_node_maker.wallet_state_manager, wallet_maker, uint64(1)
    )
    spend_bundle_list = await wallet_node_maker.wallet_state_manager.tx_store.get_unconfirmed_for_wallet(
        did_wallet_maker.id()
    )

    spend_bundle = spend_bundle_list[0].spend_bundle
    await time_out_assert_not_none(5, full_node_api.full_node.mempool_manager.get_spendbundle, spend_bundle.name())

    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    await time_out_assert(15, wallet_maker.get_pending_change_balance, 0)
    await time_out_assert(10, wallet_maker.get_unconfirmed_balance, funds - 1)
    await time_out_assert(10, wallet_maker.get_confirmed_balance, funds - 1)

    hex_did_id = did_wallet_maker.get_my_DID()
    hmr_did_id = encode_puzzle_hash(bytes32.from_hexstr(hex_did_id), DID_HRP)

    nft_wallet_maker = await api_maker.create_new_wallet(
        dict(wallet_type="nft_wallet", name="NFT WALLET 1", did_id=hmr_did_id)
    )
    assert isinstance(nft_wallet_maker, dict)
    assert nft_wallet_maker.get("success")

    nft_wallet_taker = await api_taker.create_new_wallet(dict(wallet_type="nft_wallet", name="NFT WALLET 2"))

    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    n = 50
    chunk = 25
    header: List[str] = [
        "hash",
        "uris",
        "meta_hash",
        "meta_uris",
        "license_hash",
        "license_uris",
        "edition_number",
        "edition_count",
        "target",
    ]
    sample_metadata: List[List[Any]] = [
        [
            bytes32(token_bytes(32)).hex(),
            "https://data.com/1234",
            bytes32(token_bytes(32)).hex(),
            "https://meatadata.com/1234",
            bytes32(token_bytes(32)).hex(),
            "https://license.com/1234",
            i,
            n,
            encode_puzzle_hash((ph_taker), "xch"),
        ]
        for i in range(n)
    ]

    input_file = tmp_path / "sample_metadata.csv"
    output_file = tmp_path / "sample_spend_bundles.csv"
    sample_data: List[Any] = [header] + sample_metadata
    with open(input_file, "w") as f:
        writer = csv.writer(f)
        writer.writerows(sample_data)

    royalty_address = encode_puzzle_hash(bytes32(token_bytes(32)), "xch")
    royalty_percentage = 300

    minter = Minter(wallet_client, node_client)
    await minter.connect()

    spend_bundles = await minter.create_spend_bundles(
        input_file,
        output_file,
        minter.did_wallet_id,
        royalty_address=royalty_address,
        royalty_percentage=royalty_percentage,
        has_targets=True,
    )
    assert len(spend_bundles) == int(n / chunk)
    with open(output_file, "wb") as f:  # type: ignore
        pickle.dump(spend_bundles, f)  # type: ignore
    assert output_file.exists()

    # fee = 100
    spends = []
    with open(output_file, "rb") as f:  # type: ignore
        spends_bytes = pickle.load(f)  # type: ignore
    for spend_bytes in spends_bytes:
        spends.append(SpendBundle.from_bytes(spend_bytes))

    sb = spends[0]
    resp = await node_client.push_tx(sb)
    assert resp["success"]
    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    async def get_taker_nfts():
        nfts = (await api_taker.nft_get_nfts({"wallet_id": nft_wallet_taker["wallet_id"]}))["nft_list"]
        return len(nfts)

    await time_out_assert(n * 2, get_taker_nfts, chunk)

    wallet_client.close()
    node_client.close()
    await wallet_client.await_closed()
    await node_client.await_closed()
    await rpc_cleanup()
    await rpc_cleanup_node()


@pytest.mark.parametrize(
    "trusted",
    [True],
)
@pytest.mark.asyncio
async def test_nft_mint_with_offers(tmp_path, two_wallet_nodes: Any, trusted: Any, self_hostname) -> None:
    num_blocks = 5
    full_nodes, wallets = two_wallet_nodes
    full_node_api: FullNodeSimulator = full_nodes[0]
    bt = full_node_api.bt
    full_node_server = full_node_api.server
    wallet_node_maker, server_0 = wallets[0]
    wallet_node_taker, server_1 = wallets[1]
    wallet_maker = wallet_node_maker.wallet_state_manager.main_wallet
    wallet_taker = wallet_node_taker.wallet_state_manager.main_wallet

    ph_maker = await wallet_maker.get_new_puzzlehash()
    ph_taker = await wallet_taker.get_new_puzzlehash()
    ph_token = bytes32(token_bytes())

    if trusted:
        wallet_node_maker.config["trusted_peers"] = {
            full_node_api.full_node.server.node_id.hex(): full_node_api.full_node.server.node_id.hex()
        }
        wallet_node_taker.config["trusted_peers"] = {
            full_node_api.full_node.server.node_id.hex(): full_node_api.full_node.server.node_id.hex()
        }
    else:
        wallet_node_maker.config["trusted_peers"] = {}
        wallet_node_taker.config["trusted_peers"] = {}

    await server_0.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)
    await server_1.start_client(PeerInfo("localhost", uint16(full_node_server._port)), None)

    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_maker))
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_taker))
    await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    funds = sum(
        [calculate_pool_reward(uint32(i)) + calculate_base_farmer_reward(uint32(i)) for i in range(1, num_blocks)]
    )

    await time_out_assert(10, wallet_maker.get_unconfirmed_balance, funds)
    await time_out_assert(10, wallet_maker.get_confirmed_balance, funds)
    await time_out_assert(10, wallet_taker.get_unconfirmed_balance, funds)
    await time_out_assert(10, wallet_taker.get_confirmed_balance, funds)

    api_maker = WalletRpcApi(wallet_node_maker)
    # api_taker = WalletRpcApi(wallet_node_taker)
    config = bt.config
    daemon_port = config["daemon_port"]

    def stop_node_cb():
        pass

    full_node_rpc_api = FullNodeRpcApi(full_node_api.full_node)

    rpc_cleanup_node, test_rpc_port_node = await start_rpc_server(
        full_node_rpc_api,
        self_hostname,
        daemon_port,
        uint16(0),
        stop_node_cb,
        bt.root_path,
        config,
        connect_to_daemon=False,
    )

    rpc_cleanup, test_rpc_port = await start_rpc_server(
        api_maker,
        self_hostname,
        daemon_port,
        uint16(0),
        lambda x: None,  # type: ignore
        bt.root_path,
        config,
        connect_to_daemon=False,
    )
    wallet_client = await WalletRpcClient.create(self_hostname, test_rpc_port, bt.root_path, config)
    node_client = await FullNodeRpcClient.create(self_hostname, test_rpc_port_node, bt.root_path, config)

    did_wallet_maker: DIDWallet = await DIDWallet.create_new_did_wallet(
        wallet_node_maker.wallet_state_manager, wallet_maker, uint64(1)
    )
    spend_bundle_list = await wallet_node_maker.wallet_state_manager.tx_store.get_unconfirmed_for_wallet(
        did_wallet_maker.id()
    )

    spend_bundle = spend_bundle_list[0].spend_bundle
    await time_out_assert_not_none(5, full_node_api.full_node.mempool_manager.get_spendbundle, spend_bundle.name())

    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    await time_out_assert(15, wallet_maker.get_pending_change_balance, 0)
    await time_out_assert(10, wallet_maker.get_unconfirmed_balance, funds - 1)
    await time_out_assert(10, wallet_maker.get_confirmed_balance, funds - 1)

    hex_did_id = did_wallet_maker.get_my_DID()
    hmr_did_id = encode_puzzle_hash(bytes32.from_hexstr(hex_did_id), DID_HRP)

    nft_wallet_maker = await api_maker.create_new_wallet(
        dict(wallet_type="nft_wallet", name="NFT WALLET 1", did_id=hmr_did_id)
    )
    assert isinstance(nft_wallet_maker, dict)
    assert nft_wallet_maker.get("success")

    # nft_wallet_taker = await api_taker.create_new_wallet(dict(wallet_type="nft_wallet", name="NFT WALLET 2"))
    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    n = 50
    chunk = 25
    header: List[str] = [
        "hash",
        "uris",
        "meta_hash",
        "meta_uris",
        "license_hash",
        "license_uris",
        "edition_number",
        "edition_count",
    ]
    sample_metadata: List[List[Any]] = [
        [
            bytes32(token_bytes(32)).hex(),
            "https://data.com/1234",
            bytes32(token_bytes(32)).hex(),
            "https://meatadata.com/1234",
            bytes32(token_bytes(32)).hex(),
            "https://license.com/1234",
            i,
            n,
            # encode_puzzle_hash((ph_taker), "xch")
        ]
        for i in range(n)
    ]

    input_file = tmp_path / "sample_metadata.csv"
    output_file = tmp_path / "sample_spend_bundles.csv"
    sample_data: List[Any] = [header] + sample_metadata
    with open(input_file, "w") as f:
        writer = csv.writer(f)
        writer.writerows(sample_data)

    royalty_address = encode_puzzle_hash(bytes32(token_bytes(32)), "xch")
    royalty_percentage = 300

    minter = Minter(wallet_client, node_client)
    await minter.connect()
    # bal = await minter.wallet_client.get_wallet_balance(wallet_id=1)

    spend_bundles = await minter.create_spend_bundles(
        input_file,
        output_file,
        minter.did_wallet_id,
        royalty_address=royalty_address,
        royalty_percentage=royalty_percentage,
        # has_targets=True,
    )
    assert len(spend_bundles) == int(n / chunk)
    with open(output_file, "wb") as f:  # type: ignore
        pickle.dump(spend_bundles, f)  # type: ignore
    assert output_file.exists()

    # fee = 100
    spends = []
    with open(output_file, "rb") as f:  # type: ignore
        spends_bytes = pickle.load(f)  # type: ignore
    for spend_bytes in spends_bytes:
        spends.append(SpendBundle.from_bytes(spend_bytes))

    sb = spends[0]
    resp = await node_client.push_tx(sb)
    assert resp["success"]
    for _ in range(1, num_blocks):
        await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))

    launchers = [coin for coin in sb.removals() if coin.puzzle_hash == LAUNCHER_PUZZLE_HASH]
    launcher = launchers[0]
    info = NFTInfo.from_json_dict((await wallet_client.get_nft_info(launcher.name().hex()))["nft_info"])

    offer_dict = {info.launcher_id.hex(): -1, wallet_maker.id(): 10}

    offer, tr = await wallet_client.create_offer_for_ids(offer_dict, fee=0)

    wallet_client.close()
    node_client.close()
    await wallet_client.await_closed()
    await node_client.await_closed()
    await rpc_cleanup()
    await rpc_cleanup_node()
