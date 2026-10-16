import hashlib
import sys

def make_bid_hash(bidder_addr: str, price_cents: int, salt: str, proposal_url: str) -> str:
    clean_addr = bidder_addr.strip().lower()
    clean_salt = salt.strip()
    clean_url = proposal_url.strip()
    preimage = f"{clean_addr}_{int(price_cents)}_{clean_salt}_{clean_url}".encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python generate_hashes.py <bidder_address> <price_cents> <salt> <proposal_url>")
        print("\nExample:")
        print("python generate_hashes.py 0x1111111111111111111111111111111111111111 8000 salt1 https://raw.githubusercontent.com/.../spec.md")
        sys.exit(1)

    addr = sys.argv[1]
    price = int(sys.argv[2])
    salt = sys.argv[3]
    url = sys.argv[4]

    computed = make_bid_hash(addr, price, salt, url)
    print(f"\n[Generated Bid Commitment]")
    print(f"Bidder Address : {addr.lower()}")
    print(f"Price (Cents)  : {price}")
    print(f"Salt           : {salt}")
    print(f"Proposal URL   : {url}")
    print(f"SHA-256 Hash   : {computed}\n")
