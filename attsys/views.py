from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Event, Attendee
from django.http import HttpResponseForbidden


@login_required
def dashboard(request):
    if request.user.role == 'ADMIN':
        events = Event.objects.all()
    else:
        events = Event.objects.filter(created_by=request.user)

    return render(request, 'dashboard.html', {'events': events})


@login_required
def create_event(request):
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

    attendees = event.attendees.all()
    return render(request, 'event_detail.html', {
        'event': event,
        'attendees': attendees
    })


@login_required
def toggle_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    event.is_active = not event.is_active
    event.save()
    return redirect('event_detail', event_id=event.id)


def check_in(request, event_id, token):
    event = get_object_or_404(
        Event,
        id=event_id,
        qr_token=token,
        is_active=True
    )

    if request.method == 'POST':
        Attendee.objects.create(
            event=event,
            name=request.POST['name'],
            email=request.POST['email'],
            phone_number=request.POST['phone']
        )
        return render(request, 'success.html')

    return render(request, 'check_in.html', {'event': event})
