# cashier_logic.py

from sqlalchemy import func, case, and_, not_
from sqlalchemy.orm import Session
from datetime import date
import models

# --- PDF Generation Imports ---
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def get_opening_balance(db: Session, branch_id: str, target_date: date, mode: str = None) -> float:
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
        query = query.filter(models.CashierTransaction.payment_mode == mode)

    balance = query.scalar()
    return balance if balance else 0.0


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

        generate_receipt = data.pop('generate_receipt_no', True)

        if txn_type == 'Receipt':
            data['is_expense'] = False

            if generate_receipt:
                branch = db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id).with_for_update().first()
                if branch:
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
    """Generates a T-Format Ledger PDF using ReportLab with Full Columns."""
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
    # Using 8pt font to allow comfortable reading without excessive shortening
    style_normal = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=8, leading=9)

    # 1. Header
    title_text = f"GENERAL LEDGER: {branch_id} ({start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')})"
    elements.append(Paragraph(title_text, style_title))
    elements.append(Spacer(1, 5 * mm))

    # 2. Process Data
    receipts = []
    vouchers = []
    total_r_cash = 0.0
    total_v_cash = 0.0

    for t in transactions:
        # Full Description (No truncation)
        desc = f"{t.party_name or ''} {t.description or ''}".strip()
        if t.dc_number:
            desc = f"[{t.dc_number}] {desc}"

        # Wrapped Category
        category = Paragraph(t.category, style_normal)

        # Payment Mode
        mode = t.payment_mode

        # Receipt Row Structure: Date, Ref, Category, Mode, Particulars, Amount
        if t.transaction_type == "Receipt":
            row = [
                t.date.strftime("%d-%m-%Y"),
                str(t.receipt_number or ''),
                category,
                mode,
                Paragraph(desc, style_normal),  # Wraps long text
                f"{t.amount:,.2f}"
            ]
            receipts.append(row)
            if t.payment_mode == "Cash": total_r_cash += t.amount

        # Voucher Row Structure: Date, Ref, Category, Particulars, Amount
        else:
            row = [
                t.date.strftime("%d-%m-%Y"),
                str(t.voucher_number or ''),
                category,
                # Mode not explicitly shown in voucher column structure to save space,
                # or can be added. Usually Vouchers in T-Format imply cash unless bank column exists.
                # Adding Particulars
                Paragraph(desc, style_normal),
                f"{t.amount:,.2f}"
            ]
            vouchers.append(row)
            if t.payment_mode == "Cash": total_v_cash += t.amount

    # 3. Create Table Data
    max_len = max(len(receipts), len(vouchers))
    table_data = []

    # Header Row
    headers = [
        "Date", "Ref No", "Category", "Mode", "Particulars (Receipts)", "Amount",  # Left Side
        "Date", "Ref No", "Category", "Particulars (Vouchers)", "Amount"  # Right Side
    ]
    table_data.append(headers)

    for i in range(max_len):
        r = receipts[i] if i < len(receipts) else [""] * 6
        v = vouchers[i] if i < len(vouchers) else [""] * 5

        combined_row = r + v
        table_data.append(combined_row)

    # 4. Table Configuration (Approx 285mm usable width)
    # Receipts (6 cols): 20 + 15 + 25 + 15 + 50 + 20 = 145mm
    # Vouchers (5 cols): 20 + 15 + 25 + 60 + 20 = 140mm
    # Total: 285mm

    col_widths = [
        20 * mm, 12 * mm, 25 * mm, 15 * mm, 50 * mm, 20 * mm,  # Receipts
        20 * mm, 12 * mm, 25 * mm, 66 * mm, 20 * mm  # Vouchers
    ]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)

    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),  # Slightly smaller for data
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (5, 0), (5, -1), 'RIGHT'),  # Amt R
        ('ALIGN', (10, 0), (10, -1), 'RIGHT'),  # Amt V
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('LINEAFTER', (5, 0), (5, -1), 1.5, colors.black),  # Thick divider between R & V
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))

    elements.append(t)
    elements.append(Spacer(1, 5 * mm))

    # 5. Summary Table
    closing_cash = initial_cash + total_r_cash - total_v_cash

    summary_data = [
        ["Opening Cash Balance:", f"{initial_cash:,.2f}"],
        ["(+) Total Cash Receipts:", f"{total_r_cash:,.2f}"],
        ["(-) Total Cash Vouchers:", f"{total_v_cash:,.2f}"],
        ["CLOSING CASH BALANCE:", f"{closing_cash:,.2f}"]
    ]

    s_table = Table(summary_data, colWidths=[50 * mm, 30 * mm], hAlign='RIGHT')
    s_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Last row bold
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
    ]))

    elements.append(s_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer