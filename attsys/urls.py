from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('event/create/', views.create_event, name='create_event'),
    path('event/<int:event_id>/', views.event_detail, name='event_detail'),
    path('event/<int:event_id>/toggle/', views.toggle_event, name='toggle_event'),

    # QR public page
    path('check-in/<int:event_id>/<uuid:token>/', views.check_in, name='check_in'),

    # CSV export
    path('event/<int:event_id>/export/', views.export_attendees_csv, name='export_attendees_csv'),
]