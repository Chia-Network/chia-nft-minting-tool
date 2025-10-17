from __future__ import annotations

import asyncio
import pickle
from pathlib import Path

import click
from chia_rs import SpendBundle
from chia_rs.sized_ints import uint32

from chianft import __version__
from chianft.util.clients import get_node_and_wallet_clients
from chianft.util.mint import Minter

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(
    help="\n  NFT minting for Chia Blockchain \n",
    context_settings=CONTEXT_SETTINGS,
)
@click.version_option(__version__)
@click.pass_context
def cli(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


@cli.command(
    "create-mint-spend-bundles",
    short_help="Create a set of spend bundles for minting NFTs",
)
@click.argument("metadata_input", nargs=1, required=True, type=click.Path(exists=True))
@click.argument("bundle_output", nargs=1, required=True, type=click.Path())
@click.option(
    "-w",
    "--wallet-id",
    required=True,
    help="The NFT wallet ID for minting",
)
@click.option(
    "-d",
    "--mint-from-did",
    required=False,
    default=False,
    type=bool,
    help="Set to True for minting NFTs from a DID. The DID must be attached to the NFT wallet you select",
)
@click.option(
    "-a",
    "--royalty-address",
    required=False,
    default="",
    help="A standard XCH address where royalties will be sent",
)
@click.option(
    "-r",
    "--royalty-percentage",
    required=False,
    default=0,
    help="Percentage in basis points of offer price to be paid as royalty, up to 10000 (100%)",
)
@click.option(
    "-t",
    "--has-targets",
    required=False,
    default=True,
    help="Select whether the input csv includes a column of target addresses to send NFTs",
)
@click.option(
    "-c",
    "--chunk",
    required=False,
    default=25,
    help="The number of NFTs to mint per spend bundle. Default: 25",
)
@click.option(
    "-wp",
    "--wallet-rpc-port",
    help="Set the port where the Wallet is hosting the RPC interface. See the rpc_port under wallet in config.yaml",
    type=int,
    default=None,
)
@click.option(
    "-f",
    "--fingerprint",
    help="Set the fingerprint to specify which wallet to use",
    type=int,
    default=None,
)
@click.option(
    "-np",
    "--node-rpc-port",
    help="Set the port where the Node is hosting the RPC interface. See the rpc_port under full_node in config.yaml",
    type=int,
    default=None,
)
def create_spend_bundles_cmd(
    metadata_input: Path,
    bundle_output: Path,
    wallet_id: int,
    mint_from_did: bool | None = False,
    royalty_address: str | None = "",
    royalty_percentage: int | None = 0,
    has_targets: bool | None = False,
    chunk: int | None = 25,
    wallet_rpc_port: int | None = None,
    fingerprint: int | None = None,
    node_rpc_port: int | None = None,
) -> None:
    """
    \b
    INPUT is the path of the csv file of NFT metadata to be created
    OUTPUT is the path of the pickle file where spendbundles will be written
    """

    async def do_command() -> None:
        maybe_clients = await get_node_and_wallet_clients(node_rpc_port, wallet_rpc_port, fingerprint)
        if maybe_clients is None:
            print("Failed to connect to wallet and node")
            return
        node_client, wallet_client = maybe_clients
        if node_client is None or wallet_client is None:
            print("Failed to connect to wallet and node")
            return

        try:
            minter = Minter(wallet_client, node_client)
            spend_bundles = await minter.create_spend_bundles(
                metadata_input,
                bundle_output,
                uint32(wallet_id),
                mint_from_did,
                royalty_address=royalty_address,
                royalty_percentage=royalty_percentage,
                has_targets=has_targets,
                chunk=chunk,
            )
            with open(bundle_output, "wb") as f:
                pickle.dump(spend_bundles, f)
            print(f"Successfully created {len(spend_bundles)} spend bundles")
        finally:
            node_client.close()
            wallet_client.close()
            await node_client.await_closed()
            await wallet_client.await_closed()

    asyncio.get_event_loop().run_until_complete(do_command())


@cli.command("submit-spend-bundles", short_help="Submit spend bundles to mempool")
@click.argument("bundle_input", nargs=1, required=True, type=click.Path())
@click.option(
    "-m",
    "--fee",
    type=int,
    required=False,
    help="Optional default fee - all spends will attempt to use this fee. If not given, fees are estimated",
)
@click.option(
    "-o",
    "--create-sell-offer",
    required=False,
    help="Create an offer for each created NFT at the specified price.",
)
@click.option(
    "-wp",
    "--wallet-rpc-port",
    help="Set the port where the Wallet is hosting the RPC interface. See the rpc_port under wallet in config.yaml",
    type=int,
    default=None,
)
@click.option(
    "-f",
    "--fingerprint",
    help="Set the fingerprint to specify which wallet to use",
    type=int,
    default=None,
)
@click.option(
    "-np",
    "--node-rpc-port",
    help="Set the port where the Node is hosting the RPC interface. See the rpc_port under full_node in config.yaml",
    type=int,
    default=None,
)
def submit_spend_bundles_cmd(
    bundle_input: Path,
    fee: int | None = None,
    create_sell_offer: int | None = None,
    wallet_rpc_port: int | None = None,
    fingerprint: int | None = None,
    node_rpc_port: int | None = None,
) -> None:
    """
    \b
    BUNDLE_INPUT is the path of the saved spend bundles from create-mint-spend-bundles
    """

    async def do_command() -> None:
        maybe_clients = await get_node_and_wallet_clients(node_rpc_port, wallet_rpc_port, fingerprint)
        if maybe_clients is None:
            print("Failed to connect to wallet and node")
            return
        node_client, wallet_client = maybe_clients
        if node_client is None or wallet_client is None:
            print("Failed to connect to wallet and node")
            return

        try:
            spends = []
            with open(bundle_input, "rb") as f:
                spends_bytes = pickle.load(f)
            for spend_bytes in spends_bytes:
                spends.append(SpendBundle.from_bytes(spend_bytes))

            minter = Minter(wallet_client, node_client)
            await minter.submit_spend_bundles(spends, fee, create_sell_offer=create_sell_offer)

        finally:
            node_client.close()
            wallet_client.close()
            await node_client.await_closed()
            await wallet_client.await_closed()

    asyncio.get_event_loop().run_until_complete(do_command())


def main() -> None:
    asyncio.run(cli())  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
