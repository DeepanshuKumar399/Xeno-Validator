# Xeno Transaction Validator

A web-based platform for transaction data validation and processing — built as part of the **Xeno Pvt. Ltd. Implementation Internship Assignment**.

---

## 🚀 Live Demo
> Coming soon — will be hosted on Render

---

## 📌 What It Does

Upload any transaction CSV containing order-level, product-level, and payment mode data. The platform performs comprehensive validation and returns a cleaned, downloadable output.

### Validation Checks
- **Phone numbers** — country-specific rules (India, Singapore, USA, UK, UAE, Australia, Malaysia)
- **Date & time** — validates against 8 common formats (DD-MM-YYYY, YYYY-MM-DD, MM/DD/YYYY, etc.)
- **Payment mode** — checks against allowed values (upi, card, cash, cod, emi, netbanking, wallet, etc.)
- **Required fields** — flags missing order_id, product_id, payment_mode
- **Numeric fields** — validates amount, price, quantity, discount, tax
- **Email format** — basic regex validation
- **Order/Product IDs** — alphanumeric format check
- **Currency code** — 3-letter ISO format
- **Strict mode** — additionally flags negative amounts

### Output
- ✅ Cleaned CSV (valid rows only)
- 📋 `validation_summary.json` with full error report
- 📦 Auto-splits into 500-row chunks for large files
- Everything bundled in a `.zip` download

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Data Processing | Pandas |
| Frontend | HTML, CSS, JavaScript |
| Charts | Chart.js |
| Output | ZIP + CSV + JSON |

---

## 📁 Project Structure

```
xeno-validator/
├── app.py                  # Flask backend + all validation logic
├── requirements.txt        # Dependencies
├── templates/
│   └── index.html          # Frontend UI
└── README.md
```

---

## ⚙️ Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/DeepanshuKumar399/Xeno-Validator.git
cd Xeno-Validator

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## 📂 Sample CSV

A sample transaction CSV is available at `/sample` once the server is running, or download it directly from the UI.

Expected columns:
```
order_id, product_id, product_name, quantity, unit_price, amount,
payment_mode, currency, customer_name, email, phone_number, order_date, country_code
```

---

## 🌍 Supported Country Phone Rules

| Country | Code | Rule |
|---|---|---|
| India | IN | 10 digits, starts with 6–9 |
| Singapore | SG | 8 digits, starts with 8 or 9 |
| USA | US | 10 digits |
| UK | GB | 10 digits |
| UAE | AE | 9 digits, starts with 5 |
| Australia | AU | 9 digits, starts with 4 or 5 |
| Malaysia | MY | 9 digits, starts with 1 |

---

## 💡 Approach & Tradeoffs

- Chose **Flask** for simplicity and fast iteration — no overhead of a full framework
- Validation logic is **row-by-row** with categorised error counts for the dashboard
- Used **client-side Chart.js** to avoid heavy backend dependencies
- Did not build: user authentication, database storage, or async job queues — kept it stateless and simple for this scope

---

## 👤 Author

**Deepanshu Kumar**  
Implementation Internship Candidate — Xeno Pvt. Ltd.
