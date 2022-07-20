import asyncio
import csv
from secrets import token_bytes
from typing import Any, List

from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.bech32m import encode_puzzle_hash
from faker import Faker

fake = Faker()


async def create_nft_sample() -> List[Any]:
    sample = [
        bytes32(token_bytes(32)).hex(),  # data_hash
        fake.image_url(),  # data_url
        fake.image_url(),
        bytes32(token_bytes(32)).hex(),  # metadata_hash
        fake.url(),  # metadata_url
        fake.url(),
        bytes32(token_bytes(32)).hex(),  # license_hash
        fake.url(),  # license_url
        fake.url(),
        fake.url(),
        1,  # edition_number
        1,  # edition_count
        # encode_puzzle_hash(bytes32(token_bytes(32)), "txch"),  # Target
    ]
    return sample


async def create_target_sample() -> List[Any]:
    return [encode_puzzle_hash(bytes32(token_bytes(32)), "txch")]


async def main() -> None:
    count = 100
    header = [
        "hash",
        "uris",
        "uris",
        "meta_hash",
        "meta_uris",
        "meta_uris",
        "license_hash",
        "license_uris",
        "license_uris",
        "license_uris",
        "series_number",
        "series_total",
    ]
    coros = [create_nft_sample() for _ in range(count)]
    data = await asyncio.gather(*coros)
    with open("metadata.csv", "w") as f:
        writer = csv.writer(f)
        writer.writerows([header] + data)

    royalty_address = encode_puzzle_hash(bytes32(token_bytes(32)), "txch")
    royalty_basis_pts = 300
    print("Royalty Address: %s" % royalty_address)
    print("Royalty Percent: %s" % royalty_basis_pts)

    # target_coro = [create_target_sample() for _ in range(count)]
    # target_data = await asyncio.gather(*target_coro)
    # with open("target_sample.csv", "w") as f:
    #     writer = csv.writer(f)
    #     writer.writerows(target_data)


if __name__ == "__main__":
    asyncio.run(main())
