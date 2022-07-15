# ChiaNFT - WIP

## Instructions
- Install the branch `gw.mint_from_did` here: https://github.com/Chia-Network/chia-blockchain/tree/gw.mint_from_did

- Start testnet wallet and node using this branch

- Generate some test data with: `python factory_metadata.py`

- Generate spend bundles:

```bash
chianft create-mint-spend-bundles -w 2 -a txch1q02aryjymlslllpauhu7rhk3802lk3e5peuce8gy947dnggpegysqegkzk -r 300 metadata.csv output.pkl
```

- Submit spend bundles:

```bash
chianft submit-spend-bundles -f 100 output.pkl
```

## TODO:
- Add the fee transaction to the submit-spend-bundles function
- Create the offer files for each spend bundle
- Make setup.py
- Write CLI tests
- flake8 and mypy


# Tool Specification

The mint tool will be a Command Line Interface (CLI) tool. It will have commands and options that can be specified by the user to control settings they wish to configure. The mint process will be split into two phases: offline spend bundle creation and online spend bundle submission.

The program itself will be called: chianft
## Phase 1: Spend Bundle Creation
The program will have a create-mint-spend-bundles command
This option will accept the following parameters

`(Required) –input <filename>`
This option will provide the name of a CSV file containing the on-chain metadata for each NFT to be minted

**Fields:**
data_url, data_hash, metadata_url, metadata_hash, license_url, license_hash, edition_number, edition_count, owner_address
The owner address is optional

`(Optional) –minter-did`
This option will specify a DID that should be used as the minter

`(Optional) –enable-did`
This option will indicate if a DID inner puzzle should be used. If not specified, then DID will not be supported for this NFT (i.e. NFT0)

`(Optional) –royalty-amount <amount>`
This option specifies the percentage amount of a royalty that should be paid on transfer.
Requires –enable-did

`(Optional) –royalty-address <address>`
This option specifies the address that royalty payments should be paid to on transfer.
Requires –enable-did

`(Required) –output <filename>`
This option specifies the file that should be used to store the generated spend bundles. 

## Phase 2: Spend Bundle Submission
The program will have a submit-spend-bundles command
This option will accept the following parameters:

`(Required) –input <filename>`
This option will provide the name of the file outputted by the create-mint-spend-bundles command

`(Optional) –fee-per-cost <cost>`
This option will provide the number of mojos that should be paid for each cost of the spend bundle as a fee.

`(Optional) –assign-did <did>`
This option will provide the DID that should be used to assign as the owner of the NFT.

`(Optional) –create-sell-offer <amount>`
This option will specify if an offer file should be created to sell each NFT. The offer files will be saved in an “offers” subdirectory.
If the command stops before submitting all the spend bundles, it should be able to resume where it left off.

Process should be displayed as spend bundles are submitted to the mempool:
`Progress output: Queued: x Mempool: y Complete: z`

