import hashlib
import json
import sys
import math
from time import time, sleep
from urllib.parse import urlparse
import requests
from flask import Flask, jsonify, request, render_template
import ecdsa
import threading
import secrets

def calculate_node_capacity(node_id):
    hash_value = int(hashlib.md5(str(node_id).encode('utf-8')).hexdigest(), 16)
    return (hash_value % 99) + 1

def verify_data_affinity(node_id, node_capacity, data_summary):
    pair_combination = f"{node_id}_{data_summary}"
    affinity_score = int(hashlib.md5(pair_combination.encode('utf-8')).hexdigest(), 16)
    score_percentage = (affinity_score % 99) + 1
    return score_percentage <= node_capacity

WORD_LIST = [
    "apple", "river", "mountain", "token", "coin", "node", "block", "chain", 
    "secure", "miner", "shield", "network", "crypto", "digital", "ledger", 
    "protocol", "hash", "proof", "work", "stake", "wallet", "address", 
    "private", "public", "key", "transfer", "supply", "limit", "burn", "gas"
]

def generate_mnemonic_wallet():
    chosen_words = [secrets.choice(WORD_LIST) for _ in range(12)]
    mnemonic_phrase = " ".join(chosen_words)
    seed_bytes = hashlib.sha256(mnemonic_phrase.encode()).digest()
    sk = ecdsa.SigningKey.from_string(seed_bytes, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    return {
        'mnemonic': mnemonic_phrase,
        'private_key': sk.to_string().hex(),
        'public_key': vk.to_string().hex()
    }

def wallet_from_mnemonic(mnemonic_phrase):
    seed_bytes = hashlib.sha256(mnemonic_phrase.strip().encode()).digest()
    sk = ecdsa.SigningKey.from_string(seed_bytes, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    return sk.to_string().hex(), vk.to_string().hex()

def verify_key_match(private_key_hex, public_key_hex):
    if not private_key_hex or not public_key_hex:
        return False
    try:
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(private_key_hex), curve=ecdsa.SECP256k1)
        return sk.verifying_key.to_string().hex() == public_key_hex
    except Exception:
        return False

class Blockchain(object):
    def __init__(self):
        self.current_transactions = []
        self.BURN_ADDRESS = "0x000000000000000000000000000000000000dEaD"
        self.lock = threading.Lock()
        
        self.chain_space = {} 
        self.connected_nodes = set()

        random_suffix = secrets.randbelow(1000000000)
        self.node_id = f"Node_{random_suffix}"
        self.storage_capacity = calculate_node_capacity(self.node_id)
        
        self.target_price = 0.0
        self.BASE_MAX_MAIN = 21000000
        self.BASE_MAIN_REWARD = 50.0
        self.sub_coin_name = "SHIELD_COIN"
        self.supply_variance_limit = 1000000
        self.dynamic_supply_offset = 0
        self.burned_main_coins = 0
        
        self.difficulty_offset = 0
        self.difficulty_blocks_left = 0
        self.user_stats = {}  

        if not self.chain_space:
            self.mint_block(proof=100, difficulty=4, previous_hash='1', force_catch=True)
            
        self.start_background_sync()

    def register_node(self, address):
        parsed_url = urlparse(address)
        netloc = parsed_url.netloc if parsed_url.netloc else parsed_url.path
        if netloc:
            with self.lock:
                self.connected_nodes.add(netloc)

    @property
    def nodes(self):
        return list(self.connected_nodes)

    def store_block(self, block, force_catch=False):
        data_summary = block.get('hash', str(block['index']))
        with self.lock:
            if block['index'] not in self.chain_space:
                if force_catch or verify_data_affinity(self.node_id, self.storage_capacity, data_summary) or block['index'] == 1:
                    self.chain_space[block['index']] = block

    def sync_chain_data(self):
        while True:
            sleep(20)
            for node in list(self.connected_nodes):
                try:
                    res_nodes = requests.get(f'http://{node}/nodes/list', timeout=3)
                    if res_nodes.status_code == 200:
                        for peer in res_nodes.json().get('nodes', []):
                            self.register_node(peer)
                            
                    res = requests.get(f'http://{node}/space/fragments', timeout=3)
                    if res.status_code == 200:
                        for block in res.json().get('chain_blocks', []):
                            self.store_block(block)
                except Exception:
                    pass

    def start_background_sync(self):
        threading.Thread(target=self.sync_chain_data, daemon=True).start()

    def get_chain_length(self):
        if not self.chain_space:
            return 0
        return max(self.chain_space.keys())

    @property
    def last_block(self):
        if not self.chain_space:
            return None
        return self.chain_space[self.get_chain_length()]

    def mint_block(self, proof, difficulty, previous_hash=None, force_catch=False):
        with self.lock:
            last = self.last_block
            prev_hash = previous_hash or (self.hash(last) if last else '1')
            
            block = {
                'index': (last['index'] + 1) if last else 1,
                'timestamp': time(),
                'transactions': self.current_transactions,
                'proof': proof,
                'difficulty': difficulty,
                'previous_hash': prev_hash,
            }
            block['hash'] = self.hash(block)
            self.current_transactions = []
            
        self.store_block(block, force_catch=force_catch)
        threading.Thread(target=self.broadcast_block, args=(block,), daemon=True).start()
        return block

    def broadcast_block(self, block):
        for node in list(self.connected_nodes):
            try:
                requests.post(f'http://{node}/space/broadcast', json=block, timeout=2)
            except Exception:
                pass

    def new_transaction(self, sender, recipient, amount, coin_type="MAIN"):
        if not isinstance(amount, (int, float)) or amount <= 0:
            return False, "Invalid amount!"
        with self.lock:
            if sender != "0" and self.get_balance(sender, coin_type, True) < amount:
                return False, "Insufficient balance!"
            self.current_transactions.append({
                'sender': sender,
                'recipient': recipient,
                'amount': amount,
                'coin_type': coin_type
            })
            return True, self.get_chain_length() + 1

    @staticmethod
    def hash(block):
        block_copy = {k: v for k, v in block.items() if k != 'hash'}
        return hashlib.sha256(json.dumps(block_copy, sort_keys=True).encode()).hexdigest()

    def proof_of_work(self, last_block, difficulty):
        last_proof = last_block['proof'] if last_block else 100
        last_hash = self.hash(last_block) if last_block else '1'
        proof = 0
        while self.valid_proof(last_proof, proof, last_hash, difficulty) is False:
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof, last_hash, difficulty):
        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:difficulty] == "0" * difficulty

    def get_user_stats(self, address):
        if address not in self.user_stats:
            self.user_stats[address] = {
                'price_mode': 'STABILIZE', 
                'active_price_shift': 0.0, 
                'diff_offset': 0, 
                'diff_blocks_left': 0, 
                'personal_supply_offset': 0, 
                'personal_burned': 0
            }
        return self.user_stats[address]

    def get_balance(self, address, coin_type="MAIN", include_pending=True):
        balance = 0
        for block in self.chain_space.values():
            for tx in block['transactions']:
                if tx.get('coin_type', 'MAIN') == coin_type:
                    if tx['sender'] == address:
                        balance -= tx['amount']
                    if tx['recipient'] == address:
                        balance += tx['amount']
        if include_pending:
            for tx in self.current_transactions:
                if tx.get('coin_type', 'MAIN') == coin_type and tx['sender'] == address:
                    balance -= tx['amount']
        return balance

    def get_effective_max_supply(self, address=None):
        base = (self.BASE_MAX_MAIN + self.dynamic_supply_offset) - self.burned_main_coins
        if address:
            stats = self.get_user_stats(address)
            base += stats['personal_supply_offset']
            base -= stats['personal_burned']
        return base

    def get_total_mined(self, coin_type="MAIN"):
        total = 0
        for block in self.chain_space.values():
            for tx in block['transactions']:
                if tx.get('coin_type', 'MAIN') == coin_type and tx['sender'] == "0":
                    total += tx['amount']
        return total

    def get_node_power(self, coin_type="MAIN", address=None):
        if coin_type == "MAIN":
            total_mined = self.get_total_mined("MAIN")
            max_limit = self.get_effective_max_supply(address)
            if total_mined >= max_limit:
                return 0.0
            progress = total_mined / max_limit
            power = 99.0 * (1.0 - progress)
            return max(0.0, round(power, 6))
        else:
            alt_mined = self.get_total_mined(self.sub_coin_name)
            alt_burned = self.get_balance(self.BURN_ADDRESS, self.sub_coin_name, False)
            total_activity = alt_mined + alt_burned
            decay_factor = 1.0 + (total_activity / 5000.0)
            power = 99.0 / decay_factor
            return max(0.000001, round(power, 8))

    def get_main_coin_reward(self, address=None):
        power = self.get_node_power("MAIN", address)
        if power <= 0.0:
            return 0.0
        reward = self.BASE_MAIN_REWARD * (power / 99.0)
        return max(0.000001, round(reward, 6))

    def get_alt_coin_reward(self):
        power = self.get_node_power(self.sub_coin_name)
        return max(0.000001, round(power * 0.05, 6))

    def get_alt_impact_power(self):
        return max(0.000001 / 99.0, min(1.0, self.get_node_power(self.sub_coin_name) / 99.0))

    def get_difficulty(self, coin_type="MAIN", address=None):
        total_blocks = self.get_chain_length()
        if coin_type == "MAIN":
            if total_blocks < 200: base = 4
            elif total_blocks < 1000: base = 5
            elif total_blocks < 5000: base = 6
            else: base = 7
            
            global_off = self.difficulty_offset if self.difficulty_blocks_left > 0 else 0
            personal_off = self.get_user_stats(address)['diff_offset'] if address and self.get_user_stats(address)['diff_blocks_left'] > 0 else 0
            return max(1, base + global_off + personal_off)
        else:
            return min(10, 4 + int(self.get_total_mined(self.sub_coin_name) / 300))

    @property
    def market_price(self):
        total_mined = self.get_total_mined("MAIN")
        total_blocks = self.get_chain_length()

        if total_mined == 0 or total_blocks <= 1:
            return 0.0

        activity = (total_blocks - 1) + len(self.current_transactions)
        demand_factor = math.log(activity + 1, 2) * 0.15

        burned = self.burned_main_coins
        circulating = max(1, total_mined - burned)
        scarcity_factor = 1.0 + (burned / circulating) * 2.0

        current_diff = self.get_difficulty("MAIN")
        difficulty_weight = (current_diff - 3) * 0.20

        shield_burned = self.get_balance(self.BURN_ADDRESS, self.sub_coin_name, False)
        protocol_burn_pressure = math.sqrt(shield_burned) * 0.05

        computed_price = demand_factor * scarcity_factor * (difficulty_weight + protocol_burn_pressure)
        return round(max(0.0, computed_price), 2)

    def get_effective_price(self, address):
        base_market = self.market_price
        if base_market == 0.0:
            return 0.0

        impact = self.get_alt_impact_power()
        stats = self.get_user_stats(address)
        
        if stats['price_mode'] == "STABILIZE":
            return round(self.target_price + ((base_market - self.target_price) / (1.0 + (impact * 0.5))), 2)
        elif stats['price_mode'] == "BOOST":
            return round(base_market * (1.0 + (stats['active_price_shift'] * impact * 0.02)), 2)
        elif stats['price_mode'] == "DISCOUNT":
            return round(base_market * (1.0 - min(0.6, (stats['active_price_shift'] * impact * 0.015))), 2)
        return round(base_market, 2)

app = Flask(__name__)
app.json.ensure_ascii = False
blockchain = Blockchain()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/wallet/new', methods=['GET'])
def new_wallet():
    return jsonify(generate_mnemonic_wallet()), 200

@app.route('/wallet/recover', methods=['POST'])
def recover_wallet():
    mnemonic = request.get_json().get('mnemonic', '')
    if not mnemonic or len(mnemonic.split()) < 12:
        return jsonify({'error': 'Invalid 12-word seed phrase!'}), 400
    priv, pub = wallet_from_mnemonic(mnemonic)
    return jsonify({'private_key': priv, 'public_key': pub}), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    nodes = request.get_json().get('nodes', [])
    if not nodes:
        return jsonify({'error': 'Error: Please supply a valid list of nodes'}), 400
    for node in nodes:
        blockchain.register_node(node)
    return jsonify({'message': 'New nodes have been added', 'total_nodes': blockchain.nodes}), 201

@app.route('/nodes/list', methods=['GET'])
def list_nodes():
    return jsonify({'nodes': blockchain.nodes}), 200

@app.route('/space/fragments', methods=['GET'])
def send_fragments():
    return jsonify({
        'node_id': blockchain.node_id,
        'storage_capacity': f"%{blockchain.storage_capacity}",
        'chain_blocks': list(blockchain.chain_space.values())
    }), 200

@app.route('/space/broadcast', methods=['POST'])
def receive_broadcast():
    blockchain.store_block(request.get_json())
    return jsonify({'message': 'Data packet broadcasted and verified by node filters.'}), 200

@app.route('/mine', methods=['GET'])
def mine():
    miner_address = request.args.get('address')
    selected_coin = request.args.get('coin', default='MAIN').upper()
    if not miner_address or len(miner_address) < 20:
        return jsonify({'error': 'Invalid miner address!'}), 400

    difficulty = blockchain.get_difficulty(coin_type=selected_coin, address=miner_address)

    if selected_coin == "MAIN":
        reward = blockchain.get_main_coin_reward(miner_address)
        if reward <= 0.0 or blockchain.get_total_mined("MAIN") >= blockchain.get_effective_max_supply(miner_address):
            return jsonify({'message': 'Main coin supply cap reached! Power is 0.'}), 400
        
        blockchain.new_transaction(sender="0", recipient=miner_address, amount=reward, coin_type="MAIN")
        earned = f"{reward} Main Coin (Power: {blockchain.get_node_power('MAIN', miner_address)})"
    elif selected_coin == "ALT":
        reward = blockchain.get_alt_coin_reward()
        blockchain.new_transaction(sender="0", recipient=miner_address, amount=reward, coin_type=blockchain.sub_coin_name)
        earned = f"{reward} Shield Coin (Power: {blockchain.get_node_power('ALT')})"
    else:
        return jsonify({'error': 'Invalid asset selection!'}), 400

    last_block = blockchain.last_block
    proof = blockchain.proof_of_work(last_block, difficulty)
    
    block = blockchain.mint_block(
        proof, 
        difficulty, 
        previous_hash=blockchain.hash(last_block) if last_block else '1'
    )

    return jsonify({
        'status': 'Success',
        'earned': earned,
        'difficulty_solved': f"{difficulty} Leading Zeros",
        'market_price': f"{blockchain.market_price}$",
        'effective_price_for_you': f"{blockchain.get_effective_price(miner_address)}$",
        'block_index': block['index']
    }), 200

@app.route('/protocol/act', methods=['POST'])
def protocol_action():
    data = request.get_json()
    address = data.get('address')
    private_key = data.get('private_key')
    alt_amount = data.get('alt_amount', 0)
    category = data.get('category')
    action = data.get('action')
    scope = data.get('scope', 'personal')

    if not address or not private_key or not verify_key_match(private_key, address):
        return jsonify({'error': 'ACCESS DENIED!'}), 403

    try:
        alt_amount = float(alt_amount)
    except ValueError:
        return jsonify({'error': 'Amount must be numeric!'}), 400

    if alt_amount <= 0 or blockchain.get_balance(address, blockchain.sub_coin_name, True) < alt_amount:
        return jsonify({'error': 'Insufficient balance or invalid amount!'}), 400

    impact = blockchain.get_alt_impact_power()
    effective_power = alt_amount * impact

    success, msg = blockchain.new_transaction(
        sender=address, 
        recipient=blockchain.BURN_ADDRESS, 
        amount=alt_amount, 
        coin_type=blockchain.sub_coin_name
    )
    if not success:
        return jsonify({'error': msg}), 400

    stats = blockchain.get_user_stats(address)
    message = ""

    with blockchain.lock:
        if category == "supply":
            if scope == "global":
                if action == "burn_main":
                    burned_qty = int(effective_power * 100)
                    blockchain.burned_main_coins += burned_qty
                    message = f"[GLOBAL] {alt_amount} Shield burned. {burned_qty} Main Coins destroyed globally."
                elif action == "expand_supply":
                    delta = int(effective_power * 150)
                    blockchain.dynamic_supply_offset = min(blockchain.supply_variance_limit, blockchain.dynamic_supply_offset + delta)
                    message = f"[GLOBAL] Main coin supply cap expanded by {delta} globally."
            else:
                if action == "burn_main":
                    burned_qty = int(effective_power * 100)
                    stats['personal_burned'] += burned_qty
                    message = f"[PERSONAL] {alt_amount} Shield burned. {burned_qty} Main Coins destroyed in your scope."
                elif action == "expand_supply":
                    delta = int(effective_power * 150)
                    stats['personal_supply_offset'] += delta
                    message = f"[PERSONAL] Your personal supply cap expanded by {delta}."

        elif category == "difficulty":
            blocks_granted = max(1, int(effective_power * 2))
            if scope == "global":
                if action == "ease":
                    blockchain.difficulty_offset = -1
                elif action == "tighten":
                    blockchain.difficulty_offset = 1
                blockchain.difficulty_blocks_left += blocks_granted
                message = f"[GLOBAL] Network difficulty updated for {blocks_granted} blocks."
            else:
                if action == "ease":
                    stats['diff_offset'] = -1
                elif action == "tighten":
                    stats['diff_offset'] = 1
                stats['diff_blocks_left'] += blocks_granted
                message = f"[PERSONAL] Personal difficulty updated for {blocks_granted} blocks."

        elif category == "price":
            if scope == "personal":
                if action == "stabilize":
                    stats['price_mode'] = "STABILIZE"
                elif action == "boost":
                    stats['price_mode'] = "BOOST"
                    stats['active_price_shift'] += round(effective_power * 0.1, 2)
                elif action == "discount":
                    stats['price_mode'] = "DISCOUNT"
                    stats['active_price_shift'] += round(effective_power * 0.1, 2)
                message = "[PERSONAL] Personal effective price modified."
            else:
                message = "[GLOBAL] Global price dynamics are driven algorithmically by supply, demand, and chain volume."

    impact_pct = max(0.000001, min(99.0, round(impact * 99.0, 6)))
    return jsonify({
        'status': 'Success',
        'action_result': message,
        'burned_shield': alt_amount,
        'current_impact_power': f"{impact_pct}%",
        'your_effective_price': f"{blockchain.get_effective_price(address)}$",
        'global_market_price': f"{blockchain.market_price}$"
    }), 200

@app.route('/chain', methods=['GET'])
def full_chain():
    user_address = request.args.get('address', 'Unknown_User')
    total_alt_mined = blockchain.get_total_mined(blockchain.sub_coin_name)
    burned_alt = blockchain.get_balance(blockchain.BURN_ADDRESS, blockchain.sub_coin_name, False)
    impact_pct = max(0.000001, min(99.0, round(blockchain.get_alt_impact_power() * 99.0, 6)))
    
    return jsonify({
        '1_GLOBAL_DATA': {
            'block_height': blockchain.get_chain_length(),
            'active_peers': len(blockchain.nodes) + 1,
            'main_coin_supply': f"{blockchain.get_total_mined('MAIN')} / {blockchain.get_effective_max_supply(user_address)}",
            'shield_coin_circulating': f"{total_alt_mined - burned_alt} (Burned: {burned_alt})",
            'global_market_price': f"{blockchain.market_price}$",
            'active_nodes': blockchain.nodes
        },
        '2_USER_DATA': {
            'wallet_address': user_address, 
            'personal_effective_price': f"{blockchain.get_effective_price(user_address)}$", 
            'impact_power': f"{impact_pct}%",
            'node_power_main': blockchain.get_node_power("MAIN", user_address),
            'node_power_shield': blockchain.get_node_power("ALT")
        },
        'chain_data': list(blockchain.chain_space.values())
    }), 200

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app.run(host='0.0.0.0', port=port, threaded=True)
