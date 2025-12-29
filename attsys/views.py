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
from .models import Event, Attendee, Feedback, Application
from django.http import HttpResponseForbidden
from django.db import IntegrityError
from django.contrib import messages
from .models import User
from django.utils.timezone import now, timedelta
from django.contrib.auth import get_user_model
from django.db.models import Count, Avg, Q, F
from django.db.models.functions import TruncHour, ExtractHour
import json
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt


User = get_user_model()

# Helper: Get current Malaysia time
def malaysia_now():
    return timezone.localtime(timezone.now())


@login_required
def dashboard(request):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role == 'ADMIN':
        total_events = Event.objects.count()
        total_attendees = Attendee.objects.count()
        total_staff = User.objects.filter(role='STAFF').count()
        total_feedback = Feedback.objects.count()
        total_applications = Application.objects.count()
        
        # Today's check-ins (Malaysia time)
        today = malaysia_now().date()
        today_checkins = Attendee.objects.filter(
            attended_at__date=today
        ).count()
        
        # Active events
        active_events = Event.objects.filter(is_active=True).count()
        
        # Average rating
        avg_rating = Feedback.objects.aggregate(Avg('rating'))['rating__avg']
        
        events = Event.objects.order_by('-created_at')[:10]

        return render(request, 'admin_dashboard.html', {
            'total_events': total_events,
            'total_attendees': total_attendees,
            'total_staff': total_staff,
            'total_feedback': total_feedback,
            'total_applications': total_applications,
            'today_checkins': today_checkins,
            'active_events': active_events,
            'avg_rating': avg_rating,
            'events': events
        })

    # STAFF view (unchanged)
    events = Event.objects.filter(created_by=request.user)
    return render(request, 'dashboard.html', {'events': events})


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
        return HttpResponseForbidden()

    # ✅ DEFINE ATTENDEES FIRST
    attendees = event.attendees.all().order_by('-attended_at')

    # 🔹 Auto stop event if ended (using Malaysia time)
    now_malaysia = malaysia_now()
    event_end = timezone.make_aware(
        timezone.datetime.combine(event.date, event.end_time)
    )
    event_end = timezone.localtime(event_end)

    if event.is_active and now_malaysia > event_end:
        event.is_active = False
        event.check_in_token = None
        event.save()

    # 🔹 QR generation
    qr_image = None
    if event.is_active and event.check_in_token:
        qr_url = f"{request.scheme}://{request.get_host()}/attsys/check-in/{event.id}/{event.check_in_token}/"

        qr = qrcode.make(qr_url)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        qr_image = base64.b64encode(buffer.getvalue()).decode()

    # 🔹 Analytics (using Malaysia time)
    attendance_by_hour = (
        attendees
        .annotate(malaysia_hour=ExtractHour(F('attended_at') + timedelta(hours=8)))
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

    # 🔹 Feedback analytics
    feedbacks = event.feedbacks.all().order_by('-submitted_at')
    avg_rating = feedbacks.aggregate(Avg('rating'))['rating__avg'] or 0

    return render(request, 'event_detail.html', {
        'event': event,
        'attendees': attendees,
        'qr_image': qr_image,
        'attendance_by_hour': formatted_attendance,
        'feedbacks': feedbacks,
        'avg_rating': avg_rating,
    })


@login_required
def toggle_event(request, event_id):
    if request.user.role != 'STAFF':
        return HttpResponseForbidden()

    event = get_object_or_404(Event, id=event_id)

    if not event.is_active:
        event.is_active = True
        event.check_in_token = uuid.uuid4()
    else:
        event.is_active = False
        event.check_in_token = uuid.uuid4()  # keep token valid

    event.save()
    return redirect('event_detail', event_id=event.id)


def check_in(request, event_id, token):
    event = get_object_or_404(
        Event,
        id=event_id,
        check_in_token=token,
        is_active=True
    )

    # Block staff/admin from checking in
    if request.user.is_authenticated and request.user.role in ['STAFF', 'ADMIN']:
        return HttpResponseForbidden("Staff/Admin cannot check in as attendee")

    if request.method == 'POST':
        try:
            # Create Application record
            application = Application.objects.create(
                event=event,
                invited_speaker=request.POST['invited_speaker'],
                applied_programme=request.POST['applied_programme'],
                full_name=request.POST['full_name'],
                address1=request.POST['address1'],
                address2=request.POST.get('address2', ''),
                city=request.POST['city'],
                postcode=request.POST['postcode'],
                state=request.POST['state'],
                ic_no=request.POST['ic_no'],
                email=request.POST['email'],
                phone_no=request.POST['phone_no'],
                marriage_status=request.POST['marriage_status'],
                father_name=request.POST['father_name'],
                father_ic=request.POST['father_ic'],
                father_phone=request.POST['father_phone'],
                father_occupation=request.POST.get('father_occupation', ''),
                father_income=request.POST.get('father_income', ''),
                father_dependants=request.POST.get('father_dependants', 0) or 0,
                mother_name=request.POST['mother_name'],
                mother_ic=request.POST['mother_ic'],
                mother_phone=request.POST['mother_phone'],
                mother_occupation=request.POST.get('mother_occupation', ''),
                mother_income=request.POST.get('mother_income', ''),
                mother_dependants=request.POST.get('mother_dependants', 0) or 0,
                interested_programme=request.POST.get('interested_programme', '')
            )
            
            # Also mark as attendee for attendance tracking
            attendee = Attendee.objects.create(
                event=event,
                name=request.POST['full_name'],
                email=request.POST['email'],
                phone_number=request.POST['phone_no']
            )
            
            return redirect('submit_feedback', event_id=event.id)

        except IntegrityError as e:
            if 'attendees' in str(e):
                error_msg = 'You have already checked in to this event.'
            else:
                error_msg = 'You have already submitted an application for this event.'
            return render(request, 'check_in.html', {
                'event': event,
                'error': error_msg
            })

    return render(request, 'check_in.html', {'event': event})


def qr_image(request, event_id):
    event = Event.objects.get(id=event_id)
    url = request.build_absolute_uri(
        f"/check-in/{event.id}/{event.qr_token}/"
    )
    img = qrcode.make(url)
    buffer = BytesIO()
    img.save(buffer)
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

    return render(request, 'manage_staff.html', {
        'staff_users': staff_users
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
            'name': attendee.name,
            'email': attendee.email,
            'phone': attendee.phone_number,
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