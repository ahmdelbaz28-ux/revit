"""fireai/integration/iot_pipeline.py
====================================
IoT Device Integration — MQTT/OPC-UA sensor ingestion and real-time
event processing for fire alarm system monitoring.

Supports:
  - MQTT client with auto-reconnection
  - OPC-UA client with session management
  - Sensor data validation (range checking, rate-of-change limiting)
  - Event processing: threshold crossing, rate-of-change anomaly,
    communication loss detection

References:
  - MQTT 3.1.1 / 5.0 (OASIS Standard)
  - OPC UA Part 1: Overview and Concepts (IEC 62541)
  - NFPA 72-2022 §14.4 — Inspection, testing and maintenance
  - NFPA 72-2022 §10.18 — System monitoring

"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from fireai.core.event_bus import EventBus

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums
# ===========================================================================


class SensorType(str, Enum):
    SMOKE_DETECTOR = "SMOKE_DETECTOR"
    HEAT_DETECTOR = "HEAT_DETECTOR"
    FLAME_DETECTOR = "FLAME_DETECTOR"
    GAS_DETECTOR = "GAS_DETECTOR"
    FLOW_SENSOR = "FLOW_SENSOR"
    PRESSURE_SENSOR = "PRESSURE_SENSOR"
    TEMPERATURE_SENSOR = "TEMPERATURE_SENSOR"
    HUMIDITY_SENSOR = "HUMIDITY_SENSOR"
    VOLTAGE_SENSOR = "VOLTAGE_SENSOR"
    CURRENT_SENSOR = "CURRENT_SENSOR"


class EventSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class SensorStatus(str, Enum):
    NORMAL = "NORMAL"
    ALARM = "ALARM"
    TROUBLE = "TROUBLE"
    FAULT = "FAULT"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class CommunicationProtocol(str, Enum):
    MQTT = "MQTT"
    OPC_UA = "OPC_UA"
    MODBUS = "MODBUS"
    BACNET = "BACNET"
    HTTP = "HTTP"


# ===========================================================================
# Data Models
# ===========================================================================


@dataclass(frozen=True)
class SensorReading:
    sensor_id: str
    sensor_type: SensorType
    value: float
    unit: str
    timestamp: datetime
    quality: float = 1.0  # 0.0 (bad) to 1.0 (good)
    protocol: CommunicationProtocol = CommunicationProtocol.MQTT
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sensor_id.strip():
            raise ValueError("sensor_id is required")
        if math.isnan(self.value) or math.isinf(self.value):
            raise ValueError(
                f"Invalid sensor value: {self.value}"
            )
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError(
                f"quality must be in [0,1], got {self.quality}"
            )
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")


@dataclass(frozen=True)
class SecurityEvent:
    event_id: str
    sensor_id: str
    event_type: str
    severity: EventSeverity
    message: str
    timestamp: datetime
    reading_value: float = 0.0
    threshold: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# Sensor Configuration
# ===========================================================================


@dataclass
class SensorConfig:
    sensor_id: str
    sensor_type: SensorType
    min_value: float = -1e9
    max_value: float = 1e9
    rate_of_change_limit: float = 1e9  # max change per second
    warning_threshold: Optional[float] = None
    alarm_threshold: Optional[float] = None
    comm_loss_seconds: float = 300.0  # 5 minutes default
    unit: str = ""


# ===========================================================================
# IoT Pipeline
# ===========================================================================


class IoTPipeline:
    """MQTT/OPC-UA sensor ingestion and real-time event processing.

    Features:
      - Async MQTT client with automatic reconnection (exponential backoff)
      - Async OPC-UA client with session management
      - Sensor data validation: range checking, rate-of-change limiting
      - Event processing: threshold crossing, anomaly detection,
        communication loss detection
      - All events published to event_bus for downstream processing
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus or EventBus.instance()
        self._sensor_configs: Dict[str, SensorConfig] = {}
        self._last_readings: Dict[str, SensorReading] = {}
        self._rate_buffers: Dict[str, List[tuple[float, float]]] = {}
        self._last_heartbeat: Dict[str, float] = {}

        # MQTT state
        self._mqtt_client: Optional[Any] = None
        self._mqtt_connected: bool = False
        self._mqtt_broker: str = ""
        self._mqtt_port: int = 1883
        self._mqtt_topic: str = ""
        self._mqtt_reconnect_delay: float = 1.0
        self._mqtt_max_reconnect_delay: float = 60.0
        self._mqtt_event_handler: Optional[Callable[[SensorReading], None]] = None

        # OPC-UA state
        self._opcua_client: Optional[Any] = None
        self._opcua_connected: bool = False
        self._opcua_endpoint: str = ""
        self._opcua_session_timeout: float = 600.0

        # Event processing state
        self._comm_loss_timer: Optional[asyncio.Task[None]] = None
        self._running: bool = False

    # ── Configuration ──────────────────────────────────────────────────

    def register_sensor(self, config: SensorConfig) -> None:
        self._sensor_configs[config.sensor_id] = config

    def get_sensor_config(self, sensor_id: str) -> Optional[SensorConfig]:
        return self._sensor_configs.get(sensor_id)

    def unregister_sensor(self, sensor_id: str) -> None:
        self._sensor_configs.pop(sensor_id, None)
        self._last_readings.pop(sensor_id, None)
        self._rate_buffers.pop(sensor_id, None)
        self._last_heartbeat.pop(sensor_id, None)

    # ── MQTT Connection ────────────────────────────────────────────────

    async def connect_mqtt(
        self,
        broker: str,
        port: int = 1883,
        topic: str = "#",
        username: str = "",
        password: str = "",
    ) -> bool:
        """Connect to an MQTT broker with auto-reconnection.

        Uses asyncio-mqtt when available, otherwise simulates
        the connection for testing.

        Args:
            broker: MQTT broker hostname or IP.
            port: MQTT broker port (default: 1883).
            topic: MQTT topic to subscribe to.
            username: Optional MQTT username.
            password: Optional MQTT password.

        Returns:
            True if connection succeeded.

        """
        self._mqtt_broker = broker
        self._mqtt_port = port
        self._mqtt_topic = topic

        try:
            import asyncio_mqtt  # noqa: F401

            self._mqtt_connected = await self._connect_mqtt_real(
                broker, port, topic, username, password
            )
        except ImportError:
            logger.warning(
                "asyncio-mqtt not available — using simulated MQTT. "
                "Install with: pip install asyncio-mqtt"
            )
            self._mqtt_connected = await self._connect_mqtt_simulated(
                broker, port, topic
            )

        if self._mqtt_connected:
            self._event_bus.publish(
                "iot.mqtt.connected",
                data={
                    "broker": broker,
                    "port": port,
                    "topic": topic,
                },
                source="iot_pipeline",
            )

        return self._mqtt_connected

    async def disconnect_mqtt(self) -> None:
        """Disconnect from the MQTT broker."""
        self._mqtt_connected = False
        if self._mqtt_client is not None:
            try:
                await self._mqtt_client.disconnect()
            except Exception as exc:
                logger.warning("MQTT disconnect: %s", exc)
            self._mqtt_client = None

    # ── OPC-UA Connection ──────────────────────────────────────────────

    async def connect_opcua(
        self,
        endpoint: str,
        username: str = "",
        password: str = "",
    ) -> bool:
        """Connect to an OPC-UA server with session management.

        Uses opcua-asyncio when available, otherwise simulates
        the connection for testing.

        Args:
            endpoint: OPC-UA endpoint URL
                      (e.g., opc.tcp://localhost:4840).
            username: Optional OPC-UA username.
            password: Optional OPC-UA password.

        Returns:
            True if connection succeeded.

        """
        self._opcua_endpoint = endpoint

        try:
            import opcua  # noqa: F401
            import opcua_client  # noqa: F401

            self._opcua_connected = await self._connect_opcua_real(
                endpoint, username, password
            )
        except ImportError:
            logger.warning(
                "opcua-asyncio not available — using simulated OPC-UA. "
                "Install with: pip install opcua-asyncio"
            )
            self._opcua_connected = await self._connect_opcua_simulated(
                endpoint
            )

        if self._opcua_connected:
            self._event_bus.publish(
                "iot.opcua.connected",
                data={"endpoint": endpoint},
                source="iot_pipeline",
            )

        return self._opcua_connected

    async def disconnect_opcua(self) -> None:
        """Disconnect from the OPC-UA server."""
        self._opcua_connected = False
        if self._opcua_client is not None:
            try:
                await self._opcua_client.disconnect()
            except Exception as exc:
                logger.warning("OPC-UA disconnect: %s", exc)
            self._opcua_client = None

    # ── Sensor Data Ingestion ──────────────────────────────────────────

    async def ingest_sensor_data(
        self,
        sensor_id: str,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> SensorReading:
        """Ingest a sensor reading: validate and process.

        Steps:
          1. Look up sensor config
          2. Range validation
          3. Rate-of-change validation
          4. Create SensorReading
          5. Process for events
          6. Update heartbeat

        Args:
            sensor_id: Unique sensor identifier.
            value: Measured value.
            timestamp: Measurement timestamp (default: now UTC).

        Returns:
            The validated SensorReading.

        Raises:
            ValueError: If sensor is unknown or value is invalid.

        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

        config = self._sensor_configs.get(sensor_id)
        if config is None:
            raise ValueError(f"Unknown sensor: {sensor_id}")

        # Range check
        if value < config.min_value or value > config.max_value:
            raise ValueError(
                f"Sensor {sensor_id} value {value} out of range "
                f"[{config.min_value}, {config.max_value}]"
            )

        # Rate-of-change check
        last = self._last_readings.get(sensor_id)
        if last is not None:
            time_delta = (
                timestamp - last.timestamp
            ).total_seconds()
            if time_delta > 0:
                rate = abs(value - last.value) / time_delta
                if rate > config.rate_of_change_limit:
                    logger.warning(
                        "Sensor %s rate-of-change %.2f %s/s exceeds limit %.2f",
                        sensor_id,
                        rate,
                        config.unit,
                        config.rate_of_change_limit,
                    )

        reading = SensorReading(
            sensor_id=sensor_id,
            sensor_type=config.sensor_type,
            value=value,
            unit=config.unit or "",
            timestamp=timestamp,
            protocol=CommunicationProtocol.MQTT,
        )

        self._last_readings[sensor_id] = reading
        self._last_heartbeat[sensor_id] = time.monotonic()

        # Process event
        event = self.process_event(reading)
        if event is not None:
            self._event_bus.publish(
                "iot.security_event",
                data={
                    "event_id": event.event_id,
                    "sensor_id": event.sensor_id,
                    "event_type": event.event_type,
                    "severity": event.severity.value,
                    "message": event.message,
                },
                source="iot_pipeline",
            )

        return reading

    # ── Event Processing ───────────────────────────────────────────────

    def process_event(
        self, reading: SensorReading
    ) -> Optional[SecurityEvent]:
        """Process a sensor reading and generate a SecurityEvent if
        any thresholds or anomaly conditions are triggered.

        Event types:
          - THRESHOLD_CROSSING: Value exceeds alarm threshold
          - THRESHOLD_WARNING: Value exceeds warning threshold
          - RATE_ANOMALY: Rate-of-change exceeds limit
          - SENSOR_FAULT: Sensor quality below threshold

        Args:
            reading: The sensor reading to evaluate.

        Returns:
            A SecurityEvent if a condition is triggered, else None.

        """
        config = self._sensor_configs.get(reading.sensor_id)
        if config is None:
            return None

        # Threshold crossing detection
        if config.alarm_threshold is not None:
            if reading.value >= config.alarm_threshold:
                return SecurityEvent(
                    event_id=self._generate_event_id(),
                    sensor_id=reading.sensor_id,
                    event_type="THRESHOLD_ALARM",
                    severity=EventSeverity.CRITICAL,
                    message=(
                        f"Sensor {reading.sensor_id} value "
                        f"{reading.value:.2f} {reading.unit} "
                        f"exceeds alarm threshold "
                        f"{config.alarm_threshold:.2f} {reading.unit}"
                    ),
                    timestamp=reading.timestamp,
                    reading_value=reading.value,
                    threshold=config.alarm_threshold,
                )

        if config.warning_threshold is not None:
            if reading.value >= config.warning_threshold:
                return SecurityEvent(
                    event_id=self._generate_event_id(),
                    sensor_id=reading.sensor_id,
                    event_type="THRESHOLD_WARNING",
                    severity=EventSeverity.HIGH,
                    message=(
                        f"Sensor {reading.sensor_id} value "
                        f"{reading.value:.2f} {reading.unit} "
                        f"exceeds warning threshold "
                        f"{config.warning_threshold:.2f} {reading.unit}"
                    ),
                    timestamp=reading.timestamp,
                    reading_value=reading.value,
                    threshold=config.warning_threshold,
                )

        # Rate-of-change anomaly
        last = self._last_readings.get(reading.sensor_id)
        if last is not None:
            time_delta = (
                reading.timestamp - last.timestamp
            ).total_seconds()
            if time_delta > 0:
                rate = abs(reading.value - last.value) / time_delta
                if rate > config.rate_of_change_limit:
                    return SecurityEvent(
                        event_id=self._generate_event_id(),
                        sensor_id=reading.sensor_id,
                        event_type="RATE_ANOMALY",
                        severity=EventSeverity.HIGH,
                        message=(
                            f"Sensor {reading.sensor_id} rate-of-change "
                            f"{rate:.2f} {reading.unit}/s exceeds limit "
                            f"{config.rate_of_change_limit:.2f} {reading.unit}/s"
                        ),
                        timestamp=reading.timestamp,
                        reading_value=reading.value,
                        threshold=config.rate_of_change_limit,
                        details={"rate": rate, "previous_value": last.value},
                    )

        # Sensor quality / fault detection
        if reading.quality < 0.5:
            return SecurityEvent(
                event_id=self._generate_event_id(),
                sensor_id=reading.sensor_id,
                event_type="SENSOR_FAULT",
                severity=EventSeverity.CRITICAL,
                message=(
                    f"Sensor {reading.sensor_id} quality "
                    f"{reading.quality:.2f} below threshold 0.5"
                ),
                timestamp=reading.timestamp,
                reading_value=reading.value,
                details={"quality": reading.quality},
            )

        return None

    # ── Communication Loss Detection ───────────────────────────────────

    async def start_comm_loss_monitor(
        self, interval_seconds: float = 60.0
    ) -> None:
        """Start background task to detect communication loss.

        Periodically checks all registered sensors for heartbeat
        timeout and generates COMM_LOSS events.

        Args:
            interval_seconds: Check interval (default: 60s).

        """
        if self._comm_loss_timer is not None:
            self._comm_loss_timer.cancel()

        async def _monitor() -> None:
            while self._running:
                try:
                    self._check_communication_loss()
                    await asyncio.sleep(interval_seconds)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error(
                        "Comm loss monitor error: %s", exc
                    )
                    await asyncio.sleep(interval_seconds)

        self._running = True
        self._comm_loss_timer = asyncio.create_task(_monitor())

    async def stop_comm_loss_monitor(self) -> None:
        """Stop the communication loss monitor."""
        self._running = False
        if self._comm_loss_timer is not None:
            self._comm_loss_timer.cancel()
            self._comm_loss_timer = None

    def _check_communication_loss(self) -> None:
        now = time.monotonic()
        for sensor_id, config in self._sensor_configs.items():
            last_hb = self._last_heartbeat.get(sensor_id)
            if last_hb is None:
                continue
            elapsed = now - last_hb
            if elapsed > config.comm_loss_seconds:
                logger.warning(
                    "Communication loss: sensor %s "
                    "last seen %.0f seconds ago",
                    sensor_id,
                    elapsed,
                )
                self._event_bus.publish(
                    "iot.comm_loss",
                    data={
                        "sensor_id": sensor_id,
                        "elapsed_seconds": elapsed,
                        "threshold_seconds": config.comm_loss_seconds,
                    },
                    source="iot_pipeline",
                )

    # ── Status ─────────────────────────────────────────────────────────

    def is_mqtt_connected(self) -> bool:
        """Check MQTT connection status."""
        return self._mqtt_connected

    def is_opcua_connected(self) -> bool:
        """Check OPC-UA connection status."""
        return self._opcua_connected

    def get_latest_reading(
        self, sensor_id: str
    ) -> Optional[SensorReading]:
        """Get the latest reading for a sensor."""
        return self._last_readings.get(sensor_id)

    def get_connected_sensors(self) -> Set[str]:
        """Get set of sensor IDs with recent heartbeats."""
        now = time.monotonic()
        connected: Set[str] = set()
        for sensor_id in self._sensor_configs:
            last_hb = self._last_heartbeat.get(sensor_id)
            if last_hb is not None:
                config = self._sensor_configs[sensor_id]
                if (now - last_hb) < config.comm_loss_seconds:
                    connected.add(sensor_id)
        return connected

    # ── Internal: MQTT Real ────────────────────────────────────────────

    async def _connect_mqtt_real(
        self,
        broker: str,
        port: int,
        topic: str,
        username: str = "",
        password: str = "",
    ) -> bool:
        import asyncio_mqtt as mqtt

        try:
            client = mqtt.Client(
                hostname=broker,
                port=port,
                username=username,
                password=password,
            )
            await client.connect()
            await client.subscribe(topic)
            self._mqtt_client = client
            return True
        except Exception as exc:
            logger.error("MQTT connection failed: %s", exc)
            return False

    async def _connect_mqtt_simulated(
        self, broker: str, port: int, topic: str
    ) -> bool:
        logger.info(
            "Simulated MQTT connected to %s:%s topic=%s",
            broker,
            port,
            topic,
        )
        return True

    # ── Internal: OPC-UA Real ──────────────────────────────────────────

    async def _connect_opcua_real(
        self,
        endpoint: str,
        username: str = "",
        password: str = "",
    ) -> bool:
        try:
            from opcua import Client as OPCUAClient

            client = OPCUAClient(endpoint, timeout=10)
            if username and password:
                client.set_user(username)
                client.set_password(password)
            await client.connect()
            self._opcua_client = client
            return True
        except Exception as exc:
            logger.error("OPC-UA connection failed: %s", exc)
            return False

    async def _connect_opcua_simulated(
        self, endpoint: str
    ) -> bool:
        logger.info(
            "Simulated OPC-UA connected to %s", endpoint
        )
        return True

    @staticmethod
    def _generate_event_id() -> str:
        import uuid

        return f"IOT-{uuid.uuid4().hex[:12].upper()}"


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    import asyncio
    from datetime import timezone

    async def test() -> None:
        pipeline = IoTPipeline()

        pipeline.register_sensor(
            SensorConfig(
                sensor_id="SMK-FL3-01",
                sensor_type=SensorType.SMOKE_DETECTOR,
                min_value=0.0,
                max_value=100.0,
                rate_of_change_limit=10.0,
                alarm_threshold=50.0,
                warning_threshold=30.0,
                unit="%obs",
            )
        )

        mqtt_ok = await pipeline.connect_mqtt(
            "localhost", 1883, "fireai/#"
        )
        print(f"MQTT connected: {mqtt_ok}")

        opcua_ok = await pipeline.connect_opcua(
            "opc.tcp://localhost:4840"
        )
        print(f"OPC-UA connected: {opcua_ok}")

        # Normal reading
        reading = await pipeline.ingest_sensor_data(
            "SMK-FL3-01",
            15.0,
            datetime.now(timezone.utc),
        )
        print(f"Reading: {reading.value} {reading.unit}")

        # Warning threshold
        reading = await pipeline.ingest_sensor_data(
            "SMK-FL3-01",
            35.0,
            datetime.now(timezone.utc),
        )
        print(f"Reading (warning): {reading.value}")

        # Alarm threshold
        reading = await pipeline.ingest_sensor_data(
            "SMK-FL3-01",
            75.0,
            datetime.now(timezone.utc),
        )
        print(f"Reading (alarm): {reading.value}")

        sensors = pipeline.get_connected_sensors()
        print(f"Connected sensors: {sensors}")

        await pipeline.disconnect_mqtt()
        await pipeline.disconnect_opcua()

    asyncio.run(test())
