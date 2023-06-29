# ChiaNFT

For detailed setup and testing instructions, visit the [NFT Bulk Minting tool](https://docs.chia.net/guides/nft-bulk-mint) page on Chia Docs.

## Setup Instructions
- Stop any running wallet/node instances: `chia stop -d all`

- Clone this repo, create/activate a new virtual environment and update pip. Note instructions for createing the python venv may vary depending on your OS
```bash
git clone https://github.com/Chia-Network/chia-nft-minting-tool.git
cd chia-nft-minting-tool
python3 -m venv venv
source ./venv/bin/activate
pip install --upgrade pip
```

- Install chianft and the necessary chia-blockchain branch (make sure to include the '.' at the end):
```bash
pip install --extra-index https://pypi.chia.net/simple/ --editable .
```

- Start testnet wallet and node: `chia start wallet`, and `chia start node`

- Create a fresh wallet `chia keys generate` and fund it with 2 coins (testnet faucet: https://testnet10-faucet.chia.net/; mainnet faucet: https://faucet.chia.net/), small amounts like 0.001 (t)xch are fine

- Create a DID for the wallet: `chia wallet did create`. This creates an NFT wallet with the DID id

- Create a regular NFT wallet (where our minted NFTs will be stored since we don't attach the DID during minting): `chia wallet nft create`

- Make sure the wallet and node are fully synced `chia wallet show` and `chia show -s` respectively

## Usage Examples

### Test 1 - Mint and air-drop to targets.
This test will create 100 NFTs and air-drop them to a target address

1. Generate the factory data. The "t" flag indicates we should include a target address in the metadata csv and 100 indicates the number of nfts to generate.
```bash
python factory_metadata.py t 100
```
2. Create the spend bundles. Here the -w is the wallet ID for the NFT wallet, -t True indicates we have targets in the metadata csv,  -a and -r are the royalty address and percentage.

```bash
chianft create-mint-spend-bundles -w 3 -d True -a txch1q02aryjymlslllpauhu7rhk3802lk3e5peuce8gy947dnggpegysqegkzk -r 300 -t True metadata.csv output.pkl
```
Non-did version:
```
chianft create-mint-spend-bundles -w 3 -d False -a txch1q02aryjymlslllpauhu7rhk3802lk3e5peuce8gy947dnggpegysqegkzk -r 300 -t True metadata.csv output.pkl
```

3. Submit the spend bundles created in output.pkl. The -m flag is for the flat fee used for each spend bundle of 25 NFTs

```bash
chianft submit-spend-bundles -m 1000 output.pkl
```

### Test 2 - Mint and create offers for each NFT
This test will create 100 NFTs and send them to your own wallet while creating sell offer files for each NFT

1. Generate the factory data. Don't use a "t" for target flag since we want to mint to our own wallet

```bash
python factory_metadata.py 1000
```
2. Create the spend bundles.  No -t flag here since we aren't transferring the NFTs out of our wallet.

```bash
chianft create-mint-spend-bundles -w 3 -d True -a txch1q02aryjymlslllpauhu7rhk3802lk3e5peuce8gy947dnggpegysqegkzk -r 300 metadata.csv output.pkl
```
Non-did version:
```bash
chianft create-mint-spend-bundles -w 3 -d False -a txch1q02aryjymlslllpauhu7rhk3802lk3e5peuce8gy947dnggpegysqegkzk -r 300 metadata.csv output.pkl
```

3. Submit the spend bundles created in output.pkl. Here the -o flag indicates we want to create an offer file for each NFT with a trade price of 1000 mojo

```bash
chianft submit-spend-bundles -m 1000000 -o 1000 output.pkl
```

## Testing
Tests are located in the tests directory. To run them, make sure to install the tool with dev dependencies:

```bash
pip install --extra-index https://pypi.chia.net/simple/ --editable .[dev]
```

Then you need to setup the simulator, run the wallet, and create a DID:
```
chia init
chia dev sim create
export CHIA_ROOT=~/.chia/simulator/main/
chia start wallet
chia wallet did create
```

Now, you can run the tests:
```bash
pytest tests/test_mint.py
```

# Tool Specification

The mint tool will be a Command Line Interface (CLI) tool. It will have commands and options that can be specified by the user to control settings they wish to configure. The mint process will be split into two phases: offline spend bundle creation and online spend bundle submission.

The program itself will be called: chianft
## Phase 1: Spend Bundle Creation
The program will have a create-mint-spend-bundles command
This option will accept the following parameters


`(Optional) -r –-royalty-amount <amount>`
This option specifies the percentage amount of a royalty that should be paid on transfer.
Requires –enable-did

`(Optional) -a –-royalty-address <address>`
This option specifies the address that royalty payments should be paid to on transfer.
Requires –enable-did

`(Optional) -t --has-targets <True/False>`
This option determines whether the spend bundles will include an extra spend to sent the created NFTs to a target address specified in the targets field of the input csv.

`(Required) -w --wallet-id <int>`
The NFT wallet ID you  want to use for minting. It is a requirement that this NFT have an associated DID.

`(Required) –-input <filename>`
This option will provide the name of a CSV file containing the on-chain metadata for each NFT to be minted

**Fields:**
data_url, dapfta_hash, metadata_url, metadata_hash, license_url, license_hash, edition_number, edition_count, target
The target address is optional and is used when you want to air-drop NFTs once they've been minted.

`(Required) –-output <filename>`
This option specifies the file that should be used to store the generated spend bundles.


## Phase 2: Spend Bundle Submission
The program will have a submit-spend-bundles command
This option will accept the following parameters:

`(Required) <filename>`
This option will provide the name of the file outputted by the create-mint-spend-bundles command

`(Optional) –fee <cost>`
This option will provide the number of mojos that should be paid for each spend bundle as a flat fee.

`(Optional) -o –create-sell-offer <amount>`
This option will specify if an offer file should be created to sell each NFT. The offer files will be saved in an “offers” subdirectory.
If the command stops before submitting all the spend bundles, it should be able to resume where it left off.

Process should be displayed as spend bundles are submitted to the mempool:
`Progress output: Queued: x Mempool: y Complete: z`
