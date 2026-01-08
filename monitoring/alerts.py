"""
Alert Rules for Agent System
=============================

Defines alert conditions and notification logic.

Alert Categories:
- Performance: High latency, slow responses
- Errors: High error rates, failures
- Cost: Excessive spending
- Capacity: Resource exhaustion
"""

import logging
from typing import Dict, Any, Callable, List
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    description: str
    condition: Callable[[], bool]
    severity: str  # critical, warning, info
    threshold: float
    duration_minutes: int = 5
    cooldown_minutes: int = 30


class AlertManager:
    """
    Manages alert rules and notifications.

    Usage:
        alert_mgr = AlertManager()
        alert_mgr.add_rule(high_latency_rule)
        alert_mgr.check_alerts()  # Call periodically
    """

    def __init__(self):
        self.rules: List[AlertRule] = []
        self.alert_history: Dict[str, datetime] = {}
        self.notification_handlers: List[Callable] = []

    def add_rule(self, rule: AlertRule):
        """Add alert rule."""
        self.rules.append(rule)
        logger.info(f"Alert rule added: {rule.name}")

    def add_notification_handler(self, handler: Callable[[str, str, Dict], None]):
        """
        Add notification handler.

        Handler signature: handler(alert_name: str, severity: str, context: dict)
        """
        self.notification_handlers.append(handler)

    def check_alerts(self) -> List[Dict[str, Any]]:
        """
        Check all alert rules and trigger notifications.

        Returns:
            List of triggered alerts
        """
        triggered = []

        for rule in self.rules:
            # Check cooldown
            if rule.name in self.alert_history:
                last_alert = self.alert_history[rule.name]
                cooldown_until = last_alert + timedelta(minutes=rule.cooldown_minutes)
                if datetime.now() < cooldown_until:
                    continue  # Still in cooldown

            # Check condition
            try:
                if rule.condition():
                    alert_data = {
                        "name": rule.name,
                        "description": rule.description,
                        "severity": rule.severity,
                        "threshold": rule.threshold,
                        "timestamp": datetime.now().isoformat()
                    }

                    triggered.append(alert_data)

                    # Send notifications
                    for handler in self.notification_handlers:
                        try:
                            handler(rule.name, rule.severity, alert_data)
                        except Exception as e:
                            logger.error(f"Notification handler failed: {e}")

                    # Update history
                    self.alert_history[rule.name] = datetime.now()

                    logger.warning(f"Alert triggered: {rule.name}")

            except Exception as e:
                logger.error(f"Alert check failed for {rule.name}: {e}")

        return triggered


# Pre-defined alert rules

def create_high_latency_alert(threshold_seconds: float = 5.0) -> AlertRule:
    """
    Alert when agent execution latency exceeds threshold.

    Args:
        threshold_seconds: Latency threshold

    Returns:
        AlertRule instance
    """
    def condition():
        # TODO: Query Prometheus for actual metrics
        # For now, return False (no alert)
        # Example query: histogram_quantile(0.95, rate(agent_execution_duration_seconds_bucket[5m])) > threshold
        return False

    return AlertRule(
        name="high_agent_latency",
        description=f"Agent execution latency > {threshold_seconds}s (p95)",
        condition=condition,
        severity="warning",
        threshold=threshold_seconds,
        duration_minutes=5
    )


def create_high_error_rate_alert(threshold_rate: float = 0.05) -> AlertRule:
    """
    Alert when error rate exceeds threshold.

    Args:
        threshold_rate: Error rate threshold (0-1)

    Returns:
        AlertRule instance
    """
    def condition():
        # TODO: Query Prometheus
        # Example: rate(agent_execution_total{status="failure"}[5m]) / rate(agent_execution_total[5m]) > threshold
        return False

    return AlertRule(
        name="high_error_rate",
        description=f"Error rate > {threshold_rate*100}%",
        condition=condition,
        severity="critical",
        threshold=threshold_rate,
        duration_minutes=5
    )


def create_high_cost_alert(threshold_usd_per_hour: float = 1.0) -> AlertRule:
    """
    Alert when cost exceeds threshold.

    Args:
        threshold_usd_per_hour: Cost threshold

    Returns:
        AlertRule instance
    """
    def condition():
        # TODO: Query Prometheus
        # Example: rate(agent_cost_usd_total[1h]) > threshold
        return False

    return AlertRule(
        name="high_cost",
        description=f"Agent cost > ${threshold_usd_per_hour}/hour",
        condition=condition,
        severity="warning",
        threshold=threshold_usd_per_hour,
        duration_minutes=10
    )


def create_memory_cache_low_hitrate_alert(threshold: float = 0.5) -> AlertRule:
    """
    Alert when cache hit rate is too low.

    Args:
        threshold: Hit rate threshold (0-1)

    Returns:
        AlertRule instance
    """
    def condition():
        # TODO: Query Prometheus
        # Example: rate(memory_cache_hit_total[5m]) / (rate(memory_cache_hit_total[5m]) + rate(memory_cache_miss_total[5m])) < threshold
        return False

    return AlertRule(
        name="low_cache_hitrate",
        description=f"Memory cache hit rate < {threshold*100}%",
        condition=condition,
        severity="info",
        threshold=threshold,
        duration_minutes=15
    )


# Notification handlers

def log_notification_handler(alert_name: str, severity: str, context: Dict[str, Any]):
    """Log alert to console."""
    logger.warning(f"[ALERT] {severity.upper()}: {alert_name} - {context.get('description')}")


def slack_notification_handler(webhook_url: str):
    """
    Create Slack notification handler.

    Args:
        webhook_url: Slack webhook URL

    Returns:
        Notification handler function
    """
    def handler(alert_name: str, severity: str, context: Dict[str, Any]):
        try:
            import requests

            emoji = {
                "critical": ":fire:",
                "warning": ":warning:",
                "info": ":information_source:"
            }.get(severity, ":bell:")

            message = {
                "text": f"{emoji} *Agent System Alert*",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} {alert_name}"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                            {"type": "mrkdwn", "text": f"*Threshold:*\n{context.get('threshold')}"}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": context.get('description')
                        }
                    }
                ]
            }

            requests.post(webhook_url, json=message, timeout=5)

        except Exception as e:
            logger.error(f"Slack notification failed: {e}")

    return handler


def email_notification_handler(smtp_config: Dict[str, str]):
    """
    Create email notification handler.

    Args:
        smtp_config: SMTP configuration (host, port, user, password, to_addresses)

    Returns:
        Notification handler function
    """
    def handler(alert_name: str, severity: str, context: Dict[str, Any]):
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['From'] = smtp_config['user']
            msg['To'] = ", ".join(smtp_config['to_addresses'])
            msg['Subject'] = f"[{severity.upper()}] Agent System Alert: {alert_name}"

            body = f"""
Agent System Alert

Alert: {alert_name}
Severity: {severity}
Description: {context.get('description')}
Threshold: {context.get('threshold')}
Timestamp: {context.get('timestamp')}

This is an automated alert from your agent monitoring system.
"""

            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
                server.starttls()
                server.login(smtp_config['user'], smtp_config['password'])
                server.send_message(msg)

        except Exception as e:
            logger.error(f"Email notification failed: {e}")

    return handler


# Example usage
def setup_default_alerts(alert_mgr: AlertManager):
    """
    Setup default alert rules.

    Args:
        alert_mgr: AlertManager instance
    """
    # Add alert rules
    alert_mgr.add_rule(create_high_latency_alert(threshold_seconds=10.0))
    alert_mgr.add_rule(create_high_error_rate_alert(threshold_rate=0.05))
    alert_mgr.add_rule(create_high_cost_alert(threshold_usd_per_hour=2.0))
    alert_mgr.add_rule(create_memory_cache_low_hitrate_alert(threshold=0.5))

    # Add notification handlers
    alert_mgr.add_notification_handler(log_notification_handler)

    # Optional: Add Slack/email if configured
    # slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
    # if slack_webhook:
    #     alert_mgr.add_notification_handler(slack_notification_handler(slack_webhook))

    logger.info("Default alerts configured")
