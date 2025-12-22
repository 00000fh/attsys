import uuid
import qrcode
import base64
import csv
from io import BytesIO
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Event, Attendee
from django.http import HttpResponseForbidden
from django.db import IntegrityError
from django.contrib import messages


@login_required
def dashboard(request):
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
    event = get_object_or_404(Event, id=event_id)

    if request.user.role == 'STAFF' and event.created_by != request.user:
        return HttpResponseForbidden()

    now = timezone.now()

    event_end = timezone.make_aware(
        timezone.datetime.combine(event.date, event.end_time)
    )

    if event.is_active and now > event_end:
        event.is_active = False
        event.check_in_token = None
        event.save()

    qr_image = None

    if event.is_active and event.check_in_token:
        qr_url = f"{request.scheme}://{request.get_host()}/attsys/check-in/{event.id}/{event.check_in_token}/"

        qr = qrcode.make(qr_url)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")

        qr_image = base64.b64encode(buffer.getvalue()).decode()

    attendees = event.attendees.all()
    total_attendees = attendees.count()
    return render(request, 'event_detail.html', {
        'event': event,
        'attendees': attendees,
        'qr_image': qr_image
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
            return render(request, 'success.html')

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