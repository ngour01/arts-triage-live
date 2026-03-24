import logging

logger = logging.getLogger("art_triage.messenger")


class Messenger:
    """Notification stub — configure a webhook or email transport to enable real alerts."""

    def send_summary(self, cycle_id):
        logger.info(
            "Cycle %s triage complete. "
            "Notifications not configured — set up a webhook/email transport to enable.",
            cycle_id,
        )
