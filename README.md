# EligibleBid — Sealed-Bid Reverse Auction with AI Technical Eligibility Adjudication

[![GenLayer StudioNet](https://img.shields.io/badge/GenLayer-StudioNet%20(61999)-blue)](https://explorer-studio.genlayer.com/address/0x3A812834111e536A690eb25cAc21c7cB8d5cC9A5)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

> **Category**: GenLayer Portal — Builder -> Intelligent Contracts  
> **Deployed Contract Address**: [`0x3A812834111e536A690eb25cAc21c7cB8d5cC9A5`](https://explorer-studio.genlayer.com/address/0x3A812834111e536A690eb25cAc21c7cB8d5cC9A5)  
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
| **0** | `Deploy` | `0x2457...932E` | [`0x10973a...`](https://explorer-studio.genlayer.com/tx/0x10973a66b609504dec4829750cc6f674e7dd038510408a409e76c4db9451f7e9) | `FINALIZED` | Contract deployed at `0x3A81...C9A5` |
| **1** | `create_auction` | `0x2457...932E` | [`0x646573...`](https://explorer-studio.genlayer.com/tx/0x6465730dc32f42c7e84dd7271c75752ad61a39f801b3e23728915a743278606f) | `FINALIZED` | Auction 0 initialized in `COMMIT` phase |
| **2** | `submit_bid_commitment` | `0x2457...932E` | [`0x1613f6...`](https://explorer-studio.genlayer.com/tx/0x1613f61e08f2984ddef98eda1245a95518baeee6f85a1c7502a37ad57237e8b9) | `FINALIZED` | Blind hash bound to proposal content SHA-256 committed |
| **3** | `reveal_bid` (Early Attempt) | `0x2457...932E` | [`0x900019...`](https://explorer-studio.genlayer.com/tx/0x900019f829a081f0c861d8497d42d85221627ea179e9836e280e44dc843ba3fb) | `FINALIZED` | **DEFENSE**: Reverts on-chain during `COMMIT` phase |
| **4** | `close_commit_phase` | `0x2457...932E` | [`0xa7ba96...`](https://explorer-studio.genlayer.com/tx/0xa7ba969aaf552843501c09c10b5e676fffe5da9a550b7d08b8681b3b4c3053bb) | `FINALIZED` | Creator transitions phase to `REVEAL` |
| **5** | `reveal_bid` (Authorized) | `0x2457...932E` | [`0xe5796a...`](https://explorer-studio.genlayer.com/tx/0xe5796ad81644854176fa7e3273883fabe0ac6bec89aa283f6c3ad7c4b28774c3) | `FINALIZED` | Preimage verified ($80.00 / 8000 cents + content hash) |
| **6** | `adjudicate_bid_eligibility` | `0x2457...932E` | [`0x999fb6...`](https://explorer-studio.genlayer.com/tx/0x999fb646fd858ca1e627bf57001c02df427a58a44665f7871755eb39df37073c) | `FINALIZED` | **`ELIGIBLE`** (Verbatim quote and content hash verified) |
| **7** | `settle_auction` (Early Attempt) | `0x2457...932E` | [`0x619344...`](https://explorer-studio.genlayer.com/tx/0x6193441563df2304942ce4f04a82276e89888771ad25827ea23d8fabf0e09a31) | `FINALIZED` | **DEFENSE**: Reverts on-chain during `REVEAL` phase |
| **8** | `close_reveal_phase` | `0x2457...932E` | [`0xab3af3...`](https://explorer-studio.genlayer.com/tx/0xab3af3359a121bc214631651634109443af725c512d218935d8ce6302ac4394c) | `FINALIZED` | Creator transitions phase to `SETTLE` |
| **9** | `settle_auction` (Final Settle) | `0x2457...932E` | [`0x727c08...`](https://explorer-studio.genlayer.com/tx/0x727c08a55cbd11886696da4507e7e3cbdcaa2b807f09cd1e71d00e8d31d63838) | `FINALIZED` | **FINALIZED**: Contract awarded to lowest ELIGIBLE bid ($80) |

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
