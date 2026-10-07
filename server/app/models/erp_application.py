from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ERPApplication(Base):
    __tablename__ = "erp_applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    form_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    applicant_name: Mapped[str] = mapped_column(String(128), nullable=False, default="申请人")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    form_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approval_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    approval_messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    final_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
