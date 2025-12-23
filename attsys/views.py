import uuid
import qrcode
import base64
import csv
from io import BytesIO
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Event, Attendee, Feedback
from django.http import HttpResponseForbidden
from django.db import IntegrityError
from django.contrib import messages
from .models import User
from django.utils.timezone import now
from django.contrib.auth import get_user_model
from django.db.models import Count, Avg
from django.db.models.functions import TruncHour


User = get_user_model()


@login_required
def dashboard(request):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role == 'ADMIN':
        total_events = Event.objects.count()
        total_attendees = Attendee.objects.count()
        total_staff = User.objects.filter(role='STAFF').count()
        events = Event.objects.order_by('-created_at')[:5]

        return render(request, 'admin_dashboard.html', {
            'total_events': total_events,
            'total_attendees': total_attendees,
            'total_staff': total_staff,
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
    attendees = event.attendees.all()

    # 🔹 Auto stop event if ended
    now = timezone.now()
    event_end = timezone.make_aware(
        timezone.datetime.combine(event.date, event.end_time)
    )

    if event.is_active and now > event_end:
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

    # 🔹 Analytics
    attendance_by_hour = (
        attendees
        .annotate(hour=TruncHour('attended_at'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )

    # 🔹 Feedback analytics
    feedbacks = event.feedbacks.all()
    avg_rating = feedbacks.aggregate(Avg('rating'))['rating__avg']

    return render(request, 'event_detail.html', {
        'event': event,
        'attendees': attendees,
        'qr_image': qr_image,
        'attendance_by_hour': attendance_by_hour,
        'feedbacks': feedbacks,
        'avg_rating': avg_rating,
    })


@login_required
def toggle_event(request, event_id):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role != 'STAFF':
        return HttpResponseForbidden()

    event = get_object_or_404(Event, id=event_id)

    if not event.is_active:
        event.is_active = True
        event.check_in_token = uuid.uuid4()
    else:
        event.is_active = False
        event.check_in_token = None

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
    if request.user.is_authenticated and request.user.role != 'STAFF':
        return HttpResponseForbidden("Staff cannot check in as attendee")

    if request.method == 'POST':
        try:
            Attendee.objects.create(
                event=event,
                name=request.POST['name'],
                email=request.POST['email'],
                phone_number=request.POST['phone']
            )
            return redirect('submit_feedback', event_id=event.id)

        except IntegrityError:
            return render(request, 'check_in.html', {
                'event': event,
                'error': 'You have already checked in for this event.'
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
    writer.writerow(['Name', 'Email', 'Phone', 'Checked In At'])

    for attendee in event.attendees.all():
        writer.writerow([
            attendee.name,
            attendee.email,
            attendee.phone_number,
            attendee.attended_at.strftime('%Y-%m-%d %H:%M')
        ])

    return response


# ===== ADMIN VIEWS =====
@login_required
def admin_dashboard(request):
    if not request.user.is_active:
        return redirect('login')

    if request.user.role == 'ADMIN':
        events = Event.objects.all()
    else:
        events = Event.objects.filter(assigned_staff=request.user)

    return render(request, 'dashboard.html', {'events': events})

    total_events = Event.objects.count()
    active_events = Event.objects.filter(is_active=True).count()
    total_attendees = Attendee.objects.count()

    today = now().date()
    today_checkins = Attendee.objects.filter(
        attended_at__date=today
    ).count()

    recent_events = Event.objects.order_by('-created_at')[:5]

    return render(request, 'admin_dashboard.html', {
        'total_events': total_events,
        'active_events': active_events,
        'total_attendees': total_attendees,
        'today_checkins': today_checkins,
        'recent_events': recent_events,
    })


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

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        email = request.POST.get('email', '')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
        else:
            User.objects.create_user(
                username=username,
                password=password,
                email=email,
                role='STAFF'
            )
            messages.success(request, 'Staff account created successfully')

    staff_list = User.objects.filter(role='STAFF')

    return render(request, 'manage_staff.html', {
        'staff_list': staff_list
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