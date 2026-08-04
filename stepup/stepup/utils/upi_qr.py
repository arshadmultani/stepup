import frappe
from urllib.parse import quote
import pyqrcode
import io
import base64
import json

def get_upi_qr_data_url(upi_url):
    """Generate base64 SVG data URL for a given UPI URL string"""
    if not upi_url:
        return ""
    try:
        qr = pyqrcode.create(upi_url)
        stream = io.BytesIO()
        qr.svg(stream, scale=3,quiet_zone=1,xmldecl=False)
        b64 = base64.b64encode(stream.getvalue()).decode('utf-8')
        return f"data:image/svg+xml;base64,{b64}"
    except Exception as e:
        frappe.log_error(f"Error generating UPI QR code: {str(e)}")
        return ""

def get_batch_expiry(batch_no):
    """Fetch expiry date for a given Batch No"""
    if not batch_no:
        return ""
    try:
        expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
        if expiry:
            return frappe.utils.formatdate(expiry)
    except Exception:
        pass
    return ""

def get_item_tax_breakdown(item, doc=None):
    """Extract CGST, SGST, IGST rates and amounts for a single invoice item"""
    taxable = float(item.net_amount or item.amount or 0)
    cgst_rate, sgst_rate, igst_rate = 0.0, 0.0, 0.0
    
    if getattr(item, 'item_tax_rate', None):
        try:
            rates = json.loads(item.item_tax_rate) if isinstance(item.item_tax_rate, str) else item.item_tax_rate
            for k, v in rates.items():
                k_lower = k.lower()
                if 'cgst' in k_lower:
                    cgst_rate = float(v)
                elif 'sgst' in k_lower or 'utgst' in k_lower:
                    sgst_rate = float(v)
                elif 'igst' in k_lower:
                    igst_rate = float(v)
        except Exception:
            pass
            
    cgst_amt = round(taxable * (cgst_rate / 100.0), 2)
    sgst_amt = round(taxable * (sgst_rate / 100.0), 2)
    igst_amt = round(taxable * (igst_rate / 100.0), 2)
    total_amt = round(taxable + cgst_amt + sgst_amt + igst_amt, 2)
    
    return {
        'taxable_amt': taxable,
        'cgst_rate': cgst_rate, 'cgst_amt': cgst_amt,
        'sgst_rate': sgst_rate, 'sgst_amt': sgst_amt,
        'igst_rate': igst_rate, 'igst_amt': igst_amt,
        'total_amt': total_amt
    }

def get_gst_summary(doc):
    """Summarize GST tax breakdown by GST percentage slab"""
    summary = {}
    for item in doc.items:
        tb = get_item_tax_breakdown(item, doc)
        rate = tb['cgst_rate'] + tb['sgst_rate'] + tb['igst_rate']
        if rate not in summary:
            summary[rate] = {
                'rate': rate,
                'taxable': 0.0,
                'cgst': 0.0,
                'sgst': 0.0,
                'igst': 0.0,
                'tax_amt': 0.0
            }
        summary[rate]['taxable'] += tb['taxable_amt']
        summary[rate]['cgst'] += tb['cgst_amt']
        summary[rate]['sgst'] += tb['sgst_amt']
        summary[rate]['igst'] += tb['igst_amt']
        summary[rate]['tax_amt'] += (tb['cgst_amt'] + tb['sgst_amt'] + tb['igst_amt'])
        
    return sorted(summary.values(), key=lambda x: x['rate'])

def get_company_bank_details(doc):
    """Fetch company bank account details from DB for Sales Invoice printing"""
    bank_account_name = getattr(doc, 'company_bank_account', None) or getattr(doc, 'bank_account', None)
    
    if not bank_account_name and getattr(doc, 'company', None):
        bank_accounts = frappe.get_all(
            "Bank Account",
            filters={"company": doc.company, "is_company_account": 1},
            fields=["name", "bank", "account_name", "bank_account_no", "branch_code", "iban"],
            order_by="is_default desc, creation asc",
            limit=1
        )
        if bank_accounts:
            acc = bank_accounts[0]
            return {
                "bank_name": acc.bank or acc.account_name or "",
                "account_no": acc.bank_account_no or "",
                "ifsc_code": acc.branch_code or acc.iban or "",
                "has_data": True
            }
            
    if bank_account_name and frappe.db.exists("Bank Account", bank_account_name):
        acc = frappe.get_doc("Bank Account", bank_account_name)
        return {
            "bank_name": acc.bank or acc.account_name or "",
            "account_no": acc.bank_account_no or "",
            "ifsc_code": acc.branch_code or acc.iban or "",
            "has_data": True
        }
        
    return {"bank_name": "", "account_no": "", "ifsc_code": "", "has_data": False}

def generate_upi_qr(doc, method=None):
    """Generate UPI payment QR string for Sales Invoice"""
    upi_id = "exponit@upi"
    payee_name = doc.company or ""
    amount = f"{float(doc.grand_total or 0):.2f}"
    note = f"Invoice {doc.name}" if doc.name else "Invoice"

    # URL encode query parameter values to ensure valid UPI URI syntax
    encoded_pn = quote(payee_name)
    encoded_tn = quote(note)

    doc.custom_upi_qr = (
        f"upi://pay?pa={upi_id}"
        f"&pn={encoded_pn}"
        f"&am={amount}"
        f"&cu=INR"
        f"&tn={encoded_tn}"
    )