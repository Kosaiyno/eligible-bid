# EligibleBid — Sealed-Bid Reverse Auction with AI Technical Eligibility Adjudication

[![GenLayer StudioNet](https://img.shields.io/badge/GenLayer-StudioNet%20(61999)-blue)](https://explorer-studio.genlayer.com/address/0x94947818bd8225cf826dE45E450833f86CB92F88)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

> **Category**: GenLayer Portal — Builder -> Intelligent Contracts  
> **Deployed Contract Address**: [`0x94947818bd8225cf826dE45E450833f86CB92F88`](https://explorer-studio.genlayer.com/address/0x94947818bd8225cf826dE45E450833f86CB92F88)  
> **Proof Manifest**: [`deploy/proof.json`](deploy/proof.json)

---

## 1. Overview & Core Mechanism

In public and decentralized procurement (RFPs / reverse auctions), choosing strictly by the lowest price creates a dangerous "race to the bottom" where contractors submit unrealistically cheap bids with non-compliant, unsafe, or missing technical specifications. Conversely, relying on centralized human review committees invites bribery and bias.

**`EligibleBid`** implements an autonomous, two-tier separation of concerns:
1. **Cryptographic Blind Commit-Reveal**: Bidders submit blinded SHA-256 hashes of their proposal and price during bidding, preventing front-running and undercutting.
2. **Price-Blind AI Eligibility Adjudication**: GenLayer validators independently evaluate the submitted technical specification (pinned on GitHub) against the buyer's mandatory RFP specifications.
   - The LLM **never** sees or judges the price.
   - Validators reach consensus under the **Equivalence Principle** (`gl.eq_principle.prompt_non_comparative`) on discrete outcomes (`ELIGIBLE` vs `INELIGIBLE`) and verify verbatim quotes.
   - Deterministic code enforces a grounding clamp: an `ELIGIBLE` status is rejected if a verifiable verbatim quote is missing.
3. **Deterministic Best-Price Award**: Pure deterministic code filters strictly `ELIGIBLE` bids, throws out non-compliant low-ball bids, and automatically awards the contract to the lowest-priced conforming bidder.

---

## 2. Architecture & Transaction Flow

```
                      +---------------------------------------+
                      |       Buyer Initializes RFP           |
                      |  create_auction(spec_floor, budget)   |
                      +---------------------------------------+
                                          |
                      +---------------------------------------+
                      |       Bidders Blind Commitment        |
                      |  submit_bid_commitment(sha256_hash)   |
                      +---------------------------------------+
                                          |
                      +---------------------------------------+
                      |             Reveal Phase              |
                      |   reveal_bid(price, salt, github_url) |
                      +---------------------------------------+
                                          |
                      +---------------------------------------+
                      |   GenLayer Validator Consensus        |
                      |    adjudicate_bid_eligibility(bid_id) |
                      |    (Price-Blind + Quote Verification) |
                      +---------------------------------------+
                                   /             \
                   [Compliant Specs]             [Adversarial / Missing Specs]
                          |                                    |
                          v                                    v
                     [ELIGIBLE]                           [INELIGIBLE]
                                   \             /
                      +---------------------------------------+
                      |      Deterministic Code Settle        |
                      |         settle_auction(auction_id)    |
                      |  Awards min(price) among ELIGIBLE     |
                      |  (Cheaper INELIGIBLE bids discarded!) |
                      +---------------------------------------+
```

---

## 3. Live StudioNet Verification & Proof Transactions

All steps of the full adversarial lifecycle have been executed and finalized on **GenLayer StudioNet (Chain ID: 61999)**:

| Step | Action | Account | Tx Hash | Consensus | Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0** | `Deploy` | `0x661E...7577` | [`0x76cb6e...`](https://explorer-studio.genlayer.com/tx/0x76cb6e34bc6eaae5f9f1fdc1c0d0b877604d78b85176c27f722532e367363b6a) | `FINALIZED` | Contract deployed at `0x9494...2F88` |
| **1** | `create_auction` | `0x661E...7577` | [`0x939992...`](https://explorer-studio.genlayer.com/tx/0x93999262f933724a6b21ed37c697df87e1fcacffbdf81fcbc11e66367d008cab) | `FINALIZED` | Auction 0 initialized ($100 budget ceiling) |
| **2** | `submit_bid_commitment` (Bidder 1) | `0x661E...7577` | [`0x547639...`](https://explorer-studio.genlayer.com/tx/0x5476394696df1113402c31e4f670e420134cda1dae0ac2f27f9cf68a000690f9) | `FINALIZED` | Blind hash committed for Bid 0 |
| **3** | `reveal_bid` (Bidder 1, $80) | `0x661E...7577` | [`0xf69231...`](https://explorer-studio.genlayer.com/tx/0xf69231ac002b578dd54d04af3d73ca6cf2694d52e864bdbd91a4093407dcfa2d) | `FINALIZED` | Preimage verified ($80.00 / 8000 cents) |
| **4** | `adjudicate_bid_eligibility` (Bid 0) | `0x661E...7577` | [`0x62cd53...`](https://explorer-studio.genlayer.com/tx/0x62cd538b6efb9536ef04afc2f07108f1c7161498a8f38cf034419826cbcaca98) | `FINALIZED` | **`ELIGIBLE`** (Verbatim quote verified) |
| **5** | `submit_bid_commitment` (Bidder 2) | `0x2457...932E` | [`0xfd9e2df...`](https://explorer-studio.genlayer.com/tx/0xfd9e2df1f2c13e170870a454c9ed7db32f60be66c655758d0f41684a65f5c579) | `FINALIZED` | Blind hash committed for Bid 1 |
| **6** | `reveal_bid` (Bidder 2, $20) | `0x2457...932E` | [`0xf375cd...`](https://explorer-studio.genlayer.com/tx/0xf375cdf1cca38c1418722b25823389b2929729a32caa992f7b04b992dded04be) | `FINALIZED` | Preimage verified ($20.00 low-ball!) |
| **7** | `adjudicate_bid_eligibility` (Bid 1) | `0x2457...932E` | [`0x75154e...`](https://explorer-studio.genlayer.com/tx/0x75154e98309feefb941c072650bfc088584230e936fdd81cee1cde665b680653) | `FINALIZED` | **`INELIGIBLE`** (Adversarial prompt injection blocked) |
| **8** | `settle_auction` (Auction 0) | `0x2457...932E` | [`0x87977c...`](https://explorer-studio.genlayer.com/tx/0x87977c2ccd90429ed1d6138676b093a16a3c5a84e4219425e86ac9a37a75d13a) | `FINALIZED` | **CORE INVARIANT PROVEN**: Winner = Bidder 1 at $80. Cheaper $20 bid discarded! |

---

## 4. Local Test Suite Coverage

The automated test suite runs in direct mode with mocked GenLayer primitives:

```powershell
uv run python -m unittest tests/test_eligible_bid.py
```

### Coverage (8 Passing Tests):
- `test_initialization`: Zero state, counter tracking, and owner binding.
- `test_create_auction_validations`: Enforces non-empty title, spec floor, and positive budget ceiling.
- `test_commitment_and_anti_replay`: Hash validation and anti-replay blocking duplicate bids.
- `test_reveal_unauthorized_callers`: Unauthorized reveal rejected; price cap enforcement; tampered preimage rejection.
- `test_adjudication_fail_closed`: Network errors and empty proposals fail closed to `INELIGIBLE`.
- `test_adversarial_leader_quote_clamp`: Missing quote forcefully clamped to `INELIGIBLE`.
- `test_settlement_core_invariant_cheapest_eligible_wins`: Confirms \$80 conforming bid defeats \$20 low-baller.
- `test_settlement_void_when_no_eligible_bids`: Correctly transitions to `VOID_NO_BIDS`.

---

## 5. Honest Limitations
- **Synthetic Monetary Units**: Bids are currently denominated in integer cents (`u256`) rather than native ERC-20 token escrows to preserve execution speed on testnet.
- **Evidence Formatting**: Relies on raw UTF-8 markdown payloads under 3,000 bytes hosted on immutable git commit SHAs or tags.
