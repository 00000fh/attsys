# views.py
import uuid
import qrcode
import base64
import csv
from io import BytesIO
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Event, Attendee, Feedback, Application, Registration
from django.http import HttpResponseForbidden, JsonResponse
from django.db import IntegrityError
from django.contrib import messages
from .models import User
from django.utils.timezone import now, timedelta
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
import pandas as pd
from django.db.models import Sum, Count, Avg, Q, F, Value
from django.db.models.functions import TruncHour, ExtractHour, Coalesce
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
import json
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from datetime import date, timedelta, datetime
from decimal import Decimal, InvalidOperation
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.conf import settings
from reportlab.pdfgen import canvas
from django.db import models


User = get_user_model()


def custom_login(request):
    # AUTO-CREATE ADMIN IF NO USERS EXIST
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    if not User.objects.exists():
        print("⚠️ No users found, creating default admin...")
        admin_user = User.objects.create_user(
            username='pejaladmin46',
            email='faizalhussin45@gmail.com',
            password='canon990',  # SIMPLE PASSWORD - CHANGE AFTER LOGIN!
            is_staff=True,
            is_superuser=True,
            role='ADMIN'
        )
        print(f"✅ Created default admin: pejaladmin46 / canon990")


def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those resources
    """
    # Convert URIs to absolute path
    if uri.startswith("data:"):
        return uri
    
    # Handle static files
    if uri.startswith("/static/"):
        path = os.path.join(settings.STATIC_ROOT, uri.replace("/static/", ""))
        if os.path.isfile(path):
            return path
    
    # Handle media files
    if uri.startswith("/media/"):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace("/media/", ""))
        if os.path.isfile(path):
            return path
    
    # Fallback to base URL
    return uri

def generate_pdf(template_src, context_dict={}):
    """
    Generate PDF from HTML template
    """
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()
    
    # Generate PDF
    pdf = pisa.CreatePDF(
        BytesIO(html.encode("UTF-8")),
        dest=result,
        encoding='UTF-8',
        link_callback=link_callback
    )
    
    if not pdf.err:
        return result.getvalue()
    return None

def render_to_pdf_response(template_src, context_dict, filename="report.pdf"):
    """
    Render template to PDF HTTP response
    """
    from io import BytesIO
    from django.template.loader import get_template
    from xhtml2pdf import pisa
    
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()
    
    # Generate PDF
    pdf = pisa.CreatePDF(
        BytesIO(html.encode("UTF-8")),
        dest=result,
        encoding='UTF-8'
    )
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    return HttpResponse('PDF generation error', status=500)


# Helper: Get current Malaysia time
def malaysia_now():
    """Get current time in Malaysia timezone (UTC+8)"""
    # Create a timezone object for UTC+8
    return timezone.now() + timedelta(hours=8)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    if not request.user.is_active:
        return redirect('login')

    # Get Malaysia time
    today = malaysia_now().date()
    
    if request.user.role == 'ADMIN':
        # ADMIN VIEW - System-wide stats
        total_events = Event.objects.count()
        total_attendees = Attendee.objects.count()
        total_staff = User.objects.filter(role='STAFF', is_active=True).count()
        total_feedback = Feedback.objects.count()
        total_applications = Application.objects.count()
        
        # Today's check-ins (Malaysia time)
        today_checkins = Attendee.objects.filter(
            attended_at__date=today
        ).count()
        
        # Active events
        active_events = Event.objects.filter(is_active=True).count()
        
        # Average rating across all events
        avg_rating = Feedback.objects.aggregate(Avg('rating'))['rating__avg']
        
        # Get recent events (all events for admin)
        events = Event.objects.order_by('-created_at')[:10]

        return render(request, 'dashboard.html', {
            'total_events': total_events,
            'total_attendees': total_attendees,
            'total_staff': total_staff,  # Only for admin
            'total_feedback': total_feedback,
            'total_applications': total_applications,
            'today_checkins': today_checkins,
            'active_events': active_events,
            'avg_rating': avg_rating,
            'events': events,
            'is_admin': True  # Add this flag
        })

    else:
        # STAFF VIEW - Only their own data
        # Get events created by this staff
        user_events = Event.objects.filter(created_by=request.user)
        
        # Count stats for this staff's events only
        total_events = user_events.count()
        total_attendees = Attendee.objects.filter(event__in=user_events).count()
        total_feedback = Feedback.objects.filter(event__in=user_events).count()
        total_applications = Application.objects.filter(event__in=user_events).count()
        
        # Today's check-ins for staff's events
        today_checkins = Attendee.objects.filter(
            event__in=user_events,
            attended_at__date=today
        ).count()
        
        # Active events for this staff
        active_events = user_events.filter(is_active=True).count()
        
        # Average rating for staff's events
        avg_rating = Feedback.objects.filter(
            event__in=user_events
        ).aggregate(Avg('rating'))['rating__avg']
        
        # Get recent events for this staff
        events = user_events.order_by('-created_at')[:10]

        return render(request, 'dashboard.html', {
            'total_events': total_events,
            'total_attendees': total_attendees,
            'total_feedback': total_feedback,
            'total_applications': total_applications,
            'today_checkins': today_checkins,
            'active_events': active_events,
            'avg_rating': avg_rating,
            'events': events,
            'is_admin': False  # Add this flag
        })


@login_required
@require_GET
def get_dashboard_stats(request):
    """API endpoint for real-time dashboard statistics"""
    if not request.user.is_active:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    today = malaysia_now().date()
    
    if request.user.role == 'ADMIN':
        # Admin gets system-wide stats
        total_events = Event.objects.count()
        total_attendees = Attendee.objects.count()
        total_staff = User.objects.filter(role='STAFF', is_active=True).count()
        total_feedback = Feedback.objects.count()
        total_applications = Application.objects.count()
        
        # Today's stats
        today_checkins = Attendee.objects.filter(
            attended_at__date=today
        ).count()
        
        # Yesterday for comparison
        yesterday = today - timedelta(days=1)
        yesterday_checkins = Attendee.objects.filter(
            attended_at__date=yesterday
        ).count()
        
        # Active events
        active_events = Event.objects.filter(is_active=True).count()
        
        # Average rating
        avg_rating = Feedback.objects.aggregate(Avg('rating'))['rating__avg'] or 0
        
        # Recent events for admin (all events)
        recent_events = Event.objects.order_by('-created_at')[:10].values(
            'id', 'title', 'is_active', 'created_at'
        ).annotate(attendees_count=Count('attendees'))
        
    else:
        # Staff gets their own stats
        user_events = Event.objects.filter(created_by=request.user)
        
        total_events = user_events.count()
        total_attendees = Attendee.objects.filter(event__in=user_events).count()
        total_feedback = Feedback.objects.filter(event__in=user_events).count()
        total_applications = Application.objects.filter(event__in=user_events).count()
        
        # Today's stats
        today_checkins = Attendee.objects.filter(
            event__in=user_events,
            attended_at__date=today
        ).count()
        
        # Yesterday for comparison
        yesterday = today - timedelta(days=1)
        yesterday_checkins = Attendee.objects.filter(
            event__in=user_events,
            attended_at__date=yesterday
        ).count()
        
        # Active events
        active_events = user_events.filter(is_active=True).count()
        
        # Average rating for user's events
        avg_rating = Feedback.objects.filter(
            event__in=user_events
        ).aggregate(Avg('rating'))['rating__avg'] or 0
        
        # Recent events for staff
        recent_events = user_events.order_by('-created_at')[:10].values(
            'id', 'title', 'is_active', 'created_at'
        ).annotate(attendees_count=Count('attendees'))
    
    # Calculate percentage changes
    checkins_change = today_checkins - yesterday_checkins if yesterday_checkins > 0 else 0
    checkins_change_percent = (checkins_change / yesterday_checkins * 100) if yesterday_checkins > 0 else 0
    
    response_data = {
        'success': True,
        'total_events': total_events,
        'total_attendees': total_attendees,
        'total_staff': total_staff if request.user.role == 'ADMIN' else 0,
        'total_feedback': total_feedback,
        'total_applications': total_applications,
        'today_checkins': today_checkins,
        'yesterday_checkins': yesterday_checkins,
        'checkins_change': checkins_change,
        'checkins_change_percent': round(checkins_change_percent, 1),
        'active_events': active_events,
        'avg_rating': round(float(avg_rating), 1),
        'recent_events': list(recent_events),
        'timestamp': malaysia_now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return JsonResponse(response_data)


@login_required
def create_event(request):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role != 'STAFF':
        return HttpResponseForbidden()

    if request.method == 'POST':
        Event.objects.create(
            title=request.POST['title'],
            venue=request.POST['venue'],
            date=request.POST['date'],
            start_time=request.POST['start_time'],
            end_time=request.POST['end_time'],
            created_by=request.user
        )
        return redirect('dashboard')

    return render(request, 'create_event.html')


@login_required
def event_detail(request, event_id):
    if not request.user.is_active:
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden("You don't have permission to view this event.")

    # ✅ DEFINE ATTENDEES FIRST
    attendees = event.attendees.all().order_by('-attended_at')

    # 🔹 Get current Malaysia time for display
    now_malaysia = malaysia_now()
    event_date = event.date
    
    # Calculate event end time for display (not for auto-stopping)
    event_end = timezone.make_aware(
        timezone.datetime.combine(event_date, event.end_time)
    )
    event_end = timezone.localtime(event_end, timezone.get_current_timezone())
    
    # 🔹 Check if event should be active based on time
    # This is for display only - NOT for auto-stopping
    is_event_ended = now_malaysia > event_end
    should_be_active = event.is_active and not is_event_ended

    # 🔹 SIMPLIFIED QR GENERATION
    qr_image = None
    qr_url = None
    
    if event.is_active:  # Use the actual is_active status from database
        # Ensure token exists
        if not event.check_in_token:
            event.check_in_token = uuid.uuid4()
            event.save(update_fields=['check_in_token'])
            event.refresh_from_db()
        
        try:
            # Build check-in URL
            token_str = str(event.check_in_token)
            qr_url = f"{request.scheme}://{request.get_host()}/check-in/{event.id}/{token_str}/"
            
            # Generate QR code
            qr = qrcode.make(qr_url)
            buffer = BytesIO()
            qr.save(buffer, format="PNG")
            buffer.seek(0)
            
            # Encode as base64
            qr_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
        except Exception as e:
            # Log error but don't crash the page
            print(f"QR generation error for event {event.id}: {str(e)}")
            qr_image = None
            qr_url = None

    # 🔹 Get registration information for each attendee (optimized)
    attendee_list = []
    # Prefetch related data to avoid N+1 queries
    attendees_with_prefetch = attendees.prefetch_related(
        'registration',
        'event__applications'
    )
    
    for attendee in attendees_with_prefetch:
        # Check for registration
        try:
            registration = attendee.registration
            attendee.has_registration = True
            attendee.registration = registration
        except Registration.DoesNotExist:
            attendee.has_registration = False
            attendee.registration = None
        
        # Check for application (case-insensitive email match)
        try:
            application = Application.objects.get(
                event=event, 
                email__iexact=attendee.email
            )
            attendee.has_application = True
            attendee.application = application
        except Application.DoesNotExist:
            attendee.has_application = False
            attendee.application = None
        
        attendee_list.append(attendee)

    # 🔹 Analytics (using Malaysia time) - Fixed timezone handling
    try:
        attendance_by_hour = (
            attendees
            .annotate(
                malaysia_hour=ExtractHour(
                    timezone.localtime(F('attended_at'), timezone.get_current_timezone())
                )
            )
            .values('malaysia_hour')
            .annotate(count=Count('id'))
            .order_by('malaysia_hour')
        )
        
        # Format hours for display
        formatted_attendance = []
        for item in attendance_by_hour:
            hour = item['malaysia_hour']
            time_str = f"{hour:02d}:00"
            formatted_attendance.append({
                'hour': time_str,
                'count': item['count']
            })
    except Exception as e:
        formatted_attendance = []

    # 🔹 Feedback analytics
    feedbacks = event.feedbacks.all().order_by('-submitted_at')
    avg_rating = feedbacks.aggregate(Avg('rating'))['rating__avg'] or 0

    # 🔹 Calculate registration statistics for the summary cards (optimized)
    try:
        registrations = Registration.objects.filter(attendee__event=event)
        total_registered = registrations.count()
        
        # Get counts in a single query
        status_counts = registrations.aggregate(
            total_paid_count=Count('id', filter=Q(payment_status='DONE')),
            total_pending_count=Count('id', filter=Q(payment_status='PENDING'))
        )
        
        total_paid = status_counts['total_paid_count'] or 0
        total_pending = status_counts['total_pending_count'] or 0
        
        # Calculate total revenue efficiently
        revenue_data = registrations.aggregate(
            total_revenue=Sum(
                F('pre_registration_fee') + F('registration_fee')
            )
        )
        total_revenue = revenue_data['total_revenue'] or Decimal('0.00')
        
    except Exception as e:
        total_registered = 0
        total_paid = 0
        total_pending = 0
        total_revenue = Decimal('0.00')

    # 🔹 Applications count
    total_applications = Application.objects.filter(event=event).count()

    # 🔹 Today's check-ins (Malaysia time)
    today_start = timezone.localtime(
        timezone.now().replace(hour=0, minute=0, second=0, microsecond=0),
        timezone.get_current_timezone()
    )
    today_checkins = attendees.filter(
        attended_at__gte=today_start
    ).count()

    return render(request, 'event_detail.html', {
        'event': event,
        'attendees': attendee_list,
        'qr_image': qr_image,
        'qr_url': qr_url,
        'attendance_by_hour': formatted_attendance,
        'feedbacks': feedbacks,
        'avg_rating': round(avg_rating, 1),
        'total_registered': total_registered,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'total_revenue': f"{total_revenue:.2f}",
        'total_applications': total_applications,
        'today_checkins': today_checkins,
        'now_malaysia': now_malaysia,
        'event_end': event_end,
        'is_event_active': event.is_active,  # Use actual database value
        'is_event_ended': is_event_ended,    # For informational display
        'should_be_active': should_be_active, # For UI logic if needed
    })


@login_required
def toggle_event(request, event_id):
    if request.user.role != 'STAFF':
        return HttpResponseForbidden()

    event = get_object_or_404(Event, id=event_id)

    if not event.is_active:
        # Starting the event: Activate it and generate new token
        event.is_active = True
        event.check_in_token = uuid.uuid4()
        event.save()
    else:
        # Stopping the event: Keep token but mark as inactive
        event.is_active = False
        # DON'T change the token when stopping
        event.save()

    return redirect('event_detail', event_id=event.id)


def check_in(request, event_id, token):
    """
    Public check-in view for attendees to submit application forms
    """
    try:
        # Debug logging
        print(f"CHECK-IN ATTEMPT:")
        print(f"  Event ID: {event_id}")
        print(f"  Token received: {token}")
        print(f"  Token type: {type(token)}")
        
        # Get the event
        event = get_object_or_404(Event, id=event_id)
        
        # Check if event is active
        if not event.is_active:
            return render(request, 'error.html', {
                'title': 'Event Inactive',
                'error': 'This event is no longer active for check-in.',
                'event': event
            })
        
        # Check token - IMPORTANT: Compare as strings
        event_token_str = str(event.check_in_token)
        received_token_str = str(token)
        
        print(f"  Event token: {event_token_str}")
        print(f"  Token match: {event_token_str == received_token_str}")
        
        if event_token_str != received_token_str:
            return render(request, 'error.html', {
                'title': 'Invalid QR Code',
                'error': 'This QR code is invalid or has expired. Please ask the event organizer for a new QR code.',
                'event': event
            })
            
    except Event.DoesNotExist:
        return render(request, 'error.html', {
            'title': 'Event Not Found',
            'error': 'The event you are trying to check into does not exist.'
        })
    except Exception as e:
        print(f"Error in check-in validation: {e}")
        import traceback
        traceback.print_exc()
        return render(request, 'error.html', {
            'title': 'Error',
            'error': 'An error occurred while processing your check-in. Please try again.'
        })

    # Block staff/admin from checking in as attendees
    if request.user.is_authenticated and request.user.role in ['STAFF', 'ADMIN']:
        return render(request, 'error.html', {
            'title': 'Staff/Admin Access',
            'error': 'Staff and Admin users cannot check in as attendees. Please use a different browser or incognito mode.'
        })

    if request.method == 'POST':
        try:
            # Validate required fields
            required_fields = [
                'registration_officer', 'applied_programme', 'full_name',
                'address1', 'city', 'postcode', 'state', 'ic_no', 'email',
                'phone_no', 'marriage_status', 'father_name', 'father_ic',
                'father_phone', 'mother_name', 'mother_ic', 'mother_phone'
            ]
            
            for field in required_fields:
                if not request.POST.get(field, '').strip():
                    return render(request, 'check_in.html', {
                        'event': event,
                        'error': f'Please fill in all required fields. Missing: {field.replace("_", " ").title()}',
                        'form_data': request.POST
                    })

            # Handle SPM Total Credit - convert to integer
            spm_total_credit_str = request.POST.get('spm_total_credit', '0').strip()
            spm_total_credit = int(spm_total_credit_str) if spm_total_credit_str.isdigit() else 0
            
            # Handle father/mother dependants - convert to integer
            father_dependants_str = request.POST.get('father_dependants', '0').strip()
            father_dependants = int(father_dependants_str) if father_dependants_str.isdigit() else 0
            
            mother_dependants_str = request.POST.get('mother_dependants', '0').strip()
            mother_dependants = int(mother_dependants_str) if mother_dependants_str.isdigit() else 0

            # Get interest choices
            interest_choice1 = request.POST.get('interest_choice1', '').strip()
            interest_choice2 = request.POST.get('interest_choice2', '').strip()
            interest_choice3 = request.POST.get('interest_choice3', '').strip()
            
            # Create Application record with all fields
            application = Application.objects.create(
                event=event,
                registration_officer=request.POST['registration_officer'].strip(),
                applied_programme=request.POST['applied_programme'],
                full_name=request.POST['full_name'].strip(),
                address1=request.POST['address1'].strip(),
                address2=request.POST.get('address2', '').strip(),
                city=request.POST['city'].strip(),
                postcode=request.POST['postcode'].strip(),
                state=request.POST['state'].strip(),
                ic_no=request.POST['ic_no'].strip(),
                email=request.POST['email'].strip().lower(),
                phone_no=request.POST['phone_no'].strip(),
                marriage_status=request.POST['marriage_status'],
                spm_total_credit=spm_total_credit,
                father_name=request.POST['father_name'].strip(),
                father_ic=request.POST['father_ic'].strip(),
                father_phone=request.POST['father_phone'].strip(),
                father_occupation=request.POST.get('father_occupation', '').strip(),
                father_income=request.POST.get('father_income', '').strip(),
                father_dependants=father_dependants,
                mother_name=request.POST['mother_name'].strip(),
                mother_ic=request.POST['mother_ic'].strip(),
                mother_phone=request.POST['mother_phone'].strip(),
                mother_occupation=request.POST.get('mother_occupation', '').strip(),
                mother_income=request.POST.get('mother_income', '').strip(),
                mother_dependants=mother_dependants,
                interest_choice1=interest_choice1,
                interest_choice2=interest_choice2,
                interest_choice3=interest_choice3,
                interested_programme=(
                    f"1. {interest_choice1}\n"
                    f"2. {interest_choice2}\n"
                    f"3. {interest_choice3}"
                ).strip()
            )
            
            # Also mark as attendee for attendance tracking
            attendee, created = Attendee.objects.get_or_create(
                event=event,
                email=request.POST['email'].strip().lower(),
                defaults={
                    'name': request.POST['full_name'].strip(),
                    'phone_number': request.POST['phone_no'].strip()
                }
            )
            
            # If attendee already exists, update their info
            if not created:
                attendee.name = request.POST['full_name'].strip()
                attendee.phone_number = request.POST['phone_no'].strip()
                attendee.save()
            
            # Log successful check-in
            print(f"SUCCESSFUL CHECK-IN:")
            print(f"  Event: {event.title}")
            print(f"  Attendee: {attendee.name}")
            print(f"  Email: {attendee.email}")
            print(f"  Application ID: {application.id}")
            
            # Show success message
            return render(request, 'success.html', {
                'event': event,
                'application': application,
                'attendee': attendee
            })

        except IntegrityError as e:
            if 'attendees' in str(e):
                error_msg = 'You have already checked in to this event.'
            elif 'applications' in str(e):
                error_msg = 'You have already submitted an application for this event.'
            else:
                error_msg = 'An error occurred. Please try again.'
            
            print(f"Integrity Error in check-in: {e}")
            return render(request, 'check_in.html', {
                'event': event,
                'error': error_msg,
                'form_data': request.POST
            })
            
        except Exception as e:
            print(f"Error in check_in POST: {e}")
            import traceback
            traceback.print_exc()
            return render(request, 'check_in.html', {
                'event': event,
                'error': 'An unexpected error occurred. Please try again.',
                'form_data': request.POST
            })

    # GET request - show check-in form
    return render(request, 'check_in.html', {'event': event})


def qr_image(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    # Use check_in_token, not qr_token
    url = request.build_absolute_uri(
        f"/check-in/{event.id}/{event.check_in_token}/"
    )
    img = qrcode.make(url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


@login_required
def export_attendees_csv(request, event_id):
    if not request.user.is_active:
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    # Staff can only export their own events
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{event.title}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Email', 'Phone', 'Checked In At (Malaysia Time)'])

    for attendee in event.attendees.all():
        # Convert to Malaysia time for display
        malaysia_time = timezone.localtime(attendee.attended_at)
        writer.writerow([
            attendee.name,
            attendee.email,
            attendee.phone_number,
            malaysia_time.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response


@login_required
@require_GET
def get_attendee_details(request, attendee_id):
    """Get detailed information about an attendee including application form data"""
    attendee = get_object_or_404(Attendee, id=attendee_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and attendee.event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Try to get the corresponding application
        application = Application.objects.get(
            event=attendee.event,
            email__iexact=attendee.email
        )
        
        data = {
            'attendee': {
                'id': attendee.id,
                'name': attendee.name,
                'email': attendee.email,
                'phone_number': attendee.phone_number,
                'attended_at': timezone.localtime(attendee.attended_at).strftime('%Y-%m-%d %H:%M:%S'),
                'attended_at_display': timezone.localtime(attendee.attended_at).strftime('%I:%M %p'),
                'attended_date_display': timezone.localtime(attendee.attended_at).strftime('%b %d'),
            },
            'application': {
                'registration_officer': application.registration_officer,
                'applied_programme': application.applied_programme,
                'full_name': application.full_name,
                'address1': application.address1,
                'address2': application.address2,
                'city': application.city,
                'postcode': application.postcode,
                'state': application.state,
                'ic_no': application.ic_no,
                'email': application.email,
                'phone_no': application.phone_no,
                'marriage_status': application.marriage_status,
                'spm_total_credit': application.spm_total_credit,
                'father_name': application.father_name,
                'father_ic': application.father_ic,
                'father_phone': application.father_phone,
                'father_occupation': application.father_occupation,
                'father_income': application.father_income,
                'father_dependants': application.father_dependants,
                'mother_name': application.mother_name,
                'mother_ic': application.mother_ic,
                'mother_phone': application.mother_phone,
                'mother_occupation': application.mother_occupation,
                'mother_income': application.mother_income,
                'mother_dependants': application.mother_dependants,
                'interest_choice1': application.interest_choice1,
                'interest_choice2': application.interest_choice2,
                'interest_choice3': application.interest_choice3,
                'interested_programme': application.interested_programme,
                'submitted_at': timezone.localtime(application.submitted_at).strftime('%Y-%m-%d %H:%M:%S'),
            }
        }
        
        return JsonResponse(data)
        
    except Application.DoesNotExist:
        # If no application found, return basic attendee info
        data = {
            'attendee': {
                'id': attendee.id,
                'name': attendee.name,
                'email': attendee.email,
                'phone_number': attendee.phone_number,
                'attended_at': timezone.localtime(attendee.attended_at).strftime('%Y-%m-%d %H:%M:%S'),
                'attended_at_display': timezone.localtime(attendee.attended_at).strftime('%I:%M %p'),
                'attended_date_display': timezone.localtime(attendee.attended_at).strftime('%b %d'),
            },
            'application': None
        }
        return JsonResponse(data)


@login_required
def admin_dashboard(request):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role == 'ADMIN':
        events = Event.objects.all()
    else:
        events = Event.objects.filter(assigned_staff=request.user)

    return render(request, 'dashboard.html', {'events': events})


@login_required
def manage_staff(request):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Admins only")

    staff_users = User.objects.filter(role='STAFF')
    active_staff_count = staff_users.filter(is_active=True).count()
    inactive_staff_count = staff_users.filter(is_active=False).count()
    total_events = Event.objects.count()

    return render(request, 'manage_staff.html', {
        'staff_users': staff_users,
        'active_staff_count': active_staff_count,
        'inactive_staff_count': inactive_staff_count,
        'total_events': total_events
    })


@login_required
def assign_staff(request, event_id):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Admins only")

    event = get_object_or_404(Event, id=event_id)
    staff_users = User.objects.filter(role='STAFF')

    if request.method == 'POST':
        selected_staff = request.POST.getlist('staff')
        event.assigned_staff.set(selected_staff)
        messages.success(request, "Staff assigned successfully")
        return redirect('event_detail', event_id=event.id)

    return render(request, 'assign_staff.html', {
        'event': event,
        'staff_users': staff_users
    })


@login_required
def toggle_staff_status(request, user_id):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Admins only")

    staff = get_object_or_404(User, id=user_id, role='STAFF')
    staff.is_active = not staff.is_active
    staff.save()

    messages.success(
        request,
        f"Staff '{staff.username}' {'enabled' if staff.is_active else 'disabled'}"
    )

    return redirect('manage_staff')


def submit_feedback(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if request.method == 'POST':
        try:
            Feedback.objects.create(
                event=event,
                name=request.POST['name'],
                email=request.POST['email'],
                rating=request.POST['rating'],
                comment=request.POST.get('comment', '')
            )
            return render(request, 'feedback_success.html')

        except IntegrityError:
            return render(request, 'feedback.html', {
                'event': event,
                'error': 'You already submitted feedback.'
            })

    return render(request, 'feedback.html', {'event': event})


# ============================
# REAL-TIME API ENDPOINTS
# ============================
@login_required
@require_GET
def get_realtime_attendees(request, event_id):
    """API endpoint for real-time attendee updates"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Get last update timestamp from request
    last_update = request.GET.get('last_update')
    
    # Get attendees
    if last_update:
        try:
            last_update_dt = timezone.datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            attendees = event.attendees.filter(attended_at__gt=last_update_dt)
        except:
            attendees = event.attendees.all()
    else:
        attendees = event.attendees.all()
    
    # Get latest timestamp for next request
    latest_timestamp = None
    if attendees.exists():
        latest_timestamp = attendees.first().attended_at
    
    # Format response
    attendees_data = []
    for attendee in attendees.order_by('-attended_at'):
        malaysia_time = timezone.localtime(attendee.attended_at)
        attendees_data.append({
            'id': attendee.id,
            'name': attendee.full_name,
            'email': attendee.email,
            'phone': attendee.phone_no,
            'attended_at': malaysia_time.strftime('%Y-%m-%d %H:%M:%S'),
            'attended_at_display': malaysia_time.strftime('%I:%M %p'),
            'attended_date_display': malaysia_time.strftime('%b %d')
        })
    
    # Get statistics
    total_attendees = event.attendees.count()
    
    # Check if event has ended
    now_malaysia = malaysia_now()
    event_end = timezone.make_aware(
        timezone.datetime.combine(event.date, event.end_time)
    )
    event_end = timezone.localtime(event_end)
    is_event_ended = now_malaysia > event_end
    
    response_data = {
        'success': True,
        'event_id': event_id,
        'event_title': event.title,
        'event_active': event.is_active,
        'event_ended': is_event_ended,
        'attendees': attendees_data,
        'total_attendees': total_attendees,
        'latest_timestamp': latest_timestamp.isoformat() if latest_timestamp else None,
        'malaysia_time_now': malaysia_now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return JsonResponse(response_data)


@login_required
@require_GET
def get_realtime_stats(request, event_id):
    """API endpoint for real-time statistics updates"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Get statistics
    total_attendees = event.attendees.count()
    
    # Get hourly attendance (last 6 hours)
    six_hours_ago = malaysia_now() - timedelta(hours=6)
    recent_attendees = event.attendees.filter(attended_at__gte=six_hours_ago)
    
    # Calculate hourly distribution
    hourly_data = {}
    for i in range(6):
        hour_start = malaysia_now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=i)
        hour_end = hour_start + timedelta(hours=1)
        hour_key = hour_start.strftime('%H:00')
        
        count = recent_attendees.filter(
            attended_at__gte=hour_start,
            attended_at__lt=hour_end
        ).count()
        hourly_data[hour_key] = count
    
    # Get latest attendee
    latest_attendee = None
    if event.attendees.exists():
        latest = event.attendees.latest('attended_at')
        malaysia_time = timezone.localtime(latest.attended_at)
        latest_attendee = {
            'name': latest.name,
            'time': malaysia_time.strftime('%I:%M %p')
        }
    
    # Feedback stats
    feedbacks = event.feedbacks.all()
    avg_rating = feedbacks.aggregate(Avg('rating'))['rating__avg'] or 0
    feedback_count = feedbacks.count()
    
    response_data = {
        'success': True,
        'event_id': event_id,
        'total_attendees': total_attendees,
        'hourly_attendance': hourly_data,
        'latest_attendee': latest_attendee,
        'average_rating': round(float(avg_rating), 1),
        'feedback_count': feedback_count,
        'malaysia_time': malaysia_now().strftime('%I:%M %p')
    }
    
    return JsonResponse(response_data)


@login_required
@require_GET
def get_attendee_registration(request, attendee_id):
    """Get registration data for an attendee"""
    attendee = get_object_or_404(Attendee, id=attendee_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and attendee.event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        registration = Registration.objects.get(attendee=attendee)
        data = {
            'registration': {
                'id': registration.id,
                'course': registration.course,
                'college': registration.college,
                'register_date': registration.register_date.strftime('%Y-%m-%d') if registration.register_date else '',
                'pre_registration_fee': str(registration.pre_registration_fee),
                'registration_fee': str(registration.registration_fee),
                'payment_status': registration.payment_status,
                'remark': registration.remark,
                'closer': registration.closer,
                'referral_number': registration.referral_number,
                'total_fee': str(registration.total_fee()),
                'created_at': timezone.localtime(registration.created_at).strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': timezone.localtime(registration.updated_at).strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        return JsonResponse(data)
    except Registration.DoesNotExist:
        return JsonResponse({'registration': None})

@login_required
@csrf_exempt
def save_registration(request):
    """Save or update registration data with better validation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    attendee_id = request.POST.get('attendee_id')
    if not attendee_id:
        return JsonResponse({'error': 'Attendee ID required'}, status=400)
    
    try:
        attendee = Attendee.objects.get(id=attendee_id)
    except Attendee.DoesNotExist:
        return JsonResponse({'error': 'Attendee not found'}, status=404)
    
    # Check permissions
    if request.user.role == 'STAFF' and attendee.event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Validate and parse data
        course = request.POST.get('course', '').strip()
        college = request.POST.get('college', '').strip()
        closer = request.POST.get('closer', '').strip()
        
        # Required field validation
        if not course:
            return JsonResponse({'error': 'Course is required'}, status=400)
        if not college:
            return JsonResponse({'error': 'College is required'}, status=400)
        if not closer:
            return JsonResponse({'error': 'Closer name is required'}, status=400)
        
        # Parse date
        register_date_str = request.POST.get('register_date', '')
        if not register_date_str:
            return JsonResponse({'error': 'Registration date is required'}, status=400)
        
        try:
            # Accept multiple date formats
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    register_date = datetime.strptime(register_date_str, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        except (ValueError, TypeError) as e:
            return JsonResponse({'error': f'Invalid date: {str(e)}'}, status=400)
        
        # FIX: Use Malaysia time for date validation
        malaysia_today = malaysia_now().date()
        
        # Validate date is not in future (using Malaysia time)
        if register_date > malaysia_today:
            return JsonResponse({'error': 'Registration date cannot be in the future'}, status=400)
        
        # ALSO: Validate date is not too far in the past (optional)
        # Let's say not more than 30 days ago
        thirty_days_ago = malaysia_today - timedelta(days=30)
        if register_date < thirty_days_ago:
            return JsonResponse({'error': 'Registration date cannot be more than 30 days ago'}, status=400)
        
        # Parse fees with validation
        try:
            pre_registration_fee = Decimal(request.POST.get('pre_registration_fee', '0') or '0')
            registration_fee = Decimal(request.POST.get('registration_fee', '0') or '0')
            
            if pre_registration_fee < 0:
                return JsonResponse({'error': 'Pre-registration fee cannot be negative'}, status=400)
            if registration_fee < 0:
                return JsonResponse({'error': 'Registration fee cannot be negative'}, status=400)
        except (ValueError, TypeError, InvalidOperation) as e:  # InvalidOperation needs to be imported
            return JsonResponse({'error': f'Invalid fee format: {str(e)}'}, status=400)
        
        # Get or create registration
        registration, created = Registration.objects.get_or_create(
            attendee=attendee,
            defaults={
                'course': course,
                'college': college,
                'register_date': register_date,
                'pre_registration_fee': pre_registration_fee,
                'registration_fee': registration_fee,
                'payment_status': request.POST.get('payment_status', 'PENDING'),
                'remark': request.POST.get('remark', '').strip(),
                'closer': closer,
                'referral_number': request.POST.get('referral_number', '').strip()
            }
        )
        
        # Update if exists
        if not created:
            registration.course = course
            registration.college = college
            registration.register_date = register_date
            registration.pre_registration_fee = pre_registration_fee
            registration.registration_fee = registration_fee
            registration.payment_status = request.POST.get('payment_status', 'PENDING')
            registration.remark = request.POST.get('remark', '').strip()
            registration.closer = closer
            registration.referral_number = request.POST.get('referral_number', '').strip()
            registration.save()
        
        # Prepare response data
        response_data = {
            'success': True,
            'message': 'Registration saved successfully',
            'registration': {
                'id': registration.id,
                'course': registration.course,
                'college': registration.college,
                'register_date': registration.register_date.strftime('%Y-%m-%d'),
                'pre_registration_fee': str(registration.pre_registration_fee),
                'registration_fee': str(registration.registration_fee),
                'total_fee': str(registration.total_fee()),
                'payment_status': registration.payment_status,
                'closer': registration.closer,
                'referral_number': registration.referral_number
            }
        }
        
        return JsonResponse(response_data)
        
    except IntegrityError as e:
        return JsonResponse({'error': f'Database error: {str(e)}'}, status=500)
    except Exception as e:
        print(f"Error saving registration: {e}")
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)

@login_required
@require_GET
def get_registration_stats(request, event_id):
    """Get registration statistics for an event"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Get all registrations for this event
    registrations = Registration.objects.filter(attendee__event=event)
    
    total_registered = registrations.count()
    total_paid = registrations.filter(payment_status='DONE').count()
    total_pending = registrations.filter(payment_status='PENDING').count()
    
    # Calculate total revenue
    total_revenue = registrations.aggregate(
        total=Sum(models.F('pre_registration_fee') + models.F('registration_fee'))
    )['total'] or Decimal('0.00')
    
    return JsonResponse({
        'success': True,
        'total_registered': total_registered,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'total_revenue': f"{total_revenue:.2f}"
    })

@login_required
@require_GET
def get_full_registration_stats(request, event_id):
    """Get comprehensive registration statistics with charts data"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Get all registrations for this event
    registrations = Registration.objects.filter(attendee__event=event)
    
    # Basic stats
    total_registered = registrations.count()
    total_paid = registrations.filter(payment_status='DONE').count()
    total_pending = registrations.filter(payment_status='PENDING').count()
    
    # Calculate total revenue
    total_revenue = registrations.aggregate(
        total=Sum(models.F('pre_registration_fee') + models.F('registration_fee'))
    )['total'] or Decimal('0.00')
    
    # Top courses
    top_courses = registrations.values('course').annotate(
        count=models.Count('id'),
        revenue=Sum(models.F('pre_registration_fee') + models.F('registration_fee'))
    ).order_by('-count')[:5]
    
    # Top closers
    top_closers = registrations.values('closer').annotate(
        count=models.Count('id'),
        revenue=Sum(models.F('pre_registration_fee') + models.F('registration_fee'))
    ).order_by('-count')[:5]
    
    # Timeline (last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    timeline_data = registrations.filter(
        created_at__gte=seven_days_ago
    ).extra({
        'date': "DATE(created_at)"
    }).values('date').annotate(
        count=models.Count('id')
    ).order_by('date')
    
    return JsonResponse({
        'success': True,
        'total_registered': total_registered,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'total_revenue': f"{total_revenue:.2f}",
        'charts': {
            'top_courses': [
                {'label': item['course'] or 'Unknown', 'value': item['count'], 'revenue': float(item['revenue'] or 0)}
                for item in top_courses
            ],
            'top_closers': [
                {'label': item['closer'] or 'Unknown', 'value': item['count'], 'revenue': float(item['revenue'] or 0)}
                for item in top_closers
            ],
            'timeline': [
                {'date': item['date'].strftime('%Y-%m-%d'), 'count': item['count']}
                for item in timeline_data
            ]
        }
    })

@login_required
def export_registrations_csv(request, event_id):
    """Export registration data as CSV"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="registrations_{event.title}_{date.today()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Attendee Name', 'Email', 'Phone', 
        'Course', 'College', 'Registration Date',
        'Pre-Registration Fee (RM)', 'Registration Fee (RM)', 'Total Fee (RM)',
        'Payment Status', 'Closer', 'Referral Number', 'Remarks',
        'Registered At', 'Last Updated'
    ])
    
    registrations = Registration.objects.filter(attendee__event=event).select_related('attendee')
    
    for reg in registrations:
        writer.writerow([
            reg.attendee.name,
            reg.attendee.email,
            reg.attendee.phone_number,
            reg.course,
            reg.college,
            reg.register_date.strftime('%Y-%m-%d') if reg.register_date else '',
            str(reg.pre_registration_fee),
            str(reg.registration_fee),
            str(reg.total_fee()),
            reg.get_payment_status_display(),
            reg.closer,
            reg.referral_number,
            reg.remark,
            timezone.localtime(reg.created_at).strftime('%Y-%m-%d %H:%M:%S'),
            timezone.localtime(reg.updated_at).strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response

@login_required
def export_registrations_pdf(request, event_id):
    """Enhanced PDF export with better formatting"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()
    
    # Get all registrations
    registrations = Registration.objects.filter(attendee__event=event).select_related('attendee')
    
    # Calculate statistics
    total_registered = registrations.count()
    total_paid = registrations.filter(payment_status='DONE').count()
    total_pending = registrations.filter(payment_status='PENDING').count()
    
    # Calculate revenue
    total_revenue = Decimal('0.00')
    for reg in registrations:
        total_revenue += (reg.pre_registration_fee or Decimal('0.00')) + (reg.registration_fee or Decimal('0.00'))
    
    # Get top courses
    from django.db.models import Count
    top_courses = registrations.values('course').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Create PDF in memory using SimpleDocTemplate for better tables
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=inch/2,
        leftMargin=inch/2,
        topMargin=inch/2,
        bottomMargin=inch/2
    )
    
    styles = getSampleStyleSheet()
    
    # Create custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=12,
        alignment=1  # Center
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=6,
        textColor=colors.grey
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.white,
        alignment=1
    )
    
    normal_style = styles['Normal']
    
    # Build story (content)
    story = []
    
    # Title
    story.append(Paragraph(f"<b>REGISTRATION REPORT</b>", title_style))
    story.append(Paragraph(f"Event: {event.title}", subtitle_style))
    story.append(Paragraph(f"Venue: {event.venue} | Date: {event.date}", styles['Normal']))
    story.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} by {request.user.get_full_name() or request.user.username}", styles['Italic']))
    story.append(Spacer(1, 20))
    
    # Summary Statistics
    summary_data = [
        ['Total Registrations', 'Payment Done', 'Payment Pending', 'Total Revenue'],
        [str(total_registered), str(total_paid), str(total_pending), f"RM {total_revenue:.2f}"]
    ]
    
    summary_table = Table(summary_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8f9fa')),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.black),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 20))
    
    # Top Courses
    if top_courses:
        story.append(Paragraph("<b>Top 5 Courses by Registration</b>", styles['Heading3']))
        story.append(Spacer(1, 5))
        
        course_data = [['Rank', 'Course', 'Registrations', 'Percentage']]
        for i, course in enumerate(top_courses, 1):
            percentage = (course['count'] / total_registered * 100) if total_registered > 0 else 0
            course_data.append([
                str(i),
                course['course'] or 'Unknown',
                str(course['count']),
                f"{percentage:.1f}%"
            ])
        
        course_table = Table(course_data, colWidths=[0.5*inch, 3*inch, 1.5*inch, 1.5*inch])
        course_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Left align course names
        ]))
        
        story.append(course_table)
        story.append(Spacer(1, 20))
    
    # Detailed Registration Table
    story.append(Paragraph("<b>Detailed Registration Records</b>", styles['Heading3']))
    story.append(Spacer(1, 5))
    
    # Create table data
    table_data = [['No.', 'Attendee', 'Course', 'College', 'Reg Date', 'Total Fee', 'Payment', 'Closer']]
    
    for i, reg in enumerate(registrations, 1):
        table_data.append([
            str(i),
            reg.attendee.name[:30] if reg.attendee.name else 'N/A',
            reg.course[:20] if reg.course else 'N/A',
            reg.college[:15] if reg.college else 'N/A',
            reg.register_date.strftime('%d/%m/%Y') if reg.register_date else 'N/A',
            f"RM {reg.total_fee():.2f}",
            reg.get_payment_status_display(),
            reg.closer[:15] if reg.closer else 'N/A'
        ])
    
    # Add total row
    if registrations:
        table_data.append([
            '', '', '', '', 'TOTAL:',
            f"RM {total_revenue:.2f}",
            '', ''
        ])
    
    # Create table
    col_widths = [0.4*inch, 1.8*inch, 1.5*inch, 1.2*inch, 1*inch, 1*inch, 1*inch, 1.2*inch]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Style the table
    table.setStyle(TableStyle([
        # Header style
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        
        # Row colors alternating
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),  # Exclude total row from grid
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        
        # Align columns
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # No. column
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Date column
        ('ALIGN', (5, 1), (5, -1), 'RIGHT'),   # Fee column
        ('ALIGN', (6, 1), (6, -1), 'CENTER'),  # Payment column
        
        # Total row style
        ('BACKGROUND', (4, -1), (5, -1), colors.HexColor('#f8f9fa')),
        ('TEXTCOLOR', (4, -1), (5, -1), colors.black),
        ('FONTNAME', (4, -1), (5, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (4, -1), (5, -1), 9),
        ('BOX', (4, -1), (5, -1), 0.5, colors.grey),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 20))
    
    # Payment Status Summary
    if total_registered > 0:
        paid_percentage = (total_paid / total_registered * 100)
        pending_percentage = (total_pending / total_registered * 100)
        
        status_data = [
            ['Payment Status', 'Count', 'Percentage'],
            ['Done', str(total_paid), f"{paid_percentage:.1f}%"],
            ['Pending', str(total_pending), f"{pending_percentage:.1f}%"]
        ]
        
        status_table = Table(status_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#d4edda')),
            ('BACKGROUND', (0, 2), (0, 2), colors.HexColor('#fff3cd')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        
        story.append(status_table)
        story.append(Spacer(1, 20))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Create response
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="registration_report_{event.id}_{datetime.now().strftime("%Y%m%d")}.pdf"'
    
    return response


@login_required
def export_comprehensive_report(request, event_id):
    """Export comprehensive report including attendees, applications, and registrations"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()
    
    try:
        # Get all data
        attendees = Attendee.objects.filter(event=event).select_related()
        applications = Application.objects.filter(event=event)
        registrations = Registration.objects.filter(attendee__event=event).select_related('attendee')
        
        # Create Excel file with multiple sheets
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Summary
            summary_data = {
                'Event Information': [
                    'Event Title', 'Venue', 'Date', 
                    'Start Time', 'End Time', 'Status',
                    'Total Attendees', 'Total Applications', 'Total Registrations'
                ],
                'Value': [
                    event.title,
                    event.venue,
                    event.date.strftime('%Y-%m-%d'),
                    event.start_time.strftime('%H:%M'),
                    event.end_time.strftime('%H:%M'),
                    'Active' if event.is_active else 'Inactive',
                    attendees.count(),
                    applications.count(),
                    registrations.count()
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Sheet 2: All Attendees
            if attendees.exists():
                attendees_data = []
                for attendee in attendees:
                    # Try to get application
                    try:
                        app = applications.get(email__iexact=attendee.email)
                        has_application = 'Yes'
                        applied_programme = app.applied_programme
                    except Application.DoesNotExist:
                        has_application = 'No'
                        applied_programme = ''
                    
                    # Try to get registration
                    try:
                        reg = registrations.get(attendee=attendee)
                        has_registration = 'Yes'
                        course = reg.course
                        payment_status = reg.get_payment_status_display()
                    except Registration.DoesNotExist:
                        has_registration = 'No'
                        course = ''
                        payment_status = ''
                    
                    attendees_data.append({
                        'Name': attendee.name,
                        'Email': attendee.email,
                        'Phone': attendee.phone_number or '',
                        'Checked In At': timezone.localtime(attendee.attended_at).strftime('%Y-%m-%d %H:%M:%S'),
                        'Has Application': has_application,
                        'Applied Programme': applied_programme,
                        'Has Registration': has_registration,
                        'Course': course,
                        'Payment Status': payment_status
                    })
                
                attendees_df = pd.DataFrame(attendees_data)
                attendees_df.to_excel(writer, sheet_name='All Attendees', index=False)
            
            # Sheet 3: Applications
            if applications.exists():
                apps_data = []
                for app in applications:
                    apps_data.append({
                        'Full Name': app.full_name,
                        'IC Number': app.ic_no,
                        'Email': app.email,
                        'Phone': app.phone_no,
                        'Applied Programme': app.applied_programme,
                        'SPM Credits': app.spm_total_credit,
                        'Father Name': app.father_name,
                        'Mother Name': app.mother_name,
                        'Submitted At': timezone.localtime(app.submitted_at).strftime('%Y-%m-%d %H:%M:%S')
                    })
                
                apps_df = pd.DataFrame(apps_data)
                apps_df.to_excel(writer, sheet_name='Applications', index=False)
            
            # Sheet 4: Registrations
            if registrations.exists():
                regs_data = []
                for reg in registrations:
                    regs_data.append({
                        'Attendee Name': reg.attendee.name,
                        'Email': reg.attendee.email,
                        'Course': reg.course,
                        'College': reg.college,
                        'Registration Date': reg.register_date.strftime('%Y-%m-%d') if reg.register_date else '',
                        'Pre-Reg Fee (RM)': float(reg.pre_registration_fee or 0),
                        'Reg Fee (RM)': float(reg.registration_fee or 0),
                        'Total Fee (RM)': float(reg.total_fee()),
                        'Payment Status': reg.get_payment_status_display(),
                        'Closer': reg.closer,
                        'Referral Number': reg.referral_number or '',
                        'Remarks': reg.remark or ''
                    })
                
                regs_df = pd.DataFrame(regs_data)
                regs_df.to_excel(writer, sheet_name='Registrations', index=False)
            
            # Sheet 5: Statistics
            stats_data = {
                'Category': [
                    'Total Attendees',
                    'With Applications',
                    'Without Applications',
                    'Total Registrations',
                    'Payment Completed',
                    'Payment Pending',
                    'Total Revenue (RM)',
                    'Average Fee per Registration (RM)'
                ],
                'Count': [
                    attendees.count(),
                    applications.count(),
                    attendees.count() - applications.count(),
                    registrations.count(),
                    registrations.filter(payment_status='DONE').count(),
                    registrations.filter(payment_status='PENDING').count(),
                    float(sum([reg.total_fee() for reg in registrations])),
                    float(sum([reg.total_fee() for reg in registrations]) / registrations.count()) if registrations.count() > 0 else 0
                ]
            }
            stats_df = pd.DataFrame(stats_data)
            stats_df.to_excel(writer, sheet_name='Statistics', index=False)
            
            # Auto-adjust column widths for all sheets
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{event.title}_comprehensive_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        
        return response
        
    except Exception as e:
        print(f"Error generating comprehensive report: {e}")
        messages.error(request, f"Error generating report: {str(e)}")
        return redirect('event_detail', event_id=event_id)