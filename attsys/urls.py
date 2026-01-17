from django.urls import path
from . import views
from .views import export_registrations_pdf

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('event/create/', views.create_event, name='create_event'),
    path('event/<int:event_id>/', views.event_detail, name='event_detail'),
    path('event/<int:event_id>/toggle/', views.toggle_event, name='toggle_event'),

    # Real-time API endpoints
    path('api/event/<int:event_id>/realtime-attendees/', views.get_realtime_attendees, name='realtime_attendees'),
    path('api/event/<int:event_id>/realtime-stats/', views.get_realtime_stats, name='realtime_stats'),

    # QR public page
    path('check-in/<int:event_id>/<uuid:token>/', views.check_in, name='check_in'),

    path('api/attendee/<int:attendee_id>/details/', views.get_attendee_details, name='get_attendee_details'),

    # CSV export
    path('event/<int:event_id>/export/', views.export_attendees_csv, name='export_attendees_csv'),

    path('api/attendee/<int:attendee_id>/registration/', views.get_attendee_registration, name='get_attendee_registration'),
    path('api/registration/save/', views.save_registration, name='save_registration'),
    path('api/event/<int:event_id>/registration-stats/', views.get_registration_stats, name='get_registration_stats'),
    path('api/event/<int:event_id>/registration-full-stats/', views.get_full_registration_stats, name='get_full_registration_stats'),
    path('api/event/<int:event_id>/export-registrations/', views.export_registrations_csv, name='export_registrations_csv'),
    path('api/event/<int:event_id>/export-registrations-pdf/', views.export_registrations_pdf, name='export_registrations_pdf'),

    # Admin staff management
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('api/dashboard/stats/', views.get_dashboard_stats, name='dashboard_stats'),
    path('admin/staff/', views.manage_staff, name='manage_staff'),
    path('event/<int:event_id>/assign/', views.assign_staff, name='assign_staff'),
    path('staff/', views.manage_staff, name='manage_staff'),
    path('staff/<int:user_id>/toggle/', views.toggle_staff_status, name='toggle_staff'),
    path('feedback/<int:event_id>/', views.submit_feedback, name='submit_feedback'),

]