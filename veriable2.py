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

# Masaüstü yerel pencere modülü (pywebview)
try:
    import webview
except ImportError:
    webview = None

# =====================================================================
# GLOBAL PROTOKOL YAPILANDIRMASI VE SABİTLER
# =====================================================================
MATRIX_BASE_DIR = "variable_matrix"
OVERFLOW_STORAGE_FILE = "overflow_matrix.json"
BOOTSTRAP_PEERS = ["104.248.255.163:6000"]
STORAGE_SAFETY_MARGIN_MB = 250   # Diskte 250 MB'dan az yer kalırsa otomatik taşma devreye girer
THERMAL_TIME_THRESHOLD = 0.85     # İşlemci aşırı yük koruması eşik süresi

# =====================================================================
# KRİPTOGRAFİK CÜZDAN MOTORU (BITCOIN SECP256K1)
# =====================================================================
def generate_master_wallet():
    """Bitcoin standardında 256-bit SECP256k1 anahtar çifti üretir."""
    priv_bytes = secrets.token_bytes(32)
    sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    return {
        'private_key': sk.to_string().hex(),
        'public_key': vk.to_string().hex()
    }

def wallet_from_private_key(private_key_hex):
    """64 karakterlik özel anahtardan cüzdan adresini doğrular ve türetir."""
    clean_hex = str(private_key_hex).strip().lower()
    if len(clean_hex) != 64:
        return None, None, f"Geçersiz anahtar uzunluğu ({len(clean_hex)}). 64 onaltılık karakter olmalıdır."
    try:
        key_int = int(clean_hex, 16)
        curve_order = ecdsa.SECP256k1.order
        if key_int <= 0 or key_int >= curve_order:
            return None, None, "Değer SECP256k1 eliptik eğri sınırları dışında."
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(clean_hex), curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        return sk.to_string().hex(), vk.to_string().hex(), None
    except ValueError:
        return None, None, "Biçim hatası: Özel anahtar sadece onaltılık karakter içerebilir."
    except Exception as e:
        return None, None, f"Kriptografik doğrulama hatası: {str(e)}"

def verify_key_match(private_key_hex, public_key_hex):
    """Özel anahtarın hedef cüzdan adresi ile uyuştuğunu kriptografik olarak denetler."""
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
    """Token gücünü protokol seviye kategorisine eşler."""
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
# DONANIMDAN BAĞIMSIZ RASTGELE KOTA VE DEPOLAMA DENETÇİSİ
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
        Cihaz donanımına (CPU, RAM, Disk) KESİNLİKLE BAKMAZ.
        Her 24 saatte bir (epoch) tamamen bağımsız ve rastgele 1 ile 99 arasında bir kota belirler.
        En az %1 (katılım tabanı), en çok %99 (tekel engeli).
        """
        seed = f"VERIABLE_PURE_RANDOM_TIER_{node_id}_{epoch}"
        raw_hash = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        pure_tier = (raw_hash % 99) + 1  # 1 ile 99 arası
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
# SONSUZ UZAY MATRİKS DEPOLAMA MOTORU (SPACE_1 ... SPACE_N)
# =====================================================================
class ShardedResilientVariableStorageEngine:
    """
    Sonsuz Uzay Depolama Motoru:
    - Veriler asla tek klasörde toplanmaz; space_1, space_2 ... space_N şeklinde sonsuza uzanır.
    - Her klasör 1 ile 99 seviye (en az 1, en çok 99 blok) derinliğinde veri saklar.
    - 99 blok dolduğunda otomatik olarak bir sonraki uzay klasörü açılır.
    - Disk alanı yetersiz olduğunda (<250 MB) veriler taşma havuzuna aktarılır (offload).
    - Blok tapusu ve kullanıcının fon hakkı 1.0 tabanında (BASE_LOCKED_OFFLOADED) eksiksiz korunur.
    - Budanan blokların işlem yükü %99 oranında silinir.
    - Geri yüklenen bloklar karantinada bekletilip SHA-256 ile doğrulanarak 99.0 güce yükseltilir.
    """
    def __init__(self, base_dir=MATRIX_BASE_DIR):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.index_headers = {}

    def _get_infinite_space_id(self, index):
        """Her 99 veride bir sonraki sonsuz uzay klasörünün numarasını verir."""
        idx = int(index)
        return ((idx - 1) // 99) + 1

    def _get_level_in_space(self, index):
        """Bloğun bulunduğu uzay klasörü içerisindeki 1-99 seviye derinliğini belirler."""
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

        # DİSK DOLUYSA VEYA KULLANICININ GÜNLÜK RASTGELE PAYINDAN YÜKSEKSE:
        # Fiziksel işlemler offload edilir, ancak fon tapusu ve blok 1.0 tabanında KORUNUR.
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
        """Yerel disk yetmediğinde fiziksel veriyi harici taşma dizinine yazar."""
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
        """Eski bloğun %99 işlem yükünü siler, tapuyu 1.0 tabanına kilitler."""
        idx = int(index)
        block = self.get_block(coin_type, idx)
        if not block:
            return False, "Blok bulunamadı."

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
        return True, f"Blok {coin_type}_{idx} space_{block.get('space_id')} içinde 1.0 tabanına kilitlendi."

    def request_restore_shard(self, coin_type, index, remote_transactions):
        """Dışarıdan gelen veriyi doğrudan zincire almaz, 1.0 karantinasına sokar."""
        idx = int(index)
        block = self.get_block(coin_type, idx)
        if not block:
            return False, "Blok bulunamadı."

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
        return True, "Blok karantina modunda kabul edildi (1.0)."

    def system_validate_and_elevate(self, coin_type, index):
        """Karantinadaki veriyi SHA-256 snapshot ile doğrular, tutarsa 99.0 aktif yapar."""
        idx = int(index)
        block = self.get_block(coin_type, idx)
        if not block or block.get('status') != "RESTORE_PENDING":
            return False, "Doğrulama reddedildi: Karantina durumu yok."

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
            return True, "Doğrulama başarılı: Blok 99.0 aktif gücüne yükseltildi."
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
            return False, "Kriptografik uyuşmazlık: Blok 1.0 tabanında tutuldu."

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
        """Sonsuz sayıda oluşabilecek tüm space_X klasörlerini dinamik tarar."""
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
# BLOKZİNCİR PROTOKOL ÇEKİRDEĞİ
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
        self.BASE_MAIN_REWARD = 50  # Her blok tam 50 Main Coin
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
            return False, "Geçersiz miktar parametresi."
            
        if amount <= 0:
            return False, "Miktar sıfırdan büyük olmalıdır."
            
        with self.lock:
            if sender != "0" and self.get_balance(sender, coin_type, True) < amount:
                return False, "Yetersiz bakiye."
            
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
        """Shield Coin: Kademeli azalan ve 20M sonrasında basamak basamak sönümlenen eğri."""
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
        """Main Coin: 21 milyona doğru pürüzsüz iner, tavanda 0.0'a kilitlenir."""
        total_mined = self.get_total_mined("MAIN")
        max_limit = self.get_effective_max_supply(address)
        if total_mined >= max_limit:
            return 0.0

        progress = total_mined / float(max_limit)
        power = 99.0 * (1.0 - progress)
        return max(0.0001, round(power, 4))

# =====================================================================
# 24 SAATTE BİR ROTASYON YAPAN P2P DHT AĞ VE TERMAL YÖNETİCİ
# =====================================================================
class P2PNetworkManager:
    def __init__(self, blockchain, tcp_port=6000, udp_port=6001):
        self.blockchain = blockchain
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.peers = set()
        
        self.node_id = hex(uuid.getnode())
        self.current_epoch = int(time() // 86400)
        # Donanıma bakılmaksızın 1 ile 99 arasında saf rastgele pay
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
        """Her 24 saatte bir tüm sonsuz uzay klasörlerindeki kotaları yeniden dağıtır."""
        while True:
            sleep(3600)  # Her saat başı döngüyü kontrol eder
            new_epoch = int(time() // 86400)
            if new_epoch != self.current_epoch:
                self.current_epoch = new_epoch
                old_tier = self.my_tier
                # 24 saat doldu: Yeni saf rastgele oran atanır (Donanıma bakılmaz)
                self.my_tier = StorageGovernor.assign_pure_random_tier(self.node_id, self.current_epoch)
                
                # Eğer oran düştüyse tüm sonsuz uzay klasörlerindeki fazla blokları 1.0 tabanına budar
                if self.my_tier < old_tier:
                    self._prune_excess_blocks()

    def _prune_excess_blocks(self):
        """Sonsuz uzay klasörlerinin tamamında yeni kotanın üstünde kalan blokları hafifletir."""
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
# FLASK WEB & API SERVİSİ (PYINSTALLER İLE GÖMÜLÜ ŞABLONLAR)
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
    return jsonify({"error": "Kurulum paketi disk üzerinde bulunamadı."}), 404

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
        return jsonify({'error': 'Geçersiz madenci cüzdan adresi.'}), 400

    coin_type_key = blockchain.sub_coin_name if selected_coin == "ALT" else "MAIN"
    last_block = blockchain.get_last_block(coin_type_key)
    next_index = (last_block['index'] + 1) if last_block else 1

    if coin_type_key == "MAIN":
        mining_difficulty = blockchain.get_mining_power_main(miner_address)
        target_power = mining_difficulty
        if mining_difficulty <= 0.0 or blockchain.get_total_mined("MAIN") >= blockchain.get_effective_max_supply(miner_address):
            return jsonify({'message': 'Main Coin maksimum arz tavanına (21.000.000) ulaştı.'}), 400
    else:
        mining_difficulty = blockchain.get_mining_power_shield(miner_address)
        target_power = blockchain.get_shield_impact_power()

    var_hash, attempts, resolved_val = InfiniteVariableSearchEngine.search_infinite_variables(
        f"infinite_search_{coin_type_key}_{miner_address}_{next_index}", 
        mining_difficulty,
        coin_type=coin_type_key
    )

    if coin_type_key == "MAIN":
        rem = max(0, blockchain.get_effective_max_supply(miner_address) - blockchain.get_total_mined("MAIN"))
        reward = min(blockchain.BASE_MAIN_REWARD, rem)
        blockchain.new_transaction(sender="0", recipient=miner_address, amount=reward, coin_type="MAIN")
        earned = f"{reward} Main Coin (Madencilik Gücü: {round(mining_difficulty, 4)})"
    else:
        reward = 1 
        blockchain.new_transaction(
            sender="0", 
            recipient=miner_address, 
            amount=reward, 
            coin_type=blockchain.sub_coin_name, 
            powers=[target_power]
        )
        p_disp = round(target_power, 4) if target_power >= 0.001 else target_power
        earned = f"{reward} Shield Coin (Doğuş Gücü: {p_disp})"

    block = blockchain.mint_block(
        proof=attempts, 
        coin_type=coin_type_key,
        previous_hash=blockchain.hash(last_block) if last_block else '1',
        user_tier=p2p_network.my_tier
    )

    p2p_network.broadcast_block(block)

    return jsonify({
        'status': 'Success',
        'earned': earned,
        'mining_attempts': attempts,
        'block_index': block['index'],
        'space_id': block.get('space_id', 1),
        'space_level': block.get('space_level', 1),
        'node_assigned_tier': f"%{p2p_network.my_tier}",
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
        return jsonify({'error': 'Erişim engellendi: 256-bit imza uyuşmazlığı.'}), 403

    all_user_tokens = blockchain.get_user_shield_tokens(address, include_pending=True)
    if not all_user_tokens:
        return jsonify({'error': 'Cüzdanda yakılacak Shield Coin bulunmuyor.'}), 400

    if selected_tier == 'any':
        eligible_tokens = list(all_user_tokens)
    else:
        eligible_tokens = [p for p in all_user_tokens if get_tier_for_power(p) == selected_tier]

    tier_available_count = len(eligible_tokens)
    if tier_available_count == 0:
        return jsonify({'error': f'Seçilen kademede ({selected_tier}) token bulunamadı.'}), 400

    req_count = data.get('burn_count')
    if req_count is not None and str(req_count).strip() != "":
        burn_amount = int(req_count)
    else:
        pct = float(data.get('alt_percentage', 100))
        burn_amount = max(1, int((tier_available_count * pct) / 100.0))

    if burn_amount <= 0 or burn_amount > tier_available_count:
        return jsonify({'error': f'Geçersiz miktar. Mevcut: {tier_available_count}, İstenen: {burn_amount}.'}), 400

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
                message = f"[GLOBAL] Arz imha edildi: {burned_qty} Main Coin kalıcı olarak silindi."
            else:
                stats['personal_burned'] += burned_qty
                message = f"[KİŞİSEL] Bireysel kota düşürüldü: {burned_qty} Main Coin eksiltildi."
        elif action == "expand_supply":
            expand_qty = max(1, int(effective_power * 150))
            if scope == "global":
                blockchain.dynamic_supply_offset = min(blockchain.supply_variance_limit, blockchain.dynamic_supply_offset + expand_qty)
                message = f"[GLOBAL] Kapasite genişletildi: +{expand_qty} eklendi."
            else:
                stats['personal_supply_offset'] += expand_qty
                message = f"[KİŞİSEL] Bireysel kota genişletildi: +{expand_qty} eklendi."
        elif action == "boost_price":
            boost_val = round(min(5.0, effective_power * 0.5), 2)
            if scope == "global":
                blockchain.market_boost_bonus = boost_val
                message = f"[GLOBAL] Katsayı +%{boost_val} oranında yükseltildi."
            else:
                stats['personal_boost'] = boost_val
                message = f"[KİŞİSEL] Katsayı +%{boost_val} oranında yükseltildi."
        elif action == "discount_price":
            reduction_val = round(min(5.0, effective_power * 0.5), 2)
            if scope == "global":
                blockchain.market_boost_bonus = -reduction_val
                message = f"[GLOBAL] İndirim uygulandı: -%{reduction_val}."
            else:
                stats['personal_boost'] = -reduction_val
                message = f"[KİŞİSEL] İndirim uygulandı: -%{reduction_val}."
        elif action == "peg_static":
            if scope == "global":
                blockchain.market_peg_active = True
                blockchain.market_boost_bonus = 0.0
                message = "[GLOBAL] Değerleme referansı sabitlendi."
            else:
                stats['personal_boost'] = 0.0
                message = "[KİŞİSEL] Parametreler sabitlendi."

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
            'shield_coin_circulating': f"{total_alt_mined - burned_alt} (Aktif, Yakılan: {burned_alt})",
            'current_network_mint_power': f"{shield_impact_power}",
            'active_epoch_day': p2p_network.current_epoch
        },
        '2_USER_DATA': {
            'wallet_address': user_address, 
            'main_coin_balance': blockchain.get_balance(user_address, 'MAIN'),
            'shield_coin_balance': user_shield_count,
            'shield_overall_average_power': overall_avg,
            'tiers': tier_summary,
            'all_tokens_sorted': sorted(user_tokens, reverse=True),
            'node_storage_tier': f"%{p2p_network.my_tier}"
        }
    }), 200

# =====================================================================
# BAĞIMSIZ ÇALIŞTIRMA KONTROLCÜSÜ (SUNUCU VS MASAÜSTÜ PENCERESİ)
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
        print(f"[*] Variable Coin Bağımsız Düğümü sunucu modunda 0.0.0.0:{port} üzerinde çalışıyor...")
        app.run(host='0.0.0.0', port=port, threaded=True)
    else:
        # Masaüstü yerel modunda 127.0.0.1 bağlanır (Güvenlik Duvarı uyarısı çıkmaz)
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
