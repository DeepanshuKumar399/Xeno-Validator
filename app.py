from flask import Flask, request, jsonify, send_file, render_template, Response
import pandas as pd
import re, io, zipfile, json
from datetime import datetime

app = Flask(__name__)

CHUNK_SIZE = 500

COUNTRY_PHONE_RULES = {
    "IN": {"length": 10, "pattern": r"^[6-9]\d{9}$",  "label": "India (10 digits, starts 6-9)"},
    "SG": {"length": 8,  "pattern": r"^[89]\d{7}$",   "label": "Singapore (8 digits, starts 8/9)"},
    "US": {"length": 10, "pattern": r"^\d{10}$",       "label": "USA (10 digits)"},
    "GB": {"length": 10, "pattern": r"^\d{10}$",       "label": "UK (10 digits)"},
    "AE": {"length": 9,  "pattern": r"^5\d{8}$",       "label": "UAE (9 digits, starts 5)"},
    "AU": {"length": 9,  "pattern": r"^[45]\d{8}$",    "label": "Australia (9 digits, starts 4/5)"},
    "MY": {"length": 9,  "pattern": r"^1\d{8}$",       "label": "Malaysia (9 digits, starts 1)"},
}

DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y",
                "%Y/%m/%d", "%d %b %Y", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"]

PAYMENT_MODES = {"cash", "card", "upi", "netbanking", "wallet",
                 "credit", "debit", "online", "cod", "emi", "paylater", "crypto"}

# Columns expected in a transaction dataset
ORDER_REQUIRED   = ["order_id"]
PRODUCT_REQUIRED = ["product_id", "product_name"]
PAYMENT_REQUIRED = ["payment_mode"]


def norm_cols(df):
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def validate_phone(raw, country_code):
    phone = re.sub(r"[\s\-\+\(\)]", "", str(raw))
    rule = COUNTRY_PHONE_RULES.get(country_code.upper(),
                                   {"length": 10, "pattern": r"^\d{10}$", "label": country_code})
    if re.fullmatch(rule["pattern"], phone):
        return True, ""
    return False, f"Phone invalid for {rule['label']} — got '{raw}'"


def validate_date(val, col):
    if pd.isna(val) or str(val).strip() == "":
        return False, f"'{col}' is empty"
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(str(val).strip(), fmt)
            return True, ""
        except ValueError:
            pass
    return False, f"'{col}' has invalid date '{val}'"


def validate_row(row, country_code, phone_cols, date_cols, required_cols, strict_mode):
    errors = []

    # 1. Required field check
    for col in required_cols:
        if col in row.index and (pd.isna(row[col]) or str(row[col]).strip() == ""):
            errors.append(f"Required field '{col}' is missing")

    # 2. Phone validation
    for pc in phone_cols:
        if pc in row.index and not pd.isna(row[pc]) and str(row[pc]).strip():
            ok, msg = validate_phone(row[pc], country_code)
            if not ok:
                errors.append(msg)

    # 3. Date / time validation
    for dc in date_cols:
        if dc in row.index:
            ok, msg = validate_date(row[dc], dc)
            if not ok:
                errors.append(msg)

    # 4. Payment mode
    if "payment_mode" in row.index:
        val = str(row["payment_mode"]).strip().lower()
        if val and val not in PAYMENT_MODES:
            errors.append(f"Unknown payment_mode '{row['payment_mode']}'")

    # 5. Numeric fields
    for col in ["amount", "order_amount", "price", "total", "quantity", "qty",
                "discount", "tax", "unit_price", "selling_price"]:
        if col in row.index and not pd.isna(row[col]) and str(row[col]).strip():
            try:
                v = float(str(row[col]).replace(",", ""))
                if strict_mode and v < 0:
                    errors.append(f"'{col}' cannot be negative (got {v})")
            except ValueError:
                errors.append(f"'{col}' must be numeric, got '{row[col]}'")

    # 6. Email
    for col in ["email", "customer_email", "billing_email"]:
        if col in row.index and not pd.isna(row[col]) and str(row[col]).strip():
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(row[col]).strip()):
                errors.append(f"Invalid email '{row[col]}'")

    # 7. Order ID / product ID format (alphanumeric)
    for col in ["order_id", "product_id", "transaction_id"]:
        if col in row.index and not pd.isna(row[col]) and str(row[col]).strip():
            if not re.match(r"^[A-Za-z0-9\-_#]+$", str(row[col]).strip()):
                errors.append(f"'{col}' has invalid characters '{row[col]}'")

    # 8. Duplicate-prone: currency code
    if "currency" in row.index and not pd.isna(row["currency"]):
        if not re.match(r"^[A-Z]{3}$", str(row["currency"]).strip()):
            errors.append(f"Invalid currency code '{row['currency']}'")

    return errors


def run_full_validation(df, country_code, phone_cols, date_cols, required_cols, strict_mode):
    all_errors = {}
    error_type_counts = {}
    valid_indices = []

    for idx, row in df.iterrows():
        errs = validate_row(row, country_code, phone_cols, date_cols, required_cols, strict_mode)
        if errs:
            all_errors[int(idx) + 2] = errs
            for e in errs:
                # Categorise error
                if "phone" in e.lower() or "Phone" in e:
                    key = "Phone"
                elif "date" in e.lower() or "Date" in e:
                    key = "Date/Time"
                elif "payment_mode" in e.lower():
                    key = "Payment Mode"
                elif "missing" in e.lower():
                    key = "Missing Field"
                elif "email" in e.lower():
                    key = "Email"
                elif "numeric" in e.lower() or "negative" in e.lower():
                    key = "Numeric"
                elif "order_id" in e.lower() or "product_id" in e.lower():
                    key = "ID Format"
                elif "currency" in e.lower():
                    key = "Currency"
                else:
                    key = "Other"
                error_type_counts[key] = error_type_counts.get(key, 0) + 1
        else:
            valid_indices.append(idx)

    clean_df = df.loc[valid_indices].copy()
    return clean_df, all_errors, error_type_counts


def make_zip(clean_df, summary):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if len(clean_df) > CHUNK_SIZE:
            for i in range(0, len(clean_df), CHUNK_SIZE):
                chunk = clean_df.iloc[i:i + CHUNK_SIZE]
                cb = io.StringIO()
                chunk.to_csv(cb, index=False)
                zf.writestr(f"validated_chunk_{i//CHUNK_SIZE + 1}.csv", cb.getvalue())
        else:
            cb = io.StringIO()
            clean_df.to_csv(cb, index=False)
            zf.writestr("validated_output.csv", cb.getvalue())
        zf.writestr("validation_summary.json", json.dumps(summary, indent=2))
    buf.seek(0)
    return buf


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    return render_template("index.html",
                           country_rules=COUNTRY_PHONE_RULES,
                           payment_modes=sorted(PAYMENT_MODES))


@app.route("/sample")
def sample():
    """Serve a sample transaction CSV for demo."""
    csv = (
        "order_id,product_id,product_name,quantity,unit_price,amount,payment_mode,"
        "currency,customer_name,email,phone_number,order_date,country_code\n"
        "ORD-001,PRD-101,Blue Sneakers,2,1499.00,2998.00,upi,INR,Arjun Mehta,"
        "arjun@gmail.com,9876543210,2024-03-15,IN\n"
        "ORD-002,PRD-102,Red Cap,1,299.00,299.00,card,INR,Priya Shah,"
        "priya@yahoo.com,8123456789,2024-03-16,IN\n"
        "ORD-003,PRD-103,Leather Wallet,3,850.00,2550.00,cash,INR,Rahul Verma,"
        "rahul@outlook.com,7012345678,15-03-2024,IN\n"
        "ORD-004,,Sunglasses,1,1200.00,1200.00,netbanking,INR,Sneha Kapoor,"
        "sneha@gmail.com,9988776655,2024-03-17,IN\n"
        "ORD-005,PRD-105,Yoga Mat,2,599.00,bad_amount,upi,INR,Vikram Nair,"
        "vikram@gmail.com,1234567890,2024-03-18,IN\n"
        "ORD-006,PRD-106,Water Bottle,1,349.00,349.00,unknown_pay,USD,Ananya Roy,"
        "ananya_bad_email,9123456780,2024-03-19,IN\n"
        "ORD-007,PRD-107,Dumbbell Set,1,3999.00,3999.00,cod,INR,Karan Patel,"
        "karan@gmail.com,8765432109,2024-03-20,IN\n"
        "ORD-008,PRD-108,Running Shoes,2,2499.00,4998.00,card,INR,Meera Joshi,"
        "meera@hotmail.com,9871234560,2024-03-21,IN\n"
    )
    return Response(csv, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sample_transactions.csv"})


@app.route("/preview", methods=["POST"])
def preview():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        df = pd.read_csv(file)
        df = norm_cols(df)
        return jsonify({
            "columns": list(df.columns),
            "row_count": len(df),
            "sample": df.head(8).fillna("").to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/validate-json", methods=["POST"])
def validate_json():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        df = pd.read_csv(file)
    except Exception as e:
        return jsonify({"error": f"Could not parse CSV: {e}"}), 400

    df = norm_cols(df)
    country_code  = request.form.get("country_code", "IN").strip().upper()
    strict_mode   = request.form.get("strict_mode", "false").lower() == "true"
    phone_cols    = [c.strip().lower().replace(" ", "_")
                     for c in request.form.get("phone_cols", "").split(",") if c.strip()]
    date_cols     = [c.strip().lower().replace(" ", "_")
                     for c in request.form.get("date_cols", "").split(",") if c.strip()]
    required_cols = [c.strip().lower().replace(" ", "_")
                     for c in request.form.get("required_cols", "").split(",") if c.strip()]

    # Auto-detect
    if not phone_cols:
        phone_cols = [c for c in df.columns if any(k in c for k in ["phone", "mobile", "contact"])]
    if not date_cols:
        date_cols = [c for c in df.columns if any(k in c for k in ["date", "time"])]
    if not required_cols:
        required_cols = [c for c in df.columns if c in
                         ORDER_REQUIRED + PRODUCT_REQUIRED + PAYMENT_REQUIRED]

    clean_df, all_errors, error_type_counts = run_full_validation(
        df, country_code, phone_cols, date_cols, required_cols, strict_mode)

    total = len(df)
    valid = len(clean_df)

    return jsonify({
        "total": total,
        "valid": valid,
        "invalid": total - valid,
        "quality_pct": round(valid / total * 100, 1) if total else 0,
        "columns": list(df.columns),
        "phone_cols": phone_cols,
        "date_cols": date_cols,
        "required_cols": required_cols,
        "country": COUNTRY_PHONE_RULES.get(country_code, {}).get("label", country_code),
        "error_type_counts": error_type_counts,
        "errors_preview": [{"row": k, "issues": v} for k, v in list(all_errors.items())[:60]],
        "errors_truncated": len(all_errors) > 60,
        "chunks": (valid // CHUNK_SIZE) + (1 if valid % CHUNK_SIZE else 0) if valid > CHUNK_SIZE else 1
    })


@app.route("/validate", methods=["POST"])
def validate():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        df = pd.read_csv(file)
    except Exception as e:
        return jsonify({"error": f"Could not parse CSV: {e}"}), 400

    df = norm_cols(df)
    country_code  = request.form.get("country_code", "IN").strip().upper()
    strict_mode   = request.form.get("strict_mode", "false").lower() == "true"
    phone_cols    = [c.strip().lower().replace(" ", "_")
                     for c in request.form.get("phone_cols", "").split(",") if c.strip()]
    date_cols     = [c.strip().lower().replace(" ", "_")
                     for c in request.form.get("date_cols", "").split(",") if c.strip()]
    required_cols = [c.strip().lower().replace(" ", "_")
                     for c in request.form.get("required_cols", "").split(",") if c.strip()]

    if not phone_cols:
        phone_cols = [c for c in df.columns if any(k in c for k in ["phone", "mobile", "contact"])]
    if not date_cols:
        date_cols = [c for c in df.columns if any(k in c for k in ["date", "time"])]
    if not required_cols:
        required_cols = [c for c in df.columns if c in
                         ORDER_REQUIRED + PRODUCT_REQUIRED + PAYMENT_REQUIRED]

    clean_df, all_errors, error_type_counts = run_full_validation(
        df, country_code, phone_cols, date_cols, required_cols, strict_mode)

    total = len(df)
    valid = len(clean_df)

    summary = {
        "total_rows": total, "valid_rows": valid, "invalid_rows": total - valid,
        "quality_pct": round(valid / total * 100, 1) if total else 0,
        "country_rule": COUNTRY_PHONE_RULES.get(country_code, {}).get("label", country_code),
        "phone_columns": phone_cols, "date_columns": date_cols,
        "error_type_counts": error_type_counts,
        "errors_by_row": {str(k): v for k, v in list(all_errors.items())[:200]},
        "errors_truncated": len(all_errors) > 200,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    zip_buf = make_zip(clean_df, summary)
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True, download_name="xeno_validated_output.zip")


if __name__ == "__main__":
    app.run(debug=True)
