"""
mpesa.py  –  Safaricom Daraja API helper for SchoolApp
--------------------------------------------------------
Handles:
  • OAuth token retrieval
  • STK Push (Lipa Na M-Pesa Online)
  • STK Push status query
  • Callback parsing

Environment variables required:
  MPESA_CONSUMER_KEY      – from Daraja app
  MPESA_CONSUMER_SECRET   – from Daraja app
  MPESA_SHORTCODE         – your Paybill / Till number
  MPESA_PASSKEY           – Lipa Na M-Pesa Online passkey
  MPESA_CALLBACK_URL      – public HTTPS URL for callbacks  e.g. https://yourapp.com/mpesa/callback
  MPESA_ENV               – 'sandbox' or 'production'  (default: sandbox)
"""

import os
import base64
import datetime
import requests
from requests.auth import HTTPBasicAuth


# ── Base URLs ───────────────────────────────────────────────────────────────

_ENV = os.environ.get("MPESA_ENV", "sandbox").lower()

BASE_URL = (
    "https://api.safaricom.co.ke"
    if _ENV == "production"
    else "https://sandbox.safaricom.co.ke"
)

TOKEN_URL      = f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
STK_PUSH_URL   = f"{BASE_URL}/mpesa/stkpush/v1/processrequest"
STK_QUERY_URL  = f"{BASE_URL}/mpesa/stkpushquery/v1/query"


# ── Credentials ─────────────────────────────────────────────────────────────

CONSUMER_KEY    = os.environ.get("MPESA_CONSUMER_KEY", "")
CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
SHORTCODE       = os.environ.get("MPESA_SHORTCODE", "174379")      # sandbox default
PASSKEY         = os.environ.get("MPESA_PASSKEY", "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919")  # sandbox default
CALLBACK_URL    = os.environ.get("MPESA_CALLBACK_URL", "https://example.com/mpesa/callback")


# ── Token cache ─────────────────────────────────────────────────────────────

_token_cache = {"token": None, "expires_at": 0}


def get_access_token() -> str:
    """Return a valid OAuth bearer token, refreshing when expired."""
    now = datetime.datetime.utcnow().timestamp()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 30:
        return _token_cache["token"]

    resp = requests.get(
        TOKEN_URL,
        auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3599))
    return _token_cache["token"]


# ── Timestamp & password ─────────────────────────────────────────────────────

def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def _password(timestamp: str) -> str:
    raw = SHORTCODE + PASSKEY + timestamp
    return base64.b64encode(raw.encode()).decode()


# ── STK Push ────────────────────────────────────────────────────────────────

def stk_push(phone: str, amount: int, account_ref: str, description: str = "School Fee") -> dict:
    """
    Initiate an STK Push prompt on the parent's phone.

    Parameters
    ----------
    phone        : phone number in format 2547XXXXXXXX
    amount       : integer amount in KES (minimum 1)
    account_ref  : your internal reference shown on M-Pesa prompt (max 12 chars)
    description  : transaction description (max 13 chars)

    Returns
    -------
    dict with keys:
      success          – bool
      checkout_request_id – str (use this to poll status)
      merchant_request_id – str
      response_code    – str
      response_description – str
      customer_message – str
      error            – str (only when success=False)
    """
    ts  = _timestamp()
    pwd = _password(ts)
    token = get_access_token()

    phone = _normalize_phone(phone)

    payload = {
        "BusinessShortCode": SHORTCODE,
        "Password":          pwd,
        "Timestamp":         ts,
        "TransactionType":   "CustomerPayBillOnline",
        "Amount":            max(1, int(amount)),
        "PartyA":            phone,
        "PartyB":            SHORTCODE,
        "PhoneNumber":       phone,
        "CallBackURL":       CALLBACK_URL,
        "AccountReference":  account_ref[:12],
        "TransactionDesc":   description[:13],
    }

    try:
        resp = requests.post(
            STK_PUSH_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        data = resp.json()

        if data.get("ResponseCode") == "0":
            return {
                "success":               True,
                "checkout_request_id":   data["CheckoutRequestID"],
                "merchant_request_id":   data["MerchantRequestID"],
                "response_code":         data["ResponseCode"],
                "response_description":  data["ResponseDescription"],
                "customer_message":      data["CustomerMessage"],
            }
        else:
            return {
                "success": False,
                "error":   data.get("errorMessage") or data.get("ResponseDescription", "STK push failed"),
            }

    except requests.exceptions.RequestException as exc:
        return {"success": False, "error": str(exc)}


# ── STK Status Query ─────────────────────────────────────────────────────────

def query_stk_status(checkout_request_id: str) -> dict:
    """
    Check the status of a pending STK Push.

    Returns
    -------
    dict with keys:
      success         – bool
      result_code     – str  ('0' = success, '1032' = cancelled by user, etc.)
      result_desc     – str
      status          – 'completed' | 'cancelled' | 'pending' | 'error'
    """
    ts  = _timestamp()
    pwd = _password(ts)
    token = get_access_token()

    payload = {
        "BusinessShortCode":  SHORTCODE,
        "Password":           pwd,
        "Timestamp":          ts,
        "CheckoutRequestID":  checkout_request_id,
    }

    try:
        resp = requests.post(
            STK_QUERY_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        data = resp.json()
        result_code = str(data.get("ResultCode", ""))
        result_desc = data.get("ResultDesc", "")

        if result_code == "0":
            status = "completed"
        elif result_code in ("1032", "1"):
            status = "cancelled"
        elif "pending" in result_desc.lower():
            status = "pending"
        else:
            status = "error"

        return {
            "success":     data.get("ResponseCode") == "0" or result_code == "0",
            "result_code": result_code,
            "result_desc": result_desc,
            "status":      status,
        }

    except requests.exceptions.RequestException as exc:
        return {"success": False, "result_code": "", "result_desc": str(exc), "status": "error"}


# ── Callback parser ──────────────────────────────────────────────────────────

def parse_callback(callback_data: dict) -> dict:
    """
    Parse the JSON body Safaricom POSTs to your callback URL.

    Returns
    -------
    dict with keys:
      success              – bool (True if payment completed)
      result_code          – str
      result_desc          – str
      checkout_request_id  – str
      merchant_request_id  – str
      amount               – float | None
      mpesa_receipt        – str | None   (e.g. 'QKG12AB34C')
      phone                – str | None
      transaction_date     – str | None
    """
    try:
        stk = callback_data["Body"]["stkCallback"]
        result_code = str(stk["ResultCode"])
        result_desc = stk["ResultDesc"]
        checkout_id = stk["CheckoutRequestID"]
        merchant_id = stk["MerchantRequestID"]

        if result_code != "0":
            return {
                "success":             False,
                "result_code":         result_code,
                "result_desc":         result_desc,
                "checkout_request_id": checkout_id,
                "merchant_request_id": merchant_id,
                "amount":              None,
                "mpesa_receipt":       None,
                "phone":               None,
                "transaction_date":    None,
            }

        items = {
            item["Name"]: item.get("Value")
            for item in stk.get("CallbackMetadata", {}).get("Item", [])
        }

        return {
            "success":             True,
            "result_code":         result_code,
            "result_desc":         result_desc,
            "checkout_request_id": checkout_id,
            "merchant_request_id": merchant_id,
            "amount":              items.get("Amount"),
            "mpesa_receipt":       items.get("MpesaReceiptNumber"),
            "phone":               str(items.get("PhoneNumber", "")),
            "transaction_date":    str(items.get("TransactionDate", "")),
        }

    except (KeyError, TypeError) as exc:
        return {
            "success":             False,
            "result_code":         "ERR",
            "result_desc":         f"Callback parse error: {exc}",
            "checkout_request_id": "",
            "merchant_request_id": "",
            "amount":              None,
            "mpesa_receipt":       None,
            "phone":               None,
            "transaction_date":    None,
        }


# ── Utilities ────────────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """
    Accept common Kenyan formats and return 2547XXXXXXXX.
      07XXXXXXXX  → 2547XXXXXXXX
      +2547XXXXXXXX → 2547XXXXXXXX
      2547XXXXXXXX  → unchanged
    """
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("07") or phone.startswith("01"):
        phone = "254" + phone[1:]
    return phone
