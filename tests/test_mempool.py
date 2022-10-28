from pathlib import Path
from secrets import token_bytes
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import pytest
import pytest_asyncio
from chia.consensus.block_rewards import (
    calculate_base_farmer_reward,
    calculate_pool_reward,
)
from chia.rpc.rpc_server import start_rpc_server
from chia.rpc.wallet_rpc_api import WalletRpcApi
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.server.start_wallet import create_wallet_service
from chia.simulator.block_tools import test_constants
from chia.simulator.full_node_simulator import FullNodeSimulator
from chia.simulator.simulator_full_node_rpc_client import SimulatorFullNodeRpcClient
from chia.simulator.simulator_protocol import FarmNewBlockProtocol
from chia.simulator.simulator_test_tools import get_full_chia_simulator
from chia.simulator.time_out_assert import time_out_assert
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.peer_info import PeerInfo
from chia.util.bech32m import encode_puzzle_hash
from chia.util.ints import uint16, uint32
from chia.util.keychain import Keychain
from chia.wallet.util.wallet_types import WalletType
from chia.wallet.wallet import Wallet
from faker import Faker

from chianft.util.mint import Minter


def create_metadata(mint_total: int, has_targets: bool) -> List[List[Any]]:
    fake = Faker()
    metadata = []
    header = [
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
        header.append("target")
    for i in range(mint_total):
        sample = [
            bytes32(token_bytes(32)).hex(),  # data_hash
            fake.image_url(),  # data_url
            bytes32(token_bytes(32)).hex(),  # metadata_hash
            fake.url(),  # metadata_url
            bytes32(token_bytes(32)).hex(),  # license_hash
            fake.url(),  # license_url
            1,  # edition_number
            1,  # edition_count
        ]
        if has_targets:
            sample.append(encode_puzzle_hash(bytes32(token_bytes(32)), "xch"))
        metadata.append(sample)
    return metadata


class TestBulkMint:
    @pytest_asyncio.fixture(scope="function")
    async def get_sim_and_wallet(
        self,
        automated_testing: bool = False,
        chia_root: Optional[Path] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[
        Tuple[FullNodeSimulator, SimulatorFullNodeRpcClient, Wallet, WalletRpcClient],
        None,
    ]:
        """
        Fixture to obtain simulator, node rpc, wallet, and wallet rpc
        """
        async for simulator_args in get_full_chia_simulator(
            automated_testing, chia_root, config
        ):
            simulator, root_path, sim_config, mnemonic, fingerprint = simulator_args
            rpc_port = sim_config["full_node"]["rpc_port"]
            await simulator.update_autofarm_config(False)
            node_client = await SimulatorFullNodeRpcClient.create(
                sim_config["self_hostname"], uint16(rpc_port), root_path, sim_config
            )
            daemon_port = sim_config["daemon_port"]
            self_hostname = sim_config["self_hostname"]

            def stop_node_cb() -> None:
                pass

            wallet_service = create_wallet_service(
                root_path, sim_config, test_constants
            )
            await wallet_service.start()
            wallet_node_maker = wallet_service._node
            wallet_maker = wallet_node_maker.wallet_state_manager.main_wallet
            wallet_node_maker.config["trusted_peers"] = {
                simulator.full_node.server.node_id.hex(): simulator.full_node.server.node_id.hex()
            }
            await wallet_node_maker.server.start_client(
                PeerInfo("localhost", uint16(simulator.server._port)), None
            )
            api_maker = WalletRpcApi(wallet_node_maker)
            rpc_server = await start_rpc_server(
                api_maker,
                self_hostname,
                daemon_port,
                uint16(0),
                lambda x: None,  # type: ignore
                root_path,
                sim_config,
                connect_to_daemon=False,
            )

            wallet_client = await WalletRpcClient.create(
                self_hostname, rpc_server.listen_port, root_path, sim_config
            )

            try:
                yield simulator, node_client, wallet_maker, wallet_client
            finally:
                # close up
                wallet_client.close()
                await wallet_client.await_closed()
                rpc_server.close()
                await rpc_server.await_closed()
                wallet_service.stop()
                await wallet_service.wait_closed()
                if node_client:
                    node_client.close()
                    await node_client.await_closed()
                Keychain().delete_key_by_fingerprint(fingerprint)

    @pytest.mark.asyncio
    async def test_bulk_mint(
        self,
        get_sim_and_wallet: Tuple[
            FullNodeSimulator, SimulatorFullNodeRpcClient, Wallet, WalletRpcClient
        ],
    ) -> None:
        (
            simulator,
            node_client,
            wallet,
            wallet_client,
        ) = get_sim_and_wallet

        ph_maker = await wallet.get_new_puzzlehash()
        ph_token = bytes32(token_bytes())

        # Farm a block to the wallet
        await simulator.farm_new_transaction_block(FarmNewBlockProtocol(ph_maker))
        await simulator.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))
        funds = calculate_pool_reward(uint32(1)) + calculate_base_farmer_reward(
            uint32(1)
        )
        await time_out_assert(30, wallet.get_confirmed_balance, funds)

        # Setup DID and NFT Wallets
        did_wallet_resp = await wallet_client.create_new_did_wallet(1)
        assert did_wallet_resp["success"]
        await simulator.farm_new_transaction_block(FarmNewBlockProtocol(ph_token))
        nft_wallet_resp = await wallet_client.get_wallets(wallet_type=WalletType.NFT)
        assert nft_wallet_resp[0]["data"] is not None
        metadata = create_metadata(100, has_targets=True)
        assert len(metadata) == 100
        minter = Minter(wallet_client, node_client)
        assert minter is not None
