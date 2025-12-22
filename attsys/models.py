from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

# Create your models here.

class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('STAFF', 'Staff'),
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    phone_number = models.CharField(max_length=15, blank=True)

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    venue = models.CharField(max_length=200)

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='events'
    )

    check_in_token = models.UUIDField(null=True, blank=True, unique=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Attendee(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='attendees'
    )

    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=15)
    attended_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'email')
        ordering = ['-attended_at']

    def __str__(self):
        return f"{self.name} - {self.event.title}"
