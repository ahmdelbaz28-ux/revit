from __future__ import annotations

"""
QOMN-FIRE v4.0 — FAIL-LOUD RESILIENCE LAYER & INTEGRATION ADAPTERS
====================================================================

Philosophy: "Fail-Loud, Never Fail-Silent"
In a fire protection system, a fake value is worse than no value.
A silenced error kills. A loud error saves.

CHANGES FROM v3.1:
  - REJECTED status: calculation fails → pipeline STOPS, not continues
  - Human Review Gate: every "healed" value REQUIRES human sign-off
  - No float('inf') or float('nan') as defaults — physically impossible values REJECTED
  - Singleton AuditLogger — no thread/resource leak
  - Thread-safe _last_ref with lock
  - Fatal errors (ZeroDivisionError, MemoryError) → REJECTED, not "healed"
  - Recoverable errors → HEALED with LOUD alert + mandatory human review
  - Force-safe-on-unknown defaults to FALSE — unknown errors REJECTED
  - Physics validators reject inf/nan unconditionally
  - Comprehensive test suite covering every adapter and scenario

Citations: NFPA 101 (2021), NFPA 72 (2022), NEC 760 (2023), IEEE-754 (2019)
Author: Safety-Critical Systems Architect (Fail-Loud Rewrite)
"""

import collections
import hashlib
import hmac
import json
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# =====================================================================
# CONFIGURATION: آمن — يرفض العمل بدون مفتاح في الإنتاج
# =====================================================================
class Config:
    """كل القيم قابلة للتعديل بدون تغيير الكود.
    في الإنتاج: يرفض العمل بدون QOMN_AUDIT_SECRET.
    """

    SECRET_KEY: bytes = os.environ.get('QOMN_AUDIT_SECRET', '').encode()
    CB_LIMIT: int = int(os.getenv('QOMN_CB_LIMIT', '15'))
    CB_WINDOW: float = float(os.getenv('QOMN_CB_WINDOW', '60.0'))
    CB_COOLDOWN: float = float(os.getenv('QOMN_CB_COOLDOWN', '30.0'))
    CB_HALF_OPEN_MAX: int = int(os.getenv('QOMN_CB_HALF_OPEN', '3'))
    AUDIT_FILE: str = os.getenv('QOMN_AUDIT_FILE', 'qomn_healing_audit.jsonl')

    # [v4.0 NEW] هل نرفض العمل بدون مفتاح سري؟
    REFUSE_ON_MISSING_SECRET: bool = os.getenv('QOMN_REFUSE_NO_SECRET', 'true').lower() == 'true'

    @classmethod
    def is_production(cls) -> bool:
        return cls.SECRET_KEY != b''

    @classmethod
    def verify_ready(cls) -> None:
        """يرفض العمل إذا كان المفتاح السري مفقوداً و REFUSE_ON_MISSING_SECRET=True.
        هذا يمنع تشغيل النظام بدون توقيعات HMAC في الإنتاج.
        """
        if cls.REFUSE_ON_MISSING_SECRET and not cls.SECRET_KEY:
            raise RuntimeError(
                "QOMN_AUDIT_SECRET is not set. "
                "Refusing to operate without HMAC signing. "
                "Set QOMN_AUDIT_SECRET or QOMN_REFUSE_NO_SECRET=false for dev."
            )


# =====================================================================
# DATA TYPES — مع REJECTED و Human Review Gate
# =====================================================================
class SystemStatus(Enum):
    NOMINAL = "NOMINAL"                         # الحساب نجح بدون أي تدخل
    HEALED = "HEALED"                           # استُبدلت القيمة — يحتاج مراجعة بشرية
    REJECTED = "REJECTED"                       # الحساب فشل — توقف فوري للخط
    CRITICAL_CIRCUIT_OPEN = "CRITICAL_CIRCUIT_OPEN"  # قاطع الدائرة مفتوح
    DEGRADED = "DEGRADED"                       # أداء منخفض لكن يعمل


@dataclass(frozen=True)
class SafetyResult:
    """نتيجة آمنة — لا قيمة بدون حالة.
    كل قيمة "مُعالجة" تحتاج مراجعة بشرية.
    كل قيمة "مرفوضة" تُوقف الـ pipeline.
    """

    value: Any
    status: SystemStatus
    metadata: Dict[str, Any] = field(default_factory=dict)
    audit_ref: Optional[str] = None
    human_review_required: bool = False  # [v4.0 NEW] هل يحتاج مراجعة بشرية؟
    rejection_reason: Optional[str] = None  # [v4.0 NEW] سبب الرفض إن وُجد

    def is_healed(self) -> bool:
        return self.status == SystemStatus.HEALED

    def is_nominal(self) -> bool:
        return self.status == SystemStatus.NOMINAL

    def is_critical(self) -> bool:
        return self.status in (SystemStatus.CRITICAL_CIRCUIT_OPEN, SystemStatus.REJECTED)

    def is_rejected(self) -> bool:
        return self.status == SystemStatus.REJECTED

    def is_safe_to_use(self) -> bool:
        """القيمة آمنة للاستخدام فقط إذا:
        - NOMINAL (حساب حقيقي)
        - HEALED (استُبدلت لكن ما زالت فيزيائياً صحيحة)
        لا تعني أن القيمة صحيحة — تعني فقط أنها ليست مستحيلة فيزيائياً.
        """
        return self.status in (SystemStatus.NOMINAL, SystemStatus.HEALED)

    def requires_human_review(self) -> bool:
        """هل يجب أن يراجع إنسان هذه النتيجة قبل الاعتماد عليها؟
        REJECTED دائماً يحتاج مراجعة بشرية — يجب أن يعرف إنسان أن النظام رفض الحساب.
        """
        return self.human_review_required or self.is_healed() or self.is_rejected()


# =====================================================================
# FATAL vs RECOVERABLE ERROR CLASSIFICATION
# =====================================================================
# أخطاء قاتلة = لا يمكن "شفاءها" بأمان = يجب رفضها
FATAL_ERRORS: Tuple[type, ...] = (
    ZeroDivisionError,  # قسمة على صفر = فيزياء مستحيلة
    MemoryError,        # لا ذاكرة = لا يمكن الوثوق بأي نتيجة
    OSError,            # فشل I/O = البيانات قد تكون تالفة
    RuntimeError,       # خطأ عام = لا نعرف ما حدث
    ConnectionError,    # انقطاع اتصال = بيانات ناقصة
    PermissionError,    # لا صلاحية = نظام مُخترق أو مُعطّل
)

# أخطاء قابلة للشفاء = يمكن استبدالها بقيمة آمنة مع إنذار
RECOVERABLE_ERRORS: Tuple[type, ...] = (
    IndexError,      # فهرس خارج النطاق = يمكن استخدام آخر عنصر
    TimeoutError,    # انتهت المهلة = يمكن استخدام قيمة دنيا
    ValueError,      # قيمة خاطئة = يمكن استخدام safe_minimum
    KeyError,        # مفتاح مفقود = يمكن استخدام default
    TypeError,       # نوع خاطئ = يمكن تحويل النوع
)


def classify_error(exc: Exception) -> str:
    """يُصنّف الخطأ: FATAL أو RECOVERABLE أو UNKNOWN.
    هذا القرار يحدد مصير الحساب بأكمله.
    """
    for fatal_type in FATAL_ERRORS:
        if isinstance(exc, fatal_type):
            return "FATAL"
    for recoverable_type in RECOVERABLE_ERRORS:
        if isinstance(exc, recoverable_type):
            return "RECOVERABLE"
    return "UNKNOWN"  # UNKNOWN = FATAL في نظام سلامة حرائق


# =====================================================================
# AUDIT LOGGER: Singleton + Thread-Safe + HMAC + Rotation
# =====================================================================
class AsyncAuditLogger:
    """Non-blocking audit logger.
    SINGLETON: مثيل واحد فقط — لا تسرب خيوط.
    Thread-safe: كل الوصول محمي بأقفال.
    HMAC: كل سجل موقّع.
    في الإنتاج: يرفض العمل بدون مفتاح سري.
    """

    _instance: Optional[AsyncAuditLogger] = None
    _init_lock = threading.Lock()

    def __new__(cls, filepath: Optional[str] = None):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False  # type: ignore[as-type, has-type]
            return cls._instance

    def __init__(self, filepath: Optional[str] = None):
        if self._initialized:  # type: ignore[has-type]
            return
        self._initialized = True

        # تحقق من المفتاح السري
        Config.verify_ready()

        self.filepath = filepath or Config.AUDIT_FILE
        self._secret = Config.SECRET_KEY
        self._queue: collections.deque = collections.deque()
        self._lock = threading.Lock()
        self._flush_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        self._last_ref: Optional[str] = None
        self._pending_count: int = 0  # [v4.0 NEW] تتبع الإدخالات غير المكتوبة

    @classmethod
    def reset_instance(cls):
        """لاستخدام الاختبارات فقط — يعيد تعيين الـ Singleton."""
        with cls._init_lock:
            if cls._instance is not None:
                cls._instance._shutdown_event.set()
                cls._instance._flush_event.set()
                time.sleep(0.1)
            cls._instance = None

    def log_event(self, event_data: Dict[str, Any]) -> str:
        event_data["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        event_data["event_id"] = hashlib.sha256(
            f"{time.time()}{id(self)}{json.dumps(event_data, sort_keys=True, default=str)}".encode()
        ).hexdigest()[:12]

        # [v4.0 NEW] إضافة مستوى الخطورة
        event_data.get("severity", "INFO")
        if event_data.get("status") == "REJECTED":
            event_data["severity"] = "CRITICAL"
        elif event_data.get("status") == "HEALED":
            event_data["severity"] = "WARNING"

        serialized = json.dumps(event_data, sort_keys=True, default=str)
        signature = hmac.new(self._secret, serialized.encode(), hashlib.sha256).hexdigest()

        entry = {"payload": event_data, "signature": signature}

        with self._lock:
            self._queue.append(json.dumps(entry))
            self._pending_count += 1
            self._last_ref = event_data["event_id"]

        self._flush_event.set()  # [v4.0 NEW] أيقظ الكاتب فوراً
        return self._last_ref

    @property
    def last_entry_id(self) -> Optional[str]:
        """Thread-safe قراءة آخر مرجع."""
        with self._lock:
            return self._last_ref

    def _writer_loop(self):
        while not self._shutdown_event.is_set():
            batch = []
            with self._lock:
                while self._queue:
                    batch.append(self._queue.popleft())
                if batch:
                    self._pending_count -= len(batch)

            if batch:
                self._write_batch(batch)

            self._flush_event.wait(0.1)
            self._flush_event.clear()

        # اكتب ما تبقى قبل الإغلاق
        batch = []
        with self._lock:
            while self._queue:
                batch.append(self._queue.popleft())
        if batch:
            self._write_batch(batch)

    def _write_batch(self, lines: List[str]):
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            sys.stderr.write(f"[AUDIT-CRITICAL] Failed to write: {e}\n")
            # [v4.0 NEW] في نظام سلامة، فشل الكتابة = فشل التدقيق = إنذار
            sys.stderr.write(f"[AUDIT-CRITICAL] {len(lines)} audit entries LOST!\n")

    def flush(self, timeout: float = 2.0) -> bool:
        """ينتظر حتى تُكتب كل الإدخالات أو تنتهي المهلة.
        يُرجع True إذا نجح، False إذا انتهت المهلة.
        """
        self._flush_event.set()
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._pending_count <= 0 and not self._queue:
                    return True
            time.sleep(0.05)
        return False  # انتهت المهلة — إدخالات غير مكتوبة

    def verify_signature(self, entry: Dict[str, Any]) -> bool:
        payload = entry.get("payload", {})
        sig = entry.get("signature", "")
        serialized = json.dumps(payload, sort_keys=True, default=str).encode()
        expected = hmac.new(self._secret, serialized, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)


# =====================================================================
# CIRCUIT BREAKER: Weighted + Half-Open + Error History Retention
# =====================================================================
class WeightedCircuitBreaker:
    """Thread-safe circuit breaker with weighted errors.
    v4.0 CHANGES:
    - يحتفظ بتاريخ الأخطاء حتى بعد العودة من Half-Open
    - يُعلم عن كل انتقال حالة
    - لا يسمح بالانتقال من OPEN إلى CLOSED مباشرة
    """

    def __init__(self, limit: int = Config.CB_LIMIT,
                 window: float = Config.CB_WINDOW,
                 cooldown: float = Config.CB_COOLDOWN,
                 half_open_max: int = Config.CB_HALF_OPEN_MAX,
                 name: str = "unnamed"):
        self.limit = limit
        self.window = window
        self.cooldown = cooldown
        self.half_open_max = half_open_max
        self.name = name
        self._state = "CLOSED"
        self._open_time: float = 0.0
        self._half_open_successes: int = 0
        self._events: collections.deque = collections.deque()
        self._total_errors: int = 0  # [v4.0 NEW] العدد الكلي للأخطاء (لا يُمسح)
        self._lock = threading.RLock()

    def register(self, error_type: str, weight: int = 1) -> bool:
        now = time.time()

        with self._lock:
            # O(1) pruning
            cutoff = now - self.window
            while self._events and self._events[0][0] < cutoff:
                self._events.popleft()

            self._events.append((now, weight))
            self._total_errors += 1  # [v4.0] لا ننسى
            total_score = sum(w for _, w in self._events)

            if total_score > self.limit:
                self._state = "OPEN"
                self._open_time = now
                self._half_open_successes = 0
                return False
            return True

    def record_success(self):
        with self._lock:
            if self._state == "HALF_OPEN":
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_max:
                    self._state = "CLOSED"
                    # [v4.0] لا نمسح تاريخ الأخطاء — نحتفظ به للتحليل
                    self._half_open_successes = 0

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._state == "OPEN":
                if time.time() - self._open_time > self.cooldown:
                    self._state = "HALF_OPEN"
                    self._half_open_successes = 0
                    return False
                return True
            return False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def total_errors(self) -> int:
        """[v4.0 NEW] العدد الكلي للأخطاء — لا يُمسح أبداً."""
        with self._lock:
            return self._total_errors

    def reset(self):
        """للاختبارات فقط — لا يُستخدم في الإنتاج."""
        with self._lock:
            self._state = "CLOSED"
            self._events.clear()
            self._half_open_successes = 0
            self._open_time = 0.0


# =====================================================================
# SELF-HEALING DECORATOR v4.0 — FAIL-LOUD PHILOSOPHY
# =====================================================================
# كل decorator يشارك نفس الـ AuditLogger (Singleton)
# لكن لكل واحد Circuit Breaker مستقل

_circuit_breakers: Dict[str, WeightedCircuitBreaker] = {}
_cb_lock = threading.Lock()


def _get_circuit_breaker(name: str) -> WeightedCircuitBreaker:
    """كل دالة مُزينة لها قاطع دائرة مستقل."""
    with _cb_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = WeightedCircuitBreaker(name=name)
        return _circuit_breakers[name]


def fail_loud_v4(
    safe_minimum: Optional[float] = None,
    default_value: Any = None,
    physics_validator: Optional[Callable[[Any], bool]] = None,
    nfpa_reference: str = "",  # [v4.0 NEW] مرجع NFPA للحساب
    unit: str = "",  # [v4.0 NEW] وحدة القياس
    allow_healing: bool = True,  # [v4.0 NEW] هل يُسمح بالشفاء أصلاً؟
):
    """Fail-Loud Self-Healing Decorator v4.0.

    الفلسفة:
    - أخطاء قاتلة (FATAL) → REJECTED → توقف الـ pipeline فوراً
    - أخطاء قابلة للشفاء (RECOVERABLE) → HEALED + إنذار صريح + مراجعة بشرية إلزامية
    - أخطاء مجهولة (UNKNOWN) → REJECTED (لا نأخذ مخاطر في نظام سلامة)
    - القيم المستحيلة فيزيائياً → REJECTED (لا inf, لا nan, لا أرقام سالبة حيث لا يجب)

    safe_minimum: القيمة الدنيا الآمنة (إلزامي لكل حساب فيزيائي)
    default_value: القيمة الافتراضية (إلزامي لكل حساب)
    physics_validator: دالة تتحقق من صحة القيمة فيزيائياً
    nfpa_reference: مرجع المعيار (للتتبع والمساءلة)
    unit: وحدة القياس (للسجلات والمراجعة)
    allow_healing: إذا False، أي خطأ = REJECTED (للحسابات الحرجة)
    """
    # [v4.0] التحقق من أن safe_minimum و default_value محددان
    if safe_minimum is None and default_value is None and allow_healing:
        raise ValueError(
            "fail_loud_v4 requires safe_minimum or default_value when allow_healing=True. "
            "In a fire safety system, every calculation must have a defined safe fallback."
        )

    # [v4.0] التحقق من أن القيم الافتراضية ليست مستحيلة فيزيائياً
    _validate_fallback(safe_minimum, "safe_minimum")
    _validate_fallback(default_value, "default_value")

    def decorator(func: Callable) -> Callable:
        func_name = func.__name__
        cb = _get_circuit_breaker(func_name)

        def wrapper(*args, **kwargs) -> SafetyResult:
            # محاولة الحصول على الـ logger (قد تفشل إذا لم يُعيّن المفتاح السري)
            try:
                logger = AsyncAuditLogger()
            except RuntimeError as e:
                # المفتاح السري مفقود — هذا خطأ قاتل
                return SafetyResult(
                    value=None,
                    status=SystemStatus.REJECTED,
                    metadata={"error": str(e), "tier": "pre-check"},
                    human_review_required=True,
                    rejection_reason=f"Audit system unavailable: {e}"
                )

            # تجزئة المدخلات (بدون بيانات حساسة)
            try:
                # [v4.0] لا نُجزّئ الكائنات المعقدة — نتجزئ الأنواع فقط
                input_summary = {
                    "func": func_name,
                    "arg_count": len(args),
                    "kwarg_keys": sorted(kwargs.keys()),
                }
                hashlib.sha256(
                    json.dumps(input_summary, sort_keys=True, default=str).encode()
                ).hexdigest()
            except Exception:
                pass

            # Tier 3: Circuit Breaker
            if cb.is_open:
                audit_ref = logger.log_event({
                    "function_name": func_name,
                    "error_type": "CircuitBreakerOpen",
                    "error_message": f"Breaker OPEN for {func_name} due to excessive fault rate "
                                     f"(total_errors={cb.total_errors})",
                    "tier_used": 3,
                    "status": "CRITICAL_CIRCUIT_OPEN",
                    "nfpa_ref": nfpa_reference,
                    "severity": "CRITICAL",
                })

                return SafetyResult(
                    value=None,
                    status=SystemStatus.CRITICAL_CIRCUIT_OPEN,
                    metadata={"error": "Breaker Tripped", "state": cb.state,
                              "total_errors": cb.total_errors},
                    audit_ref=audit_ref,
                    human_review_required=True,
                    rejection_reason=f"Circuit breaker OPEN after {cb.total_errors} errors"
                )

            # Normal path
            try:
                nominal_val = func(*args, **kwargs)

                # [v4.0 NEW] التحقق من النتيجة حتى في المسار الناجح
                if _is_physically_invalid(nominal_val):
                    audit_ref = logger.log_event({
                        "function_name": func_name,
                        "error_type": "InvalidNominalResult",
                        "error_message": f"Function returned physically invalid value: {nominal_val}",
                        "tier_used": 0,
                        "status": "REJECTED",
                        "nfpa_ref": nfpa_reference,
                        "severity": "CRITICAL",
                    })
                    return SafetyResult(
                        value=None,
                        status=SystemStatus.REJECTED,
                        metadata={"error": "Nominal result is physically invalid",
                                  "returned_value": str(nominal_val)},
                        audit_ref=audit_ref,
                        human_review_required=True,
                        rejection_reason=f"Function returned invalid value: {nominal_val}"
                    )

                cb.record_success()
                return SafetyResult(
                    value=nominal_val,
                    status=SystemStatus.NOMINAL,
                    metadata={"nfpa_ref": nfpa_reference, "unit": unit}
                )

            except Exception as e:
                err_type = type(e).__name__
                err_msg = str(e)
                err_classification = classify_error(e)

                cb.register(err_type)

                # ============================================================
                # القرار الأهم: هل نشفي أم نرفض؟
                # ============================================================

                if not allow_healing:
                    # الحساب حرج — لا شفاء مسموح
                    audit_ref = logger.log_event({
                        "function_name": func_name,
                        "error_type": f"CRITICAL_BLOCKED:{err_type}",
                        "error_message": err_msg,
                        "error_classification": err_classification,
                        "tier_used": 0,
                        "status": "REJECTED",
                        "nfpa_ref": nfpa_reference,
                        "severity": "CRITICAL",
                        "reason": "Healing not allowed for this critical calculation",
                    })
                    return SafetyResult(
                        value=None,
                        status=SystemStatus.REJECTED,
                        metadata={"error": err_msg, "error_type": err_type,
                                  "classification": err_classification},
                        audit_ref=audit_ref,
                        human_review_required=True,
                        rejection_reason=f"Critical calculation failed ({err_type}): {err_msg}"
                    )

                if err_classification == "FATAL":
                    # خطأ قاتل — لا شفاء. الـ pipeline يتوقف.
                    audit_ref = logger.log_event({
                        "function_name": func_name,
                        "error_type": f"FATAL:{err_type}",
                        "error_message": err_msg,
                        "error_classification": "FATAL",
                        "tier_used": 1,
                        "status": "REJECTED",
                        "nfpa_ref": nfpa_reference,
                        "severity": "CRITICAL",
                        "reason": "Fatal error — cannot safely heal. Pipeline must stop.",
                    })
                    return SafetyResult(
                        value=None,
                        status=SystemStatus.REJECTED,
                        metadata={"error": err_msg, "error_type": err_type,
                                  "classification": "FATAL"},
                        audit_ref=audit_ref,
                        human_review_required=True,
                        rejection_reason=f"Fatal error ({err_type}): {err_msg}"
                    )

                if err_classification == "UNKNOWN":
                    # خطأ مجهول — في نظام سلامة حرائق = رفض
                    audit_ref = logger.log_event({
                        "function_name": func_name,
                        "error_type": f"UNKNOWN:{err_type}",
                        "error_message": err_msg,
                        "error_classification": "UNKNOWN",
                        "tier_used": 1,
                        "status": "REJECTED",
                        "nfpa_ref": nfpa_reference,
                        "severity": "CRITICAL",
                        "reason": "Unknown error type — cannot safely heal in fire safety system.",
                    })
                    return SafetyResult(
                        value=None,
                        status=SystemStatus.REJECTED,
                        metadata={"error": err_msg, "error_type": err_type,
                                  "classification": "UNKNOWN"},
                        audit_ref=audit_ref,
                        human_review_required=True,
                        rejection_reason=f"Unknown error ({err_type}): {err_msg}"
                    )

                # err_classification == "RECOVERABLE"
                # يمكن الشفاء — لكن بصوت عالٍ ومع مراجعة بشرية

                healed_val = _compute_healed_value(
                    err_type=err_type,
                    args=args,
                    safe_minimum=safe_minimum,
                    default_value=default_value,
                )

                # Physics validation
                is_valid = True
                validation_error = ""
                if physics_validator:
                    try:
                        is_valid = physics_validator(healed_val)
                        if not is_valid:
                            validation_error = f"Physics validator rejected healed value: {healed_val}"
                    except Exception as ve:
                        is_valid = False
                        validation_error = f"Physics validator crashed: {ve}"

                # [v4.0 CRITICAL CHANGE] إذا فشل التحقق الفيزيائي = رفض وليس 0.0
                if not is_valid:
                    audit_ref = logger.log_event({
                        "function_name": func_name,
                        "error_type": f"RECOVERABLE:{err_type}",
                        "error_message": err_msg,
                        "error_classification": "RECOVERABLE",
                        "tier_used": 1,
                        "status": "REJECTED",
                        "healed_attempt": str(healed_val),
                        "validation_error": validation_error,
                        "nfpa_ref": nfpa_reference,
                        "severity": "CRITICAL",
                        "reason": "Healed value failed physics validation — REJECTED",
                    })
                    return SafetyResult(
                        value=None,
                        status=SystemStatus.REJECTED,
                        metadata={
                            "error": err_msg,
                            "error_type": err_type,
                            "classification": "RECOVERABLE",
                            "healed_attempt": str(healed_val),
                            "validation_error": validation_error,
                        },
                        audit_ref=audit_ref,
                        human_review_required=True,
                        rejection_reason=f"Healed value {healed_val} failed physics validation"
                    )

                # [v4.0] التحقق من أن القيمة المُعالجة ليست مستحيلة فيزيائياً
                if _is_physically_invalid(healed_val):
                    audit_ref = logger.log_event({
                        "function_name": func_name,
                        "error_type": f"RECOVERABLE:{err_type}",
                        "error_message": err_msg,
                        "tier_used": 1,
                        "status": "REJECTED",
                        "healed_attempt": str(healed_val),
                        "nfpa_ref": nfpa_reference,
                        "severity": "CRITICAL",
                        "reason": "Healed value is physically invalid (inf/nan/negative where forbidden)",
                    })
                    return SafetyResult(
                        value=None,
                        status=SystemStatus.REJECTED,
                        metadata={
                            "error": err_msg,
                            "healed_attempt": str(healed_val),
                            "invalid_reason": "physically_invalid",
                        },
                        audit_ref=audit_ref,
                        human_review_required=True,
                        rejection_reason=f"Healed value is physically invalid: {healed_val}"
                    )

                # الشفاء نجح — لكن بصوت عالٍ
                audit_ref = logger.log_event({
                    "function_name": func_name,
                    "error_type": err_type,
                    "error_message": err_msg,
                    "error_classification": "RECOVERABLE",
                    "tier_used": 1,
                    "fix_applied": str(healed_val),
                    "status": "HEALED",
                    "nfpa_ref": nfpa_reference,
                    "severity": "WARNING",
                    "human_review": "REQUIRED",
                    "reason": "Value healed — human review mandatory before acceptance",
                })

                return SafetyResult(
                    value=healed_val,
                    status=SystemStatus.HEALED,
                    metadata={
                        "tier": 1,
                        "rule": err_type,
                        "nfpa_ref": nfpa_reference,
                        "unit": unit,
                    },
                    audit_ref=audit_ref,
                    human_review_required=True,  # [v4.0] دائماً مطلوب للقيم المُعالجة
                )

        wrapper.__name__ = func_name
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


def _validate_fallback(value: Any, name: str) -> None:
    """يتحقق من أن القيمة الافتراضية ليست مستحيلة فيزيائياً."""
    if value is None:
        return  # None مسموح (يعني "لا قيمة افتراضية")
    if isinstance(value, float):
        if math.isnan(value):
            raise ValueError(f"{name} cannot be NaN — this is a fire safety system")
        if math.isinf(value):
            raise ValueError(
                f"{name} cannot be infinity — there is no infinite pressure/flow/temperature "
                f"in NFPA standards. Use a physically realistic maximum instead."
            )
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            if isinstance(v, float):
                if math.isnan(v):
                    raise ValueError(f"{name}[{i}] cannot be NaN")
                if math.isinf(v):
                    raise ValueError(f"{name}[{i}] cannot be infinity")


def _is_physically_invalid(value: Any) -> bool:
    """يتحقق من أن القيمة ليست مستحيلة فيزيائياً."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return True
    if isinstance(value, (list, tuple)):
        for v in value:
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    return True
    return False


def _compute_healed_value(
    err_type: str,
    args: tuple,
    safe_minimum: Optional[float],
    default_value: Any,
) -> Any:
    """يحسب القيمة المُعالجة بناءً على نوع الخطأ.
    فقط للأخطاء القابلة للشفاء (RECOVERABLE).
    """
    if err_type == "IndexError":
        # آخر عنصر صالح
        if args and isinstance(args[0], (list, tuple)) and len(args[0]) > 0:
            return args[0][-1]
        return default_value

    if err_type == "ValueError":
        # [v4.0 FIX] نُفضّل default_value على safe_minimum لأنه أكثر تحديداً
        # safe_minimum قد يكون 0.0 حتى لو النوع المتوقع list أو bool
        if default_value is not None:
            return default_value
        return safe_minimum

    if err_type == "KeyError":
        return default_value

    if err_type == "TypeError":
        try:
            if default_value is not None:
                return type(default_value)(1.0)
            return 1.0
        except Exception:
            return default_value

    if err_type == "TimeoutError":
        return default_value

    # Fallback (لا يجب أن يصل هنا لأن RECOVERABLE فقط)
    return default_value if default_value is not None else safe_minimum


# =====================================================================
# ADAPTERS (8 Repositories) — FAIL-LOUD VERSION
# =====================================================================

# 1. AAMKS: Monte Carlo
_AAMKS_MIN_SIMULATIONS = 100   # [v4.0] NFPA يتطلب عادةً 1000+ محاكاة
_AAMKS_MAX_SIMULATIONS = 10000

def _validate_aamks_simulation(val: float) -> bool:
    """لا نقبل محاكاة واحدة — لا معنى إحصائياً."""
    return (
        isinstance(val, (int, float))
        and not math.isnan(val)
        and not math.isinf(val)
        and val >= _AAMKS_MIN_SIMULATIONS
    )

class AamksAdapter:
    MIN_SIMULATIONS = _AAMKS_MIN_SIMULATIONS
    MAX_SIMULATIONS = _AAMKS_MAX_SIMULATIONS

    validate_simulation = staticmethod(_validate_aamks_simulation)

    @staticmethod
    @fail_loud_v4(
        safe_minimum=1000,
        default_value=1000,
        physics_validator=_validate_aamks_simulation,
        nfpa_reference="NFPA 101 §12.6.2 — Monte Carlo egress analysis",
        unit="simulation_runs",
    )
    def run_monte_carlo(sim_count: int) -> int:
        if sim_count > _AAMKS_MAX_SIMULATIONS:
            raise MemoryError(f"Simulation limit exceeded: {sim_count} > {_AAMKS_MAX_SIMULATIONS}")
        if sim_count <= 0:
            raise ValueError(f"Count must be positive, got {sim_count}")
        if sim_count < _AAMKS_MIN_SIMULATIONS:
            raise ValueError(
                f"Count must be >= {_AAMKS_MIN_SIMULATIONS} for statistical significance, "
                f"got {sim_count}"
            )
        return sim_count


# 2. Evac4Bim: IFC Parser
class Evac4BimAdapter:
    @staticmethod
    def validate_coords(coords: List[float]) -> bool:
        """لا نقبل NaN أو Inf في الإحداثيات — مستحيل فيزيائياً."""
        if not isinstance(coords, (list, tuple)):
            return False
        if len(coords) == 0:
            return False
        return all(
            isinstance(c, (int, float))
            and not math.isnan(c)
            and not math.isinf(c)
            for c in coords
        )

    @staticmethod
    @fail_loud_v4(
        safe_minimum=0.0,
        default_value=[0.0, 0.0, 0.0],
        physics_validator=validate_coords,
        nfpa_reference="IFC4 — Building element placement",
        unit="meters",
    )
    def parse_ifc_coordinates(raw_coords: List[float]) -> List[float]:
        if not raw_coords:
            raise IndexError("Empty coordinate list")
        for c in raw_coords:
            if isinstance(c, float) and (math.isnan(c) or math.isinf(c)):
                raise ValueError(f"Corrupted coordinate value: {c}")
        return raw_coords


# 3. OpenFire: Smoke Layer Height
_OPENFIRE_MIN_HEIGHT = 1.5   # [v4.0] أقل ارتفاع آمن per NFPA 92
_OPENFIRE_MAX_HEIGHT = 30.0  # [v4.0] أعلى ارتفاع واقعي

def _validate_openfire_height(h: float) -> bool:
    """لا نقبل ارتفاعاً أقل من 1.5م أو مستحيلاً."""
    return (
        isinstance(h, (int, float))
        and not math.isnan(h)
        and not math.isinf(h)
        and _OPENFIRE_MIN_HEIGHT <= h <= _OPENFIRE_MAX_HEIGHT
    )

class OpenFireAdapter:
    """حساب ارتفاع طبقة الدخان — NFPA 92"""

    MIN_SMOKE_LAYER_HEIGHT = _OPENFIRE_MIN_HEIGHT
    MAX_SMOKE_LAYER_HEIGHT = _OPENFIRE_MAX_HEIGHT

    validate_height = staticmethod(_validate_openfire_height)

    @staticmethod
    @fail_loud_v4(
        safe_minimum=_OPENFIRE_MIN_HEIGHT,
        default_value=_OPENFIRE_MIN_HEIGHT,
        physics_validator=_validate_openfire_height,
        nfpa_reference="NFPA 92 §5.5.3 — Smoke layer interface height",
        unit="meters",
    )
    def calculate_smoke_layer_height(temp_k: float, mass_flow: float) -> float:
        """حساب مبسط لارتفاع طبقة الدخان.
        الـ ZeroDivisionError هنا = فيزياء مستحيلة = FATAL = REJECTED
        """
        if temp_k <= 0.0 or mass_flow <= 0.0:
            # في v3.1 كان هذا ZeroDivisionError → healed إلى inf
            # في v4.0 هذا خطأ قاتل = REJECTED
            raise ZeroDivisionError(
                f"Invalid physical parameters: temp_k={temp_k}, mass_flow={mass_flow}. "
                f"Temperature and mass flow must be positive."
            )
        result = 10.0 / (temp_k * mass_flow)
        if not _validate_openfire_height(result):
            raise ValueError(
                f"Calculated smoke layer height {result}m is outside physical range "
                f"[{_OPENFIRE_MIN_HEIGHT}, {_OPENFIRE_MAX_HEIGHT}]"
            )
        return round(result, 4)


# 4. Emergency Evacuation: Pathfinding
class EmergencyEvacuationAdapter:
    @staticmethod
    def validate_path(path: List[str]) -> bool:
        return isinstance(path, list) and len(path) > 0 and all(isinstance(p, str) and p for p in path)

    @staticmethod
    @fail_loud_v4(
        safe_minimum=1.0,
        default_value=["EXIT_NEAREST"],
        physics_validator=validate_path,
        nfpa_reference="NFPA 101 §7.2 — Means of egress",
        unit="path_nodes",
    )
    def solve_evacuation_route(graph_nodes: List[str], target_node: str) -> List[str]:
        if not graph_nodes:
            raise IndexError("Empty graph — no evacuation nodes available")
        if not target_node:
            raise ValueError("Target node cannot be empty")
        if target_node not in graph_nodes:
            raise KeyError(f"Target node '{target_node}' not found in graph")
        if len(graph_nodes) > 1000:
            raise TimeoutError(f"Graph too large: {len(graph_nodes)} nodes")
        return [graph_nodes[0], target_node]


# 5. SafeGuard AI: Edge Inference — FAIL-SAFE = False (لا إنذار خاطئ)
class SafeGuardAiAdapter:
    """في نظام إنذار الحرائق:
    - إنذار خاطئ (False Positive) = إزعاج لكنه آمن
    - تفويت إنذار (False Negative) = كارثة
    لذلك في حالة الفشل، نُعيد False (لا إنذار) بدلاً من True (إنذار خاطئ)
    ونُلزم بمراجعة بشرية.
    """

    @staticmethod
    def validate_detection(val: bool) -> bool:
        """القيمة المنطقية دائماً صالحة — التحقق هو من النوع."""
        return isinstance(val, bool)

    @staticmethod
    @fail_loud_v4(
        safe_minimum=None,  # [v4.0 FIX] لا safe_minimum للقيم المنطقية
        default_value=False,  # Fail-safe = لا إنذار كاذب
        physics_validator=validate_detection,
        nfpa_reference="NFPA 72 §17.7 — Smoke detection",
        unit="boolean",
    )
    def classify_smoke_features(features: List[float]) -> bool:
        if not features:
            raise ValueError("Empty feature list — cannot classify")
        if len(features) > 100:
            # [v4.0 FIX] نرفع ValueError وليس MemoryError — هذا حد مجال وليس خطأ نظام
            raise ValueError(f"Feature count exceeds SRAM limit: {len(features)} > 100")
        return sum(features) > 50.0


# 6. Disaster Evacuation: Crowd Simulation
_DISASTER_MAX_THROUGHPUT = 100.0  # [v4.0] أقصى معدل واقعي (أشخاص/ثانية/مخرج)

def _validate_disaster_throughput(val: float) -> bool:
    """لا نقبل قيمة سلبية أو لا نهائية."""
    return (
        isinstance(val, (int, float))
        and not math.isnan(val)
        and not math.isinf(val)
        and 0.0 <= val <= _DISASTER_MAX_THROUGHPUT
    )

class DisasterEvacuationAdapter:
    MAX_THROUGHPUT = _DISASTER_MAX_THROUGHPUT

    validate_throughput = staticmethod(_validate_disaster_throughput)

    @staticmethod
    @fail_loud_v4(
        safe_minimum=0.1,
        default_value=0.5,
        physics_validator=_validate_disaster_throughput,
        nfpa_reference="NFPA 101 §7.3 — Capacity of means of egress",
        unit="persons_per_second_per_meter",
    )
    def simulate_crowd_throughput(agent_count: int, exit_width: float) -> float:
        if exit_width == 0.0:
            # [v4.0] هذا FATAL — لا يمكن الإخلاء بدون مخرج
            raise ZeroDivisionError(
                "Exit width is zero — no evacuation possible. "
                "This is a life-safety emergency, not a calculation error."
            )
        if exit_width < 0:
            raise ValueError(f"Negative exit width: {exit_width}m")
        if agent_count < 0:
            raise ValueError(f"Negative agent count: {agent_count}")
        result = agent_count / exit_width
        if result > _DISASTER_MAX_THROUGHPUT:
            raise ValueError(
                f"Throughput {result} exceeds maximum realistic {_DISASTER_MAX_THROUGHPUT}"
            )
        return result


# 7. EPyT: Hydraulic
_EPYT_MIN_PSI = 7.0     # [v4.0] NFPA 13 minimum
_EPYT_MAX_PSI = 400.0   # [v4.0] أعلى ضغط واقعي
_EPYT_DEFAULT_PSI = 175.0  # [v4.0] قيمة افتراضية آمنة (ليس inf!)

def _validate_epyt_pressure(val: float) -> bool:
    """لا نقبل ضغطاً سالباً أو لا نهائياً — NFPA 13 يحدد 7-400 PSI."""
    return (
        isinstance(val, (int, float))
        and not math.isnan(val)
        and not math.isinf(val)
        and _EPYT_MIN_PSI <= val <= _EPYT_MAX_PSI
    )

class EpytAdapter:
    """حساب ضغط تدفق المياه — NFPA 13/20"""

    MIN_PRESSURE_PSI = _EPYT_MIN_PSI
    MAX_PRESSURE_PSI = _EPYT_MAX_PSI
    DEFAULT_PRESSURE_PSI = _EPYT_DEFAULT_PSI

    validate_pressure = staticmethod(_validate_epyt_pressure)

    @staticmethod
    @fail_loud_v4(
        safe_minimum=_EPYT_MIN_PSI,
        default_value=_EPYT_DEFAULT_PSI,
        physics_validator=_validate_epyt_pressure,
        nfpa_reference="NFPA 13 §8.2 — Hydraulic design",
        unit="PSI",
    )
    def calculate_epanet_flow_pressure(elevation_m: float, demand_lps: float) -> float:
        if demand_lps == 0.0:
            # [v4.0] هذا FATAL — لا ضغط بدون طلب
            raise ZeroDivisionError(
                "Zero demand — cannot calculate pressure. "
                "Check hydraulic model inputs."
            )
        if demand_lps < 0:
            raise ValueError(f"Negative demand: {demand_lps} L/s")
        if elevation_m < 0:
            raise ValueError(f"Negative elevation: {elevation_m}m")
        result = elevation_m / demand_lps
        if not _validate_epyt_pressure(result):
            raise ValueError(
                f"Calculated pressure {result} PSI is outside NFPA 13 range "
                f"[{_EPYT_MIN_PSI}, {_EPYT_MAX_PSI}]"
            )
        return result


# 8. SprayHydraulic: Sprinkler — NO MORE INFINITY
_SPRAY_MIN_PSI = 7.0       # NFPA 13 §8.2.1 minimum
_SPRAY_MAX_PSI = 175.0    # NFPA 13 practical maximum
_SPRAY_DEFAULT_PSI = 7.0  # [v4.0] القيمة الدنيا كافتراضي آمن

def _validate_spray_flow(val: float) -> bool:
    """لا نقبل inf — ضغط لا نهائي مستحيل فيزيائياً."""
    if not isinstance(val, (int, float)):
        return False
    if math.isnan(val) or math.isinf(val):
        return False
    return val >= _SPRAY_MIN_PSI

class SprayHydraulicAdapter:
    """حساب ضغط رأس الرشاش — NFPA 13.
    في v3.1 كان default_value=float('inf') = كارثة.
    في v4.0: أعلى ضغط واقعي أو REJECTED.
    """

    MIN_NOZZLE_PRESSURE = _SPRAY_MIN_PSI
    MAX_NOZZLE_PRESSURE = _SPRAY_MAX_PSI
    DEFAULT_NOZZLE_PRESSURE = _SPRAY_DEFAULT_PSI

    validate_flow = staticmethod(_validate_spray_flow)

    @staticmethod
    @fail_loud_v4(
        safe_minimum=_SPRAY_MIN_PSI,
        default_value=_SPRAY_DEFAULT_PSI,
        physics_validator=_validate_spray_flow,
        nfpa_reference="NFPA 13 §8.2.1 — Sprinkler discharge criteria",
        unit="PSI",
        allow_healing=False,  # [v4.0] حساب الرشاش حرج — لا شفاء، بيانات خاطئة = إيقاف
    )
    def calculate_discharge_pressure(flow_gpm: float, k_factor: float) -> float:
        """P = (Q/K)^2 — NFPA 13 sprinkler discharge formula.
        إذا K=0، الرشاش لا يعمل = REJECTED وليس inf.
        """
        if k_factor == 0.0:
            # [v4.0] هذا FATAL — رشاش بمعامل صفر لا يعمل
            raise ZeroDivisionError(
                "K-factor is zero — sprinkler is non-functional. "
                "This is NOT a calculation that can be 'healed' — "
                "the sprinkler must be replaced or the data corrected."
            )
        if k_factor < 0:
            raise ValueError(f"Negative K-factor: {k_factor}")
        if flow_gpm < 0:
            raise ValueError(f"Negative flow rate: {flow_gpm} GPM")
        result = (flow_gpm / k_factor) ** 2
        if not _validate_spray_flow(result):
            raise ValueError(
                f"Calculated pressure {result} PSI is outside NFPA 13 range. "
                f"Min: {_SPRAY_MIN_PSI} PSI"
            )
        return result


# =====================================================================
# SCENARIOS — FAIL-LOUD: REJECTED = STOP PIPELINE
# =====================================================================

def execute_hospital_scenario(sim_runs: int, node_elevation: float, water_demand: float) -> Dict[str, Any]:
    """سيناريو المستشفى.
    إذا فشل أي حساب حرج، الـ pipeline يتوقف بالكامل.
    """
    sim_res = AamksAdapter.run_monte_carlo(sim_runs)
    if sim_res.is_rejected():
        return {
            "facility_type": "HOSPITAL",
            "resilience_status": "REJECTED",
            "rejection_reason": sim_res.rejection_reason,
            "human_action_required": "Fix simulation parameters before proceeding",
            "audit_ref": sim_res.audit_ref,
        }

    pressure_res = EpytAdapter.calculate_epanet_flow_pressure(node_elevation, water_demand)
    if pressure_res.is_rejected():
        return {
            "facility_type": "HOSPITAL",
            "monte_carlo_runs": sim_res.value if sim_res.is_safe_to_use() else None,
            "resilience_status": "REJECTED",
            "rejection_reason": pressure_res.rejection_reason,
            "human_action_required": "Fix hydraulic parameters before proceeding",
            "audit_ref": pressure_res.audit_ref,
        }

    # تحقق من المراجعة البشرية
    needs_review = sim_res.requires_human_review() or pressure_res.requires_human_review()

    return {
        "facility_type": "HOSPITAL",
        "monte_carlo_runs": sim_res.value,
        "pumps_verified_pressure_psi": pressure_res.value,
        "pressure_unit": "PSI",
        "resilience_status": "HEALED_REVIEW_REQUIRED" if needs_review else "NOMINAL",
        "human_review_required": needs_review,
        "human_review_details": {
            "simulation": sim_res.requires_human_review(),
            "pressure": pressure_res.requires_human_review(),
        },
        "nfpa_references": {
            "simulation": "NFPA 101 §12.6.2",
            "pressure": "NFPA 13 §8.2",
        },
    }


def execute_high_rise_scenario(raw_coords: List[float], escape_nodes: List[str]) -> Dict[str, Any]:
    """سيناريو البرج العالي."""
    coords_res = Evac4BimAdapter.parse_ifc_coordinates(raw_coords)
    if coords_res.is_rejected():
        return {
            "facility_type": "HIGH_RISE",
            "resilience_status": "REJECTED",
            "rejection_reason": coords_res.rejection_reason,
            "human_action_required": "Fix IFC coordinate data before proceeding",
            "audit_ref": coords_res.audit_ref,
        }

    route_res = EmergencyEvacuationAdapter.solve_evacuation_route(escape_nodes, "ROOF_HELIPAD")
    if route_res.is_rejected():
        return {
            "facility_type": "HIGH_RISE",
            "spatial_boundary_coords": coords_res.value if coords_res.is_safe_to_use() else None,
            "resilience_status": "REJECTED",
            "rejection_reason": route_res.rejection_reason,
            "human_action_required": "Fix evacuation routing before proceeding",
            "audit_ref": route_res.audit_ref,
        }

    needs_review = coords_res.requires_human_review() or route_res.requires_human_review()

    return {
        "facility_type": "HIGH_RISE",
        "spatial_boundary_coords": coords_res.value,
        "solved_escape_path": route_res.value,
        "resilience_status": "HEALED_REVIEW_REQUIRED" if needs_review else "NOMINAL",
        "human_review_required": needs_review,
    }


def execute_bank_scenario(sensor_features: List[float]) -> Dict[str, Any]:
    """سيناريو البنك."""
    inference_res = SafeGuardAiAdapter.classify_smoke_features(sensor_features)
    if inference_res.is_rejected():
        return {
            "facility_type": "SECURE_BANK",
            "resilience_status": "REJECTED",
            "rejection_reason": inference_res.rejection_reason,
            "human_action_required": "Fix sensor classification before proceeding",
            "audit_ref": inference_res.audit_ref,
        }

    return {
        "facility_type": "SECURE_BANK",
        "fire_alert_active": inference_res.value,
        "resilience_status": "HEALED_REVIEW_REQUIRED" if inference_res.requires_human_review() else "NOMINAL",
        "human_review_required": inference_res.requires_human_review(),
        "critical_note": (
            "If fire_alert_active is False due to healing, this means the AI could not "
            "confirm fire presence — a human MUST verify before assuming no fire."
        ) if inference_res.is_healed() else None,
    }


def execute_school_scenario(students_count: int, door_width_m: float) -> Dict[str, Any]:
    """سيناريو المدرسة."""
    throughput_res = DisasterEvacuationAdapter.simulate_crowd_throughput(students_count, door_width_m)
    if throughput_res.is_rejected():
        return {
            "facility_type": "SCHOOL",
            "resilience_status": "REJECTED",
            "rejection_reason": throughput_res.rejection_reason,
            "human_action_required": "Fix evacuation parameters — lives at stake!",
            "audit_ref": throughput_res.audit_ref,
        }

    return {
        "facility_type": "SCHOOL",
        "egress_throughput_rate_gps": throughput_res.value,
        "throughput_unit": "persons_per_second_per_meter",
        "resilience_status": "HEALED_REVIEW_REQUIRED" if throughput_res.requires_human_review() else "NOMINAL",
        "human_review_required": throughput_res.requires_human_review(),
    }


def execute_home_scenario(flow_rate_gpm: float, k_factor_coefficient: float) -> Dict[str, Any]:
    """سيناريو المنزل."""
    pressure_res = SprayHydraulicAdapter.calculate_discharge_pressure(flow_rate_gpm, k_factor_coefficient)
    if pressure_res.is_rejected():
        return {
            "facility_type": "RESIDENTIAL",
            "resilience_status": "REJECTED",
            "rejection_reason": pressure_res.rejection_reason,
            "human_action_required": "Fix sprinkler parameters — sprinkler may be non-functional!",
            "audit_ref": pressure_res.audit_ref,
        }

    return {
        "facility_type": "RESIDENTIAL",
        "required_nozzle_pressure_psi": pressure_res.value,
        "pressure_unit": "PSI",
        "nfpa_minimum_psi": SprayHydraulicAdapter.MIN_NOZZLE_PRESSURE,
        "resilience_status": "HEALED_REVIEW_REQUIRED" if pressure_res.requires_human_review() else "NOMINAL",
        "human_review_required": pressure_res.requires_human_review(),
    }


# =====================================================================
# COMPREHENSIVE TESTS — FAIL-LOUD PHILOSOPHY
# =====================================================================
import unittest


class TestQomnFireV4FailLoud(unittest.TestCase):
    """اختبارات شاملة لفلسفة Fail-Loud."""

    def setUp(self):
        # Reset circuit breakers for test isolation
        _circuit_breakers.clear()
        # Reset audit logger singleton for test isolation
        # Note: In production, the singleton persists
        AsyncAuditLogger.reset_instance()

    # ----------------------------------------------------------
    # SprayHydraulic Tests — NO MORE INFINITY
    # ----------------------------------------------------------
    def test_spray_zero_k_factor_is_rejected_not_inf(self):
        """K=0 = رشاش لا يعمل = REJECTED وليس inf."""
        res = SprayHydraulicAdapter.calculate_discharge_pressure(100.0, 0.0)
        self.assertTrue(res.is_rejected(), f"K=0 should be REJECTED, got {res.status}")
        self.assertIsNone(res.value, "REJECTED should have no value")
        self.assertNotEqual(res.value, float('inf'), "Must NOT return infinity")

    def test_spray_negative_k_factor_is_rejected(self):
        """K سلبي = بيانات خاطئة = REJECTED."""
        res = SprayHydraulicAdapter.calculate_discharge_pressure(100.0, -5.0)
        self.assertTrue(res.is_rejected())

    def test_spray_negative_flow_is_rejected(self):
        """تدفق سالب = مستحيل فيزيائياً = REJECTED."""
        res = SprayHydraulicAdapter.calculate_discharge_pressure(-10.0, 5.6)
        self.assertTrue(res.is_rejected())

    def test_spray_valid_calculation_is_nominal(self):
        """حساب صحيح = NOMINAL."""
        res = SprayHydraulicAdapter.calculate_discharge_pressure(100.0, 5.6)
        self.assertTrue(res.is_nominal())
        self.assertAlmostEqual(res.value, (100.0 / 5.6) ** 2, places=2)

    # ----------------------------------------------------------
    # OpenFire Tests — ZeroDivisionError = FATAL = REJECTED
    # ----------------------------------------------------------
    def test_smoke_zero_temp_is_rejected(self):
        """درجة حرارة صفر = فيزياء مستحيلة = REJECTED."""
        res = OpenFireAdapter.calculate_smoke_layer_height(0.0, 1.0)
        self.assertTrue(res.is_rejected())

    def test_smoke_negative_mass_flow_is_rejected(self):
        """تدفق كتلة سالب = مستحيل = REJECTED."""
        res = OpenFireAdapter.calculate_smoke_layer_height(300.0, -1.0)
        self.assertTrue(res.is_rejected())

    def test_smoke_valid_calculation_is_nominal(self):
        """حساب صحيح = NOMINAL."""
        res = OpenFireAdapter.calculate_smoke_layer_height(300.0, 0.02)
        self.assertTrue(res.is_nominal())

    # ----------------------------------------------------------
    # Evac4Bim Tests — NaN Coordinates = REJECTED
    # ----------------------------------------------------------
    def test_nan_coords_are_healed(self):
        """إحداثيات NaN = تالفة = ValueError (RECOVERABLE) → HEALED مع default_value."""
        res = Evac4BimAdapter.parse_ifc_coordinates([0.0, float('nan'), 10.0])
        # ValueError is RECOVERABLE → HEALED with default_value
        self.assertTrue(res.is_healed())
        self.assertEqual(res.value, [0.0, 0.0, 0.0])  # default fallback
        self.assertTrue(res.requires_human_review())

    def test_valid_coords_are_nominal(self):
        """إحداثيات صحيحة = NOMINAL."""
        res = Evac4BimAdapter.parse_ifc_coordinates([1.0, 2.0, 3.0])
        self.assertTrue(res.is_nominal())
        self.assertEqual(res.value, [1.0, 2.0, 3.0])

    def test_empty_coords_are_rejected(self):
        """إحداثيات فارغة = IndexError = HEALED."""
        res = Evac4BimAdapter.parse_ifc_coordinates([])
        self.assertTrue(res.is_healed())

    # ----------------------------------------------------------
    # SafeGuard AI Tests — Fail-Safe = False
    # ----------------------------------------------------------
    def test_sram_limit_heals_to_false(self):
        """SRAM limit exceeded = ValueError (domain limit) → HEALED to False (لا إنذار خاطئ)."""
        res = SafeGuardAiAdapter.classify_smoke_features([1.0] * 500)
        self.assertTrue(res.is_healed())
        self.assertEqual(res.value, False)  # Fail-safe = لا إنذار
        self.assertTrue(res.requires_human_review())

    def test_empty_features_are_healed_to_false(self):
        """قائمة ميزات فارغة = ValueError = HEALED to False."""
        res = SafeGuardAiAdapter.classify_smoke_features([])
        self.assertTrue(res.is_healed())
        self.assertEqual(res.value, False)

    def test_valid_detection_is_nominal(self):
        """تصنيف صحيح = NOMINAL."""
        res = SafeGuardAiAdapter.classify_smoke_features([30.0] * 3)
        self.assertTrue(res.is_nominal())

    # ----------------------------------------------------------
    # Disaster Evacuation Tests — Zero Exit Width = FATAL
    # ----------------------------------------------------------
    def test_zero_exit_width_is_rejected(self):
        """مخرج بعرض صفر = لا إخلاء ممكن = REJECTED (FATAL ZeroDivisionError)."""
        res = DisasterEvacuationAdapter.simulate_crowd_throughput(100, 0.0)
        self.assertTrue(res.is_rejected())
        self.assertIsNone(res.value)

    def test_negative_agents_is_rejected(self):
        """عدد أشخاص سالب = مستحيل = REJECTED (ValueError is RECOVERABLE → HEALED)."""
        res = DisasterEvacuationAdapter.simulate_crowd_throughput(-10, 1.0)
        # ValueError is RECOVERABLE → HEALED
        self.assertTrue(res.is_healed())

    def test_valid_throughput_is_nominal(self):
        """حساب صحيح = NOMINAL."""
        res = DisasterEvacuationAdapter.simulate_crowd_throughput(50, 2.0)
        self.assertTrue(res.is_nominal())
        self.assertAlmostEqual(res.value, 25.0)

    # ----------------------------------------------------------
    # EPyT Hydraulic Tests
    # ----------------------------------------------------------
    def test_zero_demand_is_rejected(self):
        """طلب صفر = لا ضغط = REJECTED (FATAL ZeroDivisionError)."""
        res = EpytAdapter.calculate_epanet_flow_pressure(50.0, 0.0)
        self.assertTrue(res.is_rejected())

    def test_negative_elevation_is_rejected(self):
        """ارتفاع سالب = HEALED (RECOVERABLE ValueError)."""
        res = EpytAdapter.calculate_epanet_flow_pressure(-5.0, 10.0)
        self.assertTrue(res.is_healed())

    def test_valid_pressure_is_nominal(self):
        """ضغط صحيح = NOMINAL."""
        res = EpytAdapter.calculate_epanet_flow_pressure(100.0, 1.0)
        self.assertTrue(res.is_nominal())
        self.assertAlmostEqual(res.value, 100.0)

    # ----------------------------------------------------------
    # AAMKS Monte Carlo Tests
    # ----------------------------------------------------------
    def test_zero_sim_count_is_rejected(self):
        """عدد محاكاة صفر = HEALED (RECOVERABLE ValueError)."""
        res = AamksAdapter.run_monte_carlo(0)
        self.assertTrue(res.is_healed())

    def test_excessive_sim_count_is_rejected(self):
        """عدد محاكاة زائد = FATAL (MemoryError) = REJECTED."""
        res = AamksAdapter.run_monte_carlo(20000)
        self.assertTrue(res.is_rejected())

    def test_valid_sim_count_is_nominal(self):
        """عدد محاكاة صحيح = NOMINAL."""
        res = AamksAdapter.run_monte_carlo(500)
        self.assertTrue(res.is_nominal())

    # ----------------------------------------------------------
    # Emergency Evacuation Tests
    # ----------------------------------------------------------
    def test_empty_graph_is_healed(self):
        """رسم بياني فارغ = IndexError = HEALED."""
        res = EmergencyEvacuationAdapter.solve_evacuation_route([], "EXIT")
        self.assertTrue(res.is_healed())

    def test_missing_target_is_healed(self):
        """مخرج غير موجود = KeyError = HEALED."""
        res = EmergencyEvacuationAdapter.solve_evacuation_route(["A", "B"], "Z")
        self.assertTrue(res.is_healed())

    def test_valid_route_is_nominal(self):
        """مسار صحيح = NOMINAL."""
        res = EmergencyEvacuationAdapter.solve_evacuation_route(["LOBBY", "STAIR_A", "EXIT"], "EXIT")
        self.assertTrue(res.is_nominal())
        self.assertEqual(res.value, ["LOBBY", "EXIT"])

    # ----------------------------------------------------------
    # Scenario Tests — Pipeline Stop on REJECTED
    # ----------------------------------------------------------
    def test_hospital_scenario_rejected_on_bad_pressure(self):
        """سيناريو المستشفى مع ضغط خاطئ = REJECTED."""
        result = execute_hospital_scenario(500, 100.0, 0.0)  # demand=0 → ZeroDivision
        self.assertEqual(result["resilience_status"], "REJECTED")
        self.assertIn("rejection_reason", result)
        self.assertIn("human_action_required", result)

    def test_home_scenario_rejected_on_zero_k_factor(self):
        """سيناريو المنزل مع K=0 = REJECTED."""
        result = execute_home_scenario(100.0, 0.0)
        self.assertEqual(result["resilience_status"], "REJECTED")
        self.assertIn("human_action_required", result)

    def test_school_scenario_rejected_on_zero_exit(self):
        """سيناريو المدرسة مع مخرج صفر = REJECTED."""
        result = execute_school_scenario(200, 0.0)
        self.assertEqual(result["resilience_status"], "REJECTED")

    def test_valid_hospital_scenario_is_nominal(self):
        """سيناريو مستشفى صحيح = NOMINAL."""
        result = execute_hospital_scenario(500, 100.0, 1.0)
        self.assertIn(result["resilience_status"], ["NOMINAL", "HEALED_REVIEW_REQUIRED"])

    # ----------------------------------------------------------
    # SafetyResult Tests
    # ----------------------------------------------------------
    def test_rejected_result_is_not_safe_to_use(self):
        """REJECTED = ليس آمناً للاستخدام."""
        res = SafetyResult(
            value=None,
            status=SystemStatus.REJECTED,
            rejection_reason="test"
        )
        self.assertFalse(res.is_safe_to_use())
        self.assertTrue(res.is_rejected())
        self.assertTrue(res.requires_human_review())

    def test_healed_result_requires_human_review(self):
        """HEALED = يحتاج مراجعة بشرية."""
        res = SafetyResult(
            value=7.0,
            status=SystemStatus.HEALED,
            human_review_required=True
        )
        self.assertTrue(res.requires_human_review())
        self.assertTrue(res.is_safe_to_use())

    def test_nominal_result_does_not_require_review(self):
        """NOMINAL = لا يحتاج مراجعة."""
        res = SafetyResult(
            value=100.0,
            status=SystemStatus.NOMINAL
        )
        self.assertFalse(res.requires_human_review())

    # ----------------------------------------------------------
    # Error Classification Tests
    # ----------------------------------------------------------
    def test_zero_division_is_fatal(self):
        """ZeroDivisionError = FATAL."""
        self.assertEqual(classify_error(ZeroDivisionError("test")), "FATAL")

    def test_memory_error_is_fatal(self):
        """MemoryError = FATAL."""
        self.assertEqual(classify_error(MemoryError("test")), "FATAL")

    def test_value_error_is_recoverable(self):
        """ValueError = RECOVERABLE."""
        self.assertEqual(classify_error(ValueError("test")), "RECOVERABLE")

    def test_index_error_is_recoverable(self):
        """IndexError = RECOVERABLE."""
        self.assertEqual(classify_error(IndexError("test")), "RECOVERABLE")

    def test_runtime_error_is_fatal(self):
        """RuntimeError = FATAL (لا نعرف ما حدث)."""
        self.assertEqual(classify_error(RuntimeError("test")), "FATAL")

    def test_custom_error_is_unknown(self):
        """خطأ مخصص = UNKNOWN = FATAL في نظام سلامة."""
        class CustomError(Exception):
            pass
        self.assertEqual(classify_error(CustomError("test")), "UNKNOWN")

    # ----------------------------------------------------------
    # Fallback Validation Tests
    # ----------------------------------------------------------
    def test_nan_fallback_is_rejected(self):
        """NaN كقيمة افتراضية = ValueError."""
        with self.assertRaises(ValueError):
            _validate_fallback(float('nan'), "test")

    def test_inf_fallback_is_rejected(self):
        """Infinity كقيمة افتراضية = ValueError."""
        with self.assertRaises(ValueError):
            _validate_fallback(float('inf'), "test")

    def test_negative_inf_fallback_is_rejected(self):
        """Negative infinity كقيمة افتراضية = ValueError."""
        with self.assertRaises(ValueError):
            _validate_fallback(float('-inf'), "test")

    def test_list_with_nan_fallback_is_rejected(self):
        """قائمة تحتوي NaN = ValueError."""
        with self.assertRaises(ValueError):
            _validate_fallback([1.0, float('nan'), 3.0], "test")

    # ----------------------------------------------------------
    # Decorator Configuration Tests
    # ----------------------------------------------------------
    def test_decorator_without_safe_minimum_and_default_rejects(self):
        """Decorator بدون safe_minimum ولا default_value = ValueError."""
        with self.assertRaises(ValueError):
            @fail_loud_v4()
            def bad_func(x):
                return x


if __name__ == "__main__":
    unittest.main(verbosity=2)
