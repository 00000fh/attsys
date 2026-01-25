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
from PIL import Image, ImageDraw, ImageFont
import re
from django.urls import reverse


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


def success_page(request):
    return render(request, 'success.html')


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
        try:
            # Get form data
            title = request.POST.get('title', '').strip()
            venue = request.POST.get('venue', '').strip()
            state = request.POST.get('state', '')
            custom_state = request.POST.get('custom_state', '').strip()
            date_str = request.POST.get('date', '')
            start_time_str = request.POST.get('start_time', '')
            end_time_str = request.POST.get('end_time', '')
            description = request.POST.get('description', '').strip()
            
            # Basic validation
            if not all([title, venue, state, date_str, start_time_str, end_time_str]):
                messages.error(request, 'Please fill in all required fields')
                return render(request, 'create_event.html', {'form_data': request.POST})
            
            # Handle custom state
            if state == 'OTHER' and custom_state:
                # For 'OTHER', store the custom state value in custom_state field
                # Keep state as 'OTHER'
                pass  # We'll use custom_state as is
            else:
                # For regular states, clear custom_state
                custom_state = ''
            
            # Convert date and time
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_time = datetime.strptime(start_time_str, '%H:%M').time()
                end_time = datetime.strptime(end_time_str, '%H:%M').time()
            except ValueError:
                messages.error(request, 'Invalid date or time format')
                return render(request, 'create_event.html', {'form_data': request.POST})
            
            # Validate date is not in past
            if date < date.today():
                messages.error(request, 'Event date cannot be in the past')
                return render(request, 'create_event.html', {'form_data': request.POST})
            
            # Validate time order
            if start_time >= end_time:
                messages.error(request, 'End time must be after start time')
                return render(request, 'create_event.html', {'form_data': request.POST})
            
            # Create event
            event = Event.objects.create(
                title=title,
                venue=venue,
                state=state,
                custom_state=custom_state,
                date=date,
                start_time=start_time,
                end_time=end_time,
                description=description,
                created_by=request.user
            )
            
            messages.success(request, f'Event "{event.title}" created successfully!')
            return redirect('event_detail', event_id=event.id)
            
        except Exception as e:
            print(f"Error creating event: {e}")
            messages.error(request, f'Error creating event: {str(e)}')
            return render(request, 'create_event.html', {'form_data': request.POST})

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
    
    # 🔹 Calculate total attendees count
    total_attendees_count = attendees.count()
    
    # 🔹 Get last check-in info
    last_checkin = None
    last_checkin_time = None
    if attendees.exists():
        last_checkin = attendees.first()  # Already ordered by -attended_at
        last_checkin_time = timezone.localtime(last_checkin.attended_at)

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
            qr_url = f"{request.scheme}://{request.get_host()}/attsys/check-in/{event.id}/{token_str}/"
            
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

    # 🔹 Format last check-in time for display
    last_checkin_display = None
    last_checkin_date_display = None
    if last_checkin_time:
        last_checkin_display = last_checkin_time.strftime('%I:%M %p')
        last_checkin_date_display = last_checkin_time.strftime('%b %d')

    return render(request, 'event_detail.html', {
        'event': event,
        'attendees': attendee_list,  # List of attendees with extra data
        'total_attendees_count': total_attendees_count,  # Total count for stats
        'last_checkin': last_checkin,  # Last attendee object
        'last_checkin_time': last_checkin_time,  # Last check-in time as datetime
        'last_checkin_display': last_checkin_display,  # Formatted time "03:45 PM"
        'last_checkin_date_display': last_checkin_date_display,  # Formatted date "Jan 22"
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
        # Get the event
        event = get_object_or_404(Event, id=event_id)
        
        # Check if event is active
        if not event.is_active:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'This event is no longer active for check-in.'
                }, status=400)
            return render(request, 'error.html', {
                'title': 'Event Inactive',
                'error': 'This event is no longer active for check-in.',
                'event': event
            })
        
        # Check token
        if str(event.check_in_token) != str(token):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid check-in token.'
                }, status=400)
            return render(request, 'error.html', {
                'title': 'Invalid Token',
                'error': 'The check-in link is invalid or expired.',
                'event': event
            })
            
    except Event.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'The event you are trying to check into does not exist.'
            }, status=404)
        return render(request, 'error.html', {
            'title': 'Event Not Found',
            'error': 'The event you are trying to check into does not exist.'
        })
    except Exception as e:
        print(f"Error in check-in validation: {e}")
        import traceback
        traceback.print_exc()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while processing your check-in.'
            }, status=500)
        return render(request, 'error.html', {
            'title': 'Error',
            'error': 'An error occurred while processing your check-in. Please try again.'
        })

    # Block staff/admin from checking in as attendees
    if request.user.is_authenticated and request.user.role in ['STAFF', 'ADMIN']:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Staff and Admin users cannot check in as attendees.'
            }, status=403)
        return render(request, 'error.html', {
            'title': 'Staff/Admin Access',
            'error': 'Staff and Admin users cannot check in as attendees. Please use a different browser or incognito mode.'
        })

    if request.method == 'POST':
        try:
            # Required fields
            required_fields = [
                'registration_officer', 'applied_programme', 'full_name',
                'city', 'postcode', 'state', 'ic_no', 'email',
                'phone_no', 'marriage_status', 'father_name', 'father_ic',
                'father_phone', 'father_occupation', 'mother_name', 'mother_ic',
                'mother_phone', 'mother_occupation'
            ]
            
            # Collect errors for validation
            errors = {}
            for field in required_fields:
                value = request.POST.get(field, '').strip()
                if not value:
                    errors[field] = f'{field.replace("_", " ").title()} is required'
            
            # If there are validation errors
            if errors:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': 'Please fill in all required fields.',
                        'field_errors': errors
                    }, status=400)
                else:
                    first_error = list(errors.values())[0] if errors else 'Please fill in all required fields.'
                    return render(request, 'check_in.html', {
                        'event': event,
                        'error': first_error,
                        'form_data': request.POST
                    })

            # Handle SPM Total Credit
            spm_total_credit_str = request.POST.get('spm_total_credit', '0').strip()
            try:
                spm_total_credit = int(spm_total_credit_str) if spm_total_credit_str.isdigit() else 0
            except ValueError:
                spm_total_credit = 0
            
            # Handle father/mother dependants
            father_dependants_str = request.POST.get('father_dependants', '0').strip()
            try:
                father_dependants = int(father_dependants_str) if father_dependants_str.isdigit() else 0
            except ValueError:
                father_dependants = 0
            
            mother_dependants_str = request.POST.get('mother_dependants', '0').strip()
            try:
                mother_dependants = int(mother_dependants_str) if mother_dependants_str.isdigit() else 0
            except ValueError:
                mother_dependants = 0
            
            # Format empty values as dash for optional fields
            def format_optional_value(value):
                if not value or not str(value).strip():
                    return '-'
                return str(value).strip()

            # Get interest choices
            interest_choice1 = format_optional_value(request.POST.get('interest_choice1', ''))
            interest_choice2 = format_optional_value(request.POST.get('interest_choice2', ''))
            interest_choice3 = format_optional_value(request.POST.get('interest_choice3', ''))
            
            # Get father and mother occupation
            father_occupation = request.POST.get('father_occupation', '').strip()
            mother_occupation = request.POST.get('mother_occupation', '').strip()
            
            # Format other optional fields
            father_income = format_optional_value(request.POST.get('father_income', ''))
            mother_income = format_optional_value(request.POST.get('mother_income', ''))
            
            # Email validation
            email = request.POST['email'].strip().lower()
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': 'Please enter a valid email address.'
                    }, status=400)
                else:
                    return render(request, 'check_in.html', {
                        'event': event,
                        'error': 'Please enter a valid email address.',
                        'form_data': request.POST
                    })
            
            # Check if already submitted
            existing_application = Application.objects.filter(
                event=event,
                email__iexact=email
            ).exists()
            
            if existing_application:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': 'You have already submitted an application for this event.'
                    }, status=400)
                else:
                    return render(request, 'check_in.html', {
                        'event': event,
                        'error': 'You have already submitted an application for this event.',
                        'form_data': request.POST
                    })
            
            # Create Application record
            application = Application.objects.create(
                event=event,
                registration_officer=request.POST['registration_officer'].strip(),
                applied_programme=request.POST['applied_programme'],
                full_name=request.POST['full_name'].strip(),
                address1=request.POST['address1'].strip(),
                city=request.POST['city'].strip(),
                postcode=request.POST['postcode'].strip(),
                state=request.POST['state'].strip(),
                ic_no=request.POST['ic_no'].strip(),
                email=email,
                phone_no=request.POST['phone_no'].strip(),
                marriage_status=request.POST['marriage_status'],
                spm_total_credit=spm_total_credit,
                father_name=request.POST['father_name'].strip(),
                father_ic=request.POST['father_ic'].strip(),
                father_phone=request.POST['father_phone'].strip(),
                father_occupation=father_occupation,
                father_income=father_income,
                father_dependants=father_dependants,
                mother_name=request.POST['mother_name'].strip(),
                mother_ic=request.POST['mother_ic'].strip(),
                mother_phone=request.POST['mother_phone'].strip(),
                mother_occupation=mother_occupation,
                mother_income=mother_income,
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
                email=email,
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
            
            # ================================================
            # CRITICAL FIX: Force immediate redirect for ALL requests
            # ================================================
            success_url = '/attsys/success/'  # Direct URL to success page
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # For AJAX requests, return a success with NO redirect URL
                # This will let JavaScript handle clearing the form
                return JsonResponse({
                    'success': True,
                    'message': 'Application submitted successfully!',
                    'application_id': application.id,
                    'attendee_id': attendee.id,
                    # NO redirect_url - let JS handle clearing form first
                })
            
            # For non-AJAX requests, redirect immediately
            return redirect(success_url)

        except IntegrityError as e:
            error_msg = 'You have already submitted an application for this event.'
            print(f"Integrity Error in check-in: {e}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_msg
                }, status=400)
            else:
                return render(request, 'check_in.html', {
                    'event': event,
                    'error': error_msg,
                    'form_data': request.POST
                })
            
        except Exception as e:
            print(f"Error in check_in POST: {e}")
            import traceback
            traceback.print_exc()
            
            error_msg = 'An unexpected error occurred. Please try again.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_msg
                }, status=500)
            else:
                return render(request, 'check_in.html', {
                    'event': event,
                    'error': error_msg,
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
    response['Content-Disposition'] = f'attachment; filename="{event.title}_attendees_{date.today()}.csv"'

    writer = csv.writer(response)
    
    # Updated headers with Inviting Officer
    writer.writerow([
        'Name', 
        'Email', 
        'Phone', 
        'Inviting Officer', 
        'Checked In At (Malaysia Time)',
        'Applied Programme',
        'SPM Total Credit',
        'IC Number',
        'Address',
        'City',
        'Postcode',
        'State',
        'Marriage Status',
        'Father Name',
        'Father IC',
        'Father Phone',
        'Father Occupation',
        'Father Income',
        'Father Dependants',
        'Mother Name',
        'Mother IC',
        'Mother Phone',
        'Mother Occupation',
        'Mother Income',
        'Mother Dependants',
        'First Choice Programme',
        'Second Choice Programme',
        'Third Choice Programme'
    ])

    # FIX: Remove select_related() or specify related fields
    attendees = event.attendees.all()  # Remove select_related()
    
    # Get all applications for this event in one query
    applications = Application.objects.filter(
        event=event
    ).values('email', 'registration_officer', 'applied_programme', 
             'spm_total_credit', 'ic_no', 'address1', 'city', 
             'postcode', 'state', 'marriage_status', 'father_name',
             'father_ic', 'father_phone', 'father_occupation',
             'father_income', 'father_dependants', 'mother_name',
             'mother_ic', 'mother_phone', 'mother_occupation',
             'mother_income', 'mother_dependants', 'interest_choice1',
             'interest_choice2', 'interest_choice3')
    
    # Create a dictionary for quick lookup of applications by email
    applications_dict = {app['email'].lower(): app for app in applications}

    for attendee in attendees:
        # Convert to Malaysia time for display
        malaysia_time = timezone.localtime(attendee.attended_at)
        
        # Get application data for this attendee
        app_data = applications_dict.get(attendee.email.lower())
        
        if app_data:
            # Attendee has an application
            writer.writerow([
                attendee.name,
                attendee.email,
                attendee.phone_number,
                app_data['registration_officer'],  # Inviting Officer
                malaysia_time.strftime('%Y-%m-%d %H:%M:%S'),
                app_data['applied_programme'],
                app_data['spm_total_credit'],
                app_data['ic_no'],
                app_data['address1'],
                app_data['city'],
                app_data['postcode'],
                app_data['state'],
                app_data['marriage_status'],
                app_data['father_name'],
                app_data['father_ic'],
                app_data['father_phone'],
                app_data['father_occupation'],
                app_data['father_income'] or '',
                app_data['father_dependants'],
                app_data['mother_name'],
                app_data['mother_ic'],
                app_data['mother_phone'],
                app_data['mother_occupation'],
                app_data['mother_income'] or '',
                app_data['mother_dependants'],
                app_data['interest_choice1'],
                app_data['interest_choice2'] or '',
                app_data['interest_choice3'] or ''
            ])
        else:
            # Attendee checked in but didn't submit application form
            writer.writerow([
                attendee.name,
                attendee.email,
                attendee.phone_number or '',
                'N/A',  # No inviting officer data
                malaysia_time.strftime('%Y-%m-%d %H:%M:%S'),
                'N/A', '0', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A',
                'N/A', 'N/A', 'N/A', 'N/A', 'N/A', '', 'N/A',
                'N/A', 'N/A', 'N/A', 'N/A', '', 'N/A', 'N/A', '', ''
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
        
        # Helper function to format empty values as dash
        def format_value(value):
            if value is None or str(value).strip() == '':
                return '-'
            return str(value).strip()
        
        # Build application data
        app_data = {
            'registration_officer': format_value(application.registration_officer),
            'applied_programme': format_value(application.applied_programme),
            'full_name': format_value(application.full_name),
            'address1': format_value(application.address1),
            'city': format_value(application.city),
            'postcode': format_value(application.postcode),
            'state': format_value(application.state),
            'ic_no': format_value(application.ic_no),
            'email': format_value(application.email),
            'phone_no': format_value(application.phone_no),
            'marriage_status': format_value(application.marriage_status),
            'spm_total_credit': format_value(application.spm_total_credit),
            'father_name': format_value(application.father_name),
            'father_ic': format_value(application.father_ic),
            'father_phone': format_value(application.father_phone),
            'father_occupation': format_value(application.father_occupation),
            'father_income': format_value(application.father_income),
            'father_dependants': format_value(application.father_dependants),
            'mother_name': format_value(application.mother_name),
            'mother_ic': format_value(application.mother_ic),
            'mother_phone': format_value(application.mother_phone),
            'mother_occupation': format_value(application.mother_occupation),
            'mother_income': format_value(application.mother_income),
            'mother_dependants': format_value(application.mother_dependants),
            'interest_choice1': format_value(application.interest_choice1),
            'interest_choice2': format_value(application.interest_choice2),
            'interest_choice3': format_value(application.interest_choice3),
            'submitted_at': timezone.localtime(application.submitted_at).strftime('%Y-%m-%d %H:%M:%S'),
        }
        
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
            'application': app_data
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
                'total_fee': str(registration.total_fee),
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
                'total_fee': str(registration.total_fee),
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
    """Modern dashboard-style PDF report with black/gray theme - UPDATED"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()
    
    try:
        # Get all registrations with related data
        registrations = Registration.objects.filter(
            attendee__event=event
        ).select_related('attendee')
        
        # Calculate statistics
        total_registered = registrations.count()
        total_paid = registrations.filter(payment_status='DONE').count()
        total_pending = registrations.filter(payment_status='PENDING').count()
        
        # Calculate revenue
        total_revenue = Decimal('0.00')
        paid_revenue = Decimal('0.00')
        pending_revenue = Decimal('0.00')
        
        for reg in registrations:
            reg_total = (reg.pre_registration_fee or Decimal('0.00')) + (reg.registration_fee or Decimal('0.00'))
            total_revenue += reg_total
            if reg.payment_status == 'DONE':
                paid_revenue += reg_total
            else:
                pending_revenue += reg_total
        
        # Get applications data for inviting officers
        email_to_inviting_officer = {}
        try:
            applications = Application.objects.filter(event=event)
            for app in applications:
                email_to_inviting_officer[app.email.lower()] = app.registration_officer
        except Exception as e:
            print(f"Error getting applications: {e}")
            # Continue without inviting officer data
        
        # Get ALL performers (not just top 5)
        try:
            all_courses = registrations.values('course').annotate(
                count=Count('id'),
                revenue=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('-count')
        except Exception as e:
            print(f"Error getting courses: {e}")
            all_courses = []
        
        try:
            all_closers = registrations.values('closer').annotate(
                count=Count('id'),
                revenue=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('-count')
        except Exception as e:
            print(f"Error getting closers: {e}")
            all_closers = []
        
        # ============================
        # PDF GENERATION SETUP
        # ============================
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from reportlab.lib.pagesizes import landscape, A4, portrait
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            import io
            import tempfile
            import os
            
            # Create PDF buffer
            buffer = io.BytesIO()
            
            # ============================
            # COLOR PALETTE (Black/Gray Theme - Matching HTML)
            # ============================
            COLORS = {
                'black': '#000000',
                'white': '#ffffff',
                'gray_50': '#fafafa',
                'gray_100': '#f5f5f5',
                'gray_200': '#e5e5e5',
                'gray_300': '#d4d4d4',
                'gray_400': '#a3a3a3',
                'gray_500': '#737373',
                'gray_600': '#525252',
                'gray_700': '#404040',
                'gray_800': '#262626',
                'gray_900': '#171717',
                'success': '#27ae60',
                'warning': '#e67e22',
                'danger': '#e74c3c',
                'info': '#3498db',
                'border': '#d4d4d4',
            }
            
            # ============================
            # TYPOGRAPHY SYSTEM - UPDATED FOR SMALLER HEADER
            # ============================
            styles = getSampleStyleSheet()
            
            # REDUCED Title style
            title_style = ParagraphStyle(
                'Title',
                parent=styles['Heading1'],
                fontSize=18,  # Reduced from 20
                spaceAfter=0.2*cm,  # Reduced spacing
                alignment=1,
                textColor=colors.HexColor(COLORS['black']),
                fontName='Helvetica-Bold'
            )
            
            # Subtitle style
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=10,  # Reduced from 11
                spaceAfter=0.3*cm,  # Reduced spacing
                textColor=colors.HexColor(COLORS['gray_600']),
                alignment=1
            )
            
            # Section header style
            section_style = ParagraphStyle(
                'Section',
                parent=styles['Heading2'],
                fontSize=12,  # Reduced from 13
                spaceBefore=0.2*cm,  # Reduced spacing
                spaceAfter=0.1*cm,  # Reduced spacing
                textColor=colors.HexColor(COLORS['black']),
                fontName='Helvetica-Bold',
                leftIndent=0.2*cm
            )
            
            # Metric value style - SMALLER
            metric_value_style = ParagraphStyle(
                'MetricValue',
                parent=styles['Normal'],
                fontSize=14,  # Reduced from 15
                textColor=colors.HexColor(COLORS['black']),
                fontName='Helvetica-Bold',
                alignment=1,
                spaceAfter=0
            )
            
            # Metric label style - SMALLER
            metric_label_style = ParagraphStyle(
                'MetricLabel',
                parent=styles['Normal'],
                fontSize=7.5,  # Reduced from 8
                textColor=colors.HexColor(COLORS['gray_600']),
                alignment=1,
                spaceAfter=0
            )
            
            # Metric subtext style - SMALLER
            metric_subtext_style = ParagraphStyle(
                'MetricSubtext',
                parent=styles['Normal'],
                fontSize=6.5,  # Reduced from 7
                textColor=colors.HexColor(COLORS['gray_500']),
                alignment=1,
                spaceAfter=0
            )
            
            # Table header style
            table_header_style = ParagraphStyle(
                'TableHeader',
                parent=styles['Normal'],
                fontSize=8.5,  # Reduced from 9
                textColor=colors.white,
                fontName='Helvetica-Bold',
                alignment=1,
                spaceBefore=2,
                spaceAfter=2,
                leading=9  # Reduced from 10
            )
            
            # Table cell style
            table_cell_style = ParagraphStyle(
                'TableCell',
                parent=styles['Normal'],
                fontSize=7.5,  # Reduced from 8
                textColor=colors.HexColor(COLORS['gray_800']),
                fontName='Helvetica',
                alignment=0,
                leading=8  # Reduced from 9
            )
            
            # Table cell center style
            table_cell_center = ParagraphStyle(
                'TableCellCenter',
                parent=table_cell_style,
                alignment=1
            )
            
            # Table cell right style
            table_cell_right = ParagraphStyle(
                'TableCellRight',
                parent=table_cell_style,
                alignment=2
            )
            
            # Status cell style
            status_cell_style = ParagraphStyle(
                'StatusCell',
                parent=table_cell_style,
                alignment=1,
                fontSize=7.5,  # Reduced from 8
                wordWrap=None,
                spaceBefore=2,
                spaceAfter=2,
                leading=8,  # Reduced from 9
                fontName='Helvetica-Bold'
            )
            
            # Status Paid style
            status_paid_style = ParagraphStyle(
                'StatusPaid',
                parent=status_cell_style,
                textColor=colors.green
            )
            
            # Status Pending style
            status_pending_style = ParagraphStyle(
                'StatusPending',
                parent=status_cell_style,
                textColor=colors.red
            )
            
            # Total amount style
            total_amount_style = ParagraphStyle(
                'TotalAmount',
                parent=table_cell_right,
                fontSize=8.5,  # Reduced from 9
                fontName='Helvetica-Bold',
                textColor=colors.HexColor(COLORS['black']),
                spaceBefore=0,
                spaceAfter=0,
                leading=10,  # Reduced from 11
                alignment=2,
                valign='MIDDLE'
            )
            
            # Total label style
            total_label_style = ParagraphStyle(
                'TotalLabel',
                parent=table_cell_style,
                fontSize=8.5,  # Reduced from 9
                fontName='Helvetica-Bold',
                textColor=colors.HexColor(COLORS['black']),
                spaceBefore=0,
                spaceAfter=0,
                leading=10,  # Reduced from 11
                alignment=0,
                valign='MIDDLE'
            )
            
            # Insight style
            insight_style = ParagraphStyle(
                'Insight',
                parent=styles['Normal'],
                fontSize=8.5,  # Reduced from 9
                textColor=colors.HexColor(COLORS['gray_800']),
                leftIndent=0.5*cm,
                spaceAfter=2
            )
            
            # Footer style
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=7.5,  # Reduced from 8
                textColor=colors.HexColor(COLORS['gray_500']),
                alignment=1
            )
            
            # ============================
            # BUILD PDF STORY
            # ============================
            story = []
            
            # ============================
            # PAGE 1: EXECUTIVE SUMMARY (Compact)
            # ============================
            
            # REDUCED Header Section
            story.append(Spacer(1, 0.1*cm))  # Reduced spacing
            story.append(Paragraph("REGISTRATION REPORT", title_style))  # Smaller title
            story.append(Paragraph(f"{event.title}", subtitle_style))
            story.append(Paragraph(f"Event Date: {event.date.strftime('%d %B %Y')} | Generated: {malaysia_now().strftime('%d/%m/%Y %H:%M')}", 
                                 ParagraphStyle('ReportInfo', parent=subtitle_style, fontSize=8.5)))  # Smaller font
            story.append(Spacer(1, 0.2*cm))  # Reduced spacing
            
            # ============================
            # SECTION 1: COMPACT KEY METRICS (4x2 Grid)
            # ============================
            
            def create_compact_metric_card(label, value, subtext=""):
                """Create a compact metric card for the grid"""
                card_data = [
                    [Paragraph(str(value), metric_value_style)],
                    [Paragraph(label, metric_label_style)],
                ]
                
                if subtext:
                    card_data.append([Paragraph(subtext, metric_subtext_style)])
                
                card_table = Table(card_data, colWidths=[4*cm])  # Reduced width
                
                card_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor(COLORS['gray_300'])),
                    ('PADDING', (0, 0), (-1, -1), 4),  # Reduced padding
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('TOPPADDING', (0, 0), (-1, 0), 4),  # Reduced padding
                    ('BOTTOMPADDING', (0, -1), (-1, -1), 4),  # Reduced padding
                ]))
                
                return card_table
            
            # Calculate metrics
            payment_rate = (total_paid/total_registered*100) if total_registered > 0 else 0
            avg_fee = total_revenue/total_registered if total_registered > 0 else 0
            avg_paid_fee = paid_revenue/total_paid if total_paid > 0 else 0
            
            # Create 8 compact metric cards for a 4x2 grid
            metric_cards = [
                create_compact_metric_card(
                    "Total Registrations",
                    total_registered,
                    f"{total_paid} paid"
                ),
                create_compact_metric_card(
                    "Payment Rate",
                    f"{payment_rate:.1f}%",
                    f"{total_pending} pending"
                ),
                create_compact_metric_card(
                    "Total Revenue",
                    f"RM {total_revenue:,.0f}" if total_revenue == int(total_revenue) else f"RM {total_revenue:,.2f}",
                    "Total collected"
                ),
                create_compact_metric_card(
                    "Avg Revenue",
                    f"RM {avg_fee:,.0f}" if avg_fee == int(avg_fee) else f"RM {avg_fee:,.2f}",
                    "Per registration"
                ),
                create_compact_metric_card(
                    "Paid Revenue",
                    f"RM {paid_revenue:,.0f}" if paid_revenue == int(paid_revenue) else f"RM {paid_revenue:,.2f}",
                    "Confirmed payments"
                ),
                create_compact_metric_card(
                    "Pending Revenue",
                    f"RM {pending_revenue:,.0f}" if pending_revenue == int(pending_revenue) else f"RM {pending_revenue:,.2f}",
                    "Outstanding"
                ),
                create_compact_metric_card(
                    "Avg Paid Fee",
                    f"RM {avg_paid_fee:,.0f}" if total_paid > 0 and avg_paid_fee == int(avg_paid_fee) else f"RM {avg_paid_fee:,.2f}",
                    "Per successful"
                ),
                create_compact_metric_card(
                    "Completion",
                    f"{(total_paid/total_registered*100):.1f}%" if total_registered > 0 else "0%",
                    "Payment completion"
                )
            ]
            
            # Create 2 rows of 4 cards each for the grid
            row1_metrics = Table([metric_cards[0:4]], colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
            row2_metrics = Table([metric_cards[4:8]], colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
            
            for metrics_row in [row1_metrics, row2_metrics]:
                metrics_row.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('PADDING', (0, 0), (-1, -1), 1),  # Minimal padding
                ]))
            
            story.append(row1_metrics)
            story.append(Spacer(1, 0.1*cm))  # Minimal spacing
            story.append(row2_metrics)
            story.append(Spacer(1, 0.2*cm))  # Reduced spacing
            
            # ============================
            # SECTION 2: REVENUE ANALYSIS (Compact)
            # ============================
            
            # Generate Revenue Analysis Chart (Paid & Pending only)
            chart_files = []
            
            try:
                # Revenue Analysis Bar Chart (Paid & Pending only)
                if float(paid_revenue) > 0 or float(pending_revenue) > 0:
                    plt.figure(figsize=(2.8, 2.2))  # Smaller chart
                    categories = ['Paid', 'Pending']
                    values = [float(paid_revenue), float(pending_revenue)]
                    bar_colors = [COLORS['success'], COLORS['warning']]
                    
                    bars = plt.bar(categories, values, color=bar_colors, width=0.35)
                    plt.ylabel('Amount (RM)', fontsize=7, color=COLORS['gray_600'])
                    plt.title('Revenue Analysis', fontsize=9, fontweight='bold',
                             color=COLORS['black'], pad=6)
                    
                    # Value labels on bars
                    for bar in bars:
                        height = bar.get_height()
                        if height > 0:
                            # Format value
                            if height >= 1000:
                                formatted_val = f'RM {height/1000:.1f}K'
                            else:
                                formatted_val = f'RM {height:,.0f}'
                            
                            plt.text(bar.get_x() + bar.get_width()/2., height + (max(values)*0.01),
                                    formatted_val, ha='center', va='bottom', 
                                    fontsize=6, fontweight='bold')
                    
                    plt.grid(axis='y', alpha=0.3, color=COLORS['gray_300'])
                    plt.tight_layout(pad=1.2)
                    
                    temp_revenue = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                    plt.savefig(temp_revenue.name, dpi=150, bbox_inches='tight', facecolor='white')
                    chart_files.append(temp_revenue.name)
                    plt.close()
                
            except Exception as e:
                print(f"Chart generation error: {e}")
                # Continue without charts
            
            # ============================
            # SECTION 3: DETAILED ANALYSIS & INSIGHTS (Compact)
            # ============================
            
            # Create a detailed analysis table
            analysis_data = []
            
            # Performance Analysis
            analysis_data.append([
                Paragraph("<b>PERFORMANCE ANALYSIS</b>", 
                         ParagraphStyle('AnalysisHeader', parent=section_style, fontSize=10))
            ])
            analysis_data.append([Spacer(1, 0.1*cm)])
            
            # Add detailed metrics
            analysis_metrics = []
            
            if total_registered > 0:
                # Calculate additional metrics
                applications_count = len(email_to_inviting_officer)
                conversion_rate = (total_registered/applications_count*100) if applications_count > 0 else 0
                
                analysis_metrics.append([
                    Paragraph(f"• <b>Applications to Registrations:</b> {conversion_rate:.1f}% ({total_registered}/{applications_count})", insight_style)
                ])
                analysis_metrics.append([
                    Paragraph(f"• <b>Payment Collection Rate:</b> {payment_rate:.1f}%", insight_style)
                ])
                
                if total_paid > 0:
                    analysis_metrics.append([
                        Paragraph(f"• <b>Average Paid Amount:</b> RM {avg_paid_fee:,.2f}", insight_style)
                    ])
                
                if total_pending > 0:
                    analysis_metrics.append([
                        Paragraph(f"• <b>Outstanding Potential:</b> RM {pending_revenue:,.2f}", insight_style)
                    ])
                
                # Course distribution insights
                if all_courses and len(all_courses) > 0:
                    top_course = all_courses[0]
                    top_course_name = top_course.get('course', 'Unknown') or 'Unknown'
                    if len(top_course_name) > 25:
                        top_course_name = top_course_name[:23] + "..."
                    course_percentage = (top_course.get('count', 0) / total_registered * 100) if total_registered > 0 else 0
                    analysis_metrics.append([
                        Paragraph(f"• <b>Top Course:</b> {top_course_name} ({course_percentage:.1f}%)", insight_style)
                    ])
                
                # Closer performance insights
                if all_closers and len(all_closers) > 0:
                    top_closer = all_closers[0]
                    top_closer_name = top_closer.get('closer', 'Unknown') or 'Unknown'
                    if len(top_closer_name) > 25:
                        top_closer_name = top_closer_name[:23] + "..."
                    closer_percentage = (top_closer.get('count', 0) / total_registered * 100) if total_registered > 0 else 0
                    analysis_metrics.append([
                        Paragraph(f"• <b>Top Performer:</b> {top_closer_name} ({closer_percentage:.1f}%)", insight_style)
                    ])
            else:
                analysis_metrics.append([
                    Paragraph("• No registrations recorded for this event", insight_style)
                ])
            
            # Create analysis table
            analysis_table = Table(analysis_metrics, colWidths=[15*cm])
            analysis_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(COLORS['white'])),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 2),
            ]))
            
            # ============================
            # COMBINED LAYOUT: Chart + Analysis side by side
            # ============================
            
            combined_content = []
            
            if len(chart_files) > 0:
                # Left side: Chart
                chart_content = [[Image(chart_files[0], width=7*cm, height=5*cm)]]
                # Right side: Analysis
                analysis_content = [[analysis_table]]
                
                combined_table = Table([
                    [Table(chart_content), Table(analysis_content)]
                ], colWidths=[8*cm, 15*cm])
            else:
                # Just analysis if no chart
                combined_table = Table([[analysis_table]], colWidths=[23*cm])
            
            combined_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 3),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ]))
            
            story.append(combined_table)
            story.append(Spacer(1, 0.2*cm))
            
            # ============================
            # SECTION 4: SUMMARY METRICS TABLE (Compact)
            # ============================
            
            summary_table_data = []
            
            # Table header
            summary_table_data.append([
                Paragraph("<b>CATEGORY</b>", table_header_style),
                Paragraph("<b>TOTAL</b>", table_header_style),
                Paragraph("<b>AMOUNT (RM)</b>", table_header_style),
                Paragraph("<b>PERCENTAGE</b>", table_header_style)
            ])
            
            # Data rows
            summary_table_data.append([
                Paragraph("Total Registrations", table_cell_style),
                Paragraph(str(total_registered), table_cell_center),
                Paragraph(f"RM {total_revenue:,.2f}", table_cell_right),
                Paragraph("100%", table_cell_center)
            ])
            
            summary_table_data.append([
                Paragraph("Paid Registrations", table_cell_style),
                Paragraph(str(total_paid), table_cell_center),
                Paragraph(f"RM {paid_revenue:,.2f}", table_cell_right),
                Paragraph(f"{payment_rate:.1f}%", table_cell_center)
            ])
            
            summary_table_data.append([
                Paragraph("Pending Registrations", table_cell_style),
                Paragraph(str(total_pending), table_cell_center),
                Paragraph(f"RM {pending_revenue:,.2f}", table_cell_right),
                Paragraph(f"{(100-payment_rate):.1f}%" if total_registered > 0 else "0%", table_cell_center)
            ])
            
            summary_table_data.append([
                Paragraph("Avg per Registration", table_cell_style),
                Paragraph("-", table_cell_center),
                Paragraph(f"RM {avg_fee:,.2f}", table_cell_right),
                Paragraph("-", table_cell_center)
            ])
            
            # Create summary table
            summary_table = Table(summary_table_data, colWidths=[7*cm, 3*cm, 5*cm, 3*cm])
            
            summary_table.setStyle(TableStyle([
                # Header - Black background
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['black'])),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8.5),
                ('PADDING', (0, 0), (-1, 0), 5),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.white),
                
                # Body
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('PADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor(COLORS['gray_300'])),
                
                # Column alignments
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
                ('ALIGN', (3, 1), (3, -1), 'CENTER'),
                
                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), 
                 [colors.white, colors.HexColor(COLORS['gray_50'])]),
            ]))
            
            # Center the summary table
            summary_container = Table([[summary_table]], colWidths=[18*cm])
            summary_container.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 3),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ]))
            
            story.append(summary_container)
            story.append(Spacer(1, 0.3*cm))
            
            # ============================
            # PAGE BREAK
            # ============================
            story.append(PageBreak())
            
            # ============================
            # PAGE 2: ALL PERFORMERS ANALYSIS
            # ============================
            
            # Header for Performers Analysis page
            story.append(Paragraph("PERFORMANCE ANALYSIS", title_style))
            story.append(Paragraph(
                f"Event: {event.title} | Total Performers: {len(all_closers) if all_closers else 0} closer(s), {len(all_courses) if all_courses else 0} course(s)", 
                subtitle_style
            ))
            story.append(Spacer(1, 0.3*cm))
            
            # ============================
            # SECTION 1: ALL CLOSERS PERFORMANCE
            # ============================
            
            if all_closers and len(all_closers) > 0:
                story.append(Paragraph("<b>ALL CLOSERS PERFORMANCE</b>", 
                            ParagraphStyle('SectionCenter', parent=section_style, fontSize=11, alignment=1)))
                story.append(Spacer(1, 0.2*cm))
                
                # Create ALL closers table
                closers_data = []
                
                # Headers
                closers_data.append([
                    Paragraph('<b>#</b>', table_header_style),
                    Paragraph('<b>CLOSER NAME</b>', table_header_style),
                    Paragraph('<b>REGISTRATIONS</b>', table_header_style),
                    Paragraph('<b>% SHARE</b>', table_header_style),
                    Paragraph('<b>REVENUE (RM)</b>', table_header_style),
                    Paragraph('<b>AVG/REG (RM)</b>', table_header_style)
                ])
                
                # Data rows for ALL closers
                for i, closer in enumerate(all_closers, 1):
                    closer_name = closer.get('closer', 'Unknown') or 'Unknown'
                    if len(closer_name) > 25:
                        closer_name = closer_name[:23] + "..."
                    
                    closer_count = closer.get('count', 0)
                    closer_percentage = (closer_count / total_registered * 100) if total_registered > 0 else 0
                    closer_revenue = closer.get('revenue', 0) or 0
                    closer_avg = closer_revenue / closer_count if closer_count > 0 else 0
                    
                    # Choose rank style for top 3
                    if i == 1:
                        rank_style = ParagraphStyle('RankGold', parent=table_cell_center, fontSize=8, 
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor('#D4AF37'))
                    elif i == 2:
                        rank_style = ParagraphStyle('RankSilver', parent=table_cell_center, fontSize=8,
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor('#C0C0C0'))
                    elif i == 3:
                        rank_style = ParagraphStyle('RankBronze', parent=table_cell_center, fontSize=8,
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor('#CD7F32'))
                    else:
                        rank_style = ParagraphStyle('RankRegular', parent=table_cell_center, fontSize=8,
                                                   textColor=colors.HexColor(COLORS['gray_500']))
                    
                    # Highlight top 3
                    if i <= 3:
                        name_style = ParagraphStyle('Highlight', parent=table_cell_style, fontSize=8,
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor(COLORS['black']))
                    else:
                        name_style = table_cell_style
                    
                    closers_data.append([
                        Paragraph(str(i), rank_style),
                        Paragraph(closer_name, name_style),
                        Paragraph(str(closer_count), table_cell_center),
                        Paragraph(f"{closer_percentage:.1f}%", table_cell_center),
                        Paragraph(f"RM {closer_revenue:,.0f}" if closer_revenue == int(closer_revenue) else f"RM {closer_revenue:,.2f}", 
                                ParagraphStyle('Revenue', parent=table_cell_right, fontSize=8)),
                        Paragraph(f"RM {closer_avg:,.0f}" if closer_avg == int(closer_avg) else f"RM {closer_avg:,.2f}", 
                                table_cell_right)
                    ])
                
                # Column widths
                closers_col_widths = [1.2*cm, 6*cm, 2.5*cm, 2.2*cm, 3.5*cm, 2.5*cm]
                
                closers_table = Table(closers_data, colWidths=closers_col_widths, repeatRows=1)
                
                # Styling for ALL closers table
                closers_table.setStyle(TableStyle([
                    # Header - Black background
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['black'])),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8.5),
                    ('PADDING', (0, 0), (-1, 0), 5),
                    ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('LINEBELOW', (0, 0), (-1, 0), 1, colors.white),
                    
                    # Body
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('PADDING', (0, 1), (-1, -1), 4),
                    ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                    
                    # Thin horizontal lines
                    ('LINEBELOW', (0, 1), (-1, -1), 0.2, colors.HexColor(COLORS['gray_300'])),
                    
                    # Column alignments
                    ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                    ('ALIGN', (2, 1), (3, -1), 'CENTER'),
                    ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
                    
                    # Top 3 highlights - Light background
                    ('BACKGROUND', (0, 1), (-1, 3), colors.HexColor(COLORS['gray_100'])),
                    
                    # Alternating rows after top 3
                    ('ROWBACKGROUNDS', (0, 4), (-1, -1), 
                     [colors.white, colors.HexColor(COLORS['gray_50'])]),
                ]))
                
                story.append(closers_table)
                story.append(Spacer(1, 0.4*cm))
            
            # ============================
            # SECTION 2: ALL COURSES PERFORMANCE
            # ============================
            
            if all_courses and len(all_courses) > 0:
                story.append(Paragraph("<b>ALL COURSES PERFORMANCE</b>", 
                            ParagraphStyle('SectionCenter', parent=section_style, fontSize=11, alignment=1)))
                story.append(Spacer(1, 0.2*cm))
                
                # Create ALL courses table
                courses_data = []
                
                # Headers
                courses_data.append([
                    Paragraph('<b>#</b>', table_header_style),
                    Paragraph('<b>COURSE NAME</b>', table_header_style),
                    Paragraph('<b>REGISTRATIONS</b>', table_header_style),
                    Paragraph('<b>% SHARE</b>', table_header_style),
                    Paragraph('<b>REVENUE (RM)</b>', table_header_style),
                    Paragraph('<b>AVG/REG (RM)</b>', table_header_style)
                ])
                
                # Data rows for ALL courses
                for i, course in enumerate(all_courses, 1):
                    course_name = course.get('course', 'Unknown') or 'Unknown'
                    if len(course_name) > 25:
                        course_name = course_name[:23] + "..."
                    
                    course_count = course.get('count', 0)
                    course_percentage = (course_count / total_registered * 100) if total_registered > 0 else 0
                    course_revenue = course.get('revenue', 0) or 0
                    course_avg = course_revenue / course_count if course_count > 0 else 0
                    
                    # Choose rank style for top 3
                    if i == 1:
                        rank_style = ParagraphStyle('RankGold', parent=table_cell_center, fontSize=8, 
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor('#D4AF37'))
                    elif i == 2:
                        rank_style = ParagraphStyle('RankSilver', parent=table_cell_center, fontSize=8,
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor('#C0C0C0'))
                    elif i == 3:
                        rank_style = ParagraphStyle('RankBronze', parent=table_cell_center, fontSize=8,
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor('#CD7F32'))
                    else:
                        rank_style = ParagraphStyle('RankRegular', parent=table_cell_center, fontSize=8,
                                                   textColor=colors.HexColor(COLORS['gray_500']))
                    
                    # Highlight top 3
                    if i <= 3:
                        name_style = ParagraphStyle('Highlight', parent=table_cell_style, fontSize=8,
                                                   fontName='Helvetica-Bold', textColor=colors.HexColor(COLORS['black']))
                    else:
                        name_style = table_cell_style
                    
                    courses_data.append([
                        Paragraph(str(i), rank_style),
                        Paragraph(course_name, name_style),
                        Paragraph(str(course_count), table_cell_center),
                        Paragraph(f"{course_percentage:.1f}%", table_cell_center),
                        Paragraph(f"RM {course_revenue:,.0f}" if course_revenue == int(course_revenue) else f"RM {course_revenue:,.2f}", 
                                ParagraphStyle('Revenue', parent=table_cell_right, fontSize=8)),
                        Paragraph(f"RM {course_avg:,.0f}" if course_avg == int(course_avg) else f"RM {course_avg:,.2f}", 
                                table_cell_right)
                    ])
                
                # Column widths
                courses_col_widths = [1.2*cm, 6*cm, 2.5*cm, 2.2*cm, 3.5*cm, 2.5*cm]
                
                courses_table = Table(courses_data, colWidths=courses_col_widths, repeatRows=1)
                
                # Styling for ALL courses table
                courses_table.setStyle(TableStyle([
                    # Header - Black background
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['black'])),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8.5),
                    ('PADDING', (0, 0), (-1, 0), 5),
                    ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('LINEBELOW', (0, 0), (-1, 0), 1, colors.white),
                    
                    # Body
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('PADDING', (0, 1), (-1, -1), 4),
                    ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                    
                    # Thin horizontal lines
                    ('LINEBELOW', (0, 1), (-1, -1), 0.2, colors.HexColor(COLORS['gray_300'])),
                    
                    # Column alignments
                    ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                    ('ALIGN', (2, 1), (3, -1), 'CENTER'),
                    ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
                    
                    # Top 3 highlights - Light background
                    ('BACKGROUND', (0, 1), (-1, 3), colors.HexColor(COLORS['gray_100'])),
                    
                    # Alternating rows after top 3
                    ('ROWBACKGROUNDS', (0, 4), (-1, -1), 
                     [colors.white, colors.HexColor(COLORS['gray_50'])]),
                ]))
                
                story.append(courses_table)
            
            # ============================
            # PAGE 3: DETAILED REGISTRATIONS
            # ============================
            story.append(PageBreak())
            
            # Header for Registration Details page
            story.append(Paragraph("REGISTRATION DETAILS", title_style))
            story.append(Paragraph(
                f"Event: {event.title} | Total: {total_registered} registration(s)", 
                subtitle_style
            ))
            story.append(Spacer(1, 0.3*cm))
            
            # Updated headers with adjusted widths
            headers = [
                ('ID', 0.8*cm),
                ('ATTENDEE', 5.5*cm),
                ('EMAIL', 3.0*cm),
                ('REFERRAL<br/>CODE', 2.2*cm),
                ('COURSE', 2.2*cm),
                ('COLLEGE', 2.0*cm),
                ('REG.<br/>DATE', 1.5*cm),
                ('PRE-<br/>REG', 1.4*cm),
                ('REG<br/>FEE', 1.4*cm),
                ('TOTAL', 2.2*cm),
                ('STATUS', 1.8*cm),
                ('CLOSER', 2.0*cm),
            ]
            
            # Create table data
            table_data = []
            
            # Headers with multiline text - Black background
            header_row = []
            for header_text, width in headers:
                header_row.append(Paragraph(f'<b>{header_text}</b>', table_header_style))
            table_data.append(header_row)
            
            # Registration rows
            sorted_registrations = registrations.order_by('-register_date', 'attendee__name')
            for i, reg in enumerate(sorted_registrations, 1):
                # Get inviting officer
                inviting_officer = email_to_inviting_officer.get(
                    reg.attendee.email.lower(), 'N/A'
                )
                
                # Truncate long text
                attendee_name = reg.attendee.name
                if len(attendee_name) > 18:
                    attendee_name = attendee_name[:16] + "..."
                
                email = reg.attendee.email
                if len(email) > 18:
                    email = email[:16] + "..."
                
                officer = inviting_officer
                if len(officer) > 12:
                    officer = officer[:10] + "..."
                
                course = reg.course or 'N/A'
                if len(course) > 12:
                    course = course[:10] + "..."
                
                college = reg.college or 'N/A'
                if len(college) > 12:
                    college = college[:10] + "..."
                
                closer = reg.closer or 'N/A'
                if len(closer) > 12:
                    closer = closer[:10] + "..."
                
                # Status with color coding
                if reg.payment_status == 'DONE':
                    status_cell = Paragraph('PAID', status_paid_style)
                else:
                    status_cell = Paragraph('PENDING', status_pending_style)
                
                # Format fees
                pre_reg_fee = f"{reg.pre_registration_fee:,.0f}" if reg.pre_registration_fee == int(reg.pre_registration_fee) else f"{reg.pre_registration_fee:,.2f}"
                reg_fee = f"{reg.registration_fee:,.0f}" if reg.registration_fee == int(reg.registration_fee) else f"{reg.registration_fee:,.2f}"
                total_fee_val = reg.total_fee  # Access property without parentheses
                if total_fee_val == int(total_fee_val):
                    total_fee = f"{total_fee_val:,.0f}"
                else:
                    total_fee = f"{total_fee_val:,.2f}"
                
                # Build row
                row = [
                    Paragraph(str(i), table_cell_center),
                    Paragraph(attendee_name, table_cell_style),
                    Paragraph(email, table_cell_style),
                    Paragraph(officer, table_cell_style),
                    Paragraph(course, table_cell_style),
                    Paragraph(college, table_cell_style),
                    Paragraph(
                        reg.register_date.strftime('%d/%m/%y') if reg.register_date else 'N/A',
                        table_cell_center
                    ),
                    Paragraph(f"RM {pre_reg_fee}", table_cell_right),
                    Paragraph(f"RM {reg_fee}", table_cell_right),
                    Paragraph(f"RM {total_fee}", table_cell_right),
                    status_cell,
                    Paragraph(closer, table_cell_style),
                ]
                
                table_data.append(row)
            
            # Add summary row
            total_row = [
                Paragraph(f'<b>SUMMARY: {total_registered} Registrations</b>', total_label_style),
                '', '', '', '', '', '',
                Paragraph('', table_cell_center),
                Paragraph('', table_cell_center),
                Paragraph(f'<b>RM {total_revenue:,.2f}</b>', total_amount_style),
                '', ''
            ]
            
            table_data.append(total_row)
            
            # Extract column widths
            col_widths = [width for _, width in headers]
            
            # Create table
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            # Apply styling - Black/Gray theme
            table.setStyle(TableStyle([
                # Header - Black background
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['black'])),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8.5),
                ('PADDING', (0, 0), (-1, 0), 6),
                ('LEFTPADDING', (0, 0), (-1, 0), 4),
                ('RIGHTPADDING', (0, 0), (-1, 0), 4),
                ('TOPPADDING', (0, 0), (-1, 0), 5),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.white),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                
                # Body
                ('FONTSIZE', (0, 1), (-1, -2), 7.5),
                ('PADDING', (0, 1), (-1, -2), 6),
                ('LEFTPADDING', (0, 1), (-1, -2), 4),
                ('RIGHTPADDING', (0, 1), (-1, -2), 4),
                ('TOPPADDING', (0, 1), (-1, -2), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -2), 5),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -2), 0.25, colors.HexColor(COLORS['gray_300'])),
                
                # STATUS column
                ('LEFTPADDING', (10, 1), (10, -2), 4),
                ('RIGHTPADDING', (10, 1), (10, -2), 4),
                ('TOPPADDING', (10, 1), (10, -2), 6),
                ('BOTTOMPADDING', (10, 1), (10, -2), 6),
                
                # Alternating rows - using gray tones
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), 
                 [colors.white, colors.HexColor(COLORS['gray_50'])]),
                
                # Column alignments
                ('ALIGN', (0, 1), (0, -2), 'CENTER'),
                ('ALIGN', (6, 1), (6, -2), 'CENTER'),
                ('ALIGN', (7, 1), (9, -2), 'RIGHT'),
                ('ALIGN', (10, 1), (10, -2), 'CENTER'),
                
                # TOTAL ROW - Gray background with black text
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLORS['gray_200'])),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 8.5),
                ('PADDING', (0, -1), (-1, -1), 5),
                ('LEFTPADDING', (0, -1), (-1, -1), 4),
                ('RIGHTPADDING', (0, -1), (-1, -1), 4),
                ('TOPPADDING', (0, -1), (-1, -1), 4),
                ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
                ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor(COLORS['black'])),
                ('VALIGN', (0, -1), (-1, -1), 'MIDDLE'),
                
                # Total amount cell
                ('TOPPADDING', (9, -1), (9, -1), 3),
                ('BOTTOMPADDING', (9, -1), (9, -1), 3),
                ('VALIGN', (9, -1), (9, -1), 'MIDDLE'),
                
                # Span cells for summary row
                ('SPAN', (0, -1), (8, -1)),
                ('SPAN', (9, -1), (9, -1)),
                
                # Remove grid for total row
                ('GRID', (0, -1), (-1, -1), 0, colors.white),
            ]))
            
            story.append(table)
            story.append(Spacer(1, 0.3*cm))
            
            # Page 3 footer
            story.append(Paragraph(
                f"Report ID: REG-{event.id}-{malaysia_now().strftime('%y%m%d%H%M')} | © ATTSYS Dashboard",
                footer_style
            ))
            
            # ============================
            # BUILD PDF DOCUMENT
            # ============================
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=landscape(A4),
                rightMargin=2.5*cm,
                leftMargin=2.5*cm,
                topMargin=1.5*cm,
                bottomMargin=1.5*cm,
            )
            
            # Build the story
            doc.build(story)
            buffer.seek(0)
            
            # Clean up temporary chart files
            for chart_file in chart_files:
                try:
                    os.unlink(chart_file)
                except:
                    pass
            
            # Create response
            response = HttpResponse(buffer, content_type='application/pdf')
            filename = f"Daily Report {event.title.replace(' ', '_')[:30]} {malaysia_now().strftime('%Y%m%d_%H%M')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"PDF generation error: {str(e)}")
            print(f"Error details: {error_details}")
            
            # Fallback: Simple PDF with error message
            buffer = io.BytesIO()
            from reportlab.pdfgen import canvas
            c = canvas.Canvas(buffer, pagesize=landscape(A4))
            
            # Add error message
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, 400, "Error Generating PDF Report")
            
            c.setFont("Helvetica", 12)
            c.drawString(50, 370, f"Event: {event.title}")
            c.drawString(50, 350, f"Error: {str(e)[:100]}")
            c.drawString(50, 330, "Please check the server logs for details.")
            
            c.save()
            buffer.seek(0)
            
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="error_report_{event.id}.pdf"'
            return response
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Overall PDF generation error: {str(e)}")
        print(f"Error details: {error_details}")
        
        # Simple error response
        return HttpResponse(
            f"Error generating PDF: {str(e)[:200]}",
            status=500,
            content_type='text/plain'
        )


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


@login_required
def download_qr_code(request, event_id):
    """Generate and download a QR code with event details"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()
    
    try:
        # Create QR code
        qr_url = f"{request.scheme}://{request.get_host()}/attsys/check-in/{event.id}/{event.check_in_token}/"
        qr = qrcode.make(qr_url)
        
        # Convert PIL Image to use with ImageDraw
        qr_img = qr.get_image()
        
        # Resize QR code for better quality
        qr_img = qr_img.resize((350, 350), Image.Resampling.LANCZOS)
        
        # Create a larger image to add text
        width, height = qr_img.size
        margin = 40
        text_height = 200  # More space for text
        padding = 30
        new_width = width + padding * 2
        new_height = height + text_height + margin * 2 + padding * 2
        
        # Create new image with gradient background
        new_img = Image.new('RGB', (new_width, new_height), '#ffffff')
        draw = ImageDraw.Draw(new_img)
        
        # Add header background
        draw.rectangle([(0, 0), (new_width, text_height + margin)], fill='#f8f9fa', outline=None)
        
        # Add border
        draw.rectangle([(padding, padding), (new_width - padding, new_height - padding)], 
                      outline='#dee2e6', width=2)
        
        # Try to load fonts
        try:
            # Try different font paths
            font_paths = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "arial.ttf",
                "Arial.ttf"
            ]
            
            font_large = None
            font_medium = None
            
            for font_path in font_paths:
                try:
                    font_large = ImageFont.truetype(font_path, 24)
                    font_medium = ImageFont.truetype(font_path, 18)
                    font_small = ImageFont.truetype(font_path, 16)
                    break
                except:
                    continue
            
            if not font_large:
                # Fallback to default font
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
                
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Calculate text positions
        center_x = new_width // 2
        
        # Event Title
        title = event.title
        title_bbox = draw.textbbox((0, 0), title, font=font_large)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = center_x - (title_width // 2)
        draw.text((title_x, margin), title, fill="#212529", font=font_large)
        
        # Event Venue
        venue = f"📍 {event.venue}"
        venue_bbox = draw.textbbox((0, 0), venue, font=font_medium)
        venue_width = venue_bbox[2] - venue_bbox[0]
        venue_x = center_x - (venue_width // 2)
        draw.text((venue_x, margin + 40), venue, fill="#495057", font=font_medium)
        
        # Event Date
        event_date = event.date.strftime("%d %B %Y")
        date_text = f"📅 {event_date}"
        date_bbox = draw.textbbox((0, 0), date_text, font=font_medium)
        date_width = date_bbox[2] - date_bbox[0]
        date_x = center_x - (date_width // 2)
        draw.text((date_x, margin + 75), date_text, fill="#495057", font=font_medium)
        
        # Paste QR code centered
        qr_x = center_x - (width // 2)
        qr_y = text_height + margin + padding
        new_img.paste(qr_img, (qr_x, qr_y))
        
        # Instruction text below QR
        instruction = "Scan to check in"
        inst_bbox = draw.textbbox((0, 0), instruction, font=font_small)
        inst_width = inst_bbox[2] - inst_bbox[0]
        inst_x = center_x - (inst_width // 2)
        inst_y = qr_y + height + 15
        draw.text((inst_x, inst_y), instruction, fill="#6c757d", font=font_small)
        
        # Website URL
        url = "Check-in System"
        url_bbox = draw.textbbox((0, 0), url, font=font_small)
        url_width = url_bbox[2] - url_bbox[0]
        url_x = center_x - (url_width // 2)
        draw.text((url_x, inst_y + 25), url, fill="#0d6efd", font=font_small)
        
        # Footer note
        footer = f"Event ID: {event.id}"
        footer_bbox = draw.textbbox((0, 0), footer, font=ImageFont.load_default())
        footer_width = footer_bbox[2] - footer_bbox[0]
        footer_x = new_width - footer_width - 15
        footer_y = new_height - 20
        draw.text((footer_x, footer_y), footer, fill="#adb5bd", font=ImageFont.load_default())
        
        # Save to buffer
        buffer = BytesIO()
        new_img.save(buffer, format="PNG", quality=100, optimize=True)
        buffer.seek(0)
        
        # Create HTTP response
        response = HttpResponse(buffer, content_type='image/png')
        filename = f"checkin_qr_{event.title.replace(' ', '_')}_{event.date}.png".replace('/', '-')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        print(f"Error generating downloadable QR: {e}")
        # Fallback: Return simple QR code
        try:
            qr_url = f"{request.scheme}://{request.get_host()}/attsys/check-in/{event.id}/{event.check_in_token}/"
            qr = qrcode.make(qr_url)
            buffer = BytesIO()
            qr.save(buffer, format="PNG")
            buffer.seek(0)
            response = HttpResponse(buffer, content_type='image/png')
            response['Content-Disposition'] = f'attachment; filename="checkin_qr_{event.id}.png"'
            return response
        except:
            return HttpResponse("Error generating QR code", status=500)

@login_required
@require_GET
def get_printable_attendee_details(request, attendee_id):
    """Get attendee details formatted specifically for printing"""
    attendee = get_object_or_404(Attendee, id=attendee_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and attendee.event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        application = Application.objects.get(
            event=attendee.event,
            email__iexact=attendee.email
        )
        
        # Format all data for printing (dash for empty values)
        def format_print_value(value, field_type='text'):
            if value is None:
                return '-'
            
            str_value = str(value).strip()
            
            if not str_value:
                return '-'
            
            # Special formatting for specific fields
            if field_type == 'ic' and len(str_value) == 12:
                return f'{str_value[:6]}-{str_value[6:8]}-{str_value[8:]}'
            elif field_type == 'phone' and len(str_value) >= 10:
                return f'{str_value[:3]}-{str_value[3:7]} {str_value[7:]}'
            elif field_type == 'money' and str_value.replace('.', '').isdigit():
                try:
                    return f'RM {float(str_value):,.2f}'
                except:
                    return str_value
            else:
                return str_value
        
        data = {
            'print_data': {
                'personal_info': {
                    'full_name': format_print_value(application.full_name),
                    'ic_no': format_print_value(application.ic_no, 'ic'),
                    'email': format_print_value(application.email),
                    'phone_no': format_print_value(application.phone_no, 'phone'),
                    'marriage_status': format_print_value(application.marriage_status),
                },
                'address': {
                    'address1': format_print_value(application.address1),
                    'address2': format_print_value(application.address2),
                    'city': format_print_value(application.city),
                    'postcode': format_print_value(application.postcode),
                    'state': format_print_value(application.state),
                },
                'father_info': {
                    'name': format_print_value(application.father_name),
                    'ic': format_print_value(application.father_ic, 'ic'),
                    'phone': format_print_value(application.father_phone, 'phone'),
                    'occupation': format_print_value(application.father_occupation),
                    'income': format_print_value(application.father_income, 'money'),
                    'dependants': format_print_value(application.father_dependants),
                },
                'mother_info': {
                    'name': format_print_value(application.mother_name),
                    'ic': format_print_value(application.mother_ic, 'ic'),
                    'phone': format_print_value(application.mother_phone, 'phone'),
                    'occupation': format_print_value(application.mother_occupation),
                    'income': format_print_value(application.mother_income, 'money'),
                    'dependants': format_print_value(application.mother_dependants),
                },
                'application_info': {
                    'inviting_officer': format_print_value(application.registration_officer),
                    'applied_programme': format_print_value(application.applied_programme),
                    'spm_total_credit': format_print_value(application.spm_total_credit),
                    'interest_choice1': format_print_value(application.interest_choice1),
                    'interest_choice2': format_print_value(application.interest_choice2),
                    'interest_choice3': format_print_value(application.interest_choice3),
                }
            }
        }
        
        return JsonResponse(data)
        
    except Application.DoesNotExist:
        return JsonResponse({'error': 'No application found'}, status=404)


@login_required
@require_GET
def get_live_stats(request, event_id):
    """Get live statistics for dashboard"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Get current date in Malaysia timezone
        today_malaysia = malaysia_now().date()
        
        # Get all data efficiently
        attendees = event.attendees.all()
        applications = Application.objects.filter(event=event)
        registrations = Registration.objects.filter(attendee__event=event)
        
        # Calculate statistics
        total_attendees = attendees.count()
        total_applications = applications.count()
        total_registered = registrations.count()
        
        # Payment status breakdown
        payment_status_counts = registrations.aggregate(
            total_paid=Count('id', filter=Q(payment_status='DONE')),
            total_pending=Count('id', filter=Q(payment_status='PENDING'))
        )
        
        total_paid = payment_status_counts['total_paid'] or 0
        total_pending = payment_status_counts['total_pending'] or 0
        
        # Calculate total revenue
        revenue_sum = registrations.aggregate(
            total=Sum(
                models.F('pre_registration_fee') + models.F('registration_fee')
            )
        )
        total_revenue = revenue_sum['total'] or Decimal('0.00')
        
        # Today's check-ins (using Malaysia time)
        today_start = timezone.localtime(
            timezone.now().replace(hour=0, minute=0, second=0, microsecond=0),
            timezone.get_current_timezone()
        )
        today_checkins = attendees.filter(
            attended_at__gte=today_start
        ).count()
        
        # Get last check-in time
        last_checkin = attendees.order_by('-attended_at').first()
        last_checkin_time = None
        if last_checkin:
            last_checkin_time = timezone.localtime(last_checkin.attended_at).strftime('%I:%M %p')
        
        # Get feedback statistics
        feedbacks = event.feedbacks.all()
        feedback_count = feedbacks.count()
        avg_rating = feedbacks.aggregate(Avg('rating'))['rating__avg'] or 0
        
        response_data = {
            'success': True,
            'statistics': {
                'attendees': {
                    'total': total_attendees,
                    'today': today_checkins,
                    'last_checkin': last_checkin_time
                },
                'applications': {
                    'total': total_applications,
                    'percentage': round((total_applications / total_attendees * 100) if total_attendees > 0 else 0, 1)
                },
                'registrations': {
                    'total': total_registered,
                    'paid': total_paid,
                    'pending': total_pending,
                    'percentage_paid': round((total_paid / total_registered * 100) if total_registered > 0 else 0, 1),
                    'revenue': float(total_revenue),
                    'avg_revenue': float(total_revenue / total_registered) if total_registered > 0 else 0
                },
                'feedback': {
                    'count': feedback_count,
                    'avg_rating': round(float(avg_rating), 1)
                }
            },
            'summary': {
                'total_revenue': f"RM {total_revenue:,.2f}",
                'total_attendees': total_attendees,
                'completion_rate': f"{round((total_registered / total_attendees * 100) if total_attendees > 0 else 0, 1)}%",
                'current_time': malaysia_now().strftime('%I:%M %p')
            }
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"Error getting live stats: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_GET
def get_daily_stats(request, event_id):
    """Get daily statistics breakdown"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Get date range (last 30 days)
        end_date = malaysia_now().date()
        start_date = end_date - timedelta(days=29)
        
        daily_stats = []
        
        # Loop through each day
        current_date = start_date
        while current_date <= end_date:
            date_start = timezone.make_aware(
                datetime.combine(current_date, datetime.min.time())
            )
            date_end = timezone.make_aware(
                datetime.combine(current_date, datetime.max.time())
            )
            
            # Adjust for Malaysia timezone
            date_start = timezone.localtime(date_start, timezone.get_current_timezone())
            date_end = timezone.localtime(date_end, timezone.get_current_timezone())
            
            # Get statistics for this day
            day_attendees = event.attendees.filter(
                attended_at__gte=date_start,
                attended_at__lt=date_end
            ).count()
            
            day_registrations = Registration.objects.filter(
                attendee__event=event,
                created_at__gte=date_start,
                created_at__lt=date_end
            ).count()
            
            day_revenue = Registration.objects.filter(
                attendee__event=event,
                created_at__gte=date_start,
                created_at__lt=date_end
            ).aggregate(
                total=Sum(
                    models.F('pre_registration_fee') + models.F('registration_fee')
                )
            )['total'] or Decimal('0.00')
            
            daily_stats.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'display': current_date.strftime('%b %d'),
                'attendees': day_attendees,
                'registrations': day_registrations,
                'revenue': float(day_revenue)
            })
            
            current_date += timedelta(days=1)
        
        return JsonResponse({
            'success': True,
            'daily_stats': daily_stats,
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        })
        
    except Exception as e:
        print(f"Error getting daily stats: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_GET
def get_realtime_updates(request, event_id):
    """WebSocket-like endpoint for real-time updates"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Get last update timestamp
    last_update_str = request.GET.get('last_update')
    last_update = None
    if last_update_str:
        try:
            last_update = timezone.datetime.fromisoformat(
                last_update_str.replace('Z', '+00:00')
            )
        except:
            pass
    
    # Check for new attendees
    new_attendees = event.attendees.all()
    if last_update:
        new_attendees = new_attendees.filter(attended_at__gt=last_update)
    
    # Check for new registrations
    new_registrations = Registration.objects.filter(attendee__event=event)
    if last_update:
        new_registrations = new_registrations.filter(created_at__gt=last_update)
    
    # Check for new feedback
    new_feedback = event.feedbacks.all()
    if last_update:
        new_feedback = new_feedback.filter(submitted_at__gt=last_update)
    
    # Get latest timestamp
    latest_timestamp = None
    timestamps = []
    
    if new_attendees.exists():
        timestamps.append(new_attendees.latest('attended_at').attended_at)
    if new_registrations.exists():
        timestamps.append(new_registrations.latest('created_at').created_at)
    if new_feedback.exists():
        timestamps.append(new_feedback.latest('submitted_at').submitted_at)
    
    if timestamps:
        latest_timestamp = max(timestamps)
    
    return JsonResponse({
        'success': True,
        'has_updates': any([
            new_attendees.exists(),
            new_registrations.exists(),
            new_feedback.exists()
        ]),
        'counts': {
            'new_attendees': new_attendees.count(),
            'new_registrations': new_registrations.count(),
            'new_feedback': new_feedback.count()
        },
        'latest_timestamp': latest_timestamp.isoformat() if latest_timestamp else None,
        'current_time': timezone.now().isoformat()
    })


@login_required
@require_GET
def get_print_form_number(request, application_id):
    """Generate or retrieve a unique form number for printing"""
    try:
        application = Application.objects.get(id=application_id)
        
        # Check if already has a print record
        print_record = PrintRecord.objects.filter(application=application).first()
        
        if print_record:
            # Return existing form number
            return JsonResponse({
                'success': True,
                'form_number': print_record.form_number,
                'is_reprint': True,
                'print_count': print_record.print_count
            })
        else:
            # Generate new form number
            event = application.event
            
            # Format: SES.STATE.MONTH.SEQUENCE
            # Get application count for this event
            sequence = Application.objects.filter(
                event=event,
                submitted_at__lt=application.submitted_at
            ).count() + 1
            
            # Format state abbreviation
            state_abbr = event.state[:3].upper() if event.state and len(event.state) >= 3 else 'EVT'
            
            # Format month (two digits)
            month = event.date.strftime('%m')
            
            # Generate form number
            form_number = f"SES.{state_abbr}.{month}.{str(sequence).zfill(4)}"
            
            # Create print record
            print_record = PrintRecord.objects.create(
                application=application,
                form_number=form_number,
                printed_by=request.user if request.user.is_authenticated else None
            )
            
            return JsonResponse({
                'success': True,
                'form_number': form_number,
                'is_reprint': False,
                'print_count': 1
            })
            
    except Application.DoesNotExist:
        return JsonResponse({'error': 'Application not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)