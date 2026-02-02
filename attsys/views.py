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
                'registration_officer', 'applied_programme', 'attended_with', 'full_name',
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
                attended_with=request.POST['attended_with'],
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
             'mother_income', 'interest_choice1',
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
            register_date = None
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    register_date = datetime.strptime(register_date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if not register_date:
                return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD, DD/MM/YYYY, or DD-MM-YYYY'}, status=400)
        except (ValueError, TypeError) as e:
            return JsonResponse({'error': f'Invalid date: {str(e)}'}, status=400)
        
        # Use Malaysia time for date validation
        malaysia_today = malaysia_now().date()
        
        # Validate date is not in future
        if register_date > malaysia_today:
            return JsonResponse({'error': 'Registration date cannot be in the future'}, status=400)
        
        # Validate date is not too far in past
        thirty_days_ago = malaysia_today - timedelta(days=30)
        if register_date < thirty_days_ago:
            return JsonResponse({'error': 'Registration date cannot be more than 30 days ago'}, status=400)
        
        # Parse fees with validation
        try:
            pre_registration_fee = Decimal(request.POST.get('pre_registration_fee', '0') or '0')
            registration_fee = Decimal(request.POST.get('registration_fee', '0') or '0')
            amount_paid = Decimal(request.POST.get('amount_paid', '0') or '0')
            
            if pre_registration_fee < 0:
                return JsonResponse({'error': 'Pre-registration fee cannot be negative'}, status=400)
            if registration_fee < 0:
                return JsonResponse({'error': 'Registration fee cannot be negative'}, status=400)
            if amount_paid < 0:
                return JsonResponse({'error': 'Amount paid cannot be negative'}, status=400)
        except (ValueError, TypeError, InvalidOperation) as e:
            return JsonResponse({'error': f'Invalid fee format: {str(e)}'}, status=400)
        
        # Get payment_type and payment_status
        payment_type = request.POST.get('payment_type', '').strip()
        payment_status = request.POST.get('payment_status', 'PENDING')
        
        # Validate amount_paid based on payment_status
        total_fee_calculated = pre_registration_fee + registration_fee
        
        if payment_status == 'DONE' and amount_paid != total_fee_calculated:
            return JsonResponse({
                'error': f'For completed payment, amount paid ({amount_paid}) must equal total fee ({total_fee_calculated})'
            }, status=400)
        
        if payment_status == 'PENDING' and amount_paid > 0:
            return JsonResponse({
                'error': 'For pending payment, amount paid should be 0.00'
            }, status=400)
        
        if payment_status == 'PARTIAL' and (amount_paid <= 0 or amount_paid >= total_fee_calculated):
            return JsonResponse({
                'error': f'For partial payment, amount paid ({amount_paid}) must be between 0 and total fee ({total_fee_calculated})'
            }, status=400)
        
        # Get or create registration
        registration, created = Registration.objects.get_or_create(
            attendee=attendee,
            defaults={
                'course': course,
                'college': college,
                'register_date': register_date,
                'pre_registration_fee': pre_registration_fee,
                'registration_fee': registration_fee,
                'payment_type': payment_type if payment_type else None,
                'payment_status': payment_status,
                'amount_paid': amount_paid,
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
            registration.payment_type = payment_type if payment_type else None
            registration.payment_status = payment_status
            registration.amount_paid = amount_paid
            registration.remark = request.POST.get('remark', '').strip()
            registration.closer = closer
            registration.referral_number = request.POST.get('referral_number', '').strip()
            registration.save()
        
        # Prepare response data - FIX: Use property without parentheses
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
                'amount_paid': str(registration.amount_paid),
                'total_fee': str(registration.total_fee),  # FIXED: No parentheses
                'balance_amount': str(registration.balance_amount),  # Also a property
                'payment_type': registration.payment_type,
                'payment_status': registration.payment_status,
                'closer': registration.closer,
                'referral_number': registration.referral_number,
                'updated_at': timezone.localtime(registration.updated_at).strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        return JsonResponse(response_data)
        
    except IntegrityError as e:
        return JsonResponse({'error': f'Database error: {str(e)}'}, status=500)
    except Exception as e:
        print(f"Error saving registration: {e}")
        import traceback
        traceback.print_exc()
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
    """Get comprehensive registration statistics with fee breakdowns"""
    try:
        event = get_object_or_404(Event, id=event_id)
        
        # Check permissions
        if request.user.role == 'STAFF' and event.created_by != request.user:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Get all registrations for this event
        registrations = Registration.objects.filter(attendee__event=event)
        
        # Basic stats with safe defaults
        total_registered = registrations.count()
        
        # Calculate separate fee totals safely
        try:
            pre_reg_result = registrations.aggregate(
                total=Sum('pre_registration_fee')
            )
            total_pre_reg = pre_reg_result['total'] or Decimal('0.00')
        except Exception as e:
            print(f"Pre-registration fee calculation error: {e}")
            total_pre_reg = Decimal('0.00')
        
        try:
            reg_result = registrations.aggregate(
                total=Sum('registration_fee')
            )
            total_reg = reg_result['total'] or Decimal('0.00')
        except Exception as e:
            print(f"Registration fee calculation error: {e}")
            total_reg = Decimal('0.00')
        
        total_revenue = total_pre_reg + total_reg
        
        # Payment status counts
        total_completed = registrations.filter(payment_status='DONE').count()
        total_partial = registrations.filter(payment_status='PARTIAL').count()
        total_pending = registrations.filter(payment_status='PENDING').count()
        
        # Top courses with safe handling
        try:
            top_courses = registrations.values('course').annotate(
                count=models.Count('id'),
                pre_reg_amount=Sum('pre_registration_fee'),
                reg_amount=Sum('registration_fee'),
                total_amount=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('-count')[:5]
            
            courses_data = []
            for item in top_courses:
                try:
                    courses_data.append({
                        'label': str(item['course']) if item['course'] else 'Unknown',
                        'value': item['count'] or 0,
                        'pre_reg_amount': float(item['pre_reg_amount'] or 0),
                        'reg_amount': float(item['reg_amount'] or 0),
                        'total_amount': float(item['total_amount'] or 0)
                    })
                except Exception as e:
                    print(f"Course data error: {e}")
                    continue
        except Exception as e:
            print(f"Top courses query error: {e}")
            courses_data = []
        
        # Top closers with fee breakdowns
        try:
            top_closers = registrations.values('closer').annotate(
                attendee_count=models.Count('id'),
                pre_reg_amount=Sum('pre_registration_fee'),
                reg_amount=Sum('registration_fee'),
                total_amount=Sum(F('pre_registration_fee') + F('registration_fee')),
                completed_count=Count('id', filter=Q(payment_status='DONE')),
                partial_count=Count('id', filter=Q(payment_status='PARTIAL')),
                pending_count=Count('id', filter=Q(payment_status='PENDING'))
            ).order_by('-attendee_count')[:5]
            
            closers_data = []
            for item in top_closers:
                try:
                    closers_data.append({
                        'label': str(item['closer']) if item['closer'] else 'Unknown',
                        'value': item['attendee_count'] or 0,
                        'pre_reg_amount': float(item['pre_reg_amount'] or 0),
                        'reg_amount': float(item['reg_amount'] or 0),
                        'total_amount': float(item['total_amount'] or 0),
                        'completed': item['completed_count'] or 0,
                        'partial': item['partial_count'] or 0,
                        'pending': item['pending_count'] or 0
                    })
                except Exception as e:
                    print(f"Closer data error: {e}")
                    continue
        except Exception as e:
            print(f"Top closers query error: {e}")
            closers_data = []
        
        # Timeline data for last 7 days with fee breakdown
        try:
            seven_days_ago = timezone.now() - timedelta(days=7)
            
            # Use Django's TruncDate for database compatibility
            from django.db.models.functions import TruncDate
            
            timeline_queryset = registrations.filter(
                created_at__gte=seven_days_ago
            ).annotate(
                date_trunc=TruncDate('created_at')
            ).values('date_trunc').annotate(
                count=Count('id'),
                pre_reg_amount=Sum('pre_registration_fee'),
                reg_amount=Sum('registration_fee'),
                total_amount=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('date_trunc')
            
            timeline_data = []
            for item in timeline_queryset:
                try:
                    timeline_data.append({
                        'date': item['date_trunc'].strftime('%Y-%m-%d') if item['date_trunc'] else '',
                        'count': item['count'] or 0,
                        'pre_reg_amount': float(item['pre_reg_amount'] or 0),
                        'reg_amount': float(item['reg_amount'] or 0),
                        'total_amount': float(item['total_amount'] or 0)
                    })
                except Exception as e:
                    print(f"Timeline item error: {e}")
                    continue
        except Exception as e:
            print(f"Timeline query error: {e}")
            timeline_data = []
        
        # Payment type analysis with fee breakdowns
        try:
            payment_type_stats = registrations.values('payment_type').annotate(
                count=Count('id'),
                pre_reg_amount=Sum('pre_registration_fee'),
                reg_amount=Sum('registration_fee'),
                total_amount=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('-count')
            
            payment_types_data = []
            for item in payment_type_stats:
                try:
                    payment_types_data.append({
                        'type': item['payment_type'] or 'NONE',
                        'count': item['count'] or 0,
                        'pre_reg_amount': float(item['pre_reg_amount'] or 0),
                        'reg_amount': float(item['reg_amount'] or 0),
                        'total_amount': float(item['total_amount'] or 0)
                    })
                except Exception as e:
                    print(f"Payment type data error: {e}")
                    continue
        except Exception as e:
            print(f"Payment type query error: {e}")
            payment_types_data = []
        
        # Payment status analysis with fee breakdowns
        try:
            payment_status_stats = registrations.values('payment_status').annotate(
                count=Count('id'),
                pre_reg_amount=Sum('pre_registration_fee'),
                reg_amount=Sum('registration_fee'),
                total_amount=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('-count')
            
            payment_status_data = []
            for item in payment_status_stats:
                try:
                    payment_status_data.append({
                        'status': item['payment_status'] or 'UNKNOWN',
                        'count': item['count'] or 0,
                        'pre_reg_amount': float(item['pre_reg_amount'] or 0),
                        'reg_amount': float(item['reg_amount'] or 0),
                        'total_amount': float(item['total_amount'] or 0)
                    })
                except Exception as e:
                    print(f"Payment status data error: {e}")
                    continue
        except Exception as e:
            print(f"Payment status query error: {e}")
            payment_status_data = []
        
        # Calculate performance metrics
        conversion_rate = 0
        if event.attendees.count() > 0:
            conversion_rate = (total_registered / event.attendees.count()) * 100
        
        avg_pre_reg = total_pre_reg / total_registered if total_registered > 0 else 0
        avg_reg = total_reg / total_registered if total_registered > 0 else 0
        avg_total = total_revenue / total_registered if total_registered > 0 else 0
        
        # Find peak registration day
        try:
            daily_stats = registrations.annotate(
                date_trunc=TruncDate('created_at')
            ).values('date_trunc').annotate(
                count=Count('id'),
                amount=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('-count')
            
            peak_day = daily_stats.first() if daily_stats else None
            peak_day_info = None
            if peak_day and peak_day['date_trunc']:
                peak_day_info = {
                    'date': peak_day['date_trunc'].strftime('%Y-%m-%d'),
                    'count': peak_day['count'] or 0,
                    'amount': float(peak_day['amount'] or 0)
                }
        except Exception as e:
            print(f"Peak day calculation error: {e}")
            peak_day_info = None
        
        return JsonResponse({
            'success': True,
            'basic_stats': {
                'total_registered': total_registered,
                'total_pre_reg': float(total_pre_reg),
                'total_reg': float(total_reg),
                'total_revenue': float(total_revenue),
                'total_completed': total_completed,
                'total_partial': total_partial,
                'total_pending': total_pending
            },
            'performance_metrics': {
                'conversion_rate': round(conversion_rate, 1),
                'avg_pre_reg_per_reg': round(float(avg_pre_reg), 2),
                'avg_reg_per_reg': round(float(avg_reg), 2),
                'avg_total_per_reg': round(float(avg_total), 2),
                'completion_rate': round((total_completed / total_registered * 100) if total_registered > 0 else 0, 1),
                'peak_day': peak_day_info
            },
            'charts': {
                'top_courses': courses_data,
                'top_closers': closers_data,
                'timeline': timeline_data,
                'payment_types': payment_types_data,
                'payment_statuses': payment_status_data
            },
            'summary': {
                'event_title': event.title,
                'report_generated': timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S'),
                'total_attendees': event.attendees.count(),
                'total_applications': Application.objects.filter(event=event).count()
            }
        })
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in get_full_registration_stats: {e}")
        print(f"Error details: {error_details}")
        
        # Return a safe error response
        return JsonResponse({
            'success': False,
            'error': 'Failed to load statistics',
            'details': str(e)[:200]
        }, status=500)

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
    """Professional PDF report with lightened white-gray-black color scheme and uppercase text"""
    event = get_object_or_404(Event, id=event_id)
    
    # Check permissions
    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()
    
    # Helper function to convert text to uppercase
    def uppercase_text(text):
        """Convert text to uppercase for all output"""
        if text is None:
            return ""
        return str(text).upper()
    
    # Helper function to get payment type display name
    def get_payment_type_display(payment_type):
        """Get display name for payment type"""
        if payment_type == 'CASH':
            return 'CASH'
        elif payment_type == 'ONLINE_BANKING':
            return 'ONLINE BANKING'
        elif payment_type == 'QR_PAYMENT':
            return 'QR PAYMENT'
        else:
            return uppercase_text(payment_type or 'NONE')
    
    # Helper function to get payment status display name
    def get_payment_status_display(payment_status):
        """Get display name for payment status"""
        if payment_status == 'DONE':
            return 'COMPLETED'
        elif payment_status == 'PARTIAL':
            return 'PARTIALLY PAID'
        elif payment_status == 'PENDING':
            return 'PENDING'
        else:
            return uppercase_text(payment_status or 'UNKNOWN')
    
    try:
        # Get all registrations with related data
        registrations = Registration.objects.filter(
            attendee__event=event
        ).select_related('attendee')
        
        # Calculate statistics
        total_registered = registrations.count()
        
        # Calculate payment status counts for DONE, PARTIAL, PENDING
        total_completed = registrations.filter(payment_status='DONE').count()
        total_partial = registrations.filter(payment_status='PARTIAL').count()
        total_pending = registrations.filter(payment_status='PENDING').count()
        
        # Calculate revenue with separate totals for pre-reg and reg fees
        total_pre_registration_fee = Decimal('0.00')
        total_registration_fee = Decimal('0.00')
        total_revenue = Decimal('0.00')
        completed_revenue = Decimal('0.00')
        partial_revenue = Decimal('0.00')
        pending_revenue = Decimal('0.00')
        
        # Calculate payment type statistics
        payment_type_counts = {}
        payment_type_revenue = {}
        
        # Calculate payment status revenue
        payment_status_revenue = {
            'DONE': Decimal('0.00'),
            'PARTIAL': Decimal('0.00'),
            'PENDING': Decimal('0.00')
        }
        
        # Calculate daily registration trends
        daily_registrations = {}
        daily_revenue = {}
        
        for reg in registrations:
            pre_reg_fee = reg.pre_registration_fee or Decimal('0.00')
            reg_fee = reg.registration_fee or Decimal('0.00')
            reg_total = pre_reg_fee + reg_fee
            
            total_pre_registration_fee += pre_reg_fee
            total_registration_fee += reg_fee
            total_revenue += reg_total
            
            # Track revenue by payment status
            if reg.payment_status in payment_status_revenue:
                payment_status_revenue[reg.payment_status] += reg_total
            
            # Count payment types and revenue by type
            payment_type = reg.payment_type or 'NONE'
            if payment_type not in payment_type_counts:
                payment_type_counts[payment_type] = 0
                payment_type_revenue[payment_type] = Decimal('0.00')
            payment_type_counts[payment_type] += 1
            payment_type_revenue[payment_type] += reg_total
            
            # Track daily registrations
            reg_date = reg.register_date
            if hasattr(reg_date, 'date'):
                # It's a datetime, extract date
                reg_date = reg_date.date()
            
            if reg_date not in daily_registrations:
                daily_registrations[reg_date] = {'count': 0, 'revenue': Decimal('0.00')}
            daily_registrations[reg_date]['count'] += 1
            daily_registrations[reg_date]['revenue'] += reg_total
        
        # Sort daily registrations by date
        sorted_daily_reg = sorted(daily_registrations.items())
        
        # Calculate peak registration day
        peak_day = max(daily_registrations.items(), key=lambda x: x[1]['count']) if daily_registrations else None
        
        # Get applications data for inviting officers
        email_to_inviting_officer = {}
        try:
            applications = Application.objects.filter(event=event)
            for app in applications:
                email_to_inviting_officer[app.email.lower()] = uppercase_text(app.registration_officer)
        except Exception as e:
            print(f"Error getting applications: {e}")
        
        # Get ALL courses (not just top 5)
        try:
            all_courses = registrations.values('course').annotate(
                count=Count('id'),
                revenue=Sum(F('pre_registration_fee') + F('registration_fee'))
            ).order_by('-count')
        except Exception as e:
            print(f"Error getting courses: {e}")
            all_courses = []
        
        # Get ALL closers based on attendee count AND total payment with pre-reg and reg fee breakdown
        try:
            all_closers = registrations.values('closer').annotate(
                attendee_count=Count('id'),
                total_payment=Sum(F('pre_registration_fee') + F('registration_fee')),
                pre_reg_amount=Sum('pre_registration_fee'),
                reg_amount=Sum('registration_fee'),
                completed_count=Count('id', filter=Q(payment_status='DONE')),
                partial_count=Count('id', filter=Q(payment_status='PARTIAL')),
                pending_count=Count('id', filter=Q(payment_status='PENDING'))
            ).order_by('-attendee_count', '-total_payment')
        except Exception as e:
            print(f"Error getting closers: {e}")
            all_closers = []
        
        # ============================
        # PDF GENERATION - LIGHTENED WHITE-GRAY-BLACK COLOR SCHEME
        # ============================
        try:
            from reportlab.lib.pagesizes import landscape, A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            from reportlab.pdfgen import canvas
            import io
            
            # Create PDF buffer
            buffer = io.BytesIO()
            
            # ============================
            # LIGHTENED WHITE-GRAY-BLACK COLOR SCHEME
            # ============================
            COLORS = {
                'black': '#000000',
                'white': '#ffffff',
                'gray_ultralight': '#f9f9f9',    # Background - Lightened
                'gray_light': '#f0f0f0',         # Alternate rows - Lightened
                'gray_medium': '#cccccc',        # Borders - Lightened
                'gray_dark': '#666666',          # Text - Lightened
                'gray_darker': '#444444',        # Headers - Lightened
                'gray_charcoal': '#222222',      # Titles - Lightened
                'red': '#d32f2f',                # For warnings/important
                'green': '#388e3c',              # For success/paid
                'blue': '#1976d2',               # For information
                'orange': '#f57c00',             # For warnings
                'border': '#aaaaaa',             # Border - Lightened
                'yellow': '#fbc02d',             # For partial payments
                'purple': '#7b1fa2',             # For QR payments
                'cyan': '#0097a7',               # For online banking
            }
            
            # ============================
            # STYLES - PROFESSIONAL LIGHTENED WHITE-GRAY-BLACK
            # ============================
            styles = getSampleStyleSheet()
            
            # Main title style - UPPERCASE
            title_style = ParagraphStyle(
                'ProfessionalTitle',
                parent=styles['Heading1'],
                fontSize=20,
                spaceAfter=0.2*cm,
                alignment=1,
                textColor=colors.HexColor(COLORS['gray_charcoal']),
                fontName='Helvetica-Bold',
                leading=22
            )
            
            # Subtitle style - UPPERCASE
            subtitle_style = ParagraphStyle(
                'ProfessionalSubtitle',
                parent=styles['Normal'],
                fontSize=12,
                spaceAfter=0.3*cm,
                textColor=colors.HexColor(COLORS['gray_dark']),
                alignment=1,
                fontName='Helvetica'
            )
            
            # Event info style - UPPERCASE
            event_info_style = ParagraphStyle(
                'EventInfo',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=0.4*cm,
                textColor=colors.HexColor(COLORS['gray_dark']),
                alignment=1,
                fontName='Helvetica'
            )
            
            # Section header style - UPPERCASE
            section_style = ParagraphStyle(
                'ProfessionalSection',
                parent=styles['Heading2'],
                fontSize=14,
                spaceBefore=0.2*cm,
                spaceAfter=0.15*cm,
                textColor=colors.HexColor(COLORS['gray_charcoal']),
                fontName='Helvetica-Bold',
                leftIndent=0,
                borderWidth=1,
                borderColor=colors.HexColor(COLORS['gray_medium']),
                borderPadding=3,
                borderRadius=2
            )
            
            # Table header style - UPPERCASE - REDUCED SIZE
            table_header_style = ParagraphStyle(
                'ProfessionalTableHeader',
                parent=styles['Normal'],
                fontSize=8.5,  # Reduced from 10
                textColor=colors.HexColor(COLORS['white']),
                fontName='Helvetica-Bold',
                alignment=1,
                spaceBefore=1.5,
                spaceAfter=1.5,
                leading=9  # Reduced from 12
            )
            
            # Table cell style - UPPERCASE - REDUCED SIZE
            table_cell_style = ParagraphStyle(
                'ProfessionalTableCell',
                parent=styles['Normal'],
                fontSize=7.5,  # Reduced from 9.5
                textColor=colors.HexColor(COLORS['gray_charcoal']),
                fontName='Helvetica',
                alignment=0,
                leading=9  # Reduced from 11
            )
            
            # Table cell style for LONG NAMES (NO TRUNCATION) - smaller font
            table_cell_long_name_style = ParagraphStyle(
                'ProfessionalTableCellLongName',
                parent=styles['Normal'],
                fontSize=7.5,  # Even smaller for long names
                textColor=colors.HexColor(COLORS['gray_charcoal']),
                fontName='Helvetica',
                alignment=0,
                leading=9,
                wordWrap='CJK'  # Allow word wrapping
            )
            
            # Table cell center style - UPPERCASE - REDUCED SIZE
            table_cell_center = ParagraphStyle(
                'ProfessionalTableCellCenter',
                parent=table_cell_style,
                alignment=1
            )
            
            # Table cell right style - UPPERCASE - REDUCED SIZE
            table_cell_right = ParagraphStyle(
                'ProfessionalTableCellRight',
                parent=table_cell_style,
                alignment=2
            )
            
            # Status Paid style - UPPERCASE - REDUCED SIZE
            status_completed_style = ParagraphStyle(
                'ProfessionalStatusCompleted',
                parent=table_cell_center,
                fontSize=8,  # Reduced from 9
                fontName='Helvetica-Bold',
                textColor=colors.HexColor(COLORS['green'])
            )
            
            # Status Partial style - UPPERCASE - REDUCED SIZE
            status_partial_style = ParagraphStyle(
                'ProfessionalStatusPartial',
                parent=table_cell_center,
                fontSize=8,  # Reduced from 9
                fontName='Helvetica-Bold',
                textColor=colors.HexColor(COLORS['yellow'])
            )
            
            # Status Pending style - UPPERCASE - REDUCED SIZE
            status_pending_style = ParagraphStyle(
                'ProfessionalStatusPending',
                parent=table_cell_center,
                fontSize=8,  # Reduced from 9
                fontName='Helvetica-Bold',
                textColor=colors.HexColor(COLORS['red'])
            )
            
            # Key metric style - UPPERCASE
            key_metric_style = ParagraphStyle(
                'KeyMetric',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor(COLORS['gray_charcoal']),
                fontName='Helvetica-Bold',
                alignment=1,
                leading=13
            )
            
            # Key metric value style
            key_metric_value_style = ParagraphStyle(
                'KeyMetricValue',
                parent=styles['Normal'],
                fontSize=16,
                textColor=colors.HexColor(COLORS['black']),
                fontName='Helvetica-Bold',
                alignment=1,
                leading=18
            )
            
            # Key metric sub-value style
            key_metric_subvalue_style = ParagraphStyle(
                'KeyMetricSubValue',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor(COLORS['gray_dark']),
                alignment=1,
                leading=12
            )
            
            # Footer style
            footer_style = ParagraphStyle(
                'ProfessionalFooter',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor(COLORS['gray_dark']),
                alignment=1,
                fontName='Helvetica'
            )
            
            # ============================
            # BUILD PDF STORY
            # ============================
            story = []
            
            # ============================
            # PAGE 1: EXECUTIVE SUMMARY
            # ============================
            
            # Create header with event title in UPPERCASE
            header_data = [
                [
                    Paragraph(f"<b>{uppercase_text('REGISTRATION ANALYSIS REPORT')}</b>", title_style),
                ],
                [
                    Paragraph(f"{uppercase_text(event.title)}", subtitle_style),
                ],
                [
                    Paragraph(f"{uppercase_text('EVENT DATE')}: {event.date.strftime('%d %B %Y')} | {uppercase_text('REPORT GENERATED')}: {malaysia_now().strftime('%d/%m/%Y %H:%M')}", 
                             event_info_style),
                ]
            ]
            
            header_table = Table(header_data, colWidths=[19*cm])
            header_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                ('TOPPADDING', (0, 1), (-1, 1), 2),
            ]))
            
            story.append(header_table)
            story.append(Spacer(1, 0.5*cm))
            
            # ============================
            # SECTION 1: KEY PERFORMANCE INDICATORS
            # ============================
            
            story.append(Paragraph(f"<b>{uppercase_text('KEY PERFORMANCE INDICATORS')}</b>", 
                        ParagraphStyle('SectionCenter', parent=section_style, fontSize=13, alignment=1)))
            story.append(Spacer(1, 0.3*cm))
            
            # Calculate metrics
            payment_completion_rate = (total_completed/total_registered*100) if total_registered > 0 else 0
            avg_revenue_per_reg = (total_revenue/total_registered) if total_registered > 0 else 0
            
            # Calculate additional meaningful metrics
            pre_reg_percentage = (total_pre_registration_fee / total_revenue * 100) if total_revenue > 0 else 0
            reg_percentage = (total_registration_fee / total_revenue * 100) if total_revenue > 0 else 0
            
            # Peak day metrics - FIXED DATE FORMATTING
            peak_day_text = "N/A"
            peak_day_revenue = "RM 0.00"
            if peak_day:
                peak_day_date, peak_day_data = peak_day
                # Format date safely
                if hasattr(peak_day_date, 'strftime'):
                    peak_day_text = f"{peak_day_date.strftime('%d/%m')}"
                else:
                    # If it's already a string or other format
                    peak_day_text = str(peak_day_date)
                peak_day_revenue = f"RM {peak_day_data['revenue']:,.2f}"
            
            # Create specific styles for KPI headers with WHITE text
            kpi_header_white_style = ParagraphStyle(
                'KpiHeaderWhite',
                parent=key_metric_style,
                textColor=colors.white,
                fontSize=11,
                fontName='Helvetica-Bold',
                alignment=1
            )
            
            # Updated KPI boxes to show all 3 payment statuses
            kpi_data = [
                [
                    Paragraph(uppercase_text('TOTAL REGISTRATIONS'), kpi_header_white_style),
                    Paragraph(uppercase_text('PAYMENT COMPLETION'), kpi_header_white_style),
                ],
                [
                    Paragraph(f"<font size='16'><b>{total_registered}</b></font>", key_metric_value_style),
                    Paragraph(f"<font size='16'><b>{payment_completion_rate:.1f}%</b></font>", key_metric_value_style),
                ],
                [
                    Paragraph(f"{uppercase_text(f'{total_completed} completed')} • {uppercase_text(f'{total_partial} partial')} • {uppercase_text(f'{total_pending} pending')}", 
                             ParagraphStyle('KpiDetail', parent=styles['Normal'], fontSize=8, alignment=1)),
                    Paragraph(f"{total_completed} {uppercase_text('of')} {total_registered}", 
                             ParagraphStyle('KpiDetail', parent=styles['Normal'], fontSize=8, alignment=1)),
                ],
                [
                    Paragraph(uppercase_text('TOTAL REVENUE'), kpi_header_white_style),
                    Paragraph(uppercase_text('REVENUE BY STATUS'), kpi_header_white_style),
                ],
                [
                    Paragraph(f"<font size='16'><b>RM {total_revenue:,.2f}</b></font>", key_metric_value_style),
                    Paragraph(f"<font size='16'><b>{pre_reg_percentage:.0f}% / {reg_percentage:.0f}%</b></font>", key_metric_value_style),
                ],
                [
                    Paragraph(f"{uppercase_text('pre-reg')}: RM {total_pre_registration_fee:,.2f} • {uppercase_text('reg')}: RM {total_registration_fee:,.2f}", 
                             ParagraphStyle('KpiDetail', parent=styles['Normal'], fontSize=8, alignment=1)),
                    Paragraph(f"{uppercase_text('pre-registration')} / {uppercase_text('registration')} {uppercase_text('split')}", 
                             ParagraphStyle('KpiDetail', parent=styles['Normal'], fontSize=8, alignment=1)),
                ]
            ]
            
            kpi_table = Table(kpi_data, colWidths=[9*cm, 9*cm])
            
            kpi_table.setStyle(TableStyle([
                # KPI Box borders
                ('BOX', (0, 0), (0, 2), 1, colors.HexColor(COLORS['border'])),
                ('BOX', (1, 0), (1, 2), 1, colors.HexColor(COLORS['border'])),
                ('BOX', (0, 3), (0, 5), 1, colors.HexColor(COLORS['border'])),
                ('BOX', (1, 3), (1, 5), 1, colors.HexColor(COLORS['border'])),
                
                # Background for headers - Dark gray with WHITE TEXT
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['gray_darker'])),
                ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor(COLORS['gray_darker'])),
                
                # Text colors - White for header rows
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('TEXTCOLOR', (0, 3), (-1, 3), colors.white),
                
                # Padding
                ('PADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, 1), 4),
                ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
                ('TOPPADDING', (0, 4), (-1, 4), 4),
                ('BOTTOMPADDING', (0, 4), (-1, 4), 2),
                
                # Alignment
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(kpi_table)
            story.append(Spacer(1, 0.6*cm))
            
            # ============================
            # SECTION 2: EXECUTIVE SUMMARY INSIGHTS
            # ============================
            
            story.append(Paragraph(f"<b>{uppercase_text('EXECUTIVE SUMMARY')}</b>", 
                        ParagraphStyle('SectionCenter', parent=section_style, fontSize=13, alignment=1)))
            story.append(Spacer(1, 0.2*cm))
            
            insights_content = []
            
            if total_registered > 0:
                total_attendees = Attendee.objects.filter(event=event).count()
                applications_count = Application.objects.filter(event=event).count()
                
                # Create bullet point insights in UPPERCASE
                if total_attendees > 0:
                    registration_rate = (total_registered / total_attendees * 100)
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('REGISTRATION RATE')}:</b> {registration_rate:.1f}% {uppercase_text('OF TOTAL ATTENDEES')} ({total_registered} {uppercase_text('OF')} {total_attendees})", 
                                 table_cell_style)
                    ])
                
                if applications_count > 0:
                    application_conversion = (total_registered / applications_count * 100)
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('APPLICATION CONVERSION')}:</b> {application_conversion:.1f}% ({total_registered} {uppercase_text('REGISTRATIONS FROM')} {applications_count} {uppercase_text('APPLICATIONS')})", 
                                 table_cell_style)
                    ])
                
                # Payment status breakdown
                insights_content.append([
                    Paragraph(f"• <b>{uppercase_text('PAYMENT STATUS BREAKDOWN')}:</b> {total_completed} {uppercase_text('COMPLETED')} ({payment_completion_rate:.1f}%) • {total_partial} {uppercase_text('PARTIAL')} • {total_pending} {uppercase_text('PENDING')}", 
                             table_cell_style)
                ])
                
                # Revenue composition insight (enhanced)
                insights_content.append([
                    Paragraph(f"• <b>{uppercase_text('REVENUE COMPOSITION')}:</b> {uppercase_text('PRE-REGISTRATION')}: {pre_reg_percentage:.1f}% (RM {total_pre_registration_fee:,.2f}) • {uppercase_text('REGISTRATION')}: {reg_percentage:.1f}% (RM {total_registration_fee:,.2f})", 
                             table_cell_style)
                ])
                
                # Payment type statistics (updated for 3 types)
                if payment_type_counts:
                    payment_insights = []
                    for payment_type, count in payment_type_counts.items():
                        percentage = (count / total_registered * 100) if total_registered > 0 else 0
                        revenue = payment_type_revenue.get(payment_type, 0)
                        
                        payment_type_name = get_payment_type_display(payment_type)
                        payment_insights.append(f"{payment_type_name}: {count} ({percentage:.1f}%)")
                    
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('PAYMENT METHODS')}:</b> {', '.join(payment_insights[:3])}", 
                                 table_cell_style)
                    ])
                
                # Peak registration day insight - FIXED DATE FORMATTING
                if peak_day:
                    peak_day_date, peak_day_data = peak_day
                    peak_percentage = (peak_day_data['count'] / total_registered * 100) if total_registered > 0 else 0
                    
                    # Format date safely
                    if hasattr(peak_day_date, 'strftime'):
                        formatted_date = peak_day_date.strftime('%d %b %Y')
                    else:
                        formatted_date = str(peak_day_date)
                    
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('PEAK REGISTRATION DAY')}:</b> {formatted_date} {uppercase_text('WITH')} {peak_day_data['count']} {uppercase_text('REGISTRATIONS')} ({peak_percentage:.1f}%) {uppercase_text('GENERATING')} RM {peak_day_data['revenue']:,.2f}", 
                                 table_cell_style)
                    ])
                
                # Top performer insight
                if all_closers and len(all_closers) > 0:
                    top_closer = all_closers[0]
                    top_closer_name = uppercase_text(top_closer.get('closer', 'UNKNOWN') or 'UNKNOWN')
                    top_closer_count = top_closer.get('attendee_count', 0)
                    top_closer_revenue = top_closer.get('total_payment', 0) or 0
                    
                    if len(top_closer_name) > 25:
                        top_closer_name = top_closer_name[:23] + "..."
                    
                    closer_percentage = (top_closer_count / total_registered * 100) if total_registered > 0 else 0
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('TOP PERFORMER')}:</b> {top_closer_name} {uppercase_text('ACHIEVED')} {top_closer_count} {uppercase_text('REGISTRATIONS')} ({closer_percentage:.1f}%) {uppercase_text('GENERATING')} RM {top_closer_revenue:,.2f}", 
                                 table_cell_style)
                    ])
                
                # Top course insight
                if all_courses and len(all_courses) > 0:
                    top_course = all_courses[0]
                    top_course_name = uppercase_text(top_course.get('course', 'UNKNOWN') or 'UNKNOWN')
                    top_course_count = top_course.get('count', 0)
                    
                    if len(top_course_name) > 25:
                        top_course_name = top_course_name[:23] + "..."
                    
                    course_percentage = (top_course_count / total_registered * 100) if total_registered > 0 else 0
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('MOST POPULAR COURSE')}:</b> {top_course_name} {uppercase_text('WITH')} {top_course_count} {uppercase_text('REGISTRATIONS')} ({course_percentage:.1f}% {uppercase_text('SHARE')})", 
                                 table_cell_style)
                    ])
            else:
                insights_content.append([
                    Paragraph(f"• {uppercase_text('NO REGISTRATIONS RECORDED FOR THIS EVENT')}", table_cell_style)
                ])
            
            insights_table = Table(insights_content, colWidths=[18*cm])
            insights_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(COLORS['gray_ultralight'])),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor(COLORS['gray_darker'])),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor(COLORS['gray_medium'])),
            ]))
            
            story.append(insights_table)
            story.append(Spacer(1, 0.4*cm))
            
            # ============================
            # NEW SECTION: PAYMENT ANALYSIS - MOVED TO NEW PAGE
            # ============================
            
            # Add page break after insights section
            story.append(Spacer(1, 0.3*cm))

            # Footer for page 1
            story.append(Paragraph(
                f"{uppercase_text('PAGE 1 OF 4')} | {uppercase_text('REPORT ID')}: REG-{event.id}-{malaysia_now().strftime('%y%m%d%H%M')} | {uppercase_text('GENERATED BY ATTSYS')}",
                footer_style
            ))

            # ============================
            # PAGE BREAK - NEW PAGE FOR PAYMENT ANALYSIS
            # ============================
            story.append(PageBreak())

            # ============================
            # PAGE 2: PAYMENT ANALYSIS
            # ============================

            story.append(Paragraph(f"{uppercase_text('PAYMENT ANALYSIS REPORT')}", title_style))
            story.append(Paragraph(
                f"{uppercase_text('EVENT')}: {uppercase_text(event.title)} | {uppercase_text('TOTAL TRANSACTIONS')}: {total_registered}", 
                subtitle_style
            ))
            story.append(Spacer(1, 0.5*cm))

            if payment_type_counts:
                story.append(Paragraph(f"<b>{uppercase_text('PAYMENT METHOD ANALYSIS')}</b>", 
                            ParagraphStyle('SectionCenter', parent=section_style, fontSize=13, alignment=1)))
                story.append(Spacer(1, 0.3*cm))
                
                # Create payment analysis table with updated payment types
                payment_data = []
                
                # Headers
                payment_data.append([
                    Paragraph(f'<b>{uppercase_text("PAYMENT METHOD")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("TRANSACTIONS")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("% SHARE")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("REVENUE (RM)")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("AVG. PER TXN (RM)")}</b>', table_header_style),
                ])
                
                # Data rows - process all payment types
                payment_types_to_show = []
                
                # Add specific payment types in order
                for pt in ['CASH', 'ONLINE_BANKING', 'QR_PAYMENT']:
                    if pt in payment_type_counts:
                        payment_types_to_show.append(pt)
                
                # Add any other payment types
                for payment_type in payment_type_counts.keys():
                    if payment_type not in payment_types_to_show:
                        payment_types_to_show.append(payment_type)
                
                # Now create rows
                for payment_type in payment_types_to_show:
                    count = payment_type_counts.get(payment_type, 0)
                    revenue = payment_type_revenue.get(payment_type, 0)
                    percentage = (count / total_registered * 100) if total_registered > 0 else 0
                    avg_per_txn = revenue / count if count > 0 else 0
                    
                    payment_type_name = get_payment_type_display(payment_type)
                    if len(payment_type_name) > 25:
                        payment_type_name = payment_type_name[:23] + "..."
                    
                    payment_data.append([
                        Paragraph(payment_type_name, table_cell_style),
                        Paragraph(str(count), table_cell_center),
                        Paragraph(f"{percentage:.1f}%", table_cell_center),
                        Paragraph(f"{revenue:,.2f}", table_cell_right),
                        Paragraph(f"{avg_per_txn:,.2f}", table_cell_right),
                    ])
                
                # Summary row
                summary_white_style = ParagraphStyle(
                    'SummaryWhite',
                    parent=table_cell_style,
                    fontSize=9,
                    fontName='Helvetica-Bold',
                    textColor=colors.white,
                    alignment=1
                )
                
                summary_white_right = ParagraphStyle(
                    'SummaryWhiteRight',
                    parent=table_cell_style,
                    fontSize=9,
                    fontName='Helvetica-Bold',
                    textColor=colors.white,
                    alignment=2
                )
                
                payment_data.append([
                    Paragraph(f'<b>{uppercase_text("TOTAL")}</b>', summary_white_style),
                    Paragraph(f'<b>{total_registered}</b>', summary_white_style),
                    Paragraph(f'<b>100%</b>', summary_white_style),
                    Paragraph(f'<b>{total_revenue:,.2f}</b>', summary_white_right),
                    Paragraph(f'<b>{avg_revenue_per_reg:,.2f}</b>', summary_white_right),
                ])
                
                payment_table = Table(payment_data, colWidths=[5*cm, 3*cm, 3*cm, 4*cm, 4*cm], repeatRows=1)
                
                payment_table.setStyle(TableStyle([
                    # Header - Dark gray background
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['gray_darker'])),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('PADDING', (0, 0), (-1, 0), 6),
                    ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    
                    # Body
                    ('FONTSIZE', (0, 1), (-1, -2), 8.5),
                    ('PADDING', (0, 1), (-1, -2), 5),
                    ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                    
                    # Grid lines
                    ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor(COLORS['gray_medium'])),
                    ('LINEBELOW', (0, -2), (-1, -2), 1, colors.HexColor(COLORS['gray_darker'])),
                    
                    # Column alignments
                    ('ALIGN', (1, 1), (2, -1), 'CENTER'),
                    ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
                    
                    # Alternating rows
                    ('ROWBACKGROUNDS', (0, 1), (-1, -2), 
                     [colors.white, colors.HexColor(COLORS['gray_light'])]),
                    
                    # Total row
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLORS['gray_darker'])),
                    ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, -1), (-1, -1), 9),
                    ('PADDING', (0, -1), (-1, -1), 5),
                ]))
                
                story.append(payment_table)
                story.append(Spacer(1, 0.5*cm))  # Increased spacing

            # Add Payment Status Analysis Section
            story.append(Paragraph(f"<b>{uppercase_text('PAYMENT STATUS ANALYSIS')}</b>", 
                        ParagraphStyle('SectionCenter', parent=section_style, fontSize=13, alignment=1)))
            story.append(Spacer(1, 0.3*cm))

            # Payment status analysis table
            payment_status_data = []

            # Headers
            payment_status_data.append([
                Paragraph(f'<b>{uppercase_text("PAYMENT STATUS")}</b>', table_header_style),
                Paragraph(f'<b>{uppercase_text("REGISTRATIONS")}</b>', table_header_style),
                Paragraph(f'<b>{uppercase_text("% SHARE")}</b>', table_header_style),
                Paragraph(f'<b>{uppercase_text("REVENUE (RM)")}</b>', table_header_style),
                Paragraph(f'<b>{uppercase_text("AVG. PER REG (RM)")}</b>', table_header_style),
            ])

            # Status data in order: COMPLETED, PARTIAL, PENDING
            status_order = ['DONE', 'PARTIAL', 'PENDING']
            status_display = {
                'DONE': 'COMPLETED',
                'PARTIAL': 'PARTIALLY PAID',
                'PENDING': 'PENDING'
            }

            for status_code in status_order:
                count = 0
                revenue = Decimal('0.00')
                
                if status_code == 'DONE':
                    count = total_completed
                    revenue = payment_status_revenue.get('DONE', Decimal('0.00'))
                elif status_code == 'PARTIAL':
                    count = total_partial
                    revenue = payment_status_revenue.get('PARTIAL', Decimal('0.00'))
                elif status_code == 'PENDING':
                    count = total_pending
                    revenue = payment_status_revenue.get('PENDING', Decimal('0.00'))
                
                percentage = (count / total_registered * 100) if total_registered > 0 else 0
                avg_per_reg = revenue / count if count > 0 else 0
                
                # Choose style based on status
                if status_code == 'DONE':
                    status_cell_style = status_completed_style
                elif status_code == 'PARTIAL':
                    status_cell_style = status_partial_style
                else:
                    status_cell_style = status_pending_style
                
                payment_status_data.append([
                    Paragraph(uppercase_text(status_display[status_code]), status_cell_style),
                    Paragraph(str(count), table_cell_center),
                    Paragraph(f"{percentage:.1f}%", table_cell_center),
                    Paragraph(f"{revenue:,.2f}", table_cell_right),
                    Paragraph(f"{avg_per_reg:,.2f}", table_cell_right),
                ])

            # Summary row
            payment_status_data.append([
                Paragraph(f'<b>{uppercase_text("TOTAL")}</b>', summary_white_style),
                Paragraph(f'<b>{total_registered}</b>', summary_white_style),
                Paragraph(f'<b>100%</b>', summary_white_style),
                Paragraph(f'<b>{total_revenue:,.2f}</b>', summary_white_right),
                Paragraph(f'<b>{avg_revenue_per_reg:,.2f}</b>', summary_white_right),
            ])

            payment_status_table = Table(payment_status_data, colWidths=[5*cm, 3*cm, 3*cm, 4*cm, 4*cm], repeatRows=1)

            payment_status_table.setStyle(TableStyle([
                # Header - Dark gray background
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['gray_darker'])),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('PADDING', (0, 0), (-1, 0), 6),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                
                # Body
                ('FONTSIZE', (0, 1), (-1, -2), 8.5),
                ('PADDING', (0, 1), (-1, -2), 5),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                
                # Grid lines
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor(COLORS['gray_medium'])),
                ('LINEBELOW', (0, -2), (-1, -2), 1, colors.HexColor(COLORS['gray_darker'])),
                
                # Column alignments
                ('ALIGN', (1, 1), (2, -1), 'CENTER'),
                ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
                
                # Alternating rows
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), 
                 [colors.white, colors.HexColor(COLORS['gray_light'])]),
                
                # Total row
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLORS['gray_darker'])),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 9),
                ('PADDING', (0, -1), (-1, -1), 5),
            ]))

            story.append(payment_status_table)
            story.append(Spacer(1, 0.3*cm))

            # Add payment analysis insights
            if total_registered > 0:
                story.append(Paragraph(f"<b>{uppercase_text('PAYMENT ANALYSIS INSIGHTS')}</b>", 
                            ParagraphStyle('SectionCenter', parent=section_style, fontSize=12, alignment=1)))
                story.append(Spacer(1, 0.2*cm))
                
                insights_content = []
                
                # Calculate key payment metrics
                cash_percentage = (payment_type_counts.get('CASH', 0) / total_registered * 100) if total_registered > 0 else 0
                online_percentage = (payment_type_counts.get('ONLINE_BANKING', 0) / total_registered * 100) if total_registered > 0 else 0
                qr_percentage = (payment_type_counts.get('QR_PAYMENT', 0) / total_registered * 100) if total_registered > 0 else 0
                
                # Most popular payment method
                if payment_type_counts:
                    most_popular = max(payment_type_counts.items(), key=lambda x: x[1])
                    most_popular_name = get_payment_type_display(most_popular[0])
                    most_popular_percentage = (most_popular[1] / total_registered * 100) if total_registered > 0 else 0
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('MOST POPULAR PAYMENT METHOD')}:</b> {most_popular_name} ({most_popular_percentage:.1f}% {uppercase_text('OF ALL TRANSACTIONS')})", 
                                 table_cell_style)
                    ])
                
                # Payment completion insights
                if total_completed > 0:
                    completion_percentage = (total_completed / total_registered * 100)
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('PAYMENT COMPLETION RATE')}:</b> {completion_percentage:.1f}% ({total_completed} {uppercase_text('OF')} {total_registered} {uppercase_text('REGISTRATIONS FULLY PAID')})", 
                                 table_cell_style)
                    ])
                
                # Partial payment insights
                if total_partial > 0:
                    partial_percentage = (total_partial / total_registered * 100)
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('PARTIAL PAYMENTS')}:</b> {partial_percentage:.1f}% ({total_partial} {uppercase_text('REGISTRATIONS WITH PARTIAL PAYMENT')})", 
                                 table_cell_style)
                    ])
                
                # Average revenue per completed registration
                if total_completed > 0:
                    avg_completed_revenue = payment_status_revenue['DONE'] / total_completed if total_completed > 0 else 0
                    insights_content.append([
                        Paragraph(f"• <b>{uppercase_text('AVERAGE REVENUE PER COMPLETED REGISTRATION')}:</b> RM {avg_completed_revenue:,.2f}", 
                                 table_cell_style)
                    ])
                
                # Add insights table
                if insights_content:
                    insights_table = Table(insights_content, colWidths=[18*cm])
                    insights_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(COLORS['gray_ultralight'])),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('PADDING', (0, 0), (-1, -1), 8),
                        ('LEFTPADDING', (0, 0), (-1, -1), 15),
                        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor(COLORS['gray_darker'])),
                    ]))
                    story.append(insights_table)

            # Footer for page 2
            story.append(Spacer(1, 0.3*cm))
            story.append(Paragraph(
                f"{uppercase_text('PAGE 2 OF 4')} | {uppercase_text('REPORT ID')}: REG-{event.id}-{malaysia_now().strftime('%y%m%d%H%M')}",
                footer_style
            ))

            # ============================
            # PAGE BREAK - FOR CLOSER PERFORMANCE
            # ============================
            story.append(PageBreak())

            # ============================
            # PAGE 3: CLOSER PERFORMANCE ANALYSIS (formerly page 2)
            # ============================

            story.append(Paragraph(f"{uppercase_text('PERFORMANCE ANALYSIS BY CLOSER')}", title_style))
            story.append(Paragraph(
                f"{uppercase_text('EVENT')}: {uppercase_text(event.title)} | {uppercase_text('TOTAL CLOSERS')}: {len(all_closers) if all_closers else 0}", 
                subtitle_style
            ))
            story.append(Spacer(1, 0.5*cm))

            if all_closers and len(all_closers) > 0:
                story.append(Paragraph(f"<b>{uppercase_text('CLOSER PERFORMANCE RANKING')}</b>", 
                            ParagraphStyle('SectionCenter', parent=section_style, fontSize=13, alignment=1)))
                story.append(Spacer(1, 0.3*cm))
                
                # Create ALL closers table with payment status breakdown
                closers_data = []
                
                # Headers in UPPERCASE
                closers_data.append([
                    Paragraph(f'<b>{uppercase_text("RANK")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("CLOSER NAME")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("CLOSING")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("COMPLETED")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("PARTIAL")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("PENDING")}</b>', table_header_style),
                    Paragraph(f'<b>{uppercase_text("TOTAL REVENUE (RM)")}</b>', table_header_style),
                ])
                
                # Data rows for ALL closers
                for i, closer in enumerate(all_closers, 1):
                    closer_name = uppercase_text(closer.get('closer', 'UNKNOWN') or 'UNKNOWN')
                    if len(closer_name) > 25:
                        closer_name = closer_name[:23] + "..."
                    
                    closer_count = closer.get('attendee_count', 0)
                    closer_completed = closer.get('completed_count', 0) or 0
                    closer_partial = closer.get('partial_count', 0) or 0
                    closer_pending = closer.get('pending_count', 0) or 0
                    closer_revenue = closer.get('total_payment', 0) or 0
                    
                    closers_data.append([
                        Paragraph(str(i), table_cell_center),
                        Paragraph(closer_name, table_cell_style),
                        Paragraph(str(closer_count), table_cell_center),
                        Paragraph(str(closer_completed), table_cell_center),
                        Paragraph(str(closer_partial), table_cell_center),
                        Paragraph(str(closer_pending), table_cell_center),
                        Paragraph(f"{closer_revenue:,.2f}", table_cell_right),
                    ])
                
                # Add summary row
                summary_white_style = ParagraphStyle(
                    'SummaryWhite',
                    parent=table_cell_style,
                    fontSize=8,
                    fontName='Helvetica-Bold',
                    textColor=colors.white,
                    alignment=1
                )
                
                summary_white_right = ParagraphStyle(
                    'SummaryWhiteRight',
                    parent=table_cell_style,
                    fontSize=8,
                    fontName='Helvetica-Bold',
                    textColor=colors.white,
                    alignment=2
                )
                
                closers_data.append([
                    Paragraph(f'<b>{uppercase_text("TOTAL")}</b>', summary_white_style),
                    '',
                    Paragraph(f'<b>{total_registered}</b>', summary_white_style),
                    Paragraph(f'<b>{total_completed}</b>', summary_white_style),
                    Paragraph(f'<b>{total_partial}</b>', summary_white_style),
                    Paragraph(f'<b>{total_pending}</b>', summary_white_style),
                    Paragraph(f'<b>{total_revenue:,.2f}</b>', summary_white_right),
                ])
                
                # Column widths
                closers_col_widths = [1.5*cm, 5.5*cm, 3.0*cm, 3.0*cm, 2.0*cm, 2.0*cm, 3.0*cm]
                
                closers_table = Table(closers_data, colWidths=closers_col_widths, repeatRows=1)
                
                # Styling
                closers_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['gray_darker'])),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('PADDING', (0, 0), (-1, 0), 6),
                    ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor(COLORS['gray_dark'])),
                    
                    ('FONTSIZE', (0, 1), (-1, -2), 6.5),
                    ('PADDING', (0, 1), (-1, -2), 5),
                    ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                    
                    ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor(COLORS['gray_medium'])),
                    ('LINEBELOW', (0, -2), (-1, -2), 1, colors.HexColor(COLORS['gray_darker'])),
                    
                    ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                    ('ALIGN', (2, 1), (5, -1), 'CENTER'),
                    ('ALIGN', (6, 1), (-1, -1), 'RIGHT'),
                    
                    ('ROWBACKGROUNDS', (0, 1), (-1, -2), 
                     [colors.white, colors.HexColor(COLORS['gray_light'])]),
                    
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLORS['gray_darker'])),
                    ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, -1), (-1, -1), 9),
                    ('PADDING', (0, -1), (-1, -1), 5),
                    ('SPAN', (1, -1), (1, -1)),
                    ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
                ]))
                
                story.append(closers_table)
                story.append(Spacer(1, 0.5*cm))
                
                # Performance insights
                if len(all_closers) > 1:
                    story.append(Paragraph(f"<b>{uppercase_text('PERFORMANCE INSIGHTS')}</b>", 
                                ParagraphStyle('SectionCenter', parent=section_style, fontSize=12, alignment=1)))
                    story.append(Spacer(1, 0.2*cm))
                    
                    # Calculate top 3 performance
                    top_performers = all_closers[:3]
                    top_performers_count = sum(c.get('attendee_count', 0) for c in top_performers)
                    top_performers_percentage = (top_performers_count / total_registered * 100) if total_registered > 0 else 0
                    
                    # Calculate completion rate for top performer
                    top_closer = all_closers[0]
                    top_closer_completed = top_closer.get('completed_count', 0) or 0
                    top_closer_total = top_closer.get('attendee_count', 0) or 0
                    top_closer_completion_rate = (top_closer_completed / top_closer_total * 100) if top_closer_total > 0 else 0
                    
                    insights_text = f"""
                    • {uppercase_text('TOP 3 CLOSERS ACCOUNT FOR')} {top_performers_percentage:.1f}% {uppercase_text('OF ALL REGISTRATIONS')}
                    • {uppercase_text('AVERAGE REGISTRATIONS PER CLOSER')}: {total_registered / len(all_closers):.1f}
                    • {len([c for c in all_closers if c.get('attendee_count', 0) > 0])} {uppercase_text('ACTIVE CLOSERS OUT OF')} {len(all_closers)} {uppercase_text('TOTAL')}
                    • {uppercase_text('TOP CLOSER COMPLETION RATE')}: {top_closer_completion_rate:.1f}% ({top_closer_completed} {uppercase_text('OF')} {top_closer_total})
                    """
                    
                    story.append(Paragraph(insights_text, 
                                ParagraphStyle('InsightText', parent=styles['Normal'], fontSize=10, 
                                              textColor=colors.HexColor(COLORS['gray_charcoal']),
                                              spaceAfter=0.2*cm)))
                    
            else:
                story.append(Paragraph(f"{uppercase_text('NO CLOSER PERFORMANCE DATA AVAILABLE')}", 
                            ParagraphStyle('NoData', parent=section_style, fontSize=12, alignment=1)))
            
            # UPDATE THE FOOTER ON CLOSER PERFORMANCE PAGE
            story.append(Spacer(1, 0.3*cm))
            story.append(Paragraph(
                f"{uppercase_text('PAGE 3 OF 4')} | {uppercase_text('REPORT ID')}: REG-{event.id}-{malaysia_now().strftime('%y%m%d%H%M')}",
                footer_style
            ))

            # ============================
            # PAGE BREAK - FOR REGISTRATION DETAILS
            # ============================
            story.append(PageBreak())

            # ============================
            # PAGE 4: REGISTRATION DETAILS REGISTER (formerly page 3)
            # ============================

            story.append(Paragraph(f"{uppercase_text('REGISTRATION DETAILS REGISTER')}", title_style))
            story.append(Paragraph(
                f"{uppercase_text('EVENT')}: {uppercase_text(event.title)} | {uppercase_text('TOTAL REGISTRATIONS')}: {total_registered}", 
                subtitle_style
            ))
            story.append(Spacer(1, 0.5*cm))
            
            # Column widths - UPDATED: ADDED COLLEGE COLUMN, ADJUSTED ATTENDEE NAME WIDTH
            headers = [
                (uppercase_text('NO.'), 1.0*cm),
                (uppercase_text('ATTENDEE NAME'), 4.0*cm),  # INCREASED from 3.5cm to 4.0cm
                (uppercase_text('EMAIL'), 3.0*cm),
                (uppercase_text('REF. CODE'), 2.0*cm),
                (uppercase_text('COURSE'), 2.5*cm),
                (uppercase_text('COLLEGE'), 2.5*cm),  # NEW COLUMN ADDED
                (uppercase_text('PAYMENT TYPE'), 2.0*cm),
                (uppercase_text('PAYMENT STATUS'), 2.2*cm),
                (uppercase_text('PRE REG. (RM)'), 2.0*cm),
                (uppercase_text('REG. (RM)'), 2.0*cm),
                (uppercase_text('TOTAL (RM)'), 2.0*cm),
                (uppercase_text('CLOSER'), 2.5*cm),
            ]
            
            # Create table data
            table_data = []
            
            # Headers
            header_row = []
            for header_text, width in headers:
                header_row.append(Paragraph(f'<b>{header_text}</b>', table_header_style))
            table_data.append(header_row)
            
            # Registration rows
            sorted_registrations = registrations.order_by('-register_date', 'attendee__name')
            for i, reg in enumerate(sorted_registrations, 1):
                # Get inviting officer
                inviting_officer = email_to_inviting_officer.get(
                    reg.attendee.email.lower(), uppercase_text('N/A')
                )
                
                # ATTENDEE NAME: FULL NAME SHOWN - NO TRUNCATION, use smaller font
                attendee_name = uppercase_text(reg.attendee.name)
                
                email = (reg.attendee.email)
                if len(email) > 25:
                    email = email[:23] + "..."
                
                officer = uppercase_text(inviting_officer)
                if len(officer) > 15:
                    officer = officer[:13] + "..."
                
                course = uppercase_text(reg.course or 'N/A')
                if len(course) > 20:
                    course = course[:18] + "..."
                
                # COLLEGE APPLIED - NEW COLUMN
                college = uppercase_text(reg.college or 'NONE')  # Changed from 'N/A' to 'NONE'
                if len(college) > 20:
                    college = college[:18] + "..."
                
                closer = uppercase_text(reg.closer or 'N/A')
                if len(closer) > 15:
                    closer = closer[:13] + "..."
                
                # Payment Type
                payment_type = get_payment_type_display(reg.payment_type)
                if len(payment_type) > 15:
                    payment_type = payment_type[:13] + "..."
                
                # Payment Status - Use correct style
                payment_status = get_payment_status_display(reg.payment_status)
                
                # Choose status style based on payment status
                if reg.payment_status == 'DONE':
                    status_cell = Paragraph(payment_status, status_completed_style)
                elif reg.payment_status == 'PARTIAL':
                    status_cell = Paragraph(payment_status, status_partial_style)
                else:  # PENDING
                    status_cell = Paragraph(payment_status, status_pending_style)
                
                # Format fees
                pre_reg_fee = reg.pre_registration_fee or Decimal('0.00')
                reg_fee = reg.registration_fee or Decimal('0.00')
                total_fee = pre_reg_fee + reg_fee
                
                # Build row
                row = [
                    Paragraph(str(i), table_cell_center),
                    Paragraph(attendee_name, table_cell_long_name_style),  # Use special style for long names
                    Paragraph(email, table_cell_style),
                    Paragraph(officer, table_cell_style),
                    Paragraph(course, table_cell_style),
                    Paragraph(college, table_cell_style),  # NEW COLUMN
                    Paragraph(payment_type, table_cell_center),
                    status_cell,
                    Paragraph(f"{pre_reg_fee:,.2f}", table_cell_right),
                    Paragraph(f"{reg_fee:,.2f}", table_cell_right),
                    Paragraph(f"{total_fee:,.2f}", table_cell_right),
                    Paragraph(closer, table_cell_style),
                ]
                
                table_data.append(row)
            
            # Financial summary row
            financial_summary_white_style = ParagraphStyle(
                'FinancialSummaryWhite',
                parent=table_cell_style,
                fontSize=8,
                fontName='Helvetica-Bold',
                textColor=colors.white,
                alignment=0
            )
            
            financial_summary_white_center = ParagraphStyle(
                'FinancialSummaryWhiteCenter',
                parent=table_cell_style,
                fontSize=8,
                fontName='Helvetica-Bold',
                textColor=colors.white,
                alignment=1
            )
            
            financial_summary_white_right = ParagraphStyle(
                'FinancialSummaryWhiteRight',
                parent=table_cell_style,
                fontSize=8,
                fontName='Helvetica-Bold',
                textColor=colors.white,
                alignment=2
            )
            
            summary_row = [
                Paragraph(f'<b>{uppercase_text("FINANCIAL SUMMARY")}</b>', financial_summary_white_style),
                '', '', '', '', '',  # Empty cells for No., Name, Email, Ref Code, Course, College
                Paragraph(f'<b>{uppercase_text("TOTAL")}:</b>', financial_summary_white_center),
                '',  # Empty for Payment Status
                Paragraph(f'<b>{total_pre_registration_fee:,.2f}</b>', financial_summary_white_right),
                Paragraph(f'<b>{total_registration_fee:,.2f}</b>', financial_summary_white_right),
                Paragraph(f'<b>{total_revenue:,.2f}</b>', financial_summary_white_right),
                '',  # Empty for Closer
            ]
            
            table_data.append(summary_row)
            
            # Extract column widths
            col_widths = [width for _, width in headers]
            
            # Create table
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            # Apply styling
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['gray_darker'])),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('PADDING', (0, 0), (-1, 0), 6),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor(COLORS['gray_dark'])),
                
                ('FONTSIZE', (0, 1), (-1, -2), 6.5),
                ('PADDING', (0, 1), (-1, -2), 5),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor(COLORS['gray_medium'])),
                
                # Special handling for attendee name column (column 1) - smaller font
                ('FONTSIZE', (1, 1), (1, -2), 6.5), # Smaller font for long names
                
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), 
                 [colors.white, colors.HexColor(COLORS['gray_light'])]),
                
                ('ALIGN', (0, 1), (0, -2), 'CENTER'),
                ('ALIGN', (6, 1), (7, -2), 'CENTER'),  # Payment Type and Status centered
                ('ALIGN', (8, 1), (10, -2), 'RIGHT'),  # Fee columns right-aligned
                ('ALIGN', (11, 1), (11, -2), 'LEFT'),  # Closer left-aligned
                
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(COLORS['gray_darker'])),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 9),
                ('PADDING', (0, -1), (-1, -1), 5),
                ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor(COLORS['gray_medium'])),
                ('VALIGN', (0, -1), (-1, -1), 'MIDDLE'),
                
                # Span cells for summary row
                ('SPAN', (0, -1), (5, -1)),  # Span from No. to College
                ('SPAN', (6, -1), (7, -1)),  # Span Payment Type and Payment Status
                ('SPAN', (8, -1), (8, -1)),  # Pre Reg column
                ('SPAN', (9, -1), (9, -1)),  # Reg column
                ('SPAN', (10, -1), (10, -1)), # Total column
                ('SPAN', (11, -1), (11, -1)), # Closer column
                
                ('GRID', (0, -1), (-1, -1), 0, colors.white),
            ]))
            
            story.append(table)
            story.append(Spacer(1, 0.5*cm))
            
            # Payment Legend
            legend_data = [
                [
                    Paragraph('<b>PAYMENT TYPE LEGEND</b>', ParagraphStyle('LegendHeader', parent=table_header_style, fontSize=8)),
                    Paragraph('<b>PAYMENT STATUS LEGEND</b>', ParagraphStyle('LegendHeader', parent=table_header_style, fontSize=8)),
                    Paragraph('<b>COLLEGE LEGEND</b>', ParagraphStyle('LegendHeader', parent=table_header_style, fontSize=8)),
                ],
                [
                    Paragraph('• <font color="#1976d2">CASH</font> - Cash Payment', 
                             ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                    Paragraph('• <font color="#388e3c">COMPLETED</font> - Fully Paid', 
                             ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                    Paragraph('• <font color="#666666">NONE</font> - No College Specified', 
                             ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                ],
                [
                    Paragraph('• <font color="#0097a7">ONLINE BANKING</font> - Online Transfer', 
                             ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                    Paragraph('• <font color="#fbc02d">PARTIALLY PAID</font> - Partial Payment', 
                             ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                    Paragraph('', ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                ],
                [
                    Paragraph('• <font color="#7b1fa2">QR PAYMENT</font> - QR Code Payment', 
                             ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                    Paragraph('• <font color="#d32f2f">PENDING</font> - Payment Pending', 
                             ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                    Paragraph('', ParagraphStyle('LegendItem', parent=table_cell_style, fontSize=8)),
                ],
            ]
            
            legend_table = Table(legend_data, colWidths=[6*cm, 6*cm, 6*cm])
            legend_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS['gray_light'])),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor(COLORS['gray_medium'])),
                ('PADDING', (0, 0), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(legend_table)
            story.append(Spacer(1, 0.3*cm))
            
            # UPDATE THE FINAL FOOTER
            story.append(Spacer(1, 0.3*cm))
            disclaimer = Paragraph(
                f"""<b>{uppercase_text("OFFICIAL REPORT - CONFIDENTIAL")}</b><br/>
                {uppercase_text("REPORT ID")}: REG-{event.id}-{malaysia_now().strftime('%y%m%d%H%M')} | 
                {uppercase_text("GENERATED BY ATTSYS DASHBOARD")} | 
                {uppercase_text("PAGE 4 OF 4")} | 
                {malaysia_now().strftime('%d/%m/%Y %H:%M')}<br/>
                <i>{uppercase_text("THIS DOCUMENT CONTAINS CONFIDENTIAL INFORMATION AND IS INTENDED FOR OFFICIAL USE ONLY")}.</i>""",
                ParagraphStyle('FinalFooter', parent=footer_style, fontSize=8, textColor=colors.HexColor(COLORS['gray_dark'])))

            story.append(disclaimer)
            
            # ============================
            # BUILD PDF DOCUMENT
            # ============================
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=landscape(A4),
                rightMargin=2.5*cm,
                leftMargin=2.5*cm,
                topMargin=2.0*cm,
                bottomMargin=1.5*cm,
                title=f"Registration Report - {event.title}",
                author="ATTSYS Dashboard",
                subject="Registration Analysis",
                creator="ATTSYS Professional Reporting System"
            )
            
            # Build the story
            doc.build(story)
            buffer.seek(0)
            
            # Create response
            response = HttpResponse(buffer, content_type='application/pdf')
            filename = f"REGISTRATION_REPORT_{event.title.replace(' ', '_')[:50]}_{malaysia_now().strftime('%Y%m%d_%H%M')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"PDF generation error: {str(e)}")
            print(f"Error details: {error_details}")
            
            # Return simple error PDF
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=landscape(A4))
            
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, 400, uppercase_text("Registration Report"))
            
            c.setFont("Helvetica", 12)
            c.drawString(50, 370, f"{uppercase_text('Event')}: {uppercase_text(event.title)}")
            c.drawString(50, 350, f"{uppercase_text('Total Registrations')}: {total_registered}")
            c.drawString(50, 330, f"{uppercase_text('Total Revenue')}: RM {total_revenue:,.2f}")
            c.drawString(50, 310, f"{uppercase_text('Generated')}: {malaysia_now().strftime('%d/%m/%Y %H:%M')}")
            
            # Show payment status summary
            c.drawString(50, 280, f"{uppercase_text('Completed')}: {total_completed}")
            c.drawString(50, 260, f"{uppercase_text('Partially Paid')}: {total_partial}")
            c.drawString(50, 240, f"{uppercase_text('Pending')}: {total_pending}")
            
            c.save()
            buffer.seek(0)
            
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="SIMPLE_REPORT_{event.id}.pdf"'
            return response
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Overall PDF generation error: {str(e)}")
        print(f"Error details: {error_details}")
        
        return HttpResponse(
            f"{uppercase_text('Error generating PDF:')} {str(e)[:200]}",
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