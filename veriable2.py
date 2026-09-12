import hashlib
import json
import sys
from time import time, sleep
from urllib.parse import urlparse
import requests
from flask import Flask, jsonify, request, render_template
import ecdsa
import threading
import secrets
import random

def yerin_kapasitesini_bul(yer_kimligi):
    hash_degeri = int(hashlib.md5(str(yer_kimligi).encode('utf-8')).hexdigest(), 16)
    return (hash_degeri % 99) + 1  

def veri_bu_yere_ait_mi(yer_kimligi, yerin_kapasitesi, veri_ozeti):
    ikili_kombinasyon = f"{yer_kimligi}_{veri_ozeti}"
    uyum_skoru = int(hashlib.md5(ikili_kombinasyon.encode('utf-8')).hexdigest(), 16)
    skor_yuzdesi = (uyum_skoru % 100) + 1
    return skor_yuzdesi <= yerin_kapasitesi

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
        
        self.uzay_boslugu = {} 
        self.bagli_noktalar = set()

        rastgele_sayi = secrets.randbelow(1000000000)
        self.yer_kimligi = f"Yer_{rastgele_sayi}"
        self.kapasite = yerin_kapasitesini_bul(self.yer_kimligi)
        
        self.target_price = 0.0
        self.market_price = 0.0

        self.BASE_MAX_MAIN = 21000000
        self.sub_coin_name = "SHIELD_COIN"
        self.supply_variance_limit = 1000000
        self.dynamic_supply_offset = 0
        self.burned_main_coins = 0
        
        self.difficulty_offset = 0
        self.difficulty_blocks_left = 0
        self.user_stats = {}  

        if not self.uzay_boslugu:
            self.yeni_veri_firlat(proof=100, difficulty=4, previous_hash='1', force_catch=True)
            
        self.start_background_sync()

    def register_node(self, address):
        parsed_url = urlparse(address)
        netloc = parsed_url.netloc if parsed_url.netloc else parsed_url.path
        if netloc:
            with self.lock:
                self.bagli_noktalar.add(netloc)

    @property
    def nodes(self):
        return list(self.bagli_noktalar)

    def veriyi_tut(self, block, force_catch=False):
        veri_ozeti = block.get('hash', str(block['index']))
        with self.lock:
            if block['index'] not in self.uzay_boslugu:
                if force_catch or veri_bu_yere_ait_mi(self.yer_kimligi, self.kapasite, veri_ozeti) or block['index'] == 1:
                    self.uzay_boslugu[block['index']] = block

    def bosluklari_doldur(self):
        while True:
            sleep(20)
            for node in list(self.bagli_noktalar):
                try:
                    res_nodes = requests.get(f'http://{node}/nodes/list', timeout=3)
                    if res_nodes.status_code == 200:
                        for peer in res_nodes.json().get('nodes', []):
                            self.register_node(peer)
                            
                    res = requests.get(f'http://{node}/uzay/kesitler', timeout=3)
                    if res_nodes.status_code == 200:
                        for block in res_nodes.json().get('havadaki_veriler', []):
                            self.veriyi_tut(block)
                except Exception:
                    pass

    def start_background_sync(self):
        threading.Thread(target=self.bosluklari_doldur, daemon=True).start()

    def get_chain_length(self):
        if not self.uzay_boslugu:
            return 0
        return max(self.uzay_boslugu.keys())

    @property
    def last_block(self):
        if not self.uzay_boslugu:
            return None
        return self.uzay_boslugu[self.get_chain_length()]

    def yeni_veri_firlat(self, proof, difficulty, previous_hash=None, force_catch=False):
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
            
        self.veriyi_tut(block, force_catch=force_catch)
        threading.Thread(target=self.broadcast_block, args=(block,), daemon=True).start()
        return block

    def broadcast_block(self, block):
        for node in list(self.bagli_noktalar):
            try:
                requests.post(f'http://{node}/uzay/firlat', json=block, timeout=2)
            except:
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
        for block in self.uzay_boslugu.values():
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
        for block in self.uzay_boslugu.values():
            for tx in block['transactions']:
                if tx.get('coin_type', 'MAIN') == coin_type and tx['sender'] == "0":
                    total += tx['amount']
        return total

    def get_alt_impact_power(self):
        alt_mined = self.get_total_mined(self.sub_coin_name)
        power_ratio = 1.0 / (1.0 + (alt_mined / 300.0))
        effective_ratio = max(0.01, power_ratio)
        return round(effective_ratio, 4)

    def get_alt_coin_reward(self):
        return max(0.001, round(5.0 / (1.0 + (self.get_total_mined(self.sub_coin_name) / 2000.0)), 4))

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

    def get_effective_price(self, address):
        impact = self.get_alt_impact_power()
        stats = self.get_user_stats(address)
        
        if stats['price_mode'] == "STABILIZE":
            return round(self.target_price + ((self.market_price - self.target_price) / (1.0 + (impact * 0.5))), 2)
        elif stats['price_mode'] == "BOOST":
            return round(self.market_price * (1.0 + (stats['active_price_shift'] * impact * 0.02)), 2)
        elif stats['price_mode'] == "DISCOUNT":
            return round(self.market_price * (1.0 - min(0.6, (stats['active_price_shift'] * impact * 0.015))), 2)
        return round(self.market_price, 2)

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

@app.route('/uzay/kesitler', methods=['GET'])
def send_fragments():
    return jsonify({
        'yer_kimligi': blockchain.yer_kimligi,
        'matematiksel_kapasite': f'%{blockchain.kapasite}',
        'havadaki_veriler': list(blockchain.uzay_boslugu.values())
    }), 200

@app.route('/uzay/firlat', methods=['POST'])
def receive_broadcast():
    blockchain.veriyi_tut(request.get_json())
    return jsonify({'mesaj': 'Veri uzaya fırlatıldı ve filtrelerden geçti.'}), 200

@app.route('/mine', methods=['GET'])
def mine():
    miner_address = request.args.get('address')
    selected_coin = request.args.get('coin', default='MAIN').upper()
    if not miner_address or len(miner_address) < 20:
        return jsonify({'error': 'Invalid miner address!'}), 400

    difficulty = blockchain.get_difficulty(coin_type=selected_coin, address=miner_address)

    if selected_coin == "MAIN":
        if blockchain.get_total_mined("MAIN") + 50 > blockchain.get_effective_max_supply(miner_address):
            return jsonify({'message': 'Main coin supply cap reached!'}), 400
        blockchain.new_transaction(sender="0", recipient=miner_address, amount=50, coin_type="MAIN")
        earned = "50 Main Coin"
    elif selected_coin == "ALT":
        reward = blockchain.get_alt_coin_reward()
        blockchain.new_transaction(sender="0", recipient=miner_address, amount=reward, coin_type=blockchain.sub_coin_name)
        earned = f"{reward} Shield Coin"
    else:
        return jsonify({'error': 'Invalid asset selection!'}), 400

    last_block = blockchain.last_block
    proof = blockchain.proof_of_work(last_block, difficulty)
    
    block = blockchain.yeni_veri_firlat(
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
            if scope == "global":
                if action == "stabilize":
                    blockchain.market_price = blockchain.target_price
                elif action == "boost":
                    blockchain.market_price += round(effective_power * 0.1, 2)
                elif action == "discount":
                    blockchain.market_price = max(0.0, blockchain.market_price - round(effective_power * 0.1, 2))
                message = f"[GLOBAL] Global market price updated."
            else:
                if action == "stabilize":
                    stats['price_mode'] = "STABILIZE"
                elif action == "boost":
                    stats['price_mode'] = "BOOST"
                    stats['active_price_shift'] += round(effective_power * 0.1, 2)
                elif action == "discount":
                    stats['price_mode'] = "DISCOUNT"
                    stats['active_price_shift'] += round(effective_power * 0.1, 2)
                message = f"[PERSONAL] Personal effective price modified."

    impact_pct = int(impact * 100)
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
    impact_pct = int(blockchain.get_alt_impact_power() * 100)
    
    return jsonify({
        '1_GLOBAL_DATA': {
            'main_coin_supply': f"{blockchain.get_total_mined('MAIN')} / {blockchain.get_effective_max_supply(user_address)}",
            'shield_coin_circulating': f"{total_alt_mined - burned_alt} (Burned: {burned_alt})",
            'global_market_price': f"{blockchain.market_price}$",
            'active_nodes': blockchain.nodes
        },
        '2_NODE_DATA': {
            'storage_capacity': f"%{blockchain.kapasite}", 
            'node_coordinate': blockchain.yer_kimligi
        },

    
        '3_USER_DATA': {
            'wallet_address': user_address, 
            'personal_effective_price': f"{blockchain.get_effective_price(user_address)}$", 
            'impact_power': f"{impact_pct}%"
        },
        'uzaydaki_veriler': list(blockchain.uzay_boslugu.values())
    }), 200

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app.run(host='0.0.0.0', port=port, threaded=True)
