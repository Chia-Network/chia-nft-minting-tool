import csv
import pickle
from pathlib import Path
from secrets import token_bytes
from test.cli_clients import get_node_and_wallet_clients

import pytest
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.bech32m import encode_puzzle_hash
from faker import Faker

from chianft.util.mint import Minter


async def create_metadata(tmp_path, mint_total: int, has_targets: bool) -> Path:
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
    with open(tmp_path / "metadata.csv", "w") as f:
        writer = csv.writer(f)
        writer.writerows([header] + metadata)
    return tmp_path / "metadata.csv"


@pytest.mark.asyncio
async def test_mint_with_targets(tmp_path):
    node_client, wallet_client = await get_node_and_wallet_clients(tmp_path)
    try:
        # Get the minter and connect
        minter = Minter(wallet_client, node_client)
        await minter.connect()

        # Make a metadata file
        mint_total = 10
        wallet_id = 1
        royalty_address = encode_puzzle_hash(bytes32(token_bytes(32)), "xch")
        royalty_percentage = 300
        metadata_file = await create_metadata(tmp_path, mint_total, has_targets=True)
        output_file_path = tmp_path / "output.pkl"
        has_targets = True
        spend_bundles = await minter.create_spend_bundles(
            metadata_file,
            output_file_path,
            wallet_id,
            royalty_address=royalty_address,
            royalty_percentage=royalty_percentage,
            has_targets=has_targets,
        )
        assert spend_bundles is not None
        with open(output_file_path, "wb") as f:
            pickle.dump(spend_bundles, f)

    finally:
        node_client.close()
        wallet_client.close()
        await node_client.await_closed()
        await wallet_client.await_closed()
