# cashier_logic.py

from sqlalchemy import func, case, and_, not_
from sqlalchemy.orm import Session
from datetime import date
import models


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
    ).all()


def get_ledger_transactions(db: Session, branch_id: str, start_date: date, end_date: date):
    """Fetches transactions within a date range."""
    return db.query(models.CashierTransaction).filter(
        models.CashierTransaction.branch_id == branch_id,
        models.CashierTransaction.date >= start_date,
        models.CashierTransaction.date <= end_date
    ).order_by(models.CashierTransaction.date).all()


def add_transaction(db: Session, data: dict):
    """
    Saves a new transaction.
    Handles optional receipt number generation, mandatory voucher numbering,
    and enforces is_expense flag logic.
    """
    try:
        success_msg = "Success"
        txn_type = data.get('transaction_type')
        branch_id = data.get('branch_id')

        # Pop transient flags
        generate_receipt = data.pop('generate_receipt_no', True)

        if txn_type == 'Receipt':
            # --- RULE: Receipts are NEVER expenses ---
            data['is_expense'] = False

            # Only generate number if checkbox was checked
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
            # Always generate Voucher Number
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
    """Fetches SalesRecord details for the UI."""
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
    """
    Copies transactions from remote branch to target branch.
    Preserves receipt/voucher numbers AND enforces is_expense rules.
    """
    try:
        source_txns = db.query(models.CashierTransaction).filter(
            models.CashierTransaction.id.in_(transaction_ids)
        ).all()

        count = 0
        for src in source_txns:
            # Determine is_expense flag (Safe fallback: False if Receipt)
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

                # --- Preserve Metadata ---
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