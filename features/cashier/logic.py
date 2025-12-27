from decimal import Decimal
from sqlalchemy import func, case, not_
from sqlalchemy.orm import Session
from datetime import date
from core import models # Updated Import
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def get_opening_balance(db: Session, branch_id: str, target_date: date, mode: str = None) -> Decimal:
    """Calculates closing balance of the previous day."""
    query = db.query(
        func.sum(
            case(
                (models.CashierTransaction.transaction_type == 'Receipt', models.CashierTransaction.amount),
                else_=-models.CashierTransaction.amount
            )
        )
    ).filter(
        models.CashierTransaction.branch_id == branch_id,
        models.CashierTransaction.date < target_date
    )

    if mode:
        # Check if mode is a list (for Online/Card)
        if isinstance(mode, (list, tuple)):
            query = query.filter(models.CashierTransaction.payment_mode.in_(mode))
        else:
            query = query.filter(models.CashierTransaction.payment_mode == mode)

    balance = query.scalar()
    # Return Decimal(0) instead of 0.0 to prevent type errors
    return balance if balance is not None else Decimal(0)


def get_daybook_transactions(db: Session, branch_id: str, selected_date: date):
    """Fetches transactions for a specific date."""
    return db.query(models.CashierTransaction).filter(
        models.CashierTransaction.branch_id == branch_id,
        models.CashierTransaction.date == selected_date
    ).order_by(
        models.CashierTransaction.receipt_number,
        models.CashierTransaction.voucher_number,
        models.CashierTransaction.id
    ).all()


def get_ledger_transactions(db: Session, branch_id: str, start_date: date, end_date: date):
    """Fetches transactions within a date range."""
    return db.query(models.CashierTransaction).filter(
        models.CashierTransaction.branch_id == branch_id,
        models.CashierTransaction.date >= start_date,
        models.CashierTransaction.date <= end_date
    ).order_by(
        models.CashierTransaction.date,
        models.CashierTransaction.receipt_number,
        models.CashierTransaction.voucher_number
    ).all()


def add_transaction(db: Session, data: dict):
    try:
        success_msg = "Success"
        txn_type = data.get('transaction_type')
        branch_id = data.get('branch_id')
        category = data.get('category')

        generate_receipt = data.pop('generate_receipt_no', True)

        if txn_type == 'Receipt':
            data['is_expense'] = False

            if generate_receipt:
                branch = db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id).with_for_update().first()
                if branch:
                    # 1. Branch Receipt (Specific Series)
                    if category == "Branch Receipt":
                        current_num = branch.Branch_Receipt_Last_Number if branch.Branch_Receipt_Last_Number else 0
                        next_num = current_num + 1
                        branch.Branch_Receipt_Last_Number = next_num
                        data['receipt_number'] = next_num
                        success_msg = f"Success! Branch Receipt No: {next_num}"

                    # 2. Job Card (Service) - Non-Branch 1
                    elif category == "Job Card Sale":
                        current_num = branch.Job_Card_Last_Number if branch.Job_Card_Last_Number else 0
                        next_num = current_num + 1
                        branch.Job_Card_Last_Number = next_num
                        data['receipt_number'] = next_num
                        success_msg = f"Success! Job Card No: {next_num}"

                    # 3. Out Bill (Service) - Non-Branch 1
                    elif category == "Out Bill Sale":
                        current_num = branch.Out_Bill_Last_Number if branch.Out_Bill_Last_Number else 0
                        next_num = current_num + 1
                        branch.Out_Bill_Last_Number = next_num
                        data['receipt_number'] = next_num
                        success_msg = f"Success! Out Bill No: {next_num}"

                    # 4. Standard Receipt Series (Default)
                    else:
                        current_num = branch.Receipt_Last_Number if branch.Receipt_Last_Number else 0
                        next_num = current_num + 1
                        branch.Receipt_Last_Number = next_num
                        data['receipt_number'] = next_num
                        success_msg = f"Success! Receipt No: {next_num}"
            else:
                data['receipt_number'] = None
                success_msg = "Success (No Receipt No.)"

        elif txn_type == 'Voucher':
            branch = db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id).with_for_update().first()
            if branch:
                current_num = branch.Voucher_Last_Number if branch.Voucher_Last_Number else 0
                next_num = current_num + 1
                branch.Voucher_Last_Number = next_num
                data['voucher_number'] = next_num
                success_msg = f"Success! Voucher No: {next_num}"

        new_txn = models.CashierTransaction(**data)
        db.add(new_txn)
        db.commit()
        return True, success_msg

    except Exception as e:
        db.rollback()
        return False, str(e)


def get_sales_record_by_dc(db: Session, dc_number: str):
    return db.query(models.SalesRecord).filter(models.SalesRecord.DC_Number == dc_number).first()


def get_all_sales_records_by_branch(db: Session, branch_id: str):
    return db.query(models.SalesRecord).filter(
        models.SalesRecord.Branch_ID == branch_id
    ).order_by(models.SalesRecord.Timestamp.desc()).all()


def get_remote_branch_transactions(db: Session, remote_branch_id: str, current_branch_id: str, selected_date: date):
    imported_ids = db.query(models.CashierTransaction.imported_from_id).filter(
        models.CashierTransaction.branch_id == current_branch_id,
        models.CashierTransaction.imported_from_id.isnot(None)
    ).scalar_subquery()

    return db.query(models.CashierTransaction).filter(
        models.CashierTransaction.branch_id == remote_branch_id,
        models.CashierTransaction.date == selected_date,
        not_(models.CashierTransaction.id.in_(imported_ids))
    ).all()


def import_transactions(db: Session, transaction_ids: list, target_branch_id: str, target_date: date):
    try:
        source_txns = db.query(models.CashierTransaction).filter(
            models.CashierTransaction.id.in_(transaction_ids)
        ).all()

        count = 0
        for src in source_txns:
            expense_flag = src.is_expense
            if src.transaction_type == 'Receipt':
                expense_flag = False

            new_txn = models.CashierTransaction(
                date=target_date,
                transaction_type=src.transaction_type,
                category=f"Imported: {src.category}",
                payment_mode=src.payment_mode,
                amount=src.amount,
                description=f"{src.description} (Original Date: {src.date}, From {src.branch_id})",
                branch_id=target_branch_id,
                party_name=src.party_name,
                dc_number=src.dc_number,
                receipt_number=src.receipt_number,
                voucher_number=src.voucher_number,
                is_expense=expense_flag,
                imported_from_id=src.id
            )
            db.add(new_txn)
            count += 1

        db.commit()
        return True, f"Successfully imported {count} records into {target_date}."
    except Exception as e:
        db.rollback()
        return False, str(e)


def generate_pdf_ledger(branch_id, start_date, end_date, initial_cash, transactions):
    """Generates a T-Format Ledger PDF with Grouping & Subtotals on the Receipts Side."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=5 * mm,
        rightMargin=5 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom Styles
    style_title = ParagraphStyle('Title', parent=styles['Heading2'], alignment=1, fontSize=12)
    style_normal = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=8, leading=9)
    style_subtotal = ParagraphStyle('Subtotal', parent=styles['Normal'], fontSize=8, leading=9,
                                    fontName='Helvetica-Bold', alignment=2)  # Right align

    # 1. Header
    title_text = f"GENERAL LEDGER: {branch_id} ({start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')})"
    elements.append(Paragraph(title_text, style_title))
    elements.append(Spacer(1, 5 * mm))

    # --- SORTING & GROUPING ---
    rx_objs = [t for t in transactions if t.transaction_type == 'Receipt']
    vx_objs = [t for t in transactions if t.transaction_type == 'Voucher']

    # Sort Receipts: DC Number first (grouped), then Date
    rx_objs.sort(key=lambda t: (str(t.dc_number) if t.dc_number else "zzzz", t.date))

    # 2. Process Data
    receipts_rows = []
    vouchers_rows = []

    total_r_cash = Decimal(0)
    total_v_cash = Decimal(0)

    # --- BUILD RECEIPT ROWS (LEFT SIDE) ---
    current_dc = None
    dc_subtotal = Decimal(0)

    for t in rx_objs:
        txn_dc = t.dc_number if t.dc_number else None

        # Check for DC Change -> Insert Subtotal Row
        if current_dc and txn_dc != current_dc:
            # Subtotal Row structure: 4 empty cols, Description, Amount
            row_sub = [
                "", "", "", "",
                Paragraph(f"Total {current_dc}:", style_subtotal),
                f"** {dc_subtotal:,.2f} **"
            ]
            receipts_rows.append(row_sub)
            dc_subtotal = Decimal(0)

        current_dc = txn_dc

        # Standard Row
        desc = f"{t.party_name or ''} {t.description or ''}".strip()
        if t.dc_number: desc = f"[{t.dc_number}] {desc}"

        row = [
            t.date.strftime("%d-%m-%Y"),
            str(t.receipt_number or ''),
            Paragraph(t.category, style_normal),
            t.payment_mode,
            Paragraph(desc, style_normal),
            f"{t.amount:,.2f}"
        ]
        receipts_rows.append(row)

        dc_subtotal += Decimal(t.amount)
        if t.payment_mode and t.payment_mode.strip() == "Cash":
            total_r_cash += Decimal(t.amount)

    # Final Subtotal
    if current_dc:
        row_sub = [
            "", "", "", "",
            Paragraph(f"Total {current_dc}:", style_subtotal),
            f"** {dc_subtotal:,.2f} **"
        ]
        receipts_rows.append(row_sub)

    # --- BUILD VOUCHER ROWS (RIGHT SIDE) ---
    for t in vx_objs:
        desc = f"{t.party_name or ''} {t.description or ''}".strip()

        row = [
            t.date.strftime("%d-%m-%Y"),
            str(t.voucher_number or ''),
            Paragraph(t.category, style_normal),
            Paragraph(desc, style_normal),
            f"{t.amount:,.2f}"
        ]
        vouchers_rows.append(row)

        if t.payment_mode and t.payment_mode.strip() == "Cash":
            total_v_cash += Decimal(t.amount)

    # 3. Merge into T-Format Table
    max_len = max(len(receipts_rows), len(vouchers_rows))
    table_data = []

    # Header Row
    headers = [
        "Date", "Ref No", "Category", "Mode", "Particulars (Receipts)", "Amount",  # Left
        "Date", "Ref No", "Category", "Particulars (Vouchers)", "Amount"  # Right
    ]
    table_data.append(headers)

    for i in range(max_len):
        r = receipts_rows[i] if i < len(receipts_rows) else [""] * 6
        v = vouchers_rows[i] if i < len(vouchers_rows) else [""] * 5
        table_data.append(r + v)

    # 4. Table Layout
    # Receipts (6 cols): 20 + 12 + 25 + 15 + 50 + 20 = 142mm
    # Vouchers (5 cols): 20 + 12 + 25 + 66 + 20 = 143mm
    col_widths = [
        20 * mm, 12 * mm, 25 * mm, 15 * mm, 50 * mm, 20 * mm,  # Left
        20 * mm, 12 * mm, 25 * mm, 66 * mm, 20 * mm  # Right
    ]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)

    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (5, 0), (5, -1), 'RIGHT'),  # Amt Left
        ('ALIGN', (10, 0), (10, -1), 'RIGHT'),  # Amt Right
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('LINEAFTER', (5, 0), (5, -1), 1.5, colors.black),  # Thick middle divider
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))

    elements.append(t)
    elements.append(Spacer(1, 5 * mm))

    # 5. Summary
    init_cash_dec = Decimal(str(initial_cash))
    closing_cash = init_cash_dec + total_r_cash - total_v_cash

    summary_data = [
        ["Opening Cash Balance:", f"{init_cash_dec:,.2f}"],
        ["(+) Total Cash Receipts:", f"{total_r_cash:,.2f}"],
        ["(-) Total Cash Vouchers:", f"{total_v_cash:,.2f}"],
        ["CLOSING CASH BALANCE:", f"{closing_cash:,.2f}"]
    ]

    s_table = Table(summary_data, colWidths=[50 * mm, 30 * mm], hAlign='RIGHT')
    s_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
    ]))

    elements.append(s_table)
    doc.build(elements)
    buffer.seek(0)
    return buffer