from django.urls import path

from . import views

app_name = 'sms_app'

urlpatterns = [
    path('', views.send_sms, name='send'),
    path('history/', views.history, name='history'),
    path('history/<int:pk>/refresh/', views.refresh_status, name='refresh_status'),
]
