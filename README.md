### 1. Infinite Space Allocation & The 1% – 99% Boundary Rule

* **Infinite Space Allocation Architecture:** The protocol operates across an infinite number of algorithmically defined spaces (locations), removing physical hardware limits. Data processing, storage, and validation are distributed seamlessly across these infinite locations.
* **The Absolute 1% Floor:** Every single space in the network must occupy a minimum share of **1%**. No space can ever drop to 0%, ensuring there are no dead, non-responsive, or inert points in the system.
* **The Absolute 99% Ceiling:** No individual space can ever monopolize the network; the maximum capacity share any single space can hold is capped at **99%** (`(hash % 99) + 1`). This mathematical ceiling makes 100% control, monopolies, or central choke points impossible.
* **Transformation of Proof-of-Work:** Classical PoW is transformed from an energy-wasting hash lottery into a verification engine for these infinite spaces. When miners solve a block, the cryptographic proof confirms and distributes data across these spaces bounded strictly between 1% and 99%.

---

### 2. Data Retention & Distribution Affinity (Data Affinity)

* **Deterministic Matching:** When a block is minted, its block hash is cryptographically combined with the specific space identifier to generate an **affinity score** between 1 and 99.
* **Storage Condition:** If the calculated affinity score is less than or equal to the capacity percentage of that space (1% - 99%), the data is permanently retained and preserved in that space.
* **Zero-Loss Resilience:** Because data is dispersed across infinite spaces using probabilistic rules, physical server or hardware failures cannot destroy information. Network integrity is fully sustained through the remaining spaces.

---

### 3. Helper Token (Shield): Inflation Shield & Value Stabilization

* **Dual Functional Division:** While Main Coin serves as a store of value bounded by a 21,000,000 hard cap, Shield Coin functions as an elastic governance fuel used to counteract market fluctuations.
* **Pegging Asset Value (Peg Price):** During market downturns or heavy sell pressure, users can burn Shield Coins to anchor the effective price at a baseline floor, shielding purchasing power from erosion.
* **Value Boosting (Boost Value):** Users can deploy Shield Coin impact power to scale their effective asset value above the spot market rate, establishing an active personal defense against fiat inflation.
* **Permanent Burn & Supply Contraction:** Triggering these stabilization mechanisms routes all spent Shield Coins directly to the irreversible burn address (`0x000000000000000000000000000000000000dEaD`). Burned tokens are permanently removed from circulation, and these actions can be used to destroy circulating Main Coins to accelerate systemic scarcity.

---

### 4. Node Power & Dual Mining Mathematics

* **Universal 99.0 Base Power:** Abstract mining units across all infinite spaces start with a maximum base operational power of **99.0**.
* **Main Coin Mining (99 $\to$ 0 Decay):**
  * Initial blocks grant a full reward of **50 coins** at 99 power.
  * As the 21,000,000 supply cap approaches, power decays linearly (99 $\to$ 80 $\to$ 50 $\to$ 1...). Mining rewards decrease proportionally.
  * Upon minting the 21,000,000th coin, power hits exactly **0.0**, terminating block rewards and permanently halting all future issuance.
* **Shield Coin Mining (99 $\to$ 0.000001 Asymptotic Floor):**
  * The helper token is never fully exhausted; power decays gradually as cumulative mining and burning volume rises.
  * Power never reaches zero; it asymptotically locks at a floor of **0.000001**.
  * This permanent baseline ensures the network never freezes, allowing participants to continuously mine micro-fractions of Shield Coin to trigger governance commands and protect against inflation indefinitely.
