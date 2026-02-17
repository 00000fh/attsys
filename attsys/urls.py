# attsys/urls.py
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.urls import path
from django.shortcuts import redirect
from . import views  # Import the entire module, not specific functions

@csrf_exempt
def force_create_admin(request):
    """Emergency admin creation - REMOVE AFTER USE"""
    if request.method == 'POST':
        try:
            User = get_user_model()
            data = json.loads(request.body)
            
            username = data.get('username', 'emergency_admin')
            password = data.get('password', 'Emergency@123456')
            email = data.get('email', f'{username}@example.com')
            
            # Check if any admin exists
            if User.objects.filter(role='ADMIN').exists():
                return JsonResponse({
                    'status': 'warning',
                    'message': 'Admin already exists. Try these credentials:',
                    'admins': list(User.objects.filter(role='ADMIN').values('username'))
                })
            
            # Create admin
            admin = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role='ADMIN',
                is_active=True,
                is_staff=True,
                is_superuser=True
            )
            
            return JsonResponse({
                'status': 'success',
                'message': 'Admin created successfully!',
                'credentials': {
                    'username': username,
                    'password': password
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    # GET request - show form
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Emergency Admin Creation</title>
        <style>
            body { background: #000; color: #fff; font-family: monospace; padding: 40px; }
            .container { max-width: 500px; margin: 0 auto; }
            input { width: 100%; padding: 10px; margin: 10px 0; background: #111; border: 1px solid #333; color: #fff; }
            button { background: #fff; color: #000; padding: 10px 20px; border: none; cursor: pointer; width: 100%; }
            .warning { color: #ff0; border: 1px solid #ff0; padding: 10px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 EMERGENCY ADMIN CREATION</h1>
            <div class="warning">
                ⚠️ USE ONLY IF LOCKED OUT - REMOVE AFTER USE
            </div>
            <form id="adminForm">
                <input type="text" id="username" placeholder="Username" value="admin123" required>
                <input type="password" id="password" placeholder="Password" value="Admin@123456" required>
                <input type="email" id="email" placeholder="Email" value="admin@example.com" required>
                <button type="submit">CREATE ADMIN</button>
            </form>
            <div id="result" style="margin-top: 20px;"></div>
        </div>
        
        <script>
            document.getElementById('adminForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const result = document.getElementById('result');
                result.innerHTML = 'Processing...';
                
                try {
                    const response = await fetch(window.location.href, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            username: document.getElementById('username').value,
                            password: document.getElementById('password').value,
                            email: document.getElementById('email').value
                        })
                    });
                    
                    const data = await response.json();
                    result.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                    
                    if (data.status === 'success') {
                        result.innerHTML += '<br><a href="/attsys/login/" style="color:#0f0;">→ GO TO LOGIN PAGE</a>';
                    }
                } catch (err) {
                    result.innerHTML = 'Error: ' + err.message;
                }
            });
        </script>
    </body>
    </html>
    """
    return HttpResponse(html)

urlpatterns = [
    # Redirect root to login
    path('emergency-admin/', force_create_admin, name='emergency_admin'),
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
    path('api/application/<int:application_id>/print-form-number/', views.get_print_form_number, name='get_print_form_number'),
    
    # Other API endpoints...
    path('api/attendee/<int:attendee_id>/details/', views.get_attendee_details, name='get_attendee_details'),
    path('event/<int:event_id>/export/', views.export_attendees_csv, name='export_attendees_csv'),
    path('api/attendee/<int:attendee_id>/registration/', views.get_attendee_registration, name='get_attendee_registration'),
    path('api/registration/save/', views.save_registration, name='save_registration'),
    path('api/event/<int:event_id>/registration-stats/', views.get_registration_stats, name='get_registration_stats'),
    path('api/event/<int:event_id>/registration-full-stats/', views.get_full_registration_stats, name='get_full_registration_stats'),
    path('api/event/<int:event_id>/export-registrations/', views.export_registrations_csv, name='export_registrations_csv'),
    path('api/event/<int:event_id>/export-registrations-pdf/', views.export_registrations_pdf, name='export_registrations_pdf'),
    path('api/attendee/<int:attendee_id>/delete/', views.delete_attendee, name='delete_attendee'),
    path('api/staff/create/', views.create_staff, name='create_staff'),
    
    # Admin staff management
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('api/dashboard/stats/', views.get_dashboard_stats, name='dashboard_stats'),
    path('admin/staff/', views.manage_staff, name='manage_staff'),
    path('event/<int:event_id>/assign/', views.assign_staff, name='assign_staff'),
    path('staff/', views.manage_staff, name='manage_staff'),
    path('staff/<int:user_id>/toggle/', views.toggle_staff_status, name='toggle_staff'),
]