"""
Smart Error Handling for LangGraph Workflows
=============================================

FELSEFE: "Kör retry" değil, "akıllı hata yönetimi"
- Her hata tipini tanı
- Olası nedenleri analiz et
- Uygun çözümü otomatik dene
- Çözülemezse detaylı diagnostic ver

Hata Kategorileri:
1. AUTH_ERROR - Token expired, invalid credentials
2. RATE_LIMIT - API rate limit aşıldı
3. NETWORK_ERROR - Connection timeout, refused
4. DATA_ERROR - Empty response, invalid data
5. MCP_ERROR - MCP server specific errors
6. UNKNOWN_ERROR - Tanımlanamayan hatalar
"""

import asyncio
import functools
import re
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')


# =============================================================================
# ERROR CLASSIFICATION
# =============================================================================

class ErrorCategory(Enum):
    """Hata kategorileri - her kategorinin farklı çözüm stratejisi var."""
    AUTH_ERROR = "auth_error"           # Token/credential sorunları
    RATE_LIMIT = "rate_limit"           # API rate limit
    NETWORK_ERROR = "network_error"     # Connection sorunları
    DATA_ERROR = "data_error"           # Veri formatı sorunları
    MCP_ERROR = "mcp_error"             # MCP server sorunları
    CONFIG_ERROR = "config_error"       # Eksik config/env var
    UNKNOWN_ERROR = "unknown_error"     # Bilinmeyen


@dataclass
class ErrorDiagnosis:
    """Hata teşhisi sonucu."""
    category: ErrorCategory
    original_error: str
    probable_cause: str
    suggested_fix: str
    auto_fixable: bool
    retry_recommended: bool
    retry_delay: float  # Önerilen bekleme süresi
    max_retries: int    # Önerilen max retry


# Error pattern -> diagnosis mapping
ERROR_PATTERNS = [
    # AUTH ERRORS
    {
        "patterns": [
            r"token.*expired",
            r"invalid.*token",
            r"access.*denied",
            r"unauthorized",
            r"401",
            r"oauth.*error",
            r"authentication.*failed",
        ],
        "category": ErrorCategory.AUTH_ERROR,
        "probable_cause": "API token süresi dolmuş veya geçersiz",
        "suggested_fix": "Token yenileme gerekiyor",
        "auto_fixable": True,  # Token refresh denenebilir
        "retry_recommended": False,  # Token yenilemeden retry işe yaramaz
        "retry_delay": 0,
        "max_retries": 1,
    },
    # RATE LIMIT
    {
        "patterns": [
            r"rate.*limit",
            r"too.*many.*requests",
            r"429",
            r"quota.*exceeded",
            r"throttl",
        ],
        "category": ErrorCategory.RATE_LIMIT,
        "probable_cause": "API rate limit aşıldı",
        "suggested_fix": "Biraz bekleyip tekrar dene",
        "auto_fixable": True,
        "retry_recommended": True,
        "retry_delay": 60.0,  # 1 dakika bekle
        "max_retries": 3,
    },
    # NETWORK ERRORS
    {
        "patterns": [
            r"connection.*refused",
            r"connection.*reset",
            r"connection.*timeout",
            r"timeout",
            r"timed.*out",
            r"network.*unreachable",
            r"host.*not.*found",
            r"dns.*resolution",
            r"ECONNREFUSED",
            r"ETIMEDOUT",
        ],
        "category": ErrorCategory.NETWORK_ERROR,
        "probable_cause": "Network bağlantı sorunu veya servis erişilemez",
        "suggested_fix": "Bağlantı kontrolü yap, servisi kontrol et",
        "auto_fixable": True,
        "retry_recommended": True,
        "retry_delay": 5.0,
        "max_retries": 3,
    },
    # MCP ERRORS
    {
        "patterns": [
            r"mcp.*server.*not.*found",
            r"mcp.*tool.*call.*failed",
            r"mcp.*sdk.*not.*available",
            r"server\.py.*not.*found",
            r"no.*content.*in.*response",
        ],
        "category": ErrorCategory.MCP_ERROR,
        "probable_cause": "MCP server çalışmıyor veya bulunamıyor",
        "suggested_fix": "MCP server durumunu kontrol et",
        "auto_fixable": False,
        "retry_recommended": True,
        "retry_delay": 10.0,
        "max_retries": 2,
    },
    # DATA ERRORS
    {
        "patterns": [
            r"json.*decode",
            r"invalid.*json",
            r"unexpected.*token",
            r"parse.*error",
            r"malformed",
            r"empty.*response",
            r"no.*data",
        ],
        "category": ErrorCategory.DATA_ERROR,
        "probable_cause": "API yanıtı geçersiz veya boş",
        "suggested_fix": "API yanıt formatını kontrol et",
        "auto_fixable": False,
        "retry_recommended": True,
        "retry_delay": 2.0,
        "max_retries": 2,
    },
    # CONFIG ERRORS
    {
        "patterns": [
            r"env.*var.*not.*set",
            r"missing.*config",
            r"api.*key.*not.*found",
            r"database.*url.*not.*configured",
            r"credentials.*missing",
        ],
        "category": ErrorCategory.CONFIG_ERROR,
        "probable_cause": "Gerekli environment variable veya config eksik",
        "suggested_fix": ".env dosyasını kontrol et",
        "auto_fixable": False,
        "retry_recommended": False,
        "retry_delay": 0,
        "max_retries": 0,
    },
]


def diagnose_error(error_message: str) -> ErrorDiagnosis:
    """
    Hata mesajını analiz et ve teşhis döndür.

    Args:
        error_message: Hata mesajı string

    Returns:
        ErrorDiagnosis with category, cause, fix suggestion
    """
    error_lower = error_message.lower()

    for pattern_config in ERROR_PATTERNS:
        for pattern in pattern_config["patterns"]:
            if re.search(pattern, error_lower, re.IGNORECASE):
                return ErrorDiagnosis(
                    category=pattern_config["category"],
                    original_error=error_message,
                    probable_cause=pattern_config["probable_cause"],
                    suggested_fix=pattern_config["suggested_fix"],
                    auto_fixable=pattern_config["auto_fixable"],
                    retry_recommended=pattern_config["retry_recommended"],
                    retry_delay=pattern_config["retry_delay"],
                    max_retries=pattern_config["max_retries"],
                )

    # Unknown error
    return ErrorDiagnosis(
        category=ErrorCategory.UNKNOWN_ERROR,
        original_error=error_message,
        probable_cause="Bilinmeyen hata",
        suggested_fix="Log'ları incele, manuel müdahale gerekebilir",
        auto_fixable=False,
        retry_recommended=True,  # Bilinmeyen hatalarda retry dene
        retry_delay=5.0,
        max_retries=2,
    )


# =============================================================================
# AUTO-FIX STRATEGIES
# =============================================================================

class AutoFixStrategy:
    """
    Her hata kategorisi için otomatik düzeltme stratejileri.
    """

    @staticmethod
    async def fix_auth_error(source_name: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Auth hatası düzeltme - token refresh dene.

        Returns:
            (success, message)
        """
        logger.info("auto_fix_auth_attempting", source=source_name)

        # Meta Ads token refresh
        if source_name == "meta_ads":
            try:
                # Check if we have refresh capability
                meta_token = os.getenv("META_ACCESS_TOKEN")
                meta_app_id = os.getenv("META_APP_ID")
                meta_app_secret = os.getenv("META_APP_SECRET")

                if meta_token and meta_app_id and meta_app_secret:
                    import httpx
                    # Try to exchange for long-lived token
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            "https://graph.facebook.com/v21.0/oauth/access_token",
                            params={
                                "grant_type": "fb_exchange_token",
                                "client_id": meta_app_id,
                                "client_secret": meta_app_secret,
                                "fb_exchange_token": meta_token,
                            },
                            timeout=30.0
                        )
                        if response.status_code == 200:
                            data = response.json()
                            new_token = data.get("access_token")
                            if new_token:
                                # Token'ı environment'a set et (bu session için)
                                os.environ["META_ACCESS_TOKEN"] = new_token
                                logger.info("auto_fix_auth_success", source=source_name)
                                return True, "Meta token başarıyla yenilendi"
                        else:
                            logger.warning("auto_fix_auth_failed",
                                source=source_name,
                                status=response.status_code,
                                response=response.text[:200]
                            )
            except Exception as e:
                logger.error("auto_fix_auth_exception", source=source_name, error=str(e))

        # Google Ads - credential refresh genellikle otomatik yapılır
        if source_name == "google_ads":
            # Google Ads SDK genellikle otomatik refresh yapar
            # Burada sadece kontrol yapabiliriz
            return False, "Google Ads credential refresh SDK tarafından yapılmalı"

        return False, f"{source_name} için otomatik token refresh desteklenmiyor"

    @staticmethod
    async def fix_rate_limit(source_name: str, diagnosis: ErrorDiagnosis) -> Tuple[bool, float]:
        """
        Rate limit hatası - bekle ve tekrar dene.

        Returns:
            (should_retry, wait_seconds)
        """
        # Her kaynak için farklı bekleme süreleri
        wait_times = {
            "meta_ads": 120.0,      # Meta agresif rate limit uygular
            "google_ads": 60.0,
            "shopify": 30.0,
            "search_console": 60.0,
            "merchant_center": 60.0,
            "ga4": 30.0,
            "default": diagnosis.retry_delay
        }

        wait_time = wait_times.get(source_name, wait_times["default"])
        logger.info("auto_fix_rate_limit", source=source_name, wait_seconds=wait_time)
        return True, wait_time

    @staticmethod
    async def fix_network_error(source_name: str, attempt: int) -> Tuple[bool, float]:
        """
        Network hatası - exponential backoff ile bekle.

        Returns:
            (should_retry, wait_seconds)
        """
        # Exponential backoff: 2, 4, 8, 16... seconds
        wait_time = min(2 ** attempt, 30.0)
        logger.info("auto_fix_network", source=source_name, attempt=attempt, wait_seconds=wait_time)
        return True, wait_time

    @staticmethod
    async def fix_mcp_error(source_name: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        MCP hatası - server durumunu kontrol et.

        Returns:
            (can_retry, message)
        """
        # MCP server path'i kontrol et
        mcp_dir = context.get("mcp_dir")
        if mcp_dir:
            from pathlib import Path
            server_path = Path(mcp_dir) / source_name.replace("_", "-") / "server.py"
            if server_path.exists():
                logger.info("mcp_server_exists", source=source_name, path=str(server_path))
                return True, f"MCP server mevcut: {server_path}"
            else:
                logger.error("mcp_server_missing", source=source_name, path=str(server_path))
                return False, f"MCP server bulunamadı: {server_path}"

        return False, "MCP dizini belirtilmedi"


# =============================================================================
# SMART RETRY WITH AUTO-FIX
# =============================================================================

@dataclass
class RetryResult:
    """Retry operasyonu sonucu."""
    success: bool
    data: Any
    attempts: int
    errors: List[ErrorDiagnosis]
    fixes_applied: List[str]
    total_wait_time: float


async def smart_fetch(
    source_name: str,
    fetch_func: Callable,
    context: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
) -> RetryResult:
    """
    Akıllı veri çekme - hata analizi ve otomatik düzeltme ile.

    Bu fonksiyon:
    1. Veri çekmeyi dener
    2. Hata olursa analiz eder
    3. Uygun düzeltme stratejisini uygular
    4. Gerekirse retry yapar

    Args:
        source_name: Veri kaynağı adı
        fetch_func: Async callable (lambda ile argümanları capture et)
        context: Ek bilgiler (mcp_dir, credentials, etc.)
        max_retries: Maksimum deneme sayısı

    Returns:
        RetryResult with data or detailed error info
    """
    context = context or {}
    errors: List[ErrorDiagnosis] = []
    fixes_applied: List[str] = []
    total_wait_time = 0.0
    attempt = 0

    while attempt < max_retries:
        attempt += 1

        try:
            logger.info("smart_fetch_attempt", source=source_name, attempt=attempt, max=max_retries)

            # Veri çekmeyi dene
            result = await fetch_func()

            # Başarılı yanıt kontrolü
            if isinstance(result, dict) and result.get("error"):
                raise Exception(result["error"])

            # List sonuç (batch call) - partial error kontrolü
            if isinstance(result, list):
                partial_errors = []
                for i, item in enumerate(result):
                    if isinstance(item, dict) and item.get("error"):
                        partial_errors.append(f"Tool {i}: {item['error']}")

                if partial_errors and len(partial_errors) == len(result):
                    # Tüm tool'lar fail oldu
                    raise Exception("; ".join(partial_errors))
                elif partial_errors:
                    # Kısmi başarı - log'la ama devam et
                    logger.warning(
                        "smart_fetch_partial_success",
                        source=source_name,
                        partial_errors=partial_errors
                    )

            # Başarılı!
            logger.info(
                "smart_fetch_success",
                source=source_name,
                attempt=attempt,
                fixes_applied=fixes_applied
            )

            return RetryResult(
                success=True,
                data=result,
                attempts=attempt,
                errors=errors,
                fixes_applied=fixes_applied,
                total_wait_time=total_wait_time
            )

        except Exception as e:
            error_msg = str(e)

            # Hatayı teşhis et
            diagnosis = diagnose_error(error_msg)
            errors.append(diagnosis)

            logger.warning(
                "smart_fetch_error",
                source=source_name,
                attempt=attempt,
                category=diagnosis.category.value,
                cause=diagnosis.probable_cause,
                fix=diagnosis.suggested_fix,
                auto_fixable=diagnosis.auto_fixable,
                retry_recommended=diagnosis.retry_recommended
            )

            # Son deneme mi?
            if attempt >= max_retries:
                break

            # Otomatik düzeltme dene
            should_retry = False
            wait_time = diagnosis.retry_delay

            if diagnosis.category == ErrorCategory.AUTH_ERROR and diagnosis.auto_fixable:
                # Token refresh dene
                fixed, fix_msg = await AutoFixStrategy.fix_auth_error(source_name, context)
                if fixed:
                    fixes_applied.append(fix_msg)
                    should_retry = True
                    wait_time = 1.0  # Token refresh sonrası kısa bekle

            elif diagnosis.category == ErrorCategory.RATE_LIMIT:
                should_retry, wait_time = await AutoFixStrategy.fix_rate_limit(source_name, diagnosis)
                if should_retry:
                    fixes_applied.append(f"Rate limit için {wait_time}s bekleniyor")

            elif diagnosis.category == ErrorCategory.NETWORK_ERROR:
                should_retry, wait_time = await AutoFixStrategy.fix_network_error(source_name, attempt)
                fixes_applied.append(f"Network hatası için {wait_time}s bekleniyor")

            elif diagnosis.category == ErrorCategory.MCP_ERROR:
                can_retry, fix_msg = await AutoFixStrategy.fix_mcp_error(source_name, context)
                should_retry = can_retry and diagnosis.retry_recommended
                if can_retry:
                    fixes_applied.append(fix_msg)

            elif diagnosis.retry_recommended:
                # Diğer hatalar için default retry
                should_retry = True

            if not should_retry:
                logger.error(
                    "smart_fetch_no_retry",
                    source=source_name,
                    category=diagnosis.category.value,
                    reason="Otomatik düzeltme başarısız veya retry önerilmiyor"
                )
                break

            # Bekle ve tekrar dene
            logger.info(
                "smart_fetch_waiting",
                source=source_name,
                wait_seconds=wait_time,
                next_attempt=attempt + 1
            )
            await asyncio.sleep(wait_time)
            total_wait_time += wait_time

    # Tüm denemeler başarısız
    return RetryResult(
        success=False,
        data=None,
        attempts=attempt,
        errors=errors,
        fixes_applied=fixes_applied,
        total_wait_time=total_wait_time
    )


# =============================================================================
# ERROR AGGREGATOR - Enhanced
# =============================================================================

@dataclass
class SourceError:
    """Kaynak hatası detayları."""
    source: str
    diagnosis: ErrorDiagnosis
    timestamp: datetime
    attempts: int
    fixes_tried: List[str]


class ErrorAggregator:
    """
    Tüm kaynakların hata durumunu toplar ve raporlar.
    """

    def __init__(self):
        self.errors: List[SourceError] = []
        self.successes: List[str] = []
        self.start_time: datetime = datetime.now()

    def add_error(
        self,
        source: str,
        error_message: str,
        attempts: int = 1,
        fixes_tried: List[str] = None
    ):
        """Hata ekle - otomatik teşhis ile."""
        diagnosis = diagnose_error(error_message)
        self.errors.append(SourceError(
            source=source,
            diagnosis=diagnosis,
            timestamp=datetime.now(),
            attempts=attempts,
            fixes_tried=fixes_tried or []
        ))

    def add_from_result(self, source: str, result: RetryResult):
        """RetryResult'tan hata ekle."""
        if not result.success and result.errors:
            last_error = result.errors[-1]
            self.errors.append(SourceError(
                source=source,
                diagnosis=last_error,
                timestamp=datetime.now(),
                attempts=result.attempts,
                fixes_tried=result.fixes_applied
            ))
        elif result.success:
            self.successes.append(source)

    def add_success(self, source: str):
        """Başarılı kaynak ekle."""
        if source not in self.successes:
            self.successes.append(source)

    def get_summary(self) -> Dict[str, Any]:
        """Özet al."""
        errors_by_category = {}
        for err in self.errors:
            cat = err.diagnosis.category.value
            if cat not in errors_by_category:
                errors_by_category[cat] = []
            errors_by_category[cat].append(err.source)

        return {
            "total_sources": len(self.successes) + len(set(e.source for e in self.errors)),
            "successful": len(self.successes),
            "failed": len(set(e.source for e in self.errors)),
            "success_sources": self.successes,
            "error_sources": list(set(e.source for e in self.errors)),
            "errors_by_category": errors_by_category,
            "duration_seconds": (datetime.now() - self.start_time).total_seconds()
        }

    def format_for_telegram(self) -> str:
        """Telegram için detaylı diagnostic mesajı."""
        summary = self.get_summary()

        msg = f"""🚨 **VERİ TOPLAMA DİAGNOSTİK**

📊 **Özet**
• Başarılı: {summary['successful']}/{summary['total_sources']} kaynak
• Hatalı: {summary['failed']}/{summary['total_sources']} kaynak
• Süre: {summary['duration_seconds']:.1f} saniye

"""

        if self.successes:
            msg += "✅ **Başarılı Kaynaklar**\n"
            for source in self.successes:
                msg += f"  • {source}\n"
            msg += "\n"

        if self.errors:
            msg += "❌ **Hatalı Kaynaklar (Detaylı)**\n"
            for err in self.errors:
                d = err.diagnosis
                category_emoji = {
                    ErrorCategory.AUTH_ERROR: "🔐",
                    ErrorCategory.RATE_LIMIT: "⏱️",
                    ErrorCategory.NETWORK_ERROR: "🌐",
                    ErrorCategory.MCP_ERROR: "🔧",
                    ErrorCategory.DATA_ERROR: "📄",
                    ErrorCategory.CONFIG_ERROR: "⚙️",
                    ErrorCategory.UNKNOWN_ERROR: "❓",
                }.get(d.category, "❓")

                msg += f"\n{category_emoji} **{err.source}**\n"
                msg += f"  • Kategori: {d.category.value}\n"
                msg += f"  • Neden: {d.probable_cause}\n"
                msg += f"  • Çözüm: {d.suggested_fix}\n"
                msg += f"  • Deneme: {err.attempts}\n"
                if err.fixes_tried:
                    msg += f"  • Denenen düzeltmeler: {', '.join(err.fixes_tried)}\n"

            msg += "\n"

        # Kategori bazlı özet
        if summary['errors_by_category']:
            msg += "📋 **Hata Kategorileri**\n"
            for category, sources in summary['errors_by_category'].items():
                msg += f"  • {category}: {', '.join(sources)}\n"
            msg += "\n"

        # Aksiyon önerileri
        msg += "💡 **Önerilen Aksiyonlar**\n"

        if ErrorCategory.AUTH_ERROR.value in summary.get('errors_by_category', {}):
            msg += "  🔐 Token/credential yenileme gerekiyor\n"
        if ErrorCategory.RATE_LIMIT.value in summary.get('errors_by_category', {}):
            msg += "  ⏱️ API rate limit - daha sonra tekrar deneyin\n"
        if ErrorCategory.NETWORK_ERROR.value in summary.get('errors_by_category', {}):
            msg += "  🌐 Network bağlantısını kontrol edin\n"
        if ErrorCategory.MCP_ERROR.value in summary.get('errors_by_category', {}):
            msg += "  🔧 MCP server'ları kontrol edin\n"
        if ErrorCategory.CONFIG_ERROR.value in summary.get('errors_by_category', {}):
            msg += "  ⚙️ .env dosyasını kontrol edin\n"

        return msg.strip()


# =============================================================================
# CIRCUIT BREAKER - Category Aware
# =============================================================================

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """
    Kategori-aware circuit breaker.
    Bazı hata kategorileri circuit'i açmamalı.
    """
    name: str
    failure_threshold: int = 3
    success_threshold: int = 1
    cooldown_seconds: float = 60.0

    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    success_count: int = field(default=0)
    last_failure_time: Optional[datetime] = field(default=None)
    last_error: Optional[str] = field(default=None)
    last_category: Optional[ErrorCategory] = field(default=None)

    # Bu kategoriler circuit'i açmamalı (geçici değil kalıcı sorunlar)
    NON_CIRCUIT_CATEGORIES = {
        ErrorCategory.CONFIG_ERROR,  # Config eksikse retry işe yaramaz
    }

    def can_execute(self) -> bool:
        """Çalıştırabilir miyiz?"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.cooldown_seconds:
                    logger.info("circuit_half_open", name=self.name)
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    return True
            return False

        return True  # HALF_OPEN

    def record_success(self):
        """Başarı kaydet."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                logger.info("circuit_closed", name=self.name)
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        else:
            self.failure_count = 0

    def record_failure(self, error: str, category: Optional[ErrorCategory] = None):
        """Hata kaydet - kategori aware."""
        # Kalıcı hatalar circuit'i açmamalı
        if category in self.NON_CIRCUIT_CATEGORIES:
            logger.info(
                "circuit_skip_non_transient",
                name=self.name,
                category=category.value if category else None
            )
            return

        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.last_error = error
        self.last_category = category

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("circuit_reopened", name=self.name)
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            logger.error(
                "circuit_opened",
                name=self.name,
                failures=self.failure_count,
                category=category.value if category else None
            )
            self.state = CircuitState.OPEN

    def get_status(self) -> Dict[str, Any]:
        """Durum al."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
            "last_category": self.last_category.value if self.last_category else None,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None
        }


class CircuitBreakerRegistry:
    """Global circuit breaker registry."""
    _instance: Optional['CircuitBreakerRegistry'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._breakers = {}
        return cls._instance

    def get(self, name: str, **kwargs) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name=name, **kwargs)
        return self._breakers[name]

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        return {name: b.get_status() for name, b in self._breakers.items()}

    def reset(self, name: Optional[str] = None):
        if name:
            if name in self._breakers:
                self._breakers[name] = CircuitBreaker(name=name)
        else:
            self._breakers = {}


circuit_registry = CircuitBreakerRegistry()


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def fetch_with_smart_retry(
    source_name: str,
    fetch_func: Callable,
    context: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    circuit_threshold: int = 5,
    circuit_cooldown: float = 120.0,
) -> Dict[str, Any]:
    """
    Tek fonksiyonda: Circuit Breaker + Smart Retry + Error Diagnosis.

    Args:
        source_name: Kaynak adı
        fetch_func: Async callable (lambda ile wrap et)
        context: Ek bilgiler
        max_retries: Max retry
        circuit_threshold: Circuit açmak için gereken hata sayısı
        circuit_cooldown: Circuit açık kalma süresi

    Returns:
        Dict with 'success', 'data', 'error', 'diagnosis', etc.
    """
    breaker = circuit_registry.get(
        source_name,
        failure_threshold=circuit_threshold,
        cooldown_seconds=circuit_cooldown
    )

    # Circuit açık mı?
    if not breaker.can_execute():
        return {
            "success": False,
            "data": None,
            "error": f"Circuit open for {source_name}",
            "circuit_state": "open",
            "last_error": breaker.last_error,
            "diagnosis": {
                "category": breaker.last_category.value if breaker.last_category else "unknown",
                "message": "Circuit breaker aktif - kaynak geçici olarak devre dışı"
            }
        }

    # Smart fetch ile dene
    result = await smart_fetch(
        source_name=source_name,
        fetch_func=fetch_func,
        context=context,
        max_retries=max_retries
    )

    if result.success:
        breaker.record_success()
        return {
            "success": True,
            "data": result.data,
            "attempts": result.attempts,
            "fixes_applied": result.fixes_applied,
            "total_wait_time": result.total_wait_time
        }
    else:
        # Son hatanın kategorisini al
        last_diagnosis = result.errors[-1] if result.errors else None
        category = last_diagnosis.category if last_diagnosis else None

        breaker.record_failure(
            error=last_diagnosis.original_error if last_diagnosis else "Unknown",
            category=category
        )

        return {
            "success": False,
            "data": None,
            "error": last_diagnosis.original_error if last_diagnosis else "Unknown error",
            "attempts": result.attempts,
            "fixes_applied": result.fixes_applied,
            "total_wait_time": result.total_wait_time,
            "diagnosis": {
                "category": category.value if category else "unknown",
                "probable_cause": last_diagnosis.probable_cause if last_diagnosis else "",
                "suggested_fix": last_diagnosis.suggested_fix if last_diagnosis else "",
            },
            "all_errors": [
                {
                    "category": e.category.value,
                    "cause": e.probable_cause,
                    "fix": e.suggested_fix
                }
                for e in result.errors
            ]
        }
