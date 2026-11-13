from django.db import models


class SMSMessage(models.Model):
    """One attempt to send an SMS, kept for the History page."""

    class Status(models.TextChoices):
        # The SMS service accepted the request, but the message hasn't reached the network yet.
        SUBMITTED = 'submitted', 'Submitted'
        # The mobile network accepted the message. Not yet confirmed on the recipient's phone.
        SENT = 'sent', 'Sent to network'
        # The recipient's phone confirmed it received the message (delivery report).
        DELIVERED = 'delivered', 'Delivered'
        # The provider or network rejected / failed the message, or it couldn't be sent at all.
        FAILED = 'failed', 'Failed'

    recipient = models.CharField(max_length=11, help_text='PH mobile number, e.g. 09171234567')
    body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)

    provider = models.CharField(max_length=20, help_text='smsgate or console (test mode)')
    provider_message_id = models.CharField(max_length=64, blank=True)
    provider_status = models.CharField(
        max_length=20, blank=True, help_text='Raw status from the provider, e.g. Pending or Sent'
    )
    network = models.CharField(max_length=40, blank=True, help_text='Carrier reported by the provider')
    error_message = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'SMS message'

    def __str__(self):
        return f'{self.recipient} ({self.get_status_display()})'

    @property
    def can_refresh(self):
        """Only messages whose status can still change can be re-checked."""
        from .services import is_refreshable  # imported here to avoid a circular import
        return is_refreshable(self)
