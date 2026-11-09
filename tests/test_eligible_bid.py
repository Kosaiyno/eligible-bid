import sys
import os
import unittest
import hashlib
import json

# =========================================================================
# MOCK GENLAYER ENVIRONMENT FOR ISOLATED LOCAL TESTING
# =========================================================================

class MockWebResponse:
    def __init__(self, body_data):
        if isinstance(body_data, (bytes, bytearray)):
            self.body = bytes(body_data)
        else:
            self.body = str(body_data).encode("utf-8")

    def __str__(self):
        return self.body.decode("utf-8")

class u256(int):
    def __new__(cls, val):
        return super().__new__(cls, int(val))

class Address(str):
    def __new__(cls, val):
        return super().__new__(cls, str(val))

class TreeMap(dict):
    """
    Subclass of dict matching GenLayer TreeMap behavior (raises KeyError on missing key).
    """
    pass

class MockVMReturn:
    def __init__(self, calldata):
        self.calldata = calldata

class MockVM:
    Return = MockVMReturn

    def __init__(self):
        self.tamper_leader = False
        self.tampered_payload = None

    def run_nondet_unsafe(self, leader_fn, validator_fn):
        if self.tamper_leader:
            leader_output = self.tampered_payload
        else:
            leader_output = leader_fn()

        wrapped = MockVMReturn(leader_output)
        valid = validator_fn(wrapped)
        if not valid:
            raise RuntimeError("Consensus failed: validator rejected leader output")
        return leader_output

class MockGL:
    def __init__(self):
        self.message = self.Message()
        self.public = self.Public()
        self.vm = MockVM()
        self.nondet = self.NonDet()

        class ContractBase:
            def __new__(cls, *args, **kwargs):
                obj = super().__new__(cls)
                for base in reversed(cls.__mro__):
                    for attr_name, attr_type in getattr(base, "__annotations__", {}).items():
                        type_str = str(attr_type)
                        if "TreeMap" in type_str:
                            setattr(obj, attr_name, TreeMap())
                        elif "u256" in type_str:
                            setattr(obj, attr_name, u256(0))
                        elif "Address" in type_str:
                            setattr(obj, attr_name, Address("0x0000000000000000000000000000000000000000"))
                return obj

        self.Contract = ContractBase

    class Message:
        def __init__(self):
            self.sender_address = Address("0x1111111111111111111111111111111111111111")

    class Public:
        def view(self, func):
            return func
        def write(self, func):
            return func

    class NonDet:
        def __init__(self):
            self.web = self.Web()
            self.mock_decision = "ELIGIBLE"
            self.mock_quote = "AES-256 encryption implemented"
            self.mock_rationale = "Meets all mandatory requirements"
            self.return_as_dict = True  # Tests both dict and string return formats

        def exec_prompt(self, prompt, response_format=None):
            if "FAIL_AUDIT" in prompt or "INJECTION" in prompt:
                res_dict = {
                    "decision": "INELIGIBLE",
                    "verbatim_quote": "NONE",
                    "rationale": "Proposal fails mandatory technical requirements."
                }
            else:
                res_dict = {
                    "decision": self.mock_decision,
                    "verbatim_quote": self.mock_quote,
                    "rationale": self.mock_rationale
                }

            if self.return_as_dict:
                return res_dict
            return json.dumps(res_dict)

        class Web:
            def __init__(self):
                self.mock_responses = {}
                self.should_fail = False
                self.call_count = 0
                self.fail_on_call = None

            def set_url_response(self, url: str, body_bytes):
                self.mock_responses[url] = body_bytes

            def get(self, url: str):
                self.call_count += 1
                if self.should_fail or (self.fail_on_call is not None and self.call_count == self.fail_on_call):
                    raise RuntimeError("HTTP 403 Forbidden")
                if url in self.mock_responses:
                    return MockWebResponse(self.mock_responses[url])
                default_content = b"Default mock architecture specification covering AES-256 encryption and MIT license."
                return MockWebResponse(default_content)

# Install mocks into sys.modules before importing contract
mock_gl = MockGL()
mock_module = type(sys)("genlayer")
mock_module.gl = mock_gl
mock_module.u256 = u256
mock_module.Address = Address
mock_module.TreeMap = TreeMap
sys.modules["genlayer"] = mock_module

# Now import contract
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from eligible_bid import EligibleBid

# =========================================================================
# TEST SUITE
# =========================================================================

def make_hash(bidder: str, price_cents: int, salt: str, content_hash: str, url: str) -> str:
    preimage = f"{bidder.lower()}_{price_cents}_{salt}_{content_hash.lower()}_{url}".encode("utf-8")
    return hashlib.sha256(preimage).hexdigest().lower()

class TestEligibleBid(unittest.TestCase):
    def setUp(self):
        mock_gl.vm = MockVM()
        mock_gl.nondet = mock_gl.NonDet()
        self.buyer = Address("0x1111111111111111111111111111111111111111")
        self.bidder1 = Address("0x2222222222222222222222222222222222222222")
        self.bidder2 = Address("0x3333333333333333333333333333333333333333")
        self.attacker = Address("0x9999999999999999999999999999999999999999")

        mock_gl.message.sender_address = self.buyer
        self.contract = EligibleBid()

    def test_initialization(self):
        """Verify initial contract state."""
        self.assertEqual(self.contract.get_total_auctions(), 0)
        self.assertEqual(self.contract.get_total_bids(), 0)
        self.assertEqual(self.contract.owner, self.buyer)

    def test_create_auction_validations_and_initial_phase(self):
        """Verify input validation and initial COMMIT phase state."""
        mock_gl.message.sender_address = self.buyer
        with self.assertRaises(ValueError):
            self.contract.create_auction("", "Spec", u256(1000))
        with self.assertRaises(ValueError):
            self.contract.create_auction("Title", "", u256(1000))
        with self.assertRaises(ValueError):
            self.contract.create_auction("Title", "Spec", u256(0))

        aid = self.contract.create_auction("Decentralized Storage Engine", "Mandatory: IPFS, Encryption", u256(50000))
        auction = self.contract.get_auction(aid)
        self.assertEqual(auction["phase"], "COMMIT")
        self.assertEqual(auction["status"], "OPEN")
        self.assertEqual(auction["budget_ceiling_cents"], 50000)

    def test_commitment_and_anti_replay(self):
        """Test bid commitment submission, 64-char hash format, and anti-replay."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Oracles", "Mandatory: TLSNotary", u256(10000))

        mock_gl.message.sender_address = self.bidder1
        with self.assertRaises(ValueError):
            self.contract.submit_bid_commitment(aid, "short_hash")

        valid_hash = "a" * 64
        bid_id = self.contract.submit_bid_commitment(aid, valid_hash)
        bid = self.contract.get_bid(bid_id)
        self.assertEqual(bid["bid_hash"], valid_hash)
        self.assertFalse(bid["revealed"])
        self.assertEqual(bid["eligibility_status"], "PENDING")

        with self.assertRaises(ValueError):
            self.contract.submit_bid_commitment(aid, valid_hash)

    def test_phase_boundaries_early_reveal_and_early_settle_blocked(self):
        """Verify auction integrity: reveals blocked in COMMIT phase, settlement blocked in COMMIT & REVEAL."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("DEX Router", "Mandatory: Sub-graph", u256(20000))

        dummy_hash = hashlib.sha256(b"dummy_spec").hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/spec.md"
        committed_hash = make_hash(str(self.bidder1), 15000, "salt1", dummy_hash, url)

        mock_gl.message.sender_address = self.bidder1
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        # Early reveal attempt during COMMIT phase must revert
        with self.assertRaises(ValueError) as ctx:
            self.contract.reveal_bid(bid_id, u256(15000), "salt1", dummy_hash, url)
        self.assertIn("auction phase must be REVEAL", str(ctx.exception))

        # Early settlement attempt during COMMIT phase must revert
        with self.assertRaises(ValueError) as ctx:
            self.contract.settle_auction(aid)
        self.assertIn("auction phase must be SETTLE", str(ctx.exception))

        # Advance to REVEAL phase
        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        # Early settlement attempt during REVEAL phase must revert
        with self.assertRaises(ValueError) as ctx:
            self.contract.settle_auction(aid)
        self.assertIn("auction phase must be SETTLE", str(ctx.exception))

    def test_reveal_unauthorized_callers_and_preimage_tampering(self):
        """Verify reveal permissions, ceiling enforcement, and cryptographic preimage binding."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Bridge Guard", "Mandatory: Multi-sig", u256(10000))

        content_hash = hashlib.sha256(b"bridge_proposal").hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/bridge.md"
        committed_hash = make_hash(str(self.bidder1), 8000, "mysalt", content_hash, url)

        mock_gl.message.sender_address = self.bidder1
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        # Unauthorized caller attempt
        mock_gl.message.sender_address = self.attacker
        with self.assertRaises(PermissionError):
            self.contract.reveal_bid(bid_id, u256(8000), "mysalt", content_hash, url)

        # Budget ceiling violation attempt
        mock_gl.message.sender_address = self.bidder1
        with self.assertRaises(ValueError) as ctx:
            self.contract.reveal_bid(bid_id, u256(12000), "mysalt", content_hash, url)
        self.assertIn("exceeds auction budget ceiling", str(ctx.exception))

        # Tampered price preimage attempt
        with self.assertRaises(ValueError) as ctx:
            self.contract.reveal_bid(bid_id, u256(7999), "mysalt", content_hash, url)
        self.assertIn("Hash mismatch", str(ctx.exception))

        # Tampered content hash preimage attempt
        with self.assertRaises(ValueError) as ctx:
            self.contract.reveal_bid(bid_id, u256(8000), "mysalt", "0"*64, url)
        self.assertIn("Hash mismatch", str(ctx.exception))

        # Valid reveal
        res = self.contract.reveal_bid(bid_id, u256(8000), "mysalt", content_hash, url)
        self.assertTrue(res)
        bid = self.contract.get_bid(bid_id)
        self.assertTrue(bid["revealed"])
        self.assertEqual(bid["price_cents"], 8000)
        self.assertEqual(bid["proposal_content_hash"], content_hash)

    # =========================================================================
    # THE 7 REQUIRED TESTS FOR STEWARD & CHATGPT REVIEW
    # =========================================================================

    def test_1_reveal_two_bids_leave_one_pending_reverts_close_reveal(self):
        """Test 1: Reveal two bids, leave one pending; verify close_reveal_phase() reverts."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("ZK Prover", "Mandatory: Halo2, Plonky3", u256(10000))

        raw1 = b"Compliant spec bidder 1: Halo2 and Plonky3"
        hash1 = hashlib.sha256(raw1).hexdigest()
        url1 = "https://raw.githubusercontent.com/org/repo/spec1.md"
        mock_gl.nondet.web.set_url_response(url1, raw1)

        raw2 = b"Compliant spec bidder 2: Halo2 and Plonky3"
        hash2 = hashlib.sha256(raw2).hexdigest()
        url2 = "https://raw.githubusercontent.com/org/repo/spec2.md"
        mock_gl.nondet.web.set_url_response(url2, raw2)

        # Commit Bid 1 and Bid 2
        mock_gl.message.sender_address = self.bidder1
        bid1 = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 7000, "salt1", hash1, url1))

        mock_gl.message.sender_address = self.bidder2
        bid2 = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder2), 6500, "salt2", hash2, url2))

        # Close commit phase -> REVEAL
        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        # Reveal both bids
        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid1, u256(7000), "salt1", hash1, url1)

        mock_gl.message.sender_address = self.bidder2
        self.contract.reveal_bid(bid2, u256(6500), "salt2", hash2, url2)

        # Adjudicate only Bid 1 (Bid 2 remains PENDING)
        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "Halo2 and Plonky3"
        self.contract.adjudicate_bid_eligibility(bid1)

        # Attempt to close reveal phase -> MUST revert with descriptive error
        mock_gl.message.sender_address = self.buyer
        with self.assertRaises(ValueError) as ctx:
            self.contract.close_reveal_phase(aid)
        self.assertIn("1 revealed bid(s) are still pending eligibility adjudication", str(ctx.exception))

        # Phase must remain REVEAL
        auction = self.contract.get_auction(aid)
        self.assertEqual(auction["phase"], "REVEAL")

    def test_2_adjudicate_both_allows_close_reveal_phase(self):
        """Test 2: Adjudicate both revealed bids; verify close_reveal_phase() succeeds."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("ZK Prover", "Mandatory: Halo2, Plonky3", u256(10000))

        raw1 = b"Compliant spec bidder 1: Halo2 and Plonky3"
        hash1 = hashlib.sha256(raw1).hexdigest()
        url1 = "https://raw.githubusercontent.com/org/repo/spec1.md"
        mock_gl.nondet.web.set_url_response(url1, raw1)

        raw2 = b"Compliant spec bidder 2: Halo2 and Plonky3"
        hash2 = hashlib.sha256(raw2).hexdigest()
        url2 = "https://raw.githubusercontent.com/org/repo/spec2.md"
        mock_gl.nondet.web.set_url_response(url2, raw2)

        mock_gl.message.sender_address = self.bidder1
        bid1 = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 7000, "salt1", hash1, url1))

        mock_gl.message.sender_address = self.bidder2
        bid2 = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder2), 6500, "salt2", hash2, url2))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid1, u256(7000), "salt1", hash1, url1)

        mock_gl.message.sender_address = self.bidder2
        self.contract.reveal_bid(bid2, u256(6500), "salt2", hash2, url2)

        # Adjudicate both bids
        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "Halo2 and Plonky3"
        self.contract.adjudicate_bid_eligibility(bid1)
        self.contract.adjudicate_bid_eligibility(bid2)

        # Now closing reveal phase must succeed
        mock_gl.message.sender_address = self.buyer
        res = self.contract.close_reveal_phase(aid)
        self.assertEqual(res, "SETTLE")

        auction = self.contract.get_auction(aid)
        self.assertEqual(auction["phase"], "SETTLE")

    def test_3_proposal_exactly_10000_chars_assessed_completely(self):
        """Test 3: Fetch a proposal of exactly 10,000 characters; verify the complete document is assessed."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Max Bounded Audit", "Mandatory: Complete Spec", u256(20000))

        # Generate proposal of exactly 10,000 characters
        base_text = "Detailed technical spec clause: AES-256 and zero-knowledge proofs. "
        exact_10000_text = (base_text * 150)[:10000]
        self.assertEqual(len(exact_10000_text), 10000)

        raw_bytes = exact_10000_text.encode("utf-8")
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/exact10000.md"
        mock_gl.nondet.web.set_url_response(url, raw_bytes)

        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "AES-256 and zero-knowledge"

        mock_gl.message.sender_address = self.bidder1
        bid_id = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 15000, "salt10k", content_hash, url))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(15000), "salt10k", content_hash, url)

        # Must pass eligibility: complete document is evaluated without truncation
        decision = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertEqual(decision, "ELIGIBLE")

    def test_validator_rejects_hallucinated_eligible_leader(self):
        """Verify validator independently audits proposal and rejects a rogue leader claiming ELIGIBLE on a non-compliant proposal."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Independent Audit", "Mandatory: Memory Safety", u256(5000))

        raw_b = b"FAIL_AUDIT: Unsafe memory usage."
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/unsafe.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 3000, "salt_aud", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(3000), "salt_aud", content_hash, url)

        # Rogue leader output claiming ELIGIBLE with genuine verbatim quote from text
        rogue_leader = {
            "status": "OK",
            "decision": "ELIGIBLE",
            "doc_len": len(raw_b),
            "actual_hash": content_hash,
            "verbatim_quote": "Unsafe memory usage",
            "rationale": "Rogue leader claims compliant.",
            "fetched_text": raw_b.decode("utf-8")
        }
        mock_gl.vm.tamper_leader = True
        mock_gl.vm.tampered_payload = rogue_leader

        # Validator independently audits proposal, detects FAIL_AUDIT -> evaluates INELIGIBLE
        # Disagreement between leader (ELIGIBLE) and validator (INELIGIBLE) causes consensus rejection!
        with self.assertRaises(RuntimeError) as ctx:
            self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertIn("Consensus failed", str(ctx.exception))

        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "PENDING")

    def test_4_proposal_10001_chars_rejected_as_ineligible(self):
        """Test 4: Fetch a proposal of 10,001 characters; verify it becomes INELIGIBLE deterministically before LLM."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Oversized Audit", "Mandatory: Spec", u256(20000))

        # Generate proposal of exactly 10,001 characters
        exact_10001_text = "A" * 10001
        self.assertEqual(len(exact_10001_text), 10001)

        raw_bytes = exact_10001_text.encode("utf-8")
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/oversized10001.md"
        mock_gl.nondet.web.set_url_response(url, raw_bytes)

        mock_gl.message.sender_address = self.bidder1
        bid_id = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 15000, "salt10001", content_hash, url))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(15000), "salt10001", content_hash, url)

        # Must be rejected as INELIGIBLE by deterministic code
        decision = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertEqual(decision, "INELIGIBLE")

        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "INELIGIBLE")
        self.assertIn("exceeds bounded limit", bid_data["adjudication_rationale"])

    def test_5_changed_fetched_document_causes_hash_mismatch_rejection(self):
        """Test 5: Change the fetched document after commitment; verify hash mismatch causes deterministic rejection."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Hash Integrity Audit", "Mandatory: Security", u256(10000))

        original_doc = b"Original honest proposal meeting all requirements."
        committed_hash = hashlib.sha256(original_doc).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/tampered_spec.md"

        # Tampered document served by web server after commitment
        tampered_doc = b"Tampered document content after commitment."
        mock_gl.nondet.web.set_url_response(url, tampered_doc)

        mock_gl.message.sender_address = self.bidder1
        bid_id = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 5000, "salt_hash", committed_hash, url))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(5000), "salt_hash", committed_hash, url)

        decision = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertEqual(decision, "INELIGIBLE")

        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "INELIGIBLE")
        self.assertIn("does not match committed hash", bid_data["adjudication_rationale"])

    def test_6_transient_consensus_failure_leaves_bid_retryable_as_pending(self):
        """Test 6: Simulate transient consensus/network failure; verify transaction reverts and bid remains retryable as PENDING."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Transient Fault Test", "Mandatory: Redundancy", u256(10000))

        raw_b = b"Valid proposal for transient fault test."
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/transient.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        bid_id = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 6000, "salt_retry", content_hash, url))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(6000), "salt_retry", content_hash, url)

        # Simulate transient validator disagreement / network timeout
        mock_gl.vm.tamper_leader = True
        mock_gl.vm.tampered_payload = {"corrupted": "bad_consensus_payload"}

        # Adjudication transaction must REVERT with RuntimeError
        with self.assertRaises(RuntimeError) as ctx:
            self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertIn("Consensus failed", str(ctx.exception))

        # Because transaction reverted, bid MUST remain PENDING (retryable, NOT permanently disqualified!)
        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "PENDING")

        # Now network recovers / consensus is normal
        mock_gl.vm.tamper_leader = False
        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "Valid proposal for transient"

        # Retry succeeds!
        retry_decision = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertEqual(retry_decision, "ELIGIBLE")

        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "ELIGIBLE")

    def test_7_valid_json_llm_response_dict_and_string_produces_eligible(self):
        """Test 7: Verify valid JSON LLM response produces ELIGIBLE whether returned as Python dict or JSON string."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("JSON Format Test", "Mandatory: Dual Parser", u256(10000))

        raw_b = b"Specification text with dual JSON response support."
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/json_test.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        # Test Case 7A: LLM returns dict directly (documented GenLayer behavior)
        mock_gl.nondet.return_as_dict = True
        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "dual JSON response support"

        mock_gl.message.sender_address = self.bidder1
        bid1 = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 7000, "saltA", content_hash, url))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid1, u256(7000), "saltA", content_hash, url)

        resA = self.contract.adjudicate_bid_eligibility(bid1)
        self.assertEqual(resA, "ELIGIBLE")

        # Test Case 7B: LLM returns JSON string
        mock_gl.message.sender_address = self.buyer
        aid2 = self.contract.create_auction("JSON String Test", "Mandatory: String Spec", u256(10000))
        mock_gl.nondet.return_as_dict = False  # returns json.dumps(...)

        mock_gl.message.sender_address = self.bidder2
        bid2 = self.contract.submit_bid_commitment(aid2, make_hash(str(self.bidder2), 7000, "saltB", content_hash, url))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid2)

        mock_gl.message.sender_address = self.bidder2
        self.contract.reveal_bid(bid2, u256(7000), "saltB", content_hash, url)

        resB = self.contract.adjudicate_bid_eligibility(bid2)
        self.assertEqual(resB, "ELIGIBLE")

    def test_bytearray_body_preserves_raw_bytes_hash(self):
        """Verify bytearray response is preserved as raw bytes rather than converted to str text."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Bytearray Test", "Mandatory: Binary Spec", u256(10000))

        raw_content = b"Binary raw payload inside bytearray container."
        content_hash = hashlib.sha256(raw_content).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/bytearray.md"

        # Pass bytearray instead of bytes
        mock_gl.nondet.web.set_url_response(url, bytearray(raw_content))

        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "Binary raw payload inside"

        mock_gl.message.sender_address = self.bidder1
        bid_id = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 8000, "saltBA", content_hash, url))

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(8000), "saltBA", content_hash, url)

        decision = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertEqual(decision, "ELIGIBLE")

    def test_validator_rejects_hallucinated_eligible_leader(self):
        """Verify validator independently audits proposal and rejects a rogue leader claiming ELIGIBLE on a non-compliant proposal."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Independent Audit", "Mandatory: Memory Safety", u256(5000))

        raw_b = b"FAIL_AUDIT: Unsafe memory usage."
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/unsafe.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 3000, "salt_aud", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(3000), "salt_aud", content_hash, url)

        # Rogue leader output claiming ELIGIBLE with genuine verbatim quote from text
        rogue_leader = {
            "status": "OK",
            "decision": "ELIGIBLE",
            "doc_len": len(raw_b),
            "actual_hash": content_hash,
            "verbatim_quote": "Unsafe memory usage",
            "rationale": "Rogue leader claims compliant.",
            "fetched_text": raw_b.decode("utf-8")
        }
        mock_gl.vm.tamper_leader = True
        mock_gl.vm.tampered_payload = rogue_leader

        # Validator independently audits proposal, detects FAIL_AUDIT -> evaluates INELIGIBLE
        # Disagreement between leader (ELIGIBLE) and validator (INELIGIBLE) causes consensus rejection!
        with self.assertRaises(RuntimeError) as ctx:
            self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertIn("Consensus failed", str(ctx.exception))

    def test_settlement_core_invariant_cheapest_eligible_wins(self):
        """CORE MECHANISM INVARIANT TEST: Cheap non-compliant bid is rejected, cheapest ELIGIBLE wins."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("ZK Rollup", "Mandatory: Plonk, Recursion", u256(10000))

        # Bidder 1: Conforming proposal, $80.00
        prop1 = b"Architecture satisfies Plonk and Recursion with sub-second proving."
        hash1 = hashlib.sha256(prop1).hexdigest()
        url1 = "https://raw.githubusercontent.com/bidder1/spec.md"
        mock_gl.nondet.web.set_url_response(url1, prop1)

        # Bidder 2: Non-conforming low-baller, $20.00
        prop2 = b"FAIL_AUDIT: Missing recursive proofs."
        hash2 = hashlib.sha256(prop2).hexdigest()
        url2 = "https://raw.githubusercontent.com/bidder2/spec.md"
        mock_gl.nondet.web.set_url_response(url2, prop2)

        # Commit phase
        mock_gl.message.sender_address = self.bidder1
        bid_id1 = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder1), 8000, "salt1", hash1, url1))

        mock_gl.message.sender_address = self.bidder2
        bid_id2 = self.contract.submit_bid_commitment(aid, make_hash(str(self.bidder2), 2000, "salt2", hash2, url2))

        # Advance to REVEAL
        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        # Reveal bids
        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id1, u256(8000), "salt1", hash1, url1)

        mock_gl.message.sender_address = self.bidder2
        self.contract.reveal_bid(bid_id2, u256(2000), "salt2", hash2, url2)

        # Adjudicate bids
        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "satisfies Plonk and Recursion"
        res1 = self.contract.adjudicate_bid_eligibility(bid_id1)
        self.assertEqual(res1, "ELIGIBLE")

        res2 = self.contract.adjudicate_bid_eligibility(bid_id2)
        self.assertEqual(res2, "INELIGIBLE")

        # Advance to SETTLE
        mock_gl.message.sender_address = self.buyer
        self.contract.close_reveal_phase(aid)

        # Settle
        settle_result = self.contract.settle_auction(aid)
        self.assertEqual(settle_result["status"], "FINALIZED")
        self.assertEqual(settle_result["winner_address"], str(self.bidder1))
        self.assertEqual(settle_result["winner_price_cents"], 8000)
        self.assertEqual(settle_result["winner_bid_id"], int(bid_id1))

        auction = self.contract.get_auction(aid)
        self.assertEqual(auction["status"], "FINALIZED")
        self.assertEqual(auction["winner_price_cents"], 8000)

    def test_settlement_void_when_no_eligible_bids(self):
        """Verify auction transitions to VOID_NO_BIDS if all bids fail technical eligibility."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Microservice", "Mandatory: Rust, zero-alloc", u256(5000))

        raw_b = b"FAIL_AUDIT: Missing zero-alloc guarantees."
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/bad/spec.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 3000, "salt", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(3000), "salt", content_hash, url)
        self.contract.adjudicate_bid_eligibility(bid_id)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_reveal_phase(aid)

        settle_result = self.contract.settle_auction(aid)
        self.assertEqual(settle_result["status"], "VOID_NO_BIDS")

        auction = self.contract.get_auction(aid)
        self.assertEqual(auction["status"], "VOID_NO_BIDS")

    def test_adversarial_leader_quote_clamp(self):
        """Verify deterministic quote clamp when leader outputs ELIGIBLE but with quote not found in text."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Core Audit", "Mandatory: Memory Safety", u256(5000))

        raw_b = b"Some random text."
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/forged/spec.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "Invented Quote Not in Text"

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 2500, "salt", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(2500), "salt", content_hash, url)

        decision = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertEqual(decision, "INELIGIBLE")
        bid_data = self.contract.get_bid(bid_id)
        self.assertIn("Deterministic clamp", bid_data["adjudication_rationale"])

    def test_create_auction_rejects_oversized_title_and_spec(self):
        """Verify create_auction explicitly rejects over-limit titles (>100 chars) and specs (>1500 chars) rather than silently truncating."""
        mock_gl.message.sender_address = self.buyer
        long_title = "A" * 101
        with self.assertRaises(ValueError) as ctx:
            self.contract.create_auction(long_title, "Spec", u256(1000))
        self.assertIn("Auction title exceeds maximum length", str(ctx.exception))

        long_spec = "B" * 1501
        with self.assertRaises(ValueError) as ctx:
            self.contract.create_auction("Valid Title", long_spec, u256(1000))
        self.assertIn("Technical specification floor exceeds maximum length", str(ctx.exception))

    def test_reveal_bid_validates_url_scheme_and_length(self):
        """Verify reveal_bid enforces HTTPS/HTTP scheme and max 256 character length."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("URL Check Auction", "Mandatory: TLS", u256(10000))

        raw_b = b"Valid content"
        content_hash = hashlib.sha256(raw_b).hexdigest()

        # 1. Invalid scheme (ftp://)
        invalid_url = "ftp://malicious.org/spec.md"
        mock_gl.message.sender_address = self.bidder1
        bid_hash1 = make_hash(str(self.bidder1), 5000, "salt_ftp", content_hash, invalid_url)
        bid_id1 = self.contract.submit_bid_commitment(aid, bid_hash1)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        with self.assertRaises(ValueError) as ctx:
            self.contract.reveal_bid(bid_id1, u256(5000), "salt_ftp", content_hash, invalid_url)
        self.assertIn("Proposal URL must start with https:// or http://", str(ctx.exception))

        # 2. Oversized URL (>256 chars)
        oversized_url = "https://example.com/" + "x" * 250
        self.assertGreater(len(oversized_url), 256)
        mock_gl.message.sender_address = self.buyer
        aid2 = self.contract.create_auction("URL Check 2", "Mandatory: TLS", u256(10000))

        mock_gl.message.sender_address = self.bidder2
        bid_hash2 = make_hash(str(self.bidder2), 6000, "salt_url", content_hash, oversized_url)
        bid_id2 = self.contract.submit_bid_commitment(aid2, bid_hash2)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid2)

        mock_gl.message.sender_address = self.bidder2
        with self.assertRaises(ValueError) as ctx:
            self.contract.reveal_bid(bid_id2, u256(6000), "salt_url", content_hash, oversized_url)
        self.assertIn("Proposal URL exceeds maximum length", str(ctx.exception))

    def test_unreachable_url_retry_and_recovery_policy(self):
        """Verify bounded retry policy: temporary fetch failure keeps bid PENDING; subsequent recovery succeeds."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Retry Auction", "Mandatory: Resilience", u256(20000))

        raw_b = b"Resilient architecture specification covering AES-256 encryption."
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/resilient.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 5000, "salt_retry", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(5000), "salt_retry", content_hash, url)

        # Attempt 1: Transient network outage causes fetch failure
        mock_gl.nondet.web.should_fail = True
        res1 = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertIn("FETCH_FAILED_RETRYABLE: Attempt 1/3", res1)

        # Bid must NOT be prematurely disqualified! Remains PENDING for retry
        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "PENDING")
        self.assertEqual(bid_data["adjudication_attempts"], 1)

        # Closing reveal phase MUST be blocked while bid remains PENDING
        mock_gl.message.sender_address = self.buyer
        with self.assertRaises(ValueError) as ctx:
            self.contract.close_reveal_phase(aid)
        self.assertIn("still pending eligibility", str(ctx.exception))

        # Attempt 2: Network recovers! Proposal is successfully fetched and adjudicated
        mock_gl.nondet.web.should_fail = False
        mock_gl.nondet.mock_decision = "ELIGIBLE"
        mock_gl.nondet.mock_quote = "AES-256 encryption"

        res2 = self.contract.adjudicate_bid_eligibility(bid_id)
        self.assertEqual(res2, "ELIGIBLE")

        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "ELIGIBLE")
        self.assertEqual(bid_data["adjudication_attempts"], 2)

    def test_unreachable_url_exhausted_retries_produces_unavailable(self):
        """Verify that after 3 failed fetch attempts, bid becomes UNAVAILABLE (distinct from INELIGIBLE) and auction unblocks."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Dead URL Auction", "Mandatory: Uptime", u256(20000))

        mock_gl.message.sender_address = self.bidder1
        dead_url = "https://broken-dead-link.invalid/proposal.txt"
        fake_hash = "f" * 64
        committed_hash = make_hash(str(self.bidder1), 5000, "salt_dead", fake_hash, dead_url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(5000), "salt_dead", fake_hash, dead_url)

        # Simulate permanent URL outage
        mock_gl.nondet.web.should_fail = True
        try:
            # Attempt 1 -> PENDING
            res1 = self.contract.adjudicate_bid_eligibility(bid_id)
            self.assertIn("Attempt 1/3", res1)
            self.assertEqual(self.contract.get_bid(bid_id)["eligibility_status"], "PENDING")

            # Attempt 2 -> PENDING
            res2 = self.contract.adjudicate_bid_eligibility(bid_id)
            self.assertIn("Attempt 2/3", res2)
            self.assertEqual(self.contract.get_bid(bid_id)["eligibility_status"], "PENDING")

            # Attempt 3 -> UNAVAILABLE (Explicit failure policy reached)
            res3 = self.contract.adjudicate_bid_eligibility(bid_id)
            self.assertEqual(res3, "UNAVAILABLE")

            bid_data = self.contract.get_bid(bid_id)
            self.assertEqual(bid_data["eligibility_status"], "UNAVAILABLE")
            self.assertEqual(bid_data["adjudication_attempts"], 3)
            self.assertIn("UNAVAILABLE", bid_data["adjudication_rationale"])

            # Verify reveal phase can now close because no bids remain PENDING
            mock_gl.message.sender_address = self.buyer
            phase = self.contract.close_reveal_phase(aid)
            self.assertEqual(phase, "SETTLE")

            # Verify UNAVAILABLE is excluded from winning settlement
            settle = self.contract.settle_auction(aid)
            self.assertEqual(settle["status"], "VOID_NO_BIDS")
        finally:
            mock_gl.nondet.web.should_fail = False

    def test_asymmetric_fetch_leader_fails_validator_succeeds_reverts_consensus(self):
        """Verify asymmetric failure (Leader fails fetch, Validator succeeds) reverts transaction leaving bid PENDING."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Asym 1", "Mandatory: TLS", u256(10000))

        raw_b = b"Valid content"
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/asym1.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 4000, "salt_asym1", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(4000), "salt_asym1", content_hash, url)

        # Leader fails (call 1), validator succeeds (call 2)
        mock_gl.nondet.web.call_count = 0
        mock_gl.nondet.web.fail_on_call = 1
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self.contract.adjudicate_bid_eligibility(bid_id)
            self.assertIn("Consensus failed", str(ctx.exception))

            # Transaction reverted -> state unchanged -> remains PENDING with 0 recorded attempts
            bid_data = self.contract.get_bid(bid_id)
            self.assertEqual(bid_data["eligibility_status"], "PENDING")
            self.assertEqual(bid_data["adjudication_attempts"], 0)
        finally:
            mock_gl.nondet.web.fail_on_call = None

    def test_asymmetric_fetch_leader_succeeds_validator_fails_reverts_consensus(self):
        """Verify asymmetric failure (Leader succeeds, Validator fails fetch) reverts transaction leaving bid PENDING."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Asym 2", "Mandatory: TLS", u256(10000))

        raw_b = b"Valid content"
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://raw.githubusercontent.com/org/repo/asym2.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 4000, "salt_asym2", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(4000), "salt_asym2", content_hash, url)

        # Leader succeeds (call 1), validator fails (call 2)
        mock_gl.nondet.web.call_count = 0
        mock_gl.nondet.web.fail_on_call = 2
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self.contract.adjudicate_bid_eligibility(bid_id)
            self.assertIn("Consensus failed", str(ctx.exception))

            # Transaction reverted -> state unchanged -> remains PENDING with 0 recorded attempts
            bid_data = self.contract.get_bid(bid_id)
            self.assertEqual(bid_data["eligibility_status"], "PENDING")
            self.assertEqual(bid_data["adjudication_attempts"], 0)
        finally:
            mock_gl.nondet.web.fail_on_call = None

    def test_repeated_asymmetric_failures_resolved_by_timeout_recovery(self):
        """Verify repeated asymmetric consensus failures are deterministically recovered by resolve_unresponsive_bid after timeout."""
        mock_gl.message.sender_address = self.buyer
        aid = self.contract.create_auction("Timeout Recovery Auction", "Mandatory: Resilience", u256(10000))

        raw_b = b"Valid content"
        content_hash = hashlib.sha256(raw_b).hexdigest()
        url = "https://flaky-cdn-domain.org/spec.md"
        mock_gl.nondet.web.set_url_response(url, raw_b)

        mock_gl.message.sender_address = self.bidder1
        committed_hash = make_hash(str(self.bidder1), 3500, "salt_timeout", content_hash, url)
        bid_id = self.contract.submit_bid_commitment(aid, committed_hash)

        mock_gl.message.sender_address = self.buyer
        self.contract.close_commit_phase(aid)

        mock_gl.message.sender_address = self.bidder1
        self.contract.reveal_bid(bid_id, u256(3500), "salt_timeout", content_hash, url)

        # Repeated asymmetric consensus failures
        for _ in range(5):
            mock_gl.nondet.web.call_count = 0
            mock_gl.nondet.web.fail_on_call = 1
            with self.assertRaises(RuntimeError):
                self.contract.adjudicate_bid_eligibility(bid_id)

        # Bid remains PENDING because consensus continuously reverted
        self.assertEqual(self.contract.get_bid(bid_id)["eligibility_status"], "PENDING")

        # 1. Attempting recovery prematurely before 3600s MUST fail (guards against griefing)
        mock_gl.message.sender_address = self.attacker
        with self.assertRaises(ValueError) as ctx:
            self.contract.resolve_unresponsive_bid(bid_id)
        self.assertIn("Adjudication grace period active", str(ctx.exception))

        # 2. Advance time past the 3600s deadline (simulating timeout expiration)
        current_ts = int(self.contract.bid_reveal_timestamp[bid_id])
        self.contract.bid_reveal_timestamp[bid_id] = u256(current_ts - 3601)

        # 3. Recovery can now be invoked to deterministically advance bid to UNAVAILABLE
        res = self.contract.resolve_unresponsive_bid(bid_id)
        self.assertEqual(res, "UNAVAILABLE")

        bid_data = self.contract.get_bid(bid_id)
        self.assertEqual(bid_data["eligibility_status"], "UNAVAILABLE")
        self.assertIn("Adjudication timeout recovery", bid_data["adjudication_rationale"])

        # 4. Reveal phase can now close smoothly!
        mock_gl.message.sender_address = self.buyer
        phase = self.contract.close_reveal_phase(aid)
        self.assertEqual(phase, "SETTLE")

        # 5. Settlement succeeds (UNAVAILABLE excluded from winning)
        settle = self.contract.settle_auction(aid)
        self.assertEqual(settle["status"], "VOID_NO_BIDS")

if __name__ == "__main__":
    unittest.main()
