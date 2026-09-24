import hashlib
import json
import os
import sys
import math
import shutil
from time import time, sleep
from flask import Flask, jsonify, request, render_template, send_file
import ecdsa
import threading
import secrets
import socket
import uuid
import webbrowser

# Native desktop GUI module
try:
    import webview
except ImportError:
    webview = None

# =====================================================================
# GLOBAL PROTOCOL CONFIGURATION & STORAGE PATHS
# =====================================================================
MATRIX_BASE_DIR = "variable_matrix"
OVERFLOW_STORAGE_FILE = "overflow_matrix.json"
BOOTSTRAP_PEERS = ["104.248.255.163:6000"]
STORAGE_SAFETY_MARGIN_MB = 250   # Triggers overflow when free space drops below 250 MB
THERMAL_TIME_THRESHOLD = 0.85     # Maximum processing time before throttling

# =====================================================================
# 256-BIT CRYPTOGRAPHIC KEY ENGINE (BITCOIN SECP256K1)
# =====================================================================
def generate_master_wallet():
    """Generates a standard Bitcoin-grade 256-bit SECP256k1 keypair."""
    priv_bytes = secrets.token_bytes(32)
    sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    return {
        'private_key': sk.to_string().hex(),
        'public_key': vk.to_string().hex()
    }

def wallet_from_private_key(private_key_hex):
    """Validates and derives public wallet address from a 64-char hex private key."""
    clean_hex = str(private_key_hex).strip().lower()
    if len(clean_hex) != 64:
        return None, None, f"Invalid key length ({len(clean_hex)} chars). Must be exactly 64 hex characters."
    try:
        key_int = int(clean_hex, 16)
        curve_order = ecdsa.SECP256k1.order
        if key_int <= 0 or key_int >= curve_order:
            return None, None, "Scalar value is outside SECP256k1 curve boundaries."
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(clean_hex), curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        return sk.to_string().hex(), vk.to_string().hex(), None
    except ValueError:
        return None, None, "Format error: Private key must contain hexadecimal characters only."
    except Exception as e:
        return None, None, f"Cryptographic validation error: {str(e)}"

def verify_key_match(private_key_hex, public_key_hex):
    """Verifies that the private key matches the target public wallet address."""
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
    """Maps token power to its designated protocol category."""
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

# =====================================================================
# HARDWARE-AGNOSTIC RANDOM ALLOCATION & STORAGE GOVERNOR
# =====================================================================
class StorageGovernor:
    @staticmethod
    def get_free_disk_mb():
        try:
            total, used, free = shutil.disk_usage(".")
            return free // (1024 * 1024)
        except Exception:
            return 1000

    @staticmethod
    def check_thermal_pressure(processing_duration):
        return processing_duration > THERMAL_TIME_THRESHOLD

    @staticmethod
    def assign_pure_random_tier(node_id, epoch):
        """
        DOES NOT inspect hardware capability (CPU, RAM, Disk).
        Assigns an unbiased random storage allocation percentage between 1 and 99 every 24h.
        Guarantees minimum 1% (anti-freerider) and maximum 99% (anti-monopoly).
        """
        seed = f"VERIABLE_PURE_RANDOM_TIER_{node_id}_{epoch}"
        raw_hash = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        pure_tier = (raw_hash % 99) + 1
        return pure_tier

class InfiniteVariableSearchEngine:
    @staticmethod
    def search_infinite_variables(seed_identifier, mining_difficulty, coin_type="MAIN"):
        attempts = 0
        max_attempts = 350000 if coin_type == "MAIN" else 500000
        while attempts < max_attempts:
            attempts += 1
            var_seed = f"{seed_identifier}_{attempts}"
            var_hash = hashlib.sha256(var_seed.encode('utf-8')).hexdigest()
            val = int(hashlib.md5(var_hash.encode('utf-8')).hexdigest(), 16)
            scale_val = (val % 99000000) / 1000000.0
            if scale_val <= mining_difficulty or attempts >= max_attempts:
                return var_hash, attempts, scale_val
        return "0x0", attempts, mining_difficulty

# =====================================================================
# BACKGROUND INFINITE MULTI-SPACE MATRIX STORAGE ENGINE
# =====================================================================
class ShardedResilientVariableStorageEngine:
    """
    Infinite Multi-Space Matrix Storage Engine (Operates silently in the background):
    - Blocks are distributed across infinite directories: space_1, space_2 ... space_N
    - Each directory stores blocks up to a 1-99 depth scale.
    - When disk capacity is scarce, transactions are offloaded while block ownership
      and coin balances are permanently locked down to a 1.0 base anchor (BASE_LOCKED_OFFLOADED).
    - Pruned blocks eliminate 99% of transaction overhead.
    """
    def __init__(self, base_dir=MATRIX_BASE_DIR):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.index_headers = {}

    def _get_infinite_space_id(self, index):
        idx = int(index)
        return ((idx - 1) // 99) + 1

    def _get_level_in_space(self, index):
        idx = int(index)
        return ((idx - 1) % 99) + 1

    def _block_path(self, coin_type, index):
        space_id = self._get_infinite_space_id(index)
        space_folder = os.path.join(self.base_dir, f"space_{space_id}")
        os.makedirs(space_folder, exist_ok=True)
        return os.path.join(space_folder, f"{coin_type}_{index}.json")

    def allocate_block(self, block, user_random_tier=99):
        coin_type = block.get('coin_type', 'MAIN')
        idx = int(block['index'])
        space_id = self._get_infinite_space_id(idx)
        level_in_space = self._get_level_in_space(idx)
        
        block['space_id'] = space_id
        block['space_level'] = level_in_space

        block_tier_hash = int(hashlib.sha256(f"{coin_type}_{idx}".encode()).hexdigest(), 16)
        block_tier = (block_tier_hash % 99) + 1

        free_disk_mb = StorageGovernor.get_free_disk_mb()

        # If disk is constrained or block tier exceeds node daily allocation:
        # Offload physical payload, but retain the block cryptographic anchor at 1.0 base.
        if free_disk_mb < STORAGE_SAFETY_MARGIN_MB:
            block['power_scale'] = 1.0
            block['status'] = "BASE_LOCKED_OFFLOADED"
            self._save_to_overflow_storage(block)
            block['archived_payload'] = block.get('transactions', [])
            block['transactions'] = []
        elif block_tier > user_random_tier:
            block['power_scale'] = 1.0
            block['status'] = "BASE_LOCKED"
            block['archived_payload'] = block.get('transactions', [])
            block['transactions'] = []
        else:
            block['power_scale'] = 99.0
            block['status'] = "ACTIVE"

        tx_payload = block.get('transactions', []) or block.get('archived_payload', [])
        block['data_snapshot_hash'] = hashlib.sha256(json.dumps(tx_payload, sort_keys=True).encode()).hexdigest()

        path = self._block_path(coin_type, idx)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(block, f, indent=2)
        except Exception:
            pass

        self.index_headers[(coin_type, idx)] = block

    def _save_to_overflow_storage(self, block):
        try:
            records = []
            if os.path.exists(OVERFLOW_STORAGE_FILE):
                with open(OVERFLOW_STORAGE_FILE, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            records.append({
                "coin_type": block.get('coin_type'),
                "index": block.get('index'),
                "hash": block.get('hash'),
                "transactions": block.get('transactions', []),
                "offloaded_at": int(time())
            })
            with open(OVERFLOW_STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(records[-300:], f, indent=2)
        except Exception:
            pass

    def soft_prune_shard(self, coin_type, index):
        idx = int(index)
        block = self.get_block(coin_type, idx)
        if not block:
            return False, "Block not found."

        block['archived_payload'] = block.get('transactions', [])
        block['transactions'] = []
        block['power_scale'] = 1.0
        block['status'] = "BASE_LOCKED"
        
        path = self._block_path(coin_type, idx)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(block, f, indent=2)
        except Exception:
            pass
            
        self.index_headers[(coin_type, idx)] = block
        return True, f"Block {coin_type}_{idx} anchored at 1.0 base."

    def request_restore_shard(self, coin_type, index, remote_transactions):
        idx = int(index)
        block = self.get_block(coin_type, idx)
        if not block:
            return False, "Block not found."

        block['transactions'] = remote_transactions
        block['status'] = "RESTORE_PENDING"
        block['power_scale'] = 1.0
        
        path = self._block_path(coin_type, idx)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(block, f, indent=2)
        except Exception:
            pass
            
        self.index_headers[(coin_type, idx)] = block
        return True, "Block placed in quarantine mode (1.0)."

    def system_validate_and_elevate(self, coin_type, index):
        idx = int(index)
        block = self.get_block(coin_type, idx)
        if not block or block.get('status') != "RESTORE_PENDING":
            return False, "Validation rejected: Not in quarantine state."

        current_tx_serialized = json.dumps(block.get('transactions', []), sort_keys=True)
        current_hash = hashlib.sha256(current_tx_serialized.encode()).hexdigest()

        path = self._block_path(coin_type, idx)
        if current_hash == block.get('data_snapshot_hash'):
            block['power_scale'] = 99.0
            block['status'] = "ACTIVE"
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(block, f, indent=2)
            except Exception:
                pass
            self.index_headers[(coin_type, idx)] = block
            return True, "Validation successful: Block elevated to 99.0 active state."
        else:
            block['power_scale'] = 1.0
            block['status'] = "BASE_LOCKED"
            block['transactions'] = []
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(block, f, indent=2)
            except Exception:
                pass
            self.index_headers[(coin_type, idx)] = block
            return False, "Hash mismatch: Block retained at 1.0 base anchor."

    def get_block(self, coin_type, index):
        idx = int(index)
        path = self._block_path(coin_type, idx)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return self.index_headers.get((coin_type, idx))

    def load_all_shards(self):
        self.index_headers.clear()
        if not os.path.exists(self.base_dir):
            return
            
        for space_name in os.listdir(self.base_dir):
            space_path = os.path.join(self.base_dir, space_name)
            if os.path.isdir(space_path) and space_name.startswith("space_"):
                for fname in os.listdir(space_path):
                    if fname.endswith(".json"):
                        parts = fname[:-5].rsplit('_', 1)
                        if len(parts) == 2:
                            coin_type, idx_str = parts
                            try:
                                idx = int(idx_str)
                                fpath = os.path.join(space_path, fname)
                                with open(fpath, 'r', encoding='utf-8') as f:
                                    b = json.load(f)
                                    self.index_headers[(coin_type, idx)] = b
                            except Exception:
                                pass

    def get_chain_length(self, coin_type):
        indices = [k[1] for k in self.index_headers.keys() if k[0] == coin_type]
        return max(indices) if indices else 0

    def get_all_blocks(self, coin_type):
        result = {}
        for (c, idx), b in self.index_headers.items():
            if c == coin_type:
                result[idx] = b
        return result

# =====================================================================
# BLOCKCHAIN CORE PROTOCOL ENGINE
# =====================================================================
class Blockchain(object):
    def __init__(self):
        self.current_main_transactions = []
        self.current_alt_transactions = []
        self.BURN_ADDRESS = "0x000000000000000000000000000000000000dEaD"
        self.lock = threading.Lock()
        
        self.storage = ShardedResilientVariableStorageEngine()
        self.storage.load_all_shards()
        
        self.BASE_MAX_MAIN = 21000000
        self.BASE_MAIN_REWARD = 50  # Fixed 50 Main Coins per block
        self.dynamic_supply_offset = 0
        self.supply_variance_limit = 5000000
        self.burned_main_coins = 0
        
        self.sub_coin_name = "SHIELD_COIN"
        self.market_boost_bonus = 0.0
        self.market_peg_active = False
        self.user_stats = {}

        if self.storage.get_chain_length("MAIN") == 0:
            self.mint_block(proof=100, coin_type="MAIN", previous_hash='1')
            
        if self.storage.get_chain_length(self.sub_coin_name) == 0:
            self.mint_block(proof=100, coin_type=self.sub_coin_name, previous_hash='1')

    def get_chain_length(self, coin_type="MAIN"):
        return self.storage.get_chain_length(coin_type)

    def get_last_block(self, coin_type="MAIN"):
        length = self.get_chain_length(coin_type)
        if length == 0:
            return None
        return self.storage.get_block(coin_type, length)

    def mint_block(self, proof, coin_type="MAIN", previous_hash=None, user_tier=99):
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
                'coin_type': coin_type,
                'mined_amount': sum(int(t['amount']) for t in txs if t.get('sender') == '0')
            }
            block['hash'] = self.hash(block)
            
            if coin_type == "MAIN":
                self.current_main_transactions = []
            else:
                self.current_alt_transactions = []
            
        self.storage.allocate_block(block, user_random_tier=user_tier)
        return block

    def new_transaction(self, sender, recipient, amount, coin_type="MAIN", powers=None):
        try:
            amount = int(float(amount))
        except Exception:
            return False, "Invalid amount parameter."
            
        if amount <= 0:
            return False, "Amount must be strictly greater than zero."
            
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
                tx_data['powers'] = [round(float(p), 9) for p in powers]

            target_txs = self.current_main_transactions if coin_type == "MAIN" else self.current_alt_transactions
            target_txs.append(tx_data)
            return True, self.get_chain_length(coin_type) + 1

    @staticmethod
    def hash(block):
        block_copy = {k: v for k, v in block.items() if k not in ('hash', 'status', 'power_scale', 'archived_payload', 'data_snapshot_hash', 'space_id', 'space_level')}
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
        all_blocks = self.storage.get_all_blocks(coin_type)
        for block in all_blocks.values():
            txs = block.get('transactions', []) or block.get('archived_payload', [])
            for tx in txs:
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
        tokens = []
        all_blocks = self.storage.get_all_blocks(self.sub_coin_name)
        for idx in sorted(all_blocks.keys()):
            block = all_blocks[idx]
            txs = block.get('transactions', []) or block.get('archived_payload', [])
            for tx in txs:
                if tx.get('coin_type') == self.sub_coin_name:
                    if tx.get('recipient') == address:
                        if 'powers' in tx and isinstance(tx['powers'], list):
                            tokens.extend([round(float(p), 9) for p in tx['powers']])
                        elif 'power' in tx:
                            tokens.append(round(float(tx['power']), 9))
                        else:
                            tokens.extend([99.0] * int(tx.get('amount', 1)))
                    if tx.get('sender') == address:
                        if 'powers' in tx and isinstance(tx['powers'], list):
                            for p in tx['powers']:
                                p_flt = round(float(p), 9)
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
                            p_flt = round(float(p), 9)
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
        all_blocks = self.storage.get_all_blocks(coin_type)
        for block in all_blocks.values():
            if 'mined_amount' in block:
                total += int(block['mined_amount'])
            else:
                txs = block.get('transactions', []) or block.get('archived_payload', [])
                for tx in txs:
                    if tx.get('coin_type', 'MAIN') == coin_type and tx.get('sender') == "0":
                        total += int(tx['amount'])
        return int(total)

    def get_shield_impact_power(self):
        """Shield Coin: Smooth tiered decay, damped down to 0.000000001 floor beyond 20M."""
        alt_mined = self.get_total_mined(self.sub_coin_name)
        if alt_mined <= 0:
            return 99.0

        if alt_mined < 1000:
            progress = alt_mined / 1000.0
            power = 99.0 - (progress * 29.0)
            return max(70.0, round(power, 4))
        elif alt_mined < 100000:
            progress = (alt_mined - 1000) / 99000.0
            power = 70.0 - (progress * 20.0)
            return max(50.0, round(power, 4))
        elif alt_mined < 4000000:
            progress = (alt_mined - 100000) / 3900000.0
            power = 50.0 - (progress * 20.0)
            return max(30.0, round(power, 4))
        elif alt_mined < 10000000:
            progress = (alt_mined - 4000000) / 6000000.0
            power = 30.0 - (progress * 20.0)
            return max(10.0, round(power, 4))
        elif alt_mined < 20000000:
            progress = (alt_mined - 10000000) / 10000000.0
            power = 10.0 - (progress * 9.0)
            return max(1.0, round(power, 4))
        else:
            excess = alt_mined - 20000000
            tier_step = int(excess // 10000000)
            fraction = (excess % 10000000) / 10000000.0
            base_power = 1.0 / (10.0 ** (tier_step + 1))
            next_power = base_power / 10.0
            power = base_power - (fraction * (base_power - next_power))
            return max(0.000000001, round(power, 9))

    def get_mining_power_shield(self, address=None):
        return self.get_shield_impact_power()

    def get_mining_power_main(self, address=None):
        """Main Coin: Scales toward 21M limit and strictly seals at 0.0 power."""
        total_mined = self.get_total_mined("MAIN")
        max_limit = self.get_effective_max_supply(address)
        if total_mined >= max_limit:
            return 0.0

        progress = total_mined / float(max_limit)
        power = 99.0 * (1.0 - progress)
        return max(0.0001, round(power, 4))

# =====================================================================
# 24-HOUR ROTATING P2P DHT MESH & THERMAL DISPATCHER
# =====================================================================
class P2PNetworkManager:
    def __init__(self, blockchain, tcp_port=6000, udp_port=6001):
        self.blockchain = blockchain
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.peers = set()
        
        self.node_id = hex(uuid.getnode())
        self.current_epoch = int(time() // 86400)
        # Hardware-agnostic unbiased random allocation (1-99)
        self.my_tier = StorageGovernor.assign_pure_random_tier(self.node_id, self.current_epoch)
        self.is_overheating = False
        
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server.bind(('0.0.0.0', self.tcp_port))
            self.server.listen(25)
            threading.Thread(target=self._listen_tcp, daemon=True).start()
        except Exception:
            pass

        threading.Thread(target=self._bootstrap_discovery_loop, daemon=True).start()
        threading.Thread(target=self._broadcast_beacon, daemon=True).start()
        threading.Thread(target=self._listen_beacon, daemon=True).start()
        threading.Thread(target=self._daily_rotation_loop, daemon=True).start()

    def _daily_rotation_loop(self):
        """Rotates random storage tier every 24 hours across all infinite space folders."""
        while True:
            sleep(3600)
            new_epoch = int(time() // 86400)
            if new_epoch != self.current_epoch:
                self.current_epoch = new_epoch
                old_tier = self.my_tier
                self.my_tier = StorageGovernor.assign_pure_random_tier(self.node_id, self.current_epoch)
                if self.my_tier < old_tier:
                    self._prune_excess_blocks()

    def _prune_excess_blocks(self):
        for coin_type in ("MAIN", self.blockchain.sub_coin_name):
            all_b = self.blockchain.storage.get_all_blocks(coin_type)
            for idx in list(all_b.keys()):
                slot_hash = int(hashlib.sha256(f"{coin_type}_{idx}".encode()).hexdigest(), 16)
                block_tier = (slot_hash % 99) + 1
                if block_tier > self.my_tier:
                    self.blockchain.storage.soft_prune_shard(coin_type, idx)

    def register_peer(self, peer_address):
        try:
            ip = peer_address.split(':')[0]
            ip_hash = int(hashlib.sha256(ip.encode()).hexdigest(), 16)
            ip_tier = (ip_hash % 99) + 1
            if ip_tier <= self.my_tier or peer_address in BOOTSTRAP_PEERS:
                self.peers.add(peer_address)
        except Exception:
            pass

    def _bootstrap_discovery_loop(self):
        while True:
            for seed in BOOTSTRAP_PEERS:
                try:
                    s_ip, s_port = seed.split(':')
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3.0)
                    s.connect((s_ip, int(s_port)))
                    msg = {"action": "HELLO", "address": f"NODE:{self.tcp_port}", "tier": self.my_tier}
                    s.send(json.dumps(msg).encode())
                    resp = json.loads(s.recv(16384).decode())
                    for p in resp.get("peers", []):
                        self.register_peer(p)
                    s.close()
                except Exception:
                    pass
            sleep(30)

    def _broadcast_beacon(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            try:
                msg = f"VERIABLE_NODE:{self.tcp_port}".encode()
                sock.sendto(msg, ('<broadcast>', self.udp_port))
            except Exception:
                pass
            sleep(10)

    def _listen_beacon(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('0.0.0.0', self.udp_port))
            while True:
                data, addr = sock.recvfrom(1024)
                text = data.decode()
                if text.startswith("VERIABLE_NODE:"):
                    peer_tcp_port = int(text.split(":")[1])
                    self.register_peer(f"{addr[0]}:{peer_tcp_port}")
        except Exception:
            pass

    def _cool_down_node(self):
        self.is_overheating = False

    def handle_incoming_block(self, block):
        start_time = time()
        if self.is_overheating:
            self.blockchain.storage._save_to_overflow_storage(block)
            return

        self.blockchain.storage.allocate_block(block, user_random_tier=self.my_tier)
        duration = time() - start_time
        if StorageGovernor.check_thermal_pressure(duration):
            self.is_overheating = True
            threading.Timer(15.0, self._cool_down_node).start()

    def _listen_tcp(self):
        while True:
            try:
                conn, addr = self.server.accept()
                raw_data = conn.recv(65536).decode()
                if not raw_data:
                    conn.close()
                    continue
                msg = json.loads(raw_data)
                action = msg.get("action")
                
                if action == "HELLO":
                    self.register_peer(f"{addr[0]}:{msg.get('address', '').split(':')[-1]}")
                    conn.send(json.dumps({"peers": list(self.peers)}).encode())
                elif action == "NEW_BLOCK":
                    self.handle_incoming_block(msg.get("block"))
                elif action == "GET_BLOCK":
                    c_type = msg.get("coin_type", "MAIN")
                    b_idx = msg.get("index")
                    b = self.blockchain.storage.get_block(c_type, b_idx)
                    conn.send(json.dumps({"block": b}).encode())
                elif action == "RESTORE_SYNC":
                    c_type = msg.get("coin_type", "MAIN")
                    b_idx = msg.get("index")
                    remote_txs = msg.get("transactions", [])
                    self.blockchain.storage.request_restore_shard(c_type, b_idx, remote_txs)
                    elevated, _ = self.blockchain.storage.system_validate_and_elevate(c_type, b_idx)
                    conn.send(json.dumps({"elevated": elevated}).encode())
                    
                conn.close()
            except Exception:
                pass

    def broadcast_block(self, block):
        payload = {"action": "NEW_BLOCK", "block": block}
        for peer in list(self.peers):
            try:
                ip, port = peer.split(':')
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.5)
                s.connect((ip, int(port)))
                s.send(json.dumps(payload).encode())
                s.close()
            except Exception:
                self.peers.discard(peer)

# =====================================================================
# FLASK WEB & API SERVICES (PYINSTALLER EMBEDDED)
# =====================================================================
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    app = Flask(__name__, template_folder=template_folder)
else:
    app = Flask(__name__)

app.json.ensure_ascii = False
blockchain = Blockchain()
p2p_network = P2PNetworkManager(blockchain, tcp_port=6000, udp_port=6001)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/download', methods=['GET'])
def download_app():
    for f in ["veriable2-node.zip", os.path.join("dist", "veriable2-node.zip"), "veriable2.exe", os.path.join("dist", "veriable2.exe")]:
        if os.path.exists(f):
            return send_file(f, as_attachment=True)
    return jsonify({"error": "Node binary not found on local disk."}), 404

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
        return jsonify({'error': 'Invalid miner wallet address.'}), 400

    coin_type_key = blockchain.sub_coin_name if selected_coin == "ALT" else "MAIN"
    last_block = blockchain.get_last_block(coin_type_key)
    next_index = (last_block['index'] + 1) if last_block else 1

    if coin_type_key == "MAIN":
        mining_difficulty = blockchain.get_mining_power_main(miner_address)
        if mining_difficulty <= 0.0 or blockchain.get_total_mined("MAIN") >= blockchain.get_effective_max_supply(miner_address):
            return jsonify({'message': 'Main Coin has reached its 21,000,000 maximum supply cap.'}), 400
    else:
        mining_difficulty = blockchain.get_mining_power_shield(miner_address)
        target_impact_power = blockchain.get_shield_impact_power()

    var_hash, attempts, resolved_val = InfiniteVariableSearchEngine.search_infinite_variables(
        f"infinite_search_{coin_type_key}_{miner_address}_{next_index}", 
        mining_difficulty,
        coin_type=coin_type_key
    )

    if coin_type_key == "MAIN":
        rem = max(0, blockchain.get_effective_max_supply(miner_address) - blockchain.get_total_mined("MAIN"))
        reward = min(blockchain.BASE_MAIN_REWARD, rem)
        blockchain.new_transaction(sender="0", recipient=miner_address, amount=reward, coin_type="MAIN")
        
        block = blockchain.mint_block(
            proof=attempts, 
            coin_type=coin_type_key,
            previous_hash=blockchain.hash(last_block) if last_block else '1',
            user_tier=p2p_network.my_tier
        )
        p2p_network.broadcast_block(block)

        # MAIN COIN CLEAN OUTPUT (No attempts, displays only reward, power and index)
        return jsonify({
            'status': 'Success',
            'asset': 'Main Coin',
            'block_reward': f"{reward} Main Coin",
            'mining_power': round(mining_difficulty, 4),
            'block_index': block['index']
        }), 200

    else:
        reward = 1 
        blockchain.new_transaction(
            sender="0", 
            recipient=miner_address, 
            amount=reward, 
            coin_type=blockchain.sub_coin_name, 
            powers=[target_impact_power]
        )

        m_power_disp = round(mining_difficulty, 4) if mining_difficulty >= 0.001 else mining_difficulty
        i_power_disp = round(target_impact_power, 4) if target_impact_power >= 0.001 else target_impact_power

        block = blockchain.mint_block(
            proof=attempts, 
            coin_type=coin_type_key,
            previous_hash=blockchain.hash(last_block) if last_block else '1',
            user_tier=p2p_network.my_tier
        )
        p2p_network.broadcast_block(block)

        # SHIELD COIN CLEAN OUTPUT (No attempts, displays both mining power & impact power)
        return jsonify({
            'status': 'Success',
            'asset': 'Shield Coin',
            'block_reward': f"{reward} Shield Coin",
            'mining_power': m_power_disp,
            'impact_power': i_power_disp,
            'block_index': block['index']
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
        return jsonify({'error': 'No Shield tokens available in wallet to burn.'}), 400

    if selected_tier == 'any':
        eligible_tokens = list(all_user_tokens)
    else:
        eligible_tokens = [p for p in all_user_tokens if get_tier_for_power(p) == selected_tier]

    tier_available_count = len(eligible_tokens)
    if tier_available_count == 0:
        return jsonify({'error': f'No tokens found in selected tier ({selected_tier}).'}), 400

    req_count = data.get('burn_count')
    if req_count is not None and str(req_count).strip() != "":
        burn_amount = int(req_count)
    else:
        pct = float(data.get('alt_percentage', 100))
        burn_amount = max(1, int((tier_available_count * pct) / 100.0))

    if burn_amount <= 0 or burn_amount > tier_available_count:
        return jsonify({'error': f'Invalid quantity. Available: {tier_available_count}, Requested: {burn_amount}.'}), 400

    burned_tokens = eligible_tokens[:burn_amount]
    total_raw_power = sum(burned_tokens)
    effective_power = total_raw_power / 99.0

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
                message = f"[GLOBAL] Supply permanently destroyed: {burned_qty} Main Coins burned."
            else:
                stats['personal_burned'] += burned_qty
                message = f"[PERSONAL] Personal quota reduced: {burned_qty} Main Coins deducted."
        elif action == "expand_supply":
            expand_qty = max(1, int(effective_power * 150))
            if scope == "global":
                blockchain.dynamic_supply_offset = min(blockchain.supply_variance_limit, blockchain.dynamic_supply_offset + expand_qty)
                message = f"[GLOBAL] Capacity expanded: +{expand_qty} added."
            else:
                stats['personal_supply_offset'] += expand_qty
                message = f"[PERSONAL] Personal quota expanded: +{expand_qty} added."
        elif action == "boost_price":
            boost_val = round(min(5.0, effective_power * 0.5), 2)
            if scope == "global":
                blockchain.market_boost_bonus = boost_val
                message = f"[GLOBAL] Boost coefficient +%{boost_val} applied."
            else:
                stats['personal_boost'] = boost_val
                message = f"[PERSONAL] Personal boost coefficient +%{boost_val} applied."
        elif action == "discount_price":
            reduction_val = round(min(5.0, effective_power * 0.5), 2)
            if scope == "global":
                blockchain.market_boost_bonus = -reduction_val
                message = f"[GLOBAL] Discount mode applied: -%{reduction_val}."
            else:
                stats['personal_boost'] = -reduction_val
                message = f"[PERSONAL] Discount mode applied: -%{reduction_val}."
        elif action == "peg_static":
            if scope == "global":
                blockchain.market_peg_active = True
                blockchain.market_boost_bonus = 0.0
                message = "[GLOBAL] Valuation reference pegged."
            else:
                stats['personal_boost'] = 0.0
                message = "[PERSONAL] Valuation reference pegged."

    return jsonify({
        'status': 'Success',
        'action_result': message,
        'burned_count': burn_amount,
        'total_raw_power_released': round(total_raw_power, 6),
        'remaining_total_shield': len(blockchain.get_user_shield_tokens(address, True))
    }), 200

@app.route('/shard/restore', methods=['POST'])
def restore_shard_endpoint():
    data = request.get_json()
    coin_type = data.get('coin_type', 'MAIN')
    index = data.get('index')
    remote_txs = data.get('transactions', [])
    
    blockchain.storage.request_restore_shard(coin_type, index, remote_txs)
    elevated, msg = blockchain.storage.system_validate_and_elevate(coin_type, index)
    return jsonify({'success': elevated, 'message': msg}), 200 if elevated else 400

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
            'average_power': round(sum(v) / len(v), 6) if v else 0.0,
            'powers': sorted(v, reverse=True)
        }

    overall_avg = round(sum(user_tokens) / user_shield_count, 6) if user_shield_count > 0 else 0.0

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

# =====================================================================
# DUAL-MODE LAUNCH CONTROLLER (FIREWALL AVOIDANCE: 127.0.0.1)
# =====================================================================
def run_flask_service(host_ip, port):
    app.run(host=host_ip, port=port, threaded=True)

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    
    is_headless_server = (
        port == 80 or 
        '--server' in sys.argv or 
        (sys.platform.startswith('linux') and os.environ.get('DISPLAY') is None)
    )

    if is_headless_server:
        print(f"[*] Variable Coin Sovereign Node listening on 0.0.0.0:{port}...")
        app.run(host='0.0.0.0', port=port, threaded=True)
    else:
        # Local desktop mode binds exclusively to 127.0.0.1 (No Firewall Prompts)
        flask_thread = threading.Thread(target=run_flask_service, args=('127.0.0.1', port), daemon=True)
        flask_thread.start()
        sleep(1.0)

        if webview is not None:
            try:
                webview.create_window(
                    title="Variable Coin Sovereign Node",
                    url=f"http://127.0.0.1:{port}",
                    width=1280,
                    height=850,
                    min_size=(960, 640),
                    resizable=True
                )
                webview.start()
            except Exception:
                webbrowser.open(f"http://127.0.0.1:{port}")
                flask_thread.join()
        else:
            webbrowser.open(f"http://127.0.0.1:{port}")
            flask_thread.join()
