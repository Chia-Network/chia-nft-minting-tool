import asyncio
import csv
import sys
from secrets import token_bytes
from typing import Any, List

from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.bech32m import encode_puzzle_hash
from faker import Faker

fake = Faker()


async def create_nft_sample(has_targets: bool) -> List[Any]:
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
        sample.append(encode_puzzle_hash(bytes32(token_bytes(32)), "txch"))
    return sample


async def create_target_sample() -> List[Any]:
    return [encode_puzzle_hash(bytes32(token_bytes(32)), "txch")]


async def main(has_targets: bool) -> None:
    count = 1000
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
    coros = [create_nft_sample(has_targets) for _ in range(count)]
    data = await asyncio.gather(*coros)
    with open("metadata.csv", "w") as f:
        writer = csv.writer(f)
        writer.writerows([header] + data)

    royalty_address = encode_puzzle_hash(bytes32(token_bytes(32)), "txch")
    royalty_basis_pts = 300
    print("Royalty Address: %s" % royalty_address)
    print("Royalty Percent: %s" % royalty_basis_pts)


if __name__ == "__main__":
    has_targets = False
    if len(sys.argv) > 1:
        if sys.argv[1] == "t":
            has_targets = True
    asyncio.run(main(has_targets))
