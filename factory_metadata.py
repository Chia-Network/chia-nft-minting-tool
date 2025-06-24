from __future__ import annotations

import asyncio
import csv
import sys
from secrets import token_bytes
from typing import Any

from chia.util.bech32m import encode_puzzle_hash
from chia_rs.sized_bytes import bytes32
from faker import Faker

fake = Faker()


async def create_nft_sample(has_targets: bool) -> list[Any]:
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


async def create_target_sample() -> list[Any]:
    return [encode_puzzle_hash(bytes32(token_bytes(32)), "txch")]


async def main(count: int, has_targets: bool) -> None:
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
        writer.writerows([header, *data])

    royalty_address = encode_puzzle_hash(bytes32(token_bytes(32)), "txch")
    royalty_basis_pts = 300
    print(f"Royalty Address: {royalty_address}")
    print(f"Royalty Percent: {royalty_basis_pts}")


if __name__ == "__main__":
    params = sys.argv[1:]
    if "t" in params:
        has_targets = True
        count = int(next(iter(set(params) - set("t"))))
    else:
        has_targets = False
        count = int(params[0])
    asyncio.run(main(count, has_targets))
