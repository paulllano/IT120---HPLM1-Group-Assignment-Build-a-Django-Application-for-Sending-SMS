from django.contrib import admin

from .models import SMSMessage


@admin.register(SMSMessage)
class SMSMessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'recipient', 'status', 'provider_status', 'network', 'provider')
    list_filter = ('status', 'provider', 'network')
    search_fields = ('recipient', 'body', 'provider_message_id')
    readonly_fields = ('created_at', 'updated_at')
