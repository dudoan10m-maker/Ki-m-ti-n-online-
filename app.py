import os
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import (
    create_engine, String, Integer, DateTime, Text, ForeignKey, select, desc
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

APP_NAME = "Dao Vang Backend"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dao_vang.db")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "*").split(",") if x.strip()]

# Render Postgres often provides postgres://; SQLAlchemy expects postgresql://.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    xu: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    bank: Mapped[str] = mapped_column(String(100))
    account_number: Mapped[str] = mapped_column(String(80))
    account_owner: Mapped[str] = mapped_column(String(150))
    amount_vnd: Mapped[int] = mapped_column(Integer)
    xu_deducted: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})


def utc_iso(value):
    return value.isoformat() if value else None


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not ADMIN_TOKEN:
            return jsonify({"ok": False, "error": "ADMIN_TOKEN chưa được cấu hình trên server"}), 503
        token = request.headers.get("Authorization", "")
        if not secrets.compare_digest(token, "Bearer " + ADMIN_TOKEN):
            return jsonify({"ok": False, "error": "Không có quyền quản trị"}), 401
        return fn(*args, **kwargs)
    return wrapper


def withdrawal_json(w):
    return {
        "id": w.id, "player_id": w.player_id, "bank": w.bank,
        "account_number": w.account_number, "account_owner": w.account_owner,
        "amount_vnd": w.amount_vnd, "xu_deducted": w.xu_deducted,
        "status": w.status, "note": w.note,
        "created_at": utc_iso(w.created_at), "updated_at": utc_iso(w.updated_at)
    }


@app.get("/")
def index():
    return jsonify({
        "ok": True, "service": APP_NAME,
        "message": "Backend is running. See /health and API routes."
    })


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return jsonify({"ok": True, "service": APP_NAME, "database": "connected"})
    except SQLAlchemyError:
        app.logger.exception("Database health check failed")
        return jsonify({"ok": False, "database": "unavailable"}), 503


@app.post("/api/player/init")
def player_init():
    data = request.get_json(silent=True) or {}
    player_id = str(data.get("player_id", "")).strip()
    if not player_id or len(player_id) > 80:
        return jsonify({"ok": False, "error": "player_id bắt buộc, tối đa 80 ký tự"}), 400
    with SessionLocal() as db:
        player = db.get(Player, player_id)
        if player is None:
            player = Player(id=player_id, xu=0)
            db.add(player)
            db.commit()
        return jsonify({"ok": True, "player_id": player.id, "xu": player.xu})


@app.get("/api/player/<player_id>")
def get_player(player_id):
    with SessionLocal() as db:
        player = db.get(Player, player_id)
        if player is None:
            return jsonify({"ok": False, "error": "Không tìm thấy người chơi"}), 404
        return jsonify({"ok": True, "player_id": player.id, "xu": player.xu})


@app.post("/api/player/<player_id>/withdrawals")
def create_withdrawal(player_id):
    data = request.get_json(silent=True) or {}
    bank = str(data.get("bank", "")).strip()
    account_number = str(data.get("account_number", "")).strip()
    account_owner = str(data.get("account_owner", "")).strip()
    try:
        amount_vnd = int(data.get("amount_vnd", 0))
        xu_deducted = int(data.get("xu_deducted", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Số tiền/xu không hợp lệ"}), 400

    if not all([bank, account_number, account_owner]):
        return jsonify({"ok": False, "error": "Cần nhập ngân hàng, số tài khoản và tên chủ tài khoản"}), 400
    if len(bank) > 100 or len(account_number) > 80 or len(account_owner) > 150:
        return jsonify({"ok": False, "error": "Một trường thông tin quá dài"}), 400
    if amount_vnd < 1 or amount_vnd > 100_000_000 or xu_deducted < 1 or xu_deducted > 2_000_000_000:
        return jsonify({"ok": False, "error": "Số tiền hoặc xu nằm ngoài giới hạn"}), 400

    with SessionLocal() as db:
        player = db.get(Player, player_id)
        if player is None:
            return jsonify({"ok": False, "error": "Người chơi chưa khởi tạo"}), 404

        # IMPORTANT: Do not trust xu_deducted sent by a public browser.
        # This API is a scaffold; connect an authoritative server-side earning ledger before real payouts.
        if player.xu < xu_deducted:
            return jsonify({"ok": False, "error": "Không đủ xu trong số dư máy chủ"}), 400

        player.xu -= xu_deducted
        item = Withdrawal(
            player_id=player.id, bank=bank, account_number=account_number,
            account_owner=account_owner, amount_vnd=amount_vnd,
            xu_deducted=xu_deducted, status="pending"
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return jsonify({"ok": True, "message": "Đã lưu yêu cầu chờ duyệt", "xu": player.xu, "withdrawal": withdrawal_json(item)}), 201


@app.get("/api/admin/withdrawals")
@admin_required
def admin_withdrawals():
    status = request.args.get("status", "").strip()
    with SessionLocal() as db:
        stmt = select(Withdrawal).order_by(desc(Withdrawal.created_at))
        if status:
            stmt = stmt.where(Withdrawal.status == status)
        items = db.scalars(stmt.limit(500)).all()
        return jsonify({"ok": True, "items": [withdrawal_json(x) for x in items]})


@app.post("/api/admin/withdrawals/<int:withdrawal_id>/decision")
@admin_required
def admin_decision(withdrawal_id):
    data = request.get_json(silent=True) or {}
    decision = str(data.get("decision", "")).strip().lower()
    note = str(data.get("note", "")).strip()[:500]
    if decision not in ("mark_paid", "reject"):
        return jsonify({"ok": False, "error": "decision phải là mark_paid hoặc reject"}), 400

    with SessionLocal() as db:
        item = db.get(Withdrawal, withdrawal_id)
        if item is None:
            return jsonify({"ok": False, "error": "Không tìm thấy yêu cầu"}), 404
        if item.status != "pending":
            return jsonify({"ok": False, "error": "Yêu cầu này đã được xử lý"}), 409

        if decision == "mark_paid":
            # This only marks the request as manually paid. It does NOT send a bank transfer.
            item.status = "marked_paid_manual"
        else:
            player = db.get(Player, item.player_id)
            if player:
                player.xu += item.xu_deducted
            item.status = "rejected_refunded"
        item.note = note
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return jsonify({"ok": True, "withdrawal": withdrawal_json(item)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
