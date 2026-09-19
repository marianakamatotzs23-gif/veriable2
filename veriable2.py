import hashlib
import json
import os
import sys
import math
from time import time
from flask import Flask, jsonify, request, render_template
import ecdsa
import threading
import secrets

STORAGE_FILE = "chain_storage.json"

def generate_master_wallet():
    """
    Generates Bitcoin-grade 256-bit cryptographic keys (SECP256k1).
    Total key space: 2^256 combinations (~1.1579 x 10^77).
    Mathematically impossible to brute-force or guess.
    """
    priv_bytes = secrets.token_bytes(32)
    sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    return {
        'private_key': sk.to_string().hex(),
        'public_key': vk.to_string().hex()
    }

def wallet_from_private_key(private_key_hex):
    """
    Validates and restores a wallet from a 64-character 256-bit hex private key.
    Strictly validates key length, scalar boundaries, and curve integrity.
    """
    clean_hex = str(private_key_hex).strip().lower()
    if len(clean_hex) != 64:
        return None, None, f"Invalid key length ({len(clean_hex)} characters). Private key must be exactly 64 hexadecimal characters."
    try:
        key_int = int(clean_hex, 16)
        curve_order = ecdsa.SECP256k1.order
        if key_int <= 0 or key_int >= curve_order:
            return None, None, "Invalid scalar: Value is outside SECP256k1 curve boundaries."
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(clean_hex), curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        return sk.to_string().hex(), vk.to_string().hex(), None
    except ValueError:
        return None, None, "Format error: Private key must contain valid hexadecimal characters (0-9, a-f)."
    except Exception as e:
        return None, None, f"Cryptographic verification error: {str(e)}"

def verify_key_match(private_key_hex, public_key_hex):
    if not private_key_hex or not public_key_hex:
        return False
    try:
        clean_hex = str(private_key_hex).strip().lower()
        if len(clean_hex) != 64:
            return False
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(clean_hex), curve=ecdsa.SECP256k1)
        return sk.verifying_key.to_string().hex() == str(public_key_hex).strip().lower()
    except Exception:
        return False

def get_tier_for_power(power):
    """Maps an individual token's raw power to its respective tier."""
    p = float(power)
    if p >= 70.0:
        return 'tier_99_70'
    elif p >= 50.0:
        return 'tier_70_50'
    elif p >= 30.0:
        return 'tier_50_30'
    elif p >= 10.0:
        return 'tier_30_10'
    elif p >= 1.0:
        return 'tier_10_1'
    else:
        return 'tier_below_1'


class InfiniteVariableSearchEngine:
    @staticmethod
    def search_infinite_variables(seed_identifier, mining_difficulty, coin_type="MAIN"):
        attempts = 0
        max_attempts = 350000 if coin_type == "MAIN" else 450000
        
        while attempts < max_attempts:
            attempts += 1
            var_seed = f"{seed_identifier}_{attempts}"
            var_hash = hashlib.sha256(var_seed.encode('utf-8')).hexdigest()
            val = int(hashlib.md5(var_hash.encode('utf-8')).hexdigest(), 16)
            
            scale_val = (val % 99000000) / 1000000.0
            
            if scale_val <= mining_difficulty or attempts >= max_attempts:
                return var_hash, attempts, scale_val
                
        return "0x0", attempts, mining_difficulty


class ResilientVariableStorageEngine:
    """
    1-99 State Storage Engine:
    Pruned data drops to a 1.0 base anchor.
    Upon restoration, data remains in 1.0 quarantine until SHA-256 validation elevates it back to 99.0.
    """
    def __init__(self):
        self.matrix_blocks = {}

    def allocate_block(self, block, coin_type="MAIN"):
        idx = int(block['index'])
        block['power_scale'] = 99.0
        block['status'] = "ACTIVE"
        
        tx_serialized = json.dumps(block.get('transactions', []), sort_keys=True)
        block['data_snapshot_hash'] = hashlib.sha256(tx_serialized.encode()).hexdigest()
        
        self.matrix_blocks[idx] = block

    def soft_prune_block(self, block_index):
        idx = int(block_index)
        if idx not in self.matrix_blocks:
            return False, "Block not found."

        block = self.matrix_blocks[idx]
        block['archived_payload'] = block.get('transactions', [])
        block['transactions'] = []
        block['power_scale'] = 1.0
        block['status'] = "BASE_LOCKED"
        return True, f"Block {idx} locked at base scale (1.0)."

    def request_restore_block(self, block_index):
        idx = int(block_index)
        if idx not in self.matrix_blocks:
            return False, "Block not found."

        block = self.matrix_blocks[idx]
        if block['status'] != "BASE_LOCKED":
            return False, "Block is not base-locked."

        block['transactions'] = block.get('archived_payload', [])
        block['status'] = "RESTORE_PENDING"
        block['power_scale'] = 1.0
        return True, f"Block {idx} placed in quarantine (1.0). Awaiting snapshot validation."

    def system_validate_and_elevate(self, block_index):
        idx = int(block_index)
        if idx not in self.matrix_blocks:
            return False, "Block not found."

        block = self.matrix_blocks[idx]
        if block['status'] != "RESTORE_PENDING":
            return False, "Block is not pending validation."

        current_tx_serialized = json.dumps(block.get('transactions', []), sort_keys=True)
        current_hash = hashlib.sha256(current_tx_serialized.encode()).hexdigest()

        if current_hash == block.get('data_snapshot_hash'):
            block['power_scale'] = 99.0
            block['status'] = "ACTIVE"
            return True, f"Validation successful. Block {idx} elevated to 99.0 scale."
        else:
            block['power_scale'] = 1.0
            block['status'] = "BASE_LOCKED"
            block['transactions'] = []
            return False, "Hash mismatch. Block remains locked at 1.0 base scale."

    @property
    def main_block_lookup(self):
        return {idx: b for idx, b in self.matrix_blocks.items() if b.get('coin_type') == "MAIN"}

    @property
    def alt_block_lookup(self):
        return {idx: b for idx, b in self.matrix_blocks.items() if b.get('coin_type') != "MAIN"}

    def to_dict(self):
        return {
            "matrix_blocks": {str(k): v for k, v in self.matrix_blocks.items()}
        }

    def load_from_dict(self, data):
        if "matrix_blocks" in data:
            self.matrix_blocks = {int(k): v for k, v in data["matrix_blocks"].items()}
        else:
            for k, block in data.get("main_block_lookup", {}).items():
                self.allocate_block(block, "MAIN")
            for k, block in data.get("alt_block_lookup", {}).items():
                self.allocate_block(block, "ALT")


class Blockchain(object):
    def __init__(self):
        self.current_main_transactions = []
        self.current_alt_transactions = []
        self.BURN_ADDRESS = "0x000000000000000000000000000000000000dEaD"
        self.lock = threading.Lock()
        
        self.storage = ResilientVariableStorageEngine()
        
        self.BASE_MAX_MAIN = 21000000
        self.BASE_MAIN_REWARD = 50
        self.dynamic_supply_offset = 0
        self.supply_variance_limit = 5000000
        self.burned_main_coins = 0
        
        self.sub_coin_name = "SHIELD_COIN"
        
        self.market_boost_bonus = 0.0
        self.market_peg_active = False
        self.user_stats = {}  

        self.load_from_disk()

        if not self.storage.main_block_lookup:
            self.mint_block(proof=100, coin_type="MAIN", previous_hash='1')
            
        if not self.storage.alt_block_lookup:
            self.mint_block(proof=100, coin_type="ALT", previous_hash='1')

    def save_to_disk(self):
        try:
            with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.storage.to_dict(), f, indent=2)
        except Exception as e:
            print(f"Disk write error: {e}")

    def load_from_disk(self):
        if os.path.exists(STORAGE_FILE):
            try:
                with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.storage.load_from_dict(data)
            except Exception as e:
                print(f"Disk read error: {e}")

    def get_chain_length(self, coin_type="MAIN"):
        lookup = self.storage.main_block_lookup if coin_type == "MAIN" else self.storage.alt_block_lookup
        if not lookup:
            return 0
        return max(lookup.keys())

    def get_last_block(self, coin_type="MAIN"):
        length = self.get_chain_length(coin_type)
        if length == 0:
            return None
        lookup = self.storage.main_block_lookup if coin_type == "MAIN" else self.storage.alt_block_lookup
        return lookup.get(length)

    def mint_block(self, proof, coin_type="MAIN", previous_hash=None):
        with self.lock:
            last = self.get_last_block(coin_type)
            prev_hash = previous_hash or (self.hash(last) if last else '1')
            txs = self.current_main_transactions if coin_type == "MAIN" else self.current_alt_transactions
            
            block = {
                'index': (last['index'] + 1) if last else 1,
                'timestamp': int(time()),
                'transactions': txs,
                'proof': proof,
                'previous_hash': prev_hash,
                'coin_type': coin_type
            }
            block['hash'] = self.hash(block)
            
            if coin_type == "MAIN":
                self.current_main_transactions = []
            else:
                self.current_alt_transactions = []
            
        self.storage.allocate_block(block, coin_type)
        self.save_to_disk()
        return block

    def new_transaction(self, sender, recipient, amount, coin_type="MAIN", powers=None):
        try:
            amount = int(float(amount))
        except Exception:
            return False, "Invalid amount parameter."
            
        if amount <= 0:
            return False, "Amount must be greater than zero."
            
        with self.lock:
            if sender != "0" and self.get_balance(sender, coin_type, True) < amount:
                return False, "Insufficient balance."
            
            tx_data = {
                'sender': sender,
                'recipient': recipient,
                'amount': amount,
                'coin_type': coin_type
            }
            if powers is not None:
                tx_data['powers'] = [round(float(p), 4) for p in powers]

            target_txs = self.current_main_transactions if coin_type == "MAIN" else self.current_alt_transactions
            target_txs.append(tx_data)
            return True, self.get_chain_length(coin_type) + 1

    @staticmethod
    def hash(block):
        block_copy = {k: v for k, v in block.items() if k != 'hash'}
        return hashlib.sha256(json.dumps(block_copy, sort_keys=True).encode()).hexdigest()

    def get_user_stats(self, address):
        if address not in self.user_stats:
            self.user_stats[address] = {
                'personal_supply_offset': 0,
                'personal_burned': 0,
                'personal_boost': 0.0
            }
        return self.user_stats[address]

    def get_balance(self, address, coin_type="MAIN", include_pending=True):
        balance = 0
        lookup = self.storage.main_block_lookup if coin_type == "MAIN" else self.storage.alt_block_lookup
        for block in lookup.values():
            for tx in block.get('transactions', []):
                if tx.get('coin_type', 'MAIN') == coin_type:
                    if tx['sender'] == address:
                        balance -= int(tx['amount'])
                    if tx['recipient'] == address:
                        balance += int(tx['amount'])
        if include_pending:
            pending_txs = self.current_main_transactions if coin_type == "MAIN" else self.current_alt_transactions
            for tx in pending_txs:
                if tx['sender'] == address:
                    balance -= int(tx['amount'])
        return int(balance)

    def get_user_shield_tokens(self, address, include_pending=True):
        """
        Retrieves each individual Shield Coin's raw inception power value (UTXO-like model).
        No dilution or blending; every coin preserves its exact historical power.
        """
        tokens = []
        lookup = self.storage.alt_block_lookup
        for idx in sorted(lookup.keys()):
            block = lookup[idx]
            for tx in block.get('transactions', []):
                if tx.get('coin_type') == self.sub_coin_name:
                    if tx.get('recipient') == address:
                        if 'powers' in tx and isinstance(tx['powers'], list):
                            tokens.extend([round(float(p), 4) for p in tx['powers']])
                        elif 'power' in tx:
                            tokens.append(round(float(tx['power']), 4))
                        else:
                            tokens.extend([99.0] * int(tx.get('amount', 1)))
                    if tx.get('sender') == address:
                        if 'powers' in tx and isinstance(tx['powers'], list):
                            for p in tx['powers']:
                                p_flt = round(float(p), 4)
                                if p_flt in tokens:
                                    tokens.remove(p_flt)
                        else:
                            amt = int(tx.get('amount', 1))
                            for _ in range(min(amt, len(tokens))):
                                tokens.pop(0)

        if include_pending:
            for tx in self.current_alt_transactions:
                if tx.get('coin_type') == self.sub_coin_name and tx.get('sender') == address:
                    if 'powers' in tx and isinstance(tx['powers'], list):
                        for p in tx['powers']:
                            p_flt = round(float(p), 4)
                            if p_flt in tokens:
                                tokens.remove(p_flt)
                    else:
                        amt = int(tx.get('amount', 1))
                        for _ in range(min(amt, len(tokens))):
                            tokens.pop(0)

        return tokens

    def get_effective_max_supply(self, address=None):
        base = (self.BASE_MAX_MAIN + self.dynamic_supply_offset) - self.burned_main_coins
        if address:
            stats = self.get_user_stats(address)
            base += stats['personal_supply_offset']
            base -= stats['personal_burned']
        return int(base)

    def get_total_mined(self, coin_type="MAIN"):
        total = 0
        lookup = self.storage.main_block_lookup if coin_type == "MAIN" else self.storage.alt_block_lookup
        for block in lookup.values():
            for tx in block.get('transactions', []):
                if tx.get('coin_type', 'MAIN') == coin_type and tx['sender'] == "0":
                    total += int(tx['amount'])
        return int(total)

    def get_mining_power_main(self, address=None):
        total_mined = self.get_total_mined("MAIN")
        max_limit = self.get_effective_max_supply(address)
        if total_mined >= max_limit:
            return 0.0
        progress = min(1.0, total_mined / float(max_limit))
        power = 99.0 * (1.0 - progress)
        return max(0.000001, round(power, 6))

    def get_mining_power_shield(self, address=None):
        shield_mined = self.get_total_mined(self.sub_coin_name)
        max_limit = self.get_effective_max_supply(address)
        
        # 10x faster difficulty acceleration compared to Main Coin
        equivalent_progress = (shield_mined * 10.0) / float(max_limit)
        progress = min(0.999999, equivalent_progress)
        power = 99.0 * (1.0 - progress)
        return max(0.000000001, round(power, 9))

    def get_shield_impact_power(self):
        alt_mined = self.get_total_mined(self.sub_coin_name)
        if alt_mined <= 0:
            return 99.0
            
        # Tier 1: 0 - 1,000 Coins (99 -> 70)
        if alt_mined <= 1000:
            progress = alt_mined / 1000.0
            power = 99.0 - (progress * 29.0)
        # Tier 2: 1,000 - 10,000 Coins (70 -> 50)
        elif alt_mined <= 10000:
            progress = (alt_mined - 1000) / 9000.0
            power = 70.0 - (progress * 20.0)
        # Tier 3: 10,000 - 4,000,000 Coins (50 -> 30)
        elif alt_mined <= 4000000:
            progress = (alt_mined - 10000) / 3990000.0
            power = 50.0 - (progress * 20.0)
        # Tier 4: 4,000,000 - 8,000,000 Coins (30 -> 10)
        elif alt_mined <= 8000000:
            progress = (alt_mined - 4000000) / 4000000.0
            power = 30.0 - (progress * 20.0)
        # Tier 5: 8,000,000 - 16,000,000 Coins (10 -> 1)
        elif alt_mined <= 16000000:
            progress = (alt_mined - 8000000) / 8000000.0
            power = 10.0 - (progress * 9.0)
        # Tier 6: 16,000,000+ Coins (1 -> 0.00001 Asymptotic Floor)
        else:
            extra = alt_mined - 16000000
            power = max(0.00001, 1.0 / (1.0 + (extra / 10000000.0)))
            
        return max(0.00001, round(power, 6))

app = Flask(__name__)
app.json.ensure_ascii = False
blockchain = Blockchain()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/wallet/new', methods=['GET'])
def new_wallet():
    return jsonify(generate_master_wallet()), 200

@app.route('/wallet/recover', methods=['POST'])
def recover_wallet():
    priv_hex = request.get_json().get('private_key', '')
    priv, pub, error = wallet_from_private_key(priv_hex)
    if error:
        return jsonify({'error': error}), 400
    return jsonify({'private_key': priv, 'public_key': pub}), 200

@app.route('/mine', methods=['GET'])
def mine():
    miner_address = request.args.get('address')
    selected_coin = request.args.get('coin', default='MAIN').upper()
    if not miner_address or len(miner_address) < 20:
        return jsonify({'error': 'Invalid miner address.'}), 400

    coin_type_key = blockchain.sub_coin_name if selected_coin == "ALT" else "MAIN"
    last_block = blockchain.get_last_block(coin_type_key)
    next_index = (last_block['index'] + 1) if last_block else 1

    if coin_type_key == "MAIN":
        mining_difficulty = blockchain.get_mining_power_main(miner_address)
        target_power = mining_difficulty
        if mining_difficulty <= 0.0 or blockchain.get_total_mined("MAIN") >= blockchain.get_effective_max_supply(miner_address):
            return jsonify({'message': 'Main coin has reached maximum supply ceiling.'}), 400
    else:
        mining_difficulty = blockchain.get_mining_power_shield(miner_address)
        target_power = blockchain.get_shield_impact_power()

    var_hash, attempts, resolved_val = InfiniteVariableSearchEngine.search_infinite_variables(
        f"infinite_search_{coin_type_key}_{miner_address}_{next_index}", 
        mining_difficulty,
        coin_type=coin_type_key
    )

    if coin_type_key == "MAIN":
        reward = max(1, int(blockchain.BASE_MAIN_REWARD * max(0.01, mining_difficulty / 99.0)))
        blockchain.new_transaction(sender="0", recipient=miner_address, amount=reward, coin_type="MAIN")
        earned = f"{reward} Main Coin (Target Power: {target_power} | Attempts: {attempts})"
    else:
        reward = 1 
        blockchain.new_transaction(
            sender="0", 
            recipient=miner_address, 
            amount=reward, 
            coin_type=blockchain.sub_coin_name, 
            powers=[target_power]
        )
        earned = f"{reward} Shield Coin (Inception Power: {target_power} | Difficulty: {mining_difficulty})"

    block = blockchain.mint_block(
        proof=attempts, 
        coin_type=coin_type_key,
        previous_hash=blockchain.hash(last_block) if last_block else '1'
    )

    return jsonify({
        'status': 'Success',
        'earned': earned,
        'mining_attempts': attempts,
        'block_index': block['index'],
        'chain_type': coin_type_key
    }), 200

@app.route('/protocol/act', methods=['POST'])
def protocol_action():
    data = request.get_json()
    address = data.get('address')
    private_key = data.get('private_key')
    action = data.get('action')
    scope = data.get('scope', 'personal')
    selected_tier = data.get('target_tier', 'any')

    if not address or not private_key or not verify_key_match(private_key, address):
        return jsonify({'error': 'Access denied: 256-bit cryptographic signature mismatch.'}), 403

    all_user_tokens = blockchain.get_user_shield_tokens(address, include_pending=True)
    if not all_user_tokens:
        return jsonify({'error': 'Wallet holds zero Shield Coins.'}), 400

    if selected_tier == 'any':
        eligible_tokens = list(all_user_tokens)
    else:
        eligible_tokens = [p for p in all_user_tokens if get_tier_for_power(p) == selected_tier]

    tier_available_count = len(eligible_tokens)
    if tier_available_count == 0:
        return jsonify({'error': f'No tokens available in selected tier ({selected_tier}).'}), 400

    req_count = data.get('burn_count')
    if req_count is not None and str(req_count).strip() != "":
        try:
            burn_amount = int(req_count)
        except ValueError:
            return jsonify({'error': 'Burn amount must be an integer.'}), 400
    else:
        alt_percentage = data.get('alt_percentage', 100)
        try:
            pct = float(alt_percentage)
        except ValueError:
            return jsonify({'error': 'Percentage must be numeric.'}), 400
        burn_amount = max(1, int((tier_available_count * pct) / 100.0))

    if burn_amount <= 0 or burn_amount > tier_available_count:
        return jsonify({'error': f'Invalid quantity. Available: {tier_available_count}, Requested: {burn_amount}.'}), 400

    burned_tokens = eligible_tokens[:burn_amount]

    total_raw_power = sum(burned_tokens)
    effective_power = total_raw_power / 99.0
    avg_power = round(total_raw_power / len(burned_tokens), 4)

    success, msg = blockchain.new_transaction(
        sender=address, 
        recipient=blockchain.BURN_ADDRESS, 
        amount=burn_amount, 
        coin_type=blockchain.sub_coin_name,
        powers=burned_tokens
    )
    if not success:
        return jsonify({'error': msg}), 400

    stats = blockchain.get_user_stats(address)
    message = ""

    with blockchain.lock:
        if action == "burn_main":
            burned_qty = max(1, int(effective_power * 100))
            if scope == "global":
                blockchain.burned_main_coins += burned_qty
                message = f"[GLOBAL] Supply permanently destroyed: {burned_qty} Main Coins removed."
            else:
                stats['personal_burned'] += burned_qty
                message = f"[PERSONAL] Supply quota reduced: {burned_qty} Main Coins subtracted."

        elif action == "expand_supply":
            expand_qty = max(1, int(effective_power * 150))
            if scope == "global":
                blockchain.dynamic_supply_offset = min(blockchain.supply_variance_limit, blockchain.dynamic_supply_offset + expand_qty)
                message = f"[GLOBAL] Capacity expanded: Global limit +{expand_qty} added."
            else:
                stats['personal_supply_offset'] += expand_qty
                message = f"[PERSONAL] Personal capacity expanded: Limit +{expand_qty} added."

        elif action == "boost_price":
            boost_val = round(min(5.0, effective_power * 0.5), 2)
            if scope == "global":
                blockchain.market_boost_bonus = boost_val
                message = f"[GLOBAL] Dynamic coefficient boosted by +{boost_val}%."
            else:
                stats['personal_boost'] = boost_val
                message = f"[PERSONAL] Wallet dynamic coefficient boosted by +{boost_val}%."

        elif action == "discount_price":
            reduction_val = round(min(5.0, effective_power * 0.5), 2)
            if scope == "global":
                blockchain.market_boost_bonus = -reduction_val
                message = f"[GLOBAL] Discount mode active: -{reduction_val}% coefficient applied."
            else:
                stats['personal_boost'] = -reduction_val
                message = f"[PERSONAL] Discount coefficient applied: -{reduction_val}%."

        elif action == "peg_static":
            if scope == "global":
                blockchain.market_peg_active = True
                blockchain.market_boost_bonus = 0.0
                message = "[GLOBAL] Valuation benchmark locked and stabilized."
            else:
                stats['personal_boost'] = 0.0
                message = "[PERSONAL] Wallet parameters stabilized."

    tier_labels = {
        'tier_99_70': 'Tier 1 (%99 - %70 Power)',
        'tier_70_50': 'Tier 2 (%70 - %50 Power)',
        'tier_50_30': 'Tier 3 (%50 - %30 Power)',
        'tier_30_10': 'Tier 4 (%30 - %10 Power)',
        'tier_10_1': 'Tier 5 (%10 - %1 Power)',
        'tier_below_1': 'Tier 6 (<%1 Floor)',
        'any': 'Blended / Entire Portfolio'
    }

    return jsonify({
        'status': 'Success',
        'action_result': message,
        'selected_tier': tier_labels.get(selected_tier, selected_tier),
        'burned_count': burn_amount,
        'burned_tokens_raw_powers': burned_tokens,
        'total_raw_power_released': round(total_raw_power, 4),
        'average_power_of_burned_tokens': avg_power,
        'effective_impact_multiplier': round(effective_power, 6),
        'remaining_total_shield': len(blockchain.get_user_shield_tokens(address, True))
    }), 200

@app.route('/chain', methods=['GET'])
def full_chain():
    user_address = request.args.get('address', 'Unknown_User')
    total_alt_mined = blockchain.get_total_mined(blockchain.sub_coin_name)
    burned_alt = blockchain.get_balance(blockchain.BURN_ADDRESS, blockchain.sub_coin_name, False)
    
    shield_impact_power = blockchain.get_shield_impact_power()
    user_tokens = blockchain.get_user_shield_tokens(user_address, False)
    user_shield_count = len(user_tokens)

    tier_data = {
        'tier_99_70': [p for p in user_tokens if p >= 70.0],
        'tier_70_50': [p for p in user_tokens if 50.0 <= p < 70.0],
        'tier_50_30': [p for p in user_tokens if 30.0 <= p < 50.0],
        'tier_30_10': [p for p in user_tokens if 10.0 <= p < 30.0],
        'tier_10_1':  [p for p in user_tokens if 1.0 <= p < 10.0],
        'tier_below_1': [p for p in user_tokens if p < 1.0]
    }

    tier_summary = {}
    for k, v in tier_data.items():
        tier_summary[k] = {
            'count': len(v),
            'average_power': round(sum(v) / len(v), 2) if v else 0.0,
            'powers': sorted(v, reverse=True)
        }

    overall_avg = round(sum(user_tokens) / user_shield_count, 2) if user_shield_count > 0 else 0.0

    return jsonify({
        '1_GLOBAL_DATA': {
            'main_chain_height': blockchain.get_chain_length("MAIN"),
            'alt_chain_height': blockchain.get_chain_length(blockchain.sub_coin_name),
            'main_coin_supply': f"{blockchain.get_total_mined('MAIN')} / {blockchain.get_effective_max_supply(user_address)}",
            'shield_coin_circulating': f"{total_alt_mined - burned_alt} (Active, Burned: {burned_alt})",
            'current_network_mint_power': f"{shield_impact_power}"
        },
        '2_USER_DATA': {
            'wallet_address': user_address, 
            'main_coin_balance': blockchain.get_balance(user_address, 'MAIN'),
            'shield_coin_balance': user_shield_count,
            'shield_overall_average_power': overall_avg,
            'tiers': tier_summary,
            'all_tokens_sorted': sorted(user_tokens, reverse=True)
        }
    }), 200

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app.run(host='0.0.0.0', port=port, threaded=True)
