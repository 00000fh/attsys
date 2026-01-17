from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal


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

    assigned_staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='assigned_events'
    )

    check_in_token = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# ==============================
# SIMPLE ATTENDANCE (QR CHECK-IN)
# ==============================
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


# ==================================
# FULL APPLICATION FORM (UPKB STYLE)
# ==================================
class Application(models.Model):
    PROGRAMME_CHOICES = (
        ('Diploma', 'Diploma'),
        ('Pra-Diploma', 'Pra-Diploma'),
        ('TVET', 'TVET'),
        ('Smart Tahfiz', 'Smart Tahfiz'),
    )

    MARRIAGE_STATUS = (
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Divorced', 'Divorced'),
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='applications'
    )

    registration_officer = models.CharField(max_length=150)
    applied_programme = models.CharField(
        max_length=20,
        choices=PROGRAMME_CHOICES
    )

    full_name = models.CharField(max_length=150)

    address1 = models.TextField()
    address2 = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    postcode = models.CharField(max_length=10)
    state = models.CharField(max_length=100)

    ic_no = models.CharField(max_length=20)
    email = models.EmailField()
    phone_no = models.CharField(max_length=15)

    marriage_status = models.CharField(
        max_length=10,
        choices=MARRIAGE_STATUS
    )

    # Father
    father_name = models.CharField(max_length=150)
    father_ic = models.CharField(max_length=20)
    father_phone = models.CharField(max_length=15)
    father_occupation = models.CharField(max_length=150, blank=True)
    father_income = models.CharField(max_length=50, blank=True)
    father_dependants = models.PositiveSmallIntegerField(default=0)

    # Mother
    mother_name = models.CharField(max_length=150)
    mother_ic = models.CharField(max_length=20)
    mother_phone = models.CharField(max_length=15)
    mother_occupation = models.CharField(max_length=150, blank=True)
    mother_income = models.CharField(max_length=50, blank=True)
    mother_dependants = models.PositiveSmallIntegerField(default=0)

    # Programme Interest - 3 separate fields (keeping interested_programme for backward compatibility)
    interested_programme = models.TextField(blank=True)  # Keep for existing data
    interest_choice1 = models.TextField(blank=True, verbose_name="First Choice Programme")
    interest_choice2 = models.TextField(blank=True, verbose_name="Second Choice Programme")
    interest_choice3 = models.TextField(blank=True, verbose_name="Other Programme Interests")

    # SPM Total Credit only (no individual subject fields)
    spm_total_credit = models.PositiveSmallIntegerField(
        default=0, 
        verbose_name="Total SPM Credit",
        help_text="Total credit from SPM results"
    )

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'ic_no')
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.full_name} - {self.event.title}"


class Feedback(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='feedbacks'
    )

    name = models.CharField(max_length=100)
    email = models.EmailField()
    rating = models.PositiveSmallIntegerField()  # 1–5
    comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'email')
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.event.title} - {self.rating}★"

class Registration(models.Model):
    PAYMENT_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('DONE', 'Done'),
    )
    
    attendee = models.OneToOneField(
        'Attendee',  # Use string reference to avoid circular import
        on_delete=models.CASCADE,
        related_name='registration'  # Changed from 'registration' to avoid conflict
    )
    
    # New form fields
    course = models.CharField(max_length=200, verbose_name="Course Applied")
    college = models.CharField(max_length=200, verbose_name="College/Branch")
    register_date = models.DateField(verbose_name="Registration Date")
    
    # Fee fields
    pre_registration_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0.00,
        verbose_name="Pre-Registration Fee (RM)"
    )
    registration_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0.00,
        verbose_name="Registration Fee (RM)"
    )
    
    payment_status = models.CharField(
        max_length=10,
        choices=PAYMENT_STATUS_CHOICES,
        default='PENDING',
        verbose_name="Payment Status (Registration Fee)"
    )
    
    remark = models.TextField(blank=True, verbose_name="Staff Remarks")
    closer = models.CharField(max_length=100, verbose_name="Closer (Staff Name)")
    referral_number = models.CharField(
        max_length=50, 
        blank=True,
        verbose_name="Referral Number"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Registration for {self.attendee.name} - {self.course}"
    
    def total_fee(self):
        return self.pre_registration_fee + self.registration_fee
    
    class Meta:
        ordering = ['-created_at']

    def total_fee(self):
        """Calculate total fee"""
        pre_fee = self.pre_registration_fee or Decimal('0.00')
        reg_fee = self.registration_fee or Decimal('0.00')
        return pre_fee + reg_fee

    def total_fee(self):
        """Calculate total fee"""
        pre_fee = self.pre_registration_fee or Decimal('0.00')
        reg_fee = self.registration_fee or Decimal('0.00')
        return pre_fee + reg_fee
    
    def get_payment_status_display(self):
        """Get human-readable payment status"""
        if self.payment_status == 'DONE':
            return 'Done'
        elif self.payment_status == 'PENDING':
            return 'Pending'
        return self.payment_status
    
    class Meta:
        ordering = ['-created_at']

    