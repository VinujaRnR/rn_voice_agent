"""Universal IoT and hardware registry models: devices, capabilities, gateways, bindings."""
from datetime import datetime
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import JSONType, EncryptedString


class Device(Base, TimestampMixin):
    """Universal device entity supporting hubs, nodes, sensors, and relays."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: f"dev_{uuid.uuid4().hex[:12]}",
        index=True
    )
    household_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    node_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    type: Mapped[str] = mapped_column(String(64), default="device", nullable=False)
    connection_type: Mapped[str] = mapped_column(String(64), default="WiFi", nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    power_state: Mapped[str] = mapped_column(String(32), default="off", nullable=False)
    online_status: Mapped[str] = mapped_column(String(64), default="online", nullable=False)
    is_enrolled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_token: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)

    # Relationships
    household: Mapped[Optional["Household"]] = relationship("Household", back_populates="devices")
    capabilities: Mapped[List["DeviceCapability"]] = relationship(
        "DeviceCapability", back_populates="device", cascade="all, delete-orphan"
    )
    bindings: Mapped[List["DeviceBinding"]] = relationship(
        "DeviceBinding", back_populates="device", cascade="all, delete-orphan"
    )


class DeviceCapability(Base, UUIDPrimaryKeyMixin):
    """Allowed command action and schema for a device."""
    __tablename__ = "device_capabilities"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    parameter_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="capabilities")


class Gateway(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Physical hardware hub or bridge located at a household."""
    __tablename__ = "gateways"

    household_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    gateway_identifier: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    gateway_name: Mapped[str] = mapped_column(String(128), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="online", nullable=False)

    # Relationships
    household: Mapped["Household"] = relationship("Household", back_populates="gateways")
    bindings: Mapped[List["DeviceBinding"]] = relationship("DeviceBinding", back_populates="gateway")


class DeviceBinding(Base, UUIDPrimaryKeyMixin):
    """Binds a device/sub-device to a hardware gateway and channel."""
    __tablename__ = "device_bindings"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    gateway_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("gateways.id", ondelete="SET NULL"), index=True, nullable=True
    )
    sub_device_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    channel_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    binding_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="bindings")
    gateway: Mapped[Optional["Gateway"]] = relationship("Gateway", back_populates="bindings")


class DeviceState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks live reported state vs desired target state."""
    __tablename__ = "device_states"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    reported_state: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    desired_state: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeviceTelemetry(Base, UUIDPrimaryKeyMixin):
    """Time-series sensor telemetry and state-change events."""
    __tablename__ = "device_telemetry"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(default=utc_now, index=True, nullable=False)


class DeviceCommandLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persistent state machine for IoT commands dispatched to devices."""
    __tablename__ = "device_command_logs"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class DeviceEnrollmentRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Temporary token or PIN request for secure device onboarding."""
    __tablename__ = "device_enrollment_requests"

    household_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enrollment_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

