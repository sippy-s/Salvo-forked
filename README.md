# Salvo

**Intelligent SMS stress‑testing framework with adaptive API pool scheduling.**

Salvo is a high‑performance, asynchronous tool for controlled stress‑testing of SMS‑based web
services. It dispatches requests through a weighted pool of API endpoints, dynamically manages
failures with jail/purge logic, and provides detailed colour‑coded console feedback.

---

## Features

- **Weighted random API selection** using a Fenwick tree (Binary Indexed Tree) – O(log n) pick and update.
- **Bounded and unbounded execution modes** – limit by total successes or run until exhaustion.
- **Failure‑aware scheduling** – temporary jail (20 s) and permanent removal after repeated failures.
- **Credit‑based session control** with configurable success limit and consecutive‑failure tolerance.
- **Asynchronous I/O** – non‑blocking workers, background log drain, and shared `aiohttp` sessions.
- **Proxy support with automatic fallback** to direct connection when proxy failures exceed tolerance.
- **Dynamic ticket scoring** – each API receives a 0‑100 weight computed from its success rate and relative capacity.
- **Rich console output** – ANSI colours, structured tags (`[SUCCESS]`, `[JAILED]`, …), and final summary.
- **JSON configuration** – easily add/remove APIs without touching code.
- **Comprehensive validation** – phone numbers, proxies, API templates, and CLI arguments are all validated.

---

## How It Works

### API Pool and Fenwick Tree

The core of Salvo is a weighted random dispatcher built on a **Fenwick tree** (Binary Indexed Tree).
Each API is represented as a slot with a dynamic weight. The tree allows:

- **Weighted sampling** in O(log n) by drawing a random target and performing a lower‑bound query.
- **Point updates** in O(log n) when an API’s capacity changes or it is jailed/removed.

In **bounded mode**, weight = `capacity × ticket`. Each time an API is selected, its capacity
decrements and its weight is updated. When capacity reaches zero, the slot is disabled.

### Failure Handling: Jail & Purge

| State | Trigger | Effect |
|-------|---------|--------|
| **Active** | – | Normal operation. |
| **Jailed** | `strikes` reach `strike_limit` (3) | Weight set to 0 for 20 seconds; API temporarily excluded. |
| **Freed** | Jail time expires | Weight restored (if capacity remains); `was_jailed` flag remains `True`. |
| **Purged** | Second jail cycle completed | API permanently removed from pool. |

A `strike` is added for each failed request. A successful request resets the strike counter.
This mechanism prevents the pool from wasting resources on broken or rate‑limited endpoints
while still allowing them to recover after a cooldown.

### Session Tracker

The `SessionTracker` enforces two independent stop conditions:

1. **Success limit** – when the number of successful requests reaches `limit` (bounded mode only).
2. **Consecutive failure tolerance** – when `consecutive_fail` meets or exceeds `fail_tolerance`.

Workers acquire a credit (slot) before each request and release it after completion, with an
automatic refund on failure. This prevents overshooting the success limit while still counting
attempts toward the failure threshold.

### Ticket Scoring Formula

The ticket value (0‑100) represents an API’s “desirability” and is pre‑computed.  
It is a weighted geometric mean of two factors:

```
success_rate = sent / requested
capacity_weight = log(capacity + 1) / log(max_capacity + 1)
ticket = 100 × (success_rate ^ 0.6) × (capacity_weight ^ 0.4)
```

- **success_rate** (weight 0.6): how often the API returned a 2xx status in previous runs.
- **capacity_weight** (weight 0.4): relative log‑scaled capacity compared to the largest capacity
  in the template set.

The exponents sum to 1, giving a balanced trade‑off between reliability and throughput.

### Proxy Fallback

When a proxy is configured and `--fallback` is enabled, the engine monitors consecutive failures.
If the failure count reaches `fail_tolerance`, the proxy is abandoned and requests are sent directly.
This self‑healing mechanism avoids prolonged downtime due to a misbehaving proxy.

### Console & Logging

All output goes through an async log drain queue – workers never block on I/O. Each log line is
colour‑coded and tagged with severity/event labels. A final summary shows runtime, total requests,
success/failure counts, success rate, and any dropped logs.

---

## Project Structure

```
salvo/
├── configs/
│   └── api_templates.json        # API endpoint definitions
├── kernel/
│   ├── console/
│   │   ├── colors.py             # ANSI colour codes
│   │   ├── console.py            # Async console logger
│   │   └── tags.py               # Tag enums for log labels
│   ├── core/
│   │   ├── api_factory.py        # Builds ApiSlot objects from JSON
│   │   ├── api_pool.py           # Weighted API pool (Fenwick tree)
│   │   ├── engine.py             # Execution coordinator
│   │   └── session_tracker.py    # Credit & failure tracking
│   ├── exceptions.py             # Custom exceptions
│   ├── models/
│   │   ├── api.py                # ApiCall & ApiSlot dataclasses
│   │   └── runtime_config.py     # Immutable runtime configuration
│   ├── parser.py                 # CLI argument parsing & validation
│   ├── paths.py                  # Centralised project paths
│   ├── structures/
│   │   └── fenwick_tree.py       # Fenwick tree (BIT) implementation
│   └── utils/
│       ├── _regex_patterns.py    # Internal regex patterns
│       ├── http_utils.py         # HTTP request utilities
│       ├── utils.py              # General utilities
│       └── validators.py         # API, phone & proxy validators
├── tests/
│   ├── test_api_factory.py
│   ├── test_api_pool.py
│   ├── test_console.py
│   ├── test_fenwick_tree.py
│   ├── test_http_utils.py
│   ├── test_parser.py
│   ├── test_session_tracker.py
│   └── test_validators.py
├── tools/
│   └── calculate_ticket.py       # Ticket scoring script
├── salvo.py                      # Application entry point
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/salvo.git
   cd salvo
   ```

2. **Install dependencies** (Python 3.10+ recommended)
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

Run the tool from the project root:

```bash
python salvo.py -t <target_phone>
```

### Command‑Line Options

| Argument | Description | Default |
|----------|-------------|---------|
| `-t`, `--target` | Target phone number (required). Accepts Iranian mobile formats. | – |
| `-m`, `--mode` | Execution mode: `limited` or `unlimited`. | `limited` |
| `-l`, `--limit` | Success limit (only in `limited` mode). | None |
| `--fail-tolerance` | Max consecutive failures before stop/fallback. | 6 |
| `-c`, `--concurrency` | Number of concurrent workers. | 6 |
| `--timeout` | HTTP request timeout (seconds). | 5 |
| `--api-templates` | Path to API templates JSON file. | `configs/api_templates.json` |
| `--proxy` | Proxy URL (http/https). | None |
| `--fallback` | Enable fallback to direct connection on proxy failure. | False |
| `--ssl` | Enable SSL certificate verification. | False |

### Examples

```bash
# Basic run with default settings
python salvo.py -t 0912xxxxxxx

# Unlimited mode (no success cap, no jail)
python salvo.py -t +98912xxxxxxx -m unlimited

# Limited mode, stop after 200 successes
python salvo.py -t 98912xxxxxxx -m limited -l 200

# Higher concurrency and custom timeout
python salvo.py -t 98-912-xxx-xxxx -c 10 --timeout 10

# Use a proxy with fallback to direct connection
python salvo.py -t +98(912)-xxx-xxxx --proxy http://127.0.0.1:8080 --fallback

# Enable SSL verification
python salvo.py -t 0912xxxxxxx --ssl
```

Run `python salvo.py --help` for the full help message including detailed API template format.

---

## Configuration (`api_templates.json`)

The JSON file contains an array of API objects. Example:

```json
[
    {
        "source": "example.com",
        "url": "https://example.com/sms?phone=98{phone}",
        "method": "GET",
        "capacity": 10,
        "ticket": 62
    },
    {
        "source": "sample.ir",
        "url": "https://sample.ir/auth/sms",
        "json": {"identifier": "0{phone}"},
        "method": "POST",
        "capacity": 20,
        "ticket": 100
    }
]
```

- `source` – unique identifier (lines starting with `#` are ignored as comments).
- `url` – endpoint; `{phone}` is replaced with the normalised phone number.
- `method` – `GET` or `POST`.
- `json`, `data` – optional request payloads (mutually exclusive).
- `capacity` – maximum number of times this API can be used in one bounded session.
- `ticket` – priority weight (0–100); see [Ticket Scoring Formula](#ticket-scoring-formula).

---

## Testing

The project includes a thorough test suite. Run it with:

```bash
pytest tests/
```

Tests cover the Fenwick tree, API pool (including concurrency and full jail/purge cycles),
console logging, argument parsing, validators, and more.

---

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---

## Disclaimer

This tool is provided as‑is. The author assumes **no liability** for any misuse, damage, or legal
consequences arising from its use. It is the user’s responsibility to comply with all applicable
laws and obtain proper consent before testing any service.
