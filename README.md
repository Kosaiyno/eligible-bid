# EligibleBid — Sealed-Bid Reverse Auction with AI Technical Eligibility Adjudication

[![GenLayer StudioNet](https://img.shields.io/badge/GenLayer-StudioNet%20(61999)-blue)](https://explorer-studio.genlayer.com/address/0x8aC38b5a7F25722e33a97e618d8b54cF48D553BA)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

> **Category**: GenLayer Portal — Builder -> Intelligent Contracts  
> **Deployed Contract Address**: [`0x8aC38b5a7F25722e33a97e618d8b54cF48D553BA`](https://explorer-studio.genlayer.com/address/0x8aC38b5a7F25722e33a97e618d8b54cF48D553BA)  
> **Proof Manifest**: [`deploy/proof.json`](deploy/proof.json)

---

## 1. Overview & Core Mechanism

In public and decentralized procurement (RFPs / reverse auctions), choosing strictly by the lowest price creates a dangerous "race to the bottom" where contractors submit unrealistically cheap bids with non-compliant, unsafe, or missing technical specifications. Conversely, relying on centralized human review committees invites bribery and bias.

**`EligibleBid`** implements an autonomous, two-tier separation of concerns:
1. **Strict Auction Phase Machine**: Enforces discrete boundaries (`COMMIT` $\rightarrow$ `REVEAL` $\rightarrow$ `SETTLE`). Early reveals during `COMMIT` and early settlements during `COMMIT` or `REVEAL` strictly revert on-chain.
2. **Cryptographic Proposal Content Binding**: Blinded commitments bind the exact SHA-256 content hash of the technical proposal: `sha256(bidder_addr + price + salt + proposal_content_hash + proposal_url)`.
3. **Price-Blind AI Eligibility Adjudication**: GenLayer validators independently evaluate the submitted technical specification (pinned on GitHub) against the buyer's mandatory RFP specifications and verify document content integrity.
   - The LLM **never** sees or judges the price.
   - Validators reach consensus under the **Equivalence Principle** (`gl.eq_principle.prompt_non_comparative`) on discrete outcomes (`ELIGIBLE` vs `INELIGIBLE`) and verify verbatim quotes.
   - Deterministic code enforces fail-closed clamps: an `ELIGIBLE` status is downgraded to `INELIGIBLE` if the content hash mismatches or a verifiable verbatim quote is missing.
4. **Deterministic Best-Price Award**: Pure deterministic code filters strictly `ELIGIBLE` bids, throws out non-compliant low-ball bids, and automatically awards the contract to the lowest-priced conforming bidder.

---

## 2. Live StudioNet Verification & Proof Transactions

All steps of the full adversarial lifecycle have been executed and finalized on **GenLayer StudioNet (Chain ID: 61999)**:

| Step | Action | Account | Tx Hash | Consensus | Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0** | `Deploy` | `0x2457...932E` | [`0x2c62e9...`](https://explorer-studio.genlayer.com/tx/0x2c62e97d8e8c1a0bbcac408f78b13d3b19944b1ccae805aefa0a32e244371b73) | `FINALIZED` | Contract deployed at `0x8aC3...53BA` |
| **1** | `create_auction` | `0x2457...932E` | [`0x6a0ceb...`](https://explorer-studio.genlayer.com/tx/0x6a0cebea8fb8515f029696b6965656089af9b493b32b80450d594a793cf94f36) | `FINALIZED` | Auction 0 initialized in `COMMIT` phase |
| **2** | `submit_bid_commitment` | `0x2457...932E` | [`0x723f1b...`](https://explorer-studio.genlayer.com/tx/0x723f1b8ded81301ceb608de6ced4430524754e1c9511c97d52961b856d37a398) | `FINALIZED` | Blind hash bound to proposal content SHA-256 committed |
| **3** | `reveal_bid` (Early Attempt) | `0x2457...932E` | [`0x5e42ec...`](https://explorer-studio.genlayer.com/tx/0x5e42ecfb46086898c30364d54f33233568fbdbc21300582d146bf54db18ac892) | `FINALIZED` | **DEFENSE**: Reverts on-chain during `COMMIT` phase |
| **4** | `close_commit_phase` | `0x2457...932E` | [`0x787065...`](https://explorer-studio.genlayer.com/tx/0x78706534adb2fe1ed2902b8e8092d945376448840555246549e7116cfd7deecc) | `FINALIZED` | Creator transitions phase to `REVEAL` |
| **5** | `reveal_bid` (Authorized) | `0x2457...932E` | [`0xd43d84...`](https://explorer-studio.genlayer.com/tx/0xd43d849a2f69d9667d3ebd41323ca40f22683383d1b3017f0d055ccbe9467b00) | `FINALIZED` | Preimage verified ($80.00 / 8000 cents + content hash) |
| **6** | `adjudicate_bid_eligibility` | `0x2457...932E` | [`0xc60196...`](https://explorer-studio.genlayer.com/tx/0xc60196c3fec6b0f806622d3949ebf266dcd00bdf405bb83c2b04d4f39508b1ac) | `FINALIZED` | **`ELIGIBLE`** (Verbatim quote and content hash verified) |
| **7** | `close_reveal_phase` | `0x2457...932E` | [`0xf39f10...`](https://explorer-studio.genlayer.com/tx/0xf39f10113f116d379ecc307dfb0dfff367545badb05e346ebffb7007aef43ef0) | `FINALIZED` | Creator transitions phase to `SETTLE` |
| **8** | `settle_auction` (Final Settle) | `0x2457...932E` | [`0x43cbce...`](https://explorer-studio.genlayer.com/tx/0x43cbcebbc0f9259942f01fe10dc059369c9fa0b9d30dbd4052eb9eeabd1e75fb) | `FINALIZED` | **FINALIZED**: Contract awarded to lowest ELIGIBLE bid ($80) |

---

## 3. Local Test Suite Coverage

The automated test suite runs in direct mode with mocked GenLayer primitives:

```powershell
uv run python -m unittest discover -s tests
```

### Coverage (9 Passing Tests):
- `test_initialization`: Zero state, counter tracking, and owner binding.
- `test_create_auction_validations_and_initial_phase`: Enforces non-empty title, spec floor, positive ceiling, and initial `COMMIT` phase.
- `test_commitment_and_anti_replay`: Hash validation and anti-replay blocking duplicate bids.
- `test_phase_boundaries_early_reveal_and_early_settle_blocked`: Strict phase enforcement blocking early reveals and settlements.
- `test_reveal_unauthorized_callers_and_preimage_tampering`: Unauthorized reveal rejected; price cap enforcement; tampered content hash / price preimage rejection.
- `test_adjudication_fail_closed_on_tampered_content_hash`: Content hash tampering fails closed to `INELIGIBLE`.
- `test_settlement_core_invariant_cheapest_eligible_wins`: Confirms \$80 conforming bid defeats \$20 low-baller.
- `test_settlement_void_when_no_eligible_bids`: Correctly transitions to `VOID_NO_BIDS`.
- `test_adversarial_leader_quote_clamp`: Missing quote forcefully clamped to `INELIGIBLE`.
