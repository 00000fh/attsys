# attsys/urls.py
from django.urls import path
from django.shortcuts import redirect
from . import views  # Import the entire module, not specific functions

urlpatterns = [
    # Redirect root to login
    path('', lambda request: redirect('login'), name='home'),
    
    # Login/Logout
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard (protected)
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Event URLs
    path('event/create/', views.create_event, name='create_event'),
    path('event/<int:event_id>/', views.event_detail, name='event_detail'),
    path('event/<int:event_id>/toggle/', views.toggle_event, name='toggle_event'),
    
    # Real-time API endpoints
    path('api/event/<int:event_id>/realtime-attendees/', views.get_realtime_attendees, name='realtime_attendees'),
    path('api/event/<int:event_id>/realtime-stats/', views.get_realtime_stats, name='realtime_stats'),
    path('event/<int:event_id>/live-stats/', views.get_live_stats, name='live_stats'),
    path('api/attendee/<int:attendee_id>/printable-details/', views.get_printable_attendee_details, name='printable_attendee_details'),
    
    # QR public page - THIS IS THE KEY ONE
    path('check-in/<int:event_id>/<str:token>/', views.check_in, name='check_in'),
    path('success/', views.success_page, name='success_page'),  # Add this line
    path('event/<int:event_id>/download-qr/', views.download_qr_code, name='download_qr'),
    
    
    # Other API endpoints...
    path('api/attendee/<int:attendee_id>/details/', views.get_attendee_details, name='get_attendee_details'),
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