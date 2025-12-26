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
    """Saves a new transaction."""
    try:
        new_txn = models.CashierTransaction(**data)
        db.add(new_txn)
        db.commit()
        return True, "Success"
    except Exception as e:
        db.rollback()
        return False, str(e)


def get_sales_record_by_dc(db: Session, dc_number: str):
    """Fetches SalesRecord details for the UI."""
    return db.query(models.SalesRecord).filter(models.SalesRecord.DC_Number == dc_number).first()


def get_remote_branch_transactions(db: Session, remote_branch_id: str, current_branch_id: str, selected_date: date):
    """
    Fetches transactions from a remote branch that haven't been imported yet.
    """
    # 1. Get IDs already imported to the current branch
    imported_ids = db.query(models.CashierTransaction.imported_from_id).filter(
        models.CashierTransaction.branch_id == current_branch_id,
        models.CashierTransaction.imported_from_id.isnot(None)
    ).scalar_subquery()

    # 2. Fetch remote transactions NOT IN the imported list
    return db.query(models.CashierTransaction).filter(
        models.CashierTransaction.branch_id == remote_branch_id,
        models.CashierTransaction.date == selected_date,
        not_(models.CashierTransaction.id.in_(imported_ids))
    ).all()


def import_transactions(db: Session, transaction_ids: list, target_branch_id: str):
    """
    Copies selected transactions from remote branch to target branch.
    """
    try:
        # Fetch source transactions
        source_txns = db.query(models.CashierTransaction).filter(
            models.CashierTransaction.id.in_(transaction_ids)
        ).all()

        count = 0
        for src in source_txns:
            # Create a copy
            new_txn = models.CashierTransaction(
                date=src.date,
                transaction_type=src.transaction_type,
                category=f"Imported: {src.category}",  # Tagging as imported
                payment_mode=src.payment_mode,
                amount=src.amount,
                description=f"{src.description} (From {src.branch_id})",
                branch_id=target_branch_id,
                party_name=src.party_name,
                dc_number=src.dc_number,
                imported_from_id=src.id  # Link to original to prevent re-import
            )
            db.add(new_txn)
            count += 1

        db.commit()
        return True, f"Successfully imported {count} records."
    except Exception as e:
        db.rollback()
        return False, str(e)