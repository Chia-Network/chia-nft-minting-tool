import csv

# import traceback
from secrets import token_bytes

import pytest
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.bech32m import encode_puzzle_hash
from click.testing import CliRunner, Result
from faker import Faker

from chianft.cmds.cli import cli


def create_metadata(filename: str, mint_total: int, has_targets: bool) -> str:
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
    with open(filename, "w") as f:
        writer = csv.writer(f)
        writer.writerows([header] + metadata)
    return filename


@pytest.mark.parametrize("has_targets", [True, False])
def test_mint_from_did(has_targets):
    mint_total = 10
    chunk_size = 5
    # has_targets = True

    runner = CliRunner()
    with runner.isolated_filesystem():
        input_file = create_metadata("metadata.csv", mint_total, has_targets)
        output_file = "output.pkl"
        sb_result: Result = runner.invoke(
            cli,
            [
                "create-mint-spend-bundles",
                "--wallet-id",
                "3",
                "--mint-from-did",
                True,
                "--royalty-address",
                encode_puzzle_hash(bytes32(token_bytes(32)), "xch"),
                "--royalty-percentage",
                300,
                "--has-targets",
                has_targets,
                "--chunk",
                chunk_size,
                input_file,
                output_file,
            ],
        )
        # breakpoint()

        result = runner.invoke(cli, ["submit-spend-bundles", "--fee", 0, output_file])

    # traceback.print_exception(*result.exc_info)
    assert sb_result.exception is None
    assert "created {} spend bundles".format(int(mint_total / chunk_size)) in sb_result.output
    assert result.exception is None
    assert "Queued: 0" in result.output
    # breakpoint()
