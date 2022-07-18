import asyncio
import pickle
import csv
import click
import pytest
import os
import shutil
from functools import wraps

from typing import List, Optional, Any
from pathlib import Path

from chianft import __version__
from chianft.util.mint import Minter
from chia.util.hash import std_hash
from chia.util.bech32m import encode_puzzle_hash, decode_puzzle_hash
from chia.types.spend_bundle import SpendBundle

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

def monkey_patch_click() -> None:
    import click.core
    click.core._verify_python3_env = lambda *args, **kwargs: 0  # type: ignore


@click.group(
    help="\n  NFT minting for Chia Blockchain \n",
    context_settings=CONTEXT_SETTINGS,
)
@click.version_option(__version__)
@click.pass_context
def cli(ctx: click.Context) -> None:
    ctx.ensure_object(dict)
    

@cli.command("create-mint-spend-bundles", short_help="Create a set of spend bundles for minting NFTs")
@click.argument("metadata_input", nargs=1, required=True, type=click.Path(exists=True))
@click.argument("bundle_output", nargs=1, required=True,  type=click.Path())
@click.option(
    "-w",
    "--wallet-id",
    required=True,
    help="The DID wallet ID for minting",
)
@click.option(
    "-a",
    "--royalty-address",
    required=False,
    help="A standard XCH address where royalties will be sent"
)
@click.option(
    "-r",
    "--royalty-percentage",
    required=False,
    help="Percentage in basis points of offer price to be paid as royalty, up to 10000 (100%)"
)
@click.option(
    "-t",
    "--has-targets",
    required=False,
    default=True,
    help="Select whether the input csv includes a column of target addresses to send NFTs"
)
@click.option(
    "-p",
    "--fingerprint",
    required=False,
    help="Fingerprint of wallet to use",
)
@coro
async def create_spend_bundles_cmd(
    metadata_input: Path,
    bundle_output: Path,
    wallet_id: int,
    royalty_address: Optional[str] = None,
    royalty_percentage: Optional[int] = None,
    has_targets: Optional[bool] = True,
    fingerprint: Optional[int] = None,
):
    """
    \b
    INPUT is the path of the csv file of NFT matadata to be created
    OUTPUT is the path of the pickle file where spendbundles will be written
    """
    minter = Minter()
    await minter.connect(fingerprint=fingerprint)
    spend_bundles = await minter.create_spend_bundles(
        metadata_input,
        bundle_output,
        wallet_id,
        royalty_address=royalty_address,
        royalty_percentage=royalty_percentage,
        has_targets=has_targets
    )
    await minter.close()

    with open(bundle_output, "wb") as f:
        pickle.dump(spend_bundles, f)


@cli.command("submit-spend-bundles", short_help="Submit spend bundles to mempool")
@click.argument("bundle_input", nargs=1, required=True,  type=click.Path())
@click.option(
    "-f",
    "--fee-per-cost",
    required=False,
    help="The fee (in mojos) per cost for each spend bundle",
)
@click.option(
    "-p",
    "--fingerprint",
    required=False,
    help="Fingerprint of wallet to use",
)
@coro
async def submit_spend_bundles_cmd(
    bundle_input: Path,
    fee_per_cost: Optional[int] = 0,
    fingerprint: Optional[int] = None,
) -> None:
    """
    \b
    BUNDLE_INPUT is the path of the saved spend bundles from create-mint-spend-bundles
    """
    spends = []
    with open(bundle_input, "rb") as f:
        spends_bytes = pickle.load(f)
    for spend_bytes in spends_bytes:
        spends.append(SpendBundle.from_bytes(spend_bytes))
    
    minter = Minter()
    await minter.connect(fingerprint=fingerprint)
    await minter.submit_spend_bundles(spends)
    await minter.close()


def main() -> None:
    monkey_patch_click()
    asyncio.run(cli())  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
