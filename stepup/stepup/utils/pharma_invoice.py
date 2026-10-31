import frappe
import json
import io
import base64
from urllib.parse import quote

try:
    import barcode
    from barcode.writer import SVGWriter
except ImportError:
    barcode = None
    SVGWriter = None

try:
    import pyqrcode
except ImportError:
    pyqrcode = None


def get_barcode_svg_data_url(code_text):
    """Generate base64 SVG data URL for Code128 barcode of the given text"""
    if not code_text or not barcode:
        return ""
    try:
        writer = SVGWriter()
        rv = io.BytesIO()
        code = barcode.get('code128', str(code_text), writer=writer)
        code.write(rv, options={
            'write_text': False,
            'quiet_zone': 1.0,
            'module_height': 7.0,
            'module_width': 0.18
        })
        b64 = base64.b64encode(rv.getvalue()).decode('utf-8')
        return f"data:image/svg+xml;base64,{b64}"
    except Exception as e:
        frappe.log_error(f"Error generating barcode: {str(e)}")
        return ""


def get_item_mrp(item_code, batch_no=None, fallback_rate=0.0):
    """Retrieve MRP from Batch, Item Price, or price lists"""
    # 1. Check Batch custom fields if present
    if batch_no and frappe.db.exists("Batch", batch_no):
        batch = frappe.get_cached_doc("Batch", batch_no)
        for field in ["custom_mrp", "mrp", "max_retail_price"]:
            if hasattr(batch, field) and getattr(batch, field):
                return float(getattr(batch, field))

    # 2. Check Item custom fields
    if item_code and frappe.db.exists("Item", item_code):
        item = frappe.get_cached_doc("Item", item_code)
        for field in ["custom_mrp", "mrp", "max_retail_price"]:
            if hasattr(item, field) and getattr(item, field):
                return float(getattr(item, field))

    # 3. Check 'Standard Selling' or 'MRP' Item Price
    prices = frappe.get_all(
        "Item Price",
        filters={"item_code": item_code, "price_list": ["in", ["Standard Selling", "MRP"]]},
        fields=["price_list_rate"],
        order_by="price_list_rate desc",
        limit=1
    )
    if prices and prices[0].price_list_rate:
        return float(prices[0].price_list_rate)

    return float(fallback_rate or 0.0)


def extract_scheme_from_pricing_rules(pr_names, billed_qty, free_qty):
    """Extract scheme text such as '10+3' or '+3' from Pricing Rules or free quantity"""
    if pr_names:
        if isinstance(pr_names, str):
            try:
                pr_list = json.loads(pr_names)
            except Exception:
                pr_list = [p.strip() for p in pr_names.split(",") if p.strip()]
        else:
            pr_list = pr_names

        for pr_name in pr_list:
            if frappe.db.exists("Pricing Rule", pr_name):
                pr = frappe.get_cached_doc("Pricing Rule", pr_name)
                # Check promotional scheme or title containing '+' (e.g., '10+3')
                if pr.promotional_scheme and "+" in pr.promotional_scheme:
                    return pr.promotional_scheme.strip()
                if pr.title and "+" in pr.title:
                    parts = pr.title.split()
                    for part in parts:
                        if "+" in part:
                            return part.strip()
                if pr.min_qty and pr.free_qty:
                    return f"{int(pr.min_qty)}+{int(pr.free_qty)}"
                if getattr(pr, "discount_percentage", None):
                    return f"{pr.discount_percentage:.2f}%"

    if free_qty > 0:
        if billed_qty > 0:
            return f"{int(billed_qty)}+{int(free_qty)}"
        return f"+{int(free_qty)}"

    return ""


def get_pharma_invoice_items(doc):
    """
    Process invoice items, collapsing free scheme rows into a single product line
    with the scheme (e.g. '10+3') displayed in the scheme column.
    """
    billed_items = []
    free_items = []

    for item in doc.items:
        if item.is_free_item:
            free_items.append(item)
        else:
            billed_items.append(item)

    processed_rows = []
    used_free_indices = set()

    for idx, b_item in enumerate(billed_items, 1):
        matching_free = []
        for f_idx, f_item in enumerate(free_items):
            if f_idx in used_free_indices:
                continue
            is_match = False
            if f_item.item_code == b_item.item_code:
                is_match = True
            elif b_item.pricing_rules and f_item.pricing_rules:
                try:
                    b_pr_set = set(json.loads(b_item.pricing_rules) if str(b_item.pricing_rules).startswith('[') else [b_item.pricing_rules])
                    f_pr_set = set(json.loads(f_item.pricing_rules) if str(f_item.pricing_rules).startswith('[') else [f_item.pricing_rules])
                    if b_pr_set.intersection(f_pr_set):
                        is_match = True
                except Exception:
                    pass

            if is_match:
                matching_free.append(f_item)
                used_free_indices.add(f_idx)
                break

        total_free_qty = sum(float(f.qty or 0) for f in matching_free)
        billed_qty = float(b_item.qty or 0)
        scheme_str = extract_scheme_from_pricing_rules(b_item.pricing_rules, billed_qty, total_free_qty)

        # Batch & Expiry
        batch_no = b_item.batch_no or ""
        exp_date_str = ""
        if batch_no and frappe.db.exists("Batch", batch_no):
            batch = frappe.get_cached_doc("Batch", batch_no)
            if batch.expiry_date:
                exp_date_str = frappe.utils.formatdate(batch.expiry_date, "MM/yy")

        # Item info
        item_doc = None
        if frappe.db.exists("Item", b_item.item_code):
            item_doc = frappe.get_cached_doc("Item", b_item.item_code)

        loc_row = ""
        mfac_by = ""
        pack = ""
        if item_doc:
            loc_row = getattr(item_doc, "custom_rack", None) or getattr(item_doc, "custom_location", None) or getattr(item_doc, "shelf", None) or ""
            mfac_by = getattr(item_doc, "brand", None) or getattr(item_doc, "manufacturer", None) or "EXP"
            pack = getattr(item_doc, "custom_pack", None) or item_doc.stock_uom or b_item.uom or "10's"
        if not pack:
            pack = b_item.uom or "10's"
        if not mfac_by:
            mfac_by = "EXP"

        # Pricing and Taxes
        sale_rate = float(b_item.rate or 0.0)
        mrp = get_item_mrp(b_item.item_code, batch_no, fallback_rate=b_item.price_list_rate or sale_rate)
        if mrp < sale_rate:
            mrp = sale_rate

        product_value = round(billed_qty * sale_rate, 2)
        disc_percent = float(b_item.discount_percentage or 0.0)
        hsn = b_item.gst_hsn_code or (item_doc.gst_hsn_code if item_doc else "") or ""

        # GST calculation
        cgst_rate = float(getattr(b_item, "cgst_rate", 0.0) or 0.0)
        sgst_rate = float(getattr(b_item, "sgst_rate", 0.0) or 0.0)
        igst_rate = float(getattr(b_item, "igst_rate", 0.0) or 0.0)
        total_gst_rate = cgst_rate + sgst_rate + igst_rate

        if total_gst_rate == 0.0 and getattr(b_item, "item_tax_rate", None):
            try:
                rates = json.loads(b_item.item_tax_rate) if isinstance(b_item.item_tax_rate, str) else b_item.item_tax_rate
                for k, v in rates.items():
                    k_lower = k.lower()
                    if "cgst" in k_lower:
                        cgst_rate = float(v)
                    elif "sgst" in k_lower or "utgst" in k_lower:
                        sgst_rate = float(v)
                    elif "igst" in k_lower:
                        igst_rate = float(v)
                total_gst_rate = cgst_rate + sgst_rate + igst_rate
            except Exception:
                pass

        if total_gst_rate == 0.0 and doc.taxes:
            for t in doc.taxes:
                if t.rate and t.tax_amount:
                    total_gst_rate = float(t.rate)
                    break

        cgst_amt = float(getattr(b_item, "cgst_amount", 0.0) or 0.0)
        sgst_amt = float(getattr(b_item, "sgst_amount", 0.0) or 0.0)
        igst_amt = float(getattr(b_item, "igst_amount", 0.0) or 0.0)
        gst_value = round(cgst_amt + sgst_amt + igst_amt, 2)

        if gst_value == 0.0 and total_gst_rate > 0.0:
            taxable_amt = float(b_item.net_amount or b_item.amount or product_value)
            gst_value = round(taxable_amt * (total_gst_rate / 100.0), 2)

        taxable_value = float(getattr(b_item, "taxable_value", None) or b_item.net_amount or b_item.amount or product_value)
        net_value = round(taxable_value + gst_value, 2)

        product_name = b_item.item_name or b_item.item_code

        processed_rows.append({
            "sr": idx,
            "loc_row": loc_row,
            "mfac_by": mfac_by[:6].upper(),
            "product": product_name,
            "pack": pack,
            "billed_qty": int(billed_qty) if billed_qty.is_integer() else billed_qty,
            "free_qty": int(total_free_qty) if total_free_qty.is_integer() else total_free_qty,
            "scheme": scheme_str,
            "batch": batch_no,
            "exp_date": exp_date_str,
            "mrp": f"{mrp:.2f}",
            "sale_rate": f"{sale_rate:.2f}",
            "product_value": f"{product_value:.2f}",
            "disc_percent": f"{disc_percent:.2f}",
            "hsn_code": hsn,
            "gst_rate": f"{int(total_gst_rate) if total_gst_rate.is_integer() else total_gst_rate}%",
            "gst_rate_num": total_gst_rate,
            "gst_value": f"{gst_value:.2f}",
            "net_value": f"{net_value:.2f}",
            "taxable_value": taxable_value,
            "cgst_rate": cgst_rate,
            "cgst_amt": cgst_amt,
            "sgst_rate": sgst_rate,
            "sgst_amt": sgst_amt,
            "igst_rate": igst_rate,
            "igst_amt": igst_amt,
        })

    for f_idx, f_item in enumerate(free_items):
        if f_idx not in used_free_indices:
            fq = float(f_item.qty or 0)
            batch_no = f_item.batch_no or ""
            exp_date_str = ""
            if batch_no and frappe.db.exists("Batch", batch_no):
                b_doc = frappe.get_cached_doc("Batch", batch_no)
                if b_doc.expiry_date:
                    exp_date_str = frappe.utils.formatdate(b_doc.expiry_date, "MM/yy")

            processed_rows.append({
                "sr": len(processed_rows) + 1,
                "loc_row": "",
                "mfac_by": "EXP",
                "product": f_item.item_name or f_item.item_code,
                "pack": f_item.uom or "10's",
                "billed_qty": 0,
                "free_qty": int(fq) if fq.is_integer() else fq,
                "scheme": f"+{int(fq)} FREE",
                "batch": batch_no,
                "exp_date": exp_date_str,
                "mrp": "0.00",
                "sale_rate": "0.00",
                "product_value": "0.00",
                "disc_percent": "0.00",
                "hsn_code": f_item.gst_hsn_code or "",
                "gst_rate": "0%",
                "gst_rate_num": 0.0,
                "gst_value": "0.00",
                "net_value": "0.00",
                "taxable_value": 0.0,
                "cgst_rate": 0.0,
                "cgst_amt": 0.0,
                "sgst_rate": 0.0,
                "sgst_amt": 0.0,
                "igst_rate": 0.0,
                "igst_amt": 0.0,
            })

    return processed_rows


def get_pharma_totals(doc, rows=None):
    """Calculate summary figures for the invoice footer"""
    if rows is None:
        rows = get_pharma_invoice_items(doc)

    total_billed_qty = sum(r["billed_qty"] for r in rows)
    total_free_qty = sum(r["free_qty"] for r in rows)
    total_qty = total_billed_qty + total_free_qty

    gross = sum(float(r["product_value"]) for r in rows)
    disc_amt = float(doc.discount_amount or 0.0)
    tax_amt = float(doc.total_taxes_and_charges or 0.0)
    grand_total = float(doc.grand_total or 0.0)
    to_pay = float(doc.rounded_total or doc.grand_total or 0.0)

    return {
        "total_items": len(rows),
        "total_billed_qty": int(total_billed_qty) if isinstance(total_billed_qty, float) and total_billed_qty.is_integer() else total_billed_qty,
        "total_free_qty": int(total_free_qty) if isinstance(total_free_qty, float) and total_free_qty.is_integer() else total_free_qty,
        "total_qty": int(total_qty) if isinstance(total_qty, float) and total_qty.is_integer() else total_qty,
        "gross": f"{gross:.2f}",
        "sch_disc": "0.00",
        "disc_amt": f"{disc_amt:.2f}",
        "tax_amt": f"{tax_amt:.2f}",
        "tcs_rate": "0.000",
        "tcs_amt": "0.00",
        "grand_total": f"{grand_total:.2f}",
        "to_pay": f"{to_pay:.2f}",
        "cr_no": "0.00",
        "db_no": "0.00",
    }


def get_pharma_gst_summary(doc, rows=None):
    """Calculate standard GST slab breakup (5%, 12%, 18%, 28%, 0%)"""
    if rows is None:
        rows = get_pharma_invoice_items(doc)

    is_inter_state = False
    for r in rows:
        if r.get("igst_amt", 0) > 0 or r.get("igst_rate", 0) > 0:
            is_inter_state = True
            break
    if not is_inter_state and doc.taxes:
        for t in doc.taxes:
            if "igst" in (t.account_head or "").lower():
                is_inter_state = True
                break

    slabs = [5.0, 12.0, 18.0, 28.0, 0.0]
    summary_map = {
        rate: {
            "rate": rate,
            "rate_label": f"{int(rate)} %",
            "taxable": 0.0,
            "sgst_rate": rate / 2.0,
            "sgst_amt": 0.0,
            "cgst_rate": rate / 2.0,
            "cgst_amt": 0.0,
            "igst_rate": rate,
            "igst_amt": 0.0,
        }
        for rate in slabs
    }

    total_taxable = 0.0
    total_sgst = 0.0
    total_cgst = 0.0
    total_igst = 0.0

    for r in rows:
        r_gst = r["gst_rate_num"]
        matched_slab = None
        for s in slabs:
            if abs(r_gst - s) < 0.1:
                matched_slab = s
                break
        if matched_slab is None:
            matched_slab = 5.0

        taxable = r["taxable_value"]
        summary_map[matched_slab]["taxable"] += taxable
        total_taxable += taxable

        if is_inter_state:
            igst = float(r.get("gst_value") or 0.0)
            summary_map[matched_slab]["igst_amt"] += igst
            total_igst += igst
        else:
            half_gst = round(float(r.get("gst_value") or 0.0) / 2.0, 2)
            summary_map[matched_slab]["sgst_amt"] += half_gst
            summary_map[matched_slab]["cgst_amt"] += half_gst
            total_sgst += half_gst
            total_cgst += half_gst

    slab_list = [summary_map[s] for s in slabs]

    return {
        "is_inter_state": is_inter_state,
        "slabs": slab_list,
        "total_taxable": f"{total_taxable:.2f}",
        "total_sgst": f"{total_sgst:.2f}",
        "total_cgst": f"{total_cgst:.2f}",
        "total_igst": f"{total_igst:.2f}",
    }


def get_company_pharma_info(doc):
    """Retrieve full company details including DL numbers, Food License, CIN, etc."""
    company_name = doc.company or "Exponit Labs"
    comp = frappe.get_cached_doc("Company", company_name)

    addr_line1 = "Unit-2, B-level, Sunshine Commercial"
    addr_line2 = "Achole Road"
    city = "Nalasopara-E"
    state = "Maharashtra"
    pincode = "401209"
    email = "info@exponit.com"
    phone = "022-42061111"

    if doc.company_address and frappe.db.exists("Address", doc.company_address):
        addr = frappe.get_cached_doc("Address", doc.company_address)
        addr_line1 = addr.address_line1 or addr_line1
        addr_line2 = addr.address_line2 or ""
        city = addr.city or city
        state = addr.state or state
        pincode = addr.pincode or pincode
        email = addr.email_id or email
        phone = addr.phone or phone

    cin = getattr(comp, "cin", None) or "U51909MH2018PTC314815"
    gstin = comp.gstin or "27FSGPM4353B1ZT"
    pan = comp.pan or "FSGPM4353B"
    dl_no = getattr(comp, "custom_drug_licence_no", None) or "20B MH-MZ6-310585  21B MH-MZ6-310586"
    food_lic = getattr(comp, "custom_food_licence_no", None) or "21519021000024"

    return {
        "name": company_name,
        "address_line1": addr_line1,
        "address_line2": addr_line2,
        "city": city,
        "state": state,
        "state_code": "27-Maharashtra" if "maha" in state.lower() else f"27-{state}",
        "pincode": pincode,
        "phone": phone,
        "cin": cin,
        "gstin": gstin,
        "dl_no": dl_no,
        "food_lic": food_lic,
        "pan": pan,
        "email": email,
    }


def get_customer_pharma_info(doc):
    """Retrieve full customer details including DL numbers, Food License, visit day, etc."""
    cust_name = doc.customer
    cust = frappe.get_cached_doc("Customer", cust_name) if cust_name and frappe.db.exists("Customer", cust_name) else None

    addr_line1 = ""
    addr_line2 = ""
    city = ""
    state = ""
    pincode = ""
    phone = ""
    gstin = ""

    if doc.customer_address and frappe.db.exists("Address", doc.customer_address):
        addr = frappe.get_cached_doc("Address", doc.customer_address)
        addr_line1 = addr.address_line1 or ""
        addr_line2 = addr.address_line2 or ""
        city = addr.city or ""
        state = addr.state or ""
        pincode = addr.pincode or ""
        phone = addr.phone or ""
        gstin = addr.gstin or ""

    mobile = doc.contact_mobile or phone or (getattr(cust, "mobile_no", "") if cust else "")
    dl_no = getattr(cust, "custom_drug_licence_number", None) or "20-MH-PL1-509929 21-MH-PL1-509930"
    pan = getattr(cust, "pan", None) or ""
    food_lic = getattr(cust, "custom_food_licence_no", None) or ""

    visit_day = "FRI"
    if doc.posting_date:
        visit_day = frappe.utils.getdate(doc.posting_date).strftime("%a").upper()

    return {
        "party_code": doc.customer,
        "customer_name": doc.customer_name or doc.customer,
        "address_line1": addr_line1,
        "address_line2": addr_line2,
        "city": city,
        "state": state,
        "state_full": f"27-{state}" if "maha" in state.lower() else (f"08-{state}" if "raj" in state.lower() else state),
        "pincode": pincode,
        "visit_day": visit_day,
        "s_code": "325",
        "route": "*BHAGAT",
        "due_date": frappe.utils.formatdate(doc.due_date, "dd-MMMM-yyyy") if doc.due_date else "-",
        "inv_date": frappe.utils.formatdate(doc.posting_date, "dd/MM/yyyy") if doc.posting_date else "-",
        "mobile": mobile,
        "phone": phone or mobile,
        "area": f"VVN {city.upper()}" if city else "LOCAL",
        "dl_no": dl_no,
        "food_lic": food_lic,
        "gstin": gstin or (doc.billing_address_gstin if hasattr(doc, "billing_address_gstin") else ""),
        "pan": pan,
        "ndps": "",
    }


def get_pharma_bank_details(doc):
    """Retrieve bank details for invoice footer"""
    bank_info = None
    if getattr(doc, "company", None):
        bank_accounts = frappe.get_all(
            "Bank Account",
            filters={"company": doc.company, "is_company_account": 1},
            fields=["bank", "account_name", "bank_account_no", "branch_code"],
            order_by="is_default desc, creation asc",
            limit=1
        )
        if bank_accounts:
            acc = bank_accounts[0]
            bank_info = {
                "bank_name": (acc.bank or acc.account_name or "").upper(),
                "branch": (acc.branch_code or "MAIN").upper(),
                "account_no": acc.bank_account_no or "",
                "ifsc_code": acc.branch_code or "",
            }

    if not bank_info:
        bank_info = {
            "bank_name": "ICICI BANK",
            "branch": "JOGESHWARI (EAST)",
            "account_no": "123651000001",
            "ifsc_code": "ICIC0001236",
        }
    return bank_info
