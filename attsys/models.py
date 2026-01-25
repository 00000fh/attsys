from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver


class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('STAFF', 'Staff'),
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STAFF')
    phone_number = models.CharField(max_length=15, blank=True)
    
    def save(self, *args, **kwargs):
        # Set permissions based on role
        if self.role == 'ADMIN':
            self.is_staff = True
            self.is_superuser = True
        elif self.role == 'STAFF':
            self.is_staff = True
            self.is_superuser = False
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Event(models.Model):
    # Malaysia States Choices - Simplified for storage
    STATE_CHOICES = (
        ('KUALA_LUMPUR', 'Kuala Lumpur'),
        ('SELANGOR', 'Selangor'),
        ('JOHOR', 'Johor'),
        ('PENANG', 'Penang'),
        ('PERAK', 'Perak'),
        ('SABAH', 'Sabah'),
        ('SARAWAK', 'Sarawak'),
        ('PAHANG', 'Pahang'),
        ('NEGERI_SEMBILAN', 'Negeri Sembilan'),
        ('KEDAH', 'Kedah'),
        ('KELANTAN', 'Kelantan'),
        ('TERENGGANU', 'Terengganu'),
        ('MELAKA', 'Melaka'),
        ('PERLIS', 'Perlis'),
        ('LABUAN', 'Labuan'),
        ('PUTRAJAYA', 'Putrajaya'),
        ('OTHER', 'Other'),
    )
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    venue = models.CharField(max_length=200)
    state = models.CharField(max_length=50, choices=STATE_CHOICES, default='KUALA_LUMPUR')
    custom_state = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="Other State"
    )

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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.date})"
    
    def get_state_for_display(self):  # Renamed from get_state_display
        """Get the state for display purposes"""
        if self.state == 'OTHER' and self.custom_state:
            return self.custom_state
        return self.get_state_display()  # Use Django's built-in method
    
    def get_full_location(self):
        """Get complete location string"""
        return f"{self.venue}, {self.get_state_for_display()}"
    
    def save(self, *args, **kwargs):
        # Auto-deactivate if event date has passed
        if self.date < date.today():
            self.is_active = False
        
        super().save(*args, **kwargs)


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
    
    # Additional optional fields
    student_id = models.CharField(max_length=50, blank=True, verbose_name="Student/Matric ID")
    institution = models.CharField(max_length=200, blank=True, verbose_name="School/Institution")
    
    # Check-in method (for analytics)
    CHECKIN_METHOD_CHOICES = (
        ('QR', 'QR Code Scan'),
        ('MANUAL', 'Manual Entry'),
        ('API', 'API Integration'),
    )
    checkin_method = models.CharField(
        max_length=10, 
        choices=CHECKIN_METHOD_CHOICES, 
        default='QR',
        verbose_name="Check-in Method"
    )
    
    # Status
    is_verified = models.BooleanField(default=True, verbose_name="Verified Check-in")
    notes = models.TextField(blank=True, verbose_name="Staff Notes")

    class Meta:
        verbose_name = 'Attendee'
        verbose_name_plural = 'Attendees'
        unique_together = ('event', 'email')
        ordering = ['-attended_at']
        indexes = [
            models.Index(fields=['event', 'attended_at']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f"{self.name} - {self.event.title}"
    
    @property
    def attended_time_display(self):
        """Formatted attended time"""
        return timezone.localtime(self.attended_at).strftime('%I:%M %p')
    
    @property
    def attended_date_display(self):
        """Formatted attended date"""
        return timezone.localtime(self.attended_at).strftime('%b %d, %Y')
    
    def has_application(self):
        """Check if attendee has submitted an application form"""
        return self.event.applications.filter(email__iexact=self.email).exists()
    
    def get_application(self):
        """Get the application form if exists"""
        try:
            return self.event.applications.get(email__iexact=self.email)
        except Application.DoesNotExist:
            return None
    
    def has_registration(self):
        """Check if attendee has registration"""
        try:
            return hasattr(self, 'registration') and self.registration is not None
        except Registration.DoesNotExist:
            return False


# ==================================
# FULL APPLICATION FORM (UPKB STYLE)
# ==================================
class Application(models.Model):
    PROGRAMME_CHOICES = (
        ('DIPLOMA', 'Diploma'),
        ('PRA_DIPLOMA', 'Pra-Diploma'),
        ('TVET', 'TVET'),
        ('SMART_TAHFIZ', 'Smart Tahfiz'),
        ('OTHER', 'Other Programme'),
    )

    MARRIAGE_STATUS = (
        ('SINGLE', 'Single'),
        ('MARRIED', 'Married'),
        ('DIVORCED', 'Divorced'),
        ('WIDOWED', 'Widowed'),
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='applications'
    )

    registration_officer = models.CharField(
        max_length=150,
        verbose_name="Inviting Officer/Referral"
    )

    applied_programme = models.CharField(
        max_length=20,
        choices=PROGRAMME_CHOICES,
        default='DIPLOMA'
    )
    
    custom_programme = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Other Programme (if selected)",
        help_text="Specify if 'Other Programme' is selected"
    )

    full_name = models.CharField(max_length=150)

    address1 = models.TextField(verbose_name="Address Line 1")
    address2 = models.TextField(blank=True, verbose_name="Address Line 2 (Optional)")
    city = models.CharField(max_length=100)
    postcode = models.CharField(max_length=10)
    state = models.CharField(max_length=100)

    ic_no = models.CharField(max_length=20, verbose_name="IC Number")
    email = models.EmailField()
    phone_no = models.CharField(max_length=15, verbose_name="Phone Number")

    marriage_status = models.CharField(
        max_length=10,
        choices=MARRIAGE_STATUS,
        default='SINGLE'
    )
    
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    nationality = models.CharField(max_length=50, default='Malaysian', verbose_name="Nationality")
    race = models.CharField(max_length=50, blank=True, verbose_name="Race")
    religion = models.CharField(max_length=50, blank=True, verbose_name="Religion")

    # Father Information
    father_name = models.CharField(max_length=150, verbose_name="Father's Full Name")
    father_ic = models.CharField(max_length=20, verbose_name="Father's IC Number")
    father_phone = models.CharField(max_length=15, verbose_name="Father's Phone Number")
    father_occupation = models.CharField(max_length=150, blank=True, verbose_name="Father's Occupation")
    father_income = models.CharField(max_length=50, blank=True, verbose_name="Father's Monthly Income (RM)")
    father_dependants = models.PositiveSmallIntegerField(default=0, verbose_name="Number of Dependants")
    
    # Father additional info
    father_employer = models.CharField(max_length=200, blank=True, verbose_name="Father's Employer")
    father_office_address = models.TextField(blank=True, verbose_name="Father's Office Address")
    father_office_phone = models.CharField(max_length=15, blank=True, verbose_name="Father's Office Phone")

    # Mother Information
    mother_name = models.CharField(max_length=150, verbose_name="Mother's Full Name")
    mother_ic = models.CharField(max_length=20, verbose_name="Mother's IC Number")
    mother_phone = models.CharField(max_length=15, verbose_name="Mother's Phone Number")
    mother_occupation = models.CharField(max_length=150, blank=True, verbose_name="Mother's Occupation")
    mother_income = models.CharField(max_length=50, blank=True, verbose_name="Mother's Monthly Income (RM)")
    mother_dependants = models.PositiveSmallIntegerField(default=0, verbose_name="Number of Dependants")
    
    # Mother additional info
    mother_employer = models.CharField(max_length=200, blank=True, verbose_name="Mother's Employer")
    mother_office_address = models.TextField(blank=True, verbose_name="Mother's Office Address")
    mother_office_phone = models.CharField(max_length=15, blank=True, verbose_name="Mother's Office Phone")

    # Academic Information
    spm_total_credit = models.PositiveSmallIntegerField(
        default=0, 
        verbose_name="Total SPM Credit",
        help_text="Total credit from SPM results"
    )
    
    spm_year = models.PositiveSmallIntegerField(
        null=True, 
        blank=True,
        verbose_name="SPM Year"
    )
    
    current_school = models.CharField(
        max_length=200, 
        blank=True,
        verbose_name="Current School/College"
    )
    
    current_course = models.CharField(
        max_length=200, 
        blank=True,
        verbose_name="Current Course"
    )
    
    expected_graduation = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Expected Graduation Date"
    )

    # Programme Interest - 3 separate fields
    interest_choice1 = models.TextField(
        blank=True, 
        verbose_name="First Choice Programme",
        help_text="Your primary programme of interest"
    )
    
    interest_choice2 = models.TextField(
        blank=True, 
        verbose_name="Second Choice Programme",
        help_text="Your secondary programme of interest"
    )
    
    interest_choice3 = models.TextField(
        blank=True, 
        verbose_name="Other Programme Interests",
        help_text="Any other programmes you're interested in"
    )
    
    # Keep for backward compatibility
    interested_programme = models.TextField(
        blank=True, 
        verbose_name="Programme Interests (Legacy)",
        help_text="Auto-generated from choices above"
    )
    
    # Additional questions
    how_did_you_hear = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="How did you hear about us?",
        help_text="e.g., Friend, Social Media, Newspaper, etc."
    )
    
    previous_education = models.TextField(
        blank=True,
        verbose_name="Previous Education Background"
    )
    
    career_aspirations = models.TextField(
        blank=True,
        verbose_name="Career Aspirations"
    )
    
    special_needs = models.TextField(
        blank=True,
        verbose_name="Special Needs/Requirements",
        help_text="Any special accommodations needed"
    )

    # Status
    is_approved = models.BooleanField(default=False, verbose_name="Application Approved")
    approval_date = models.DateTimeField(null=True, blank=True, verbose_name="Approval Date")
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_applications'
    )
    
    approval_notes = models.TextField(blank=True, verbose_name="Approval Notes")
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
        unique_together = ('event', 'ic_no')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['event', 'submitted_at']),
            models.Index(fields=['ic_no']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.event.title}"
    
    def save(self, *args, **kwargs):
        # Auto-generate interested_programme from choices
        programmes = []
        if self.interest_choice1:
            programmes.append(f"1. {self.interest_choice1}")
        if self.interest_choice2:
            programmes.append(f"2. {self.interest_choice2}")
        if self.interest_choice3:
            programmes.append(f"3. {self.interest_choice3}")
        
        self.interested_programme = "\n".join(programmes)
        
        # Auto-set approval date if approved
        if self.is_approved and not self.approval_date:
            self.approval_date = timezone.now()
        
        super().save(*args, **kwargs)
    
    @property
    def get_applied_programme_display(self):
        """Get human-readable applied programme"""
        if self.applied_programme == 'OTHER' and self.custom_programme:
            return self.custom_programme
        
        for code, name in self.PROGRAMME_CHOICES:
            if code == self.applied_programme:
                return name
        return self.applied_programme
    
    @property
    def formatted_phone(self):
        """Format phone number for display"""
        if self.phone_no:
            return f"{self.phone_no[:3]}-{self.phone_no[3:7]} {self.phone_no[7:]}"
        return self.phone_no
    
    @property
    def formatted_ic(self):
        """Format IC number for display"""
        if len(self.ic_no) == 12:
            return f"{self.ic_no[:6]}-{self.ic_no[6:8]}-{self.ic_no[8:]}"
        return self.ic_no
    
    @property
    def age(self):
        """Calculate age from date of birth"""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None


class Feedback(models.Model):
    RATING_CHOICES = (
        (1, '⭐ Very Poor'),
        (2, '⭐⭐ Poor'),
        (3, '⭐⭐⭐ Average'),
        (4, '⭐⭐⭐⭐ Good'),
        (5, '⭐⭐⭐⭐⭐ Excellent'),
    )
    
    CATEGORY_CHOICES = (
        ('EVENT', 'Event Overall'),
        ('VENUE', 'Venue/Facilities'),
        ('CONTENT', 'Content/Program'),
        ('SPEAKERS', 'Speakers/Presenters'),
        ('ORGANIZATION', 'Organization'),
        ('OTHER', 'Other'),
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='feedbacks'
    )

    name = models.CharField(max_length=100)
    email = models.EmailField()
    
    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        default=3
    )
    
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='EVENT'
    )
    
    comment = models.TextField(blank=True)
    
    # Additional feedback fields
    would_recommend = models.BooleanField(
        default=True,
        verbose_name="Would you recommend this event to others?"
    )
    
    improvements_suggested = models.TextField(
        blank=True,
        verbose_name="Suggestions for Improvement"
    )
    
    best_part = models.TextField(
        blank=True,
        verbose_name="What was the best part of the event?"
    )
    
    # Contact permission
    allow_contact = models.BooleanField(
        default=False,
        verbose_name="I agree to be contacted for follow-up"
    )
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback'
        unique_together = ('event', 'email')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['event', 'submitted_at']),
            models.Index(fields=['rating']),
        ]

    def __str__(self):
        return f"{self.event.title} - {self.rating}★ by {self.name}"
    
    @property
    def rating_stars(self):
        """Get rating as stars string"""
        return '⭐' * self.rating
    
    @property
    def is_positive(self):
        """Check if feedback is positive (4-5 stars)"""
        return self.rating >= 4
    
    @property
    def is_negative(self):
        """Check if feedback is negative (1-2 stars)"""
        return self.rating <= 2

class Registration(models.Model):
    PAYMENT_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID_PARTIAL', 'Paid Partial'),
        ('PAID_FULL', 'Paid Full'),
        ('OVERPAID', 'Overpaid'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled'),
        ('DONE', 'Completed'),
    )
    
    PAYMENT_METHOD_CHOICES = (
        ('CASH', 'Cash'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('CREDIT_CARD', 'Credit Card'),
        ('DEBIT_CARD', 'Debit Card'),
        ('ONLINE', 'Online Payment'),
        ('OTHER', 'Other'),
    )
    
    attendee = models.OneToOneField(
        Attendee,
        on_delete=models.CASCADE,
        related_name='registration'
    )
    
    # Course Information
    course = models.CharField(max_length=200, verbose_name="Course Applied")
    course_code = models.CharField(max_length=50, blank=True, verbose_name="Course Code")
    college = models.CharField(max_length=200, verbose_name="College/Branch")
    campus = models.CharField(max_length=100, blank=True, verbose_name="Campus/Location")
    
    # Registration Details
    register_date = models.DateField(verbose_name="Registration Date")
    intake_period = models.CharField(max_length=50, blank=True, verbose_name="Intake Period")
    study_mode = models.CharField(
        max_length=20,
        choices=(
            ('FULL_TIME', 'Full Time'),
            ('PART_TIME', 'Part Time'),
            ('DISTANCE', 'Distance Learning'),
            ('ONLINE', 'Online'),
        ),
        default='FULL_TIME',
        verbose_name="Study Mode"
    )
    
    # Fee Structure
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
    
    material_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Material Fee (RM)"
    )
    
    other_fees = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Other Fees (RM)"
    )
    
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Discount Amount (RM)"
    )
    
    discount_reason = models.TextField(
        blank=True,
        verbose_name="Discount Reason/Code"
    )
    
    # Payment Information
    payment_status = models.CharField(
        max_length=15,
        choices=PAYMENT_STATUS_CHOICES,
        default='PENDING',
        verbose_name="Payment Status"
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        verbose_name="Payment Method"
    )
    
    payment_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Payment Reference/Transaction ID"
    )
    
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Payment Date"
    )
    
    # Staff Information
    remark = models.TextField(blank=True, verbose_name="Staff Remarks")
    closer = models.CharField(max_length=100, verbose_name="Closer (Staff Name)")
    closer_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Closer Staff ID"
    )
    
    referral_number = models.CharField(
        max_length=50, 
        blank=True,
        verbose_name="Referral Number"
    )
    
    # Additional Information
    scholarship_applied = models.BooleanField(
        default=False,
        verbose_name="Applied for Scholarship"
    )
    
    scholarship_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Scholarship Type"
    )
    
    hostel_required = models.BooleanField(
        default=False,
        verbose_name="Requires Hostel Accommodation"
    )
    
    transportation_required = models.BooleanField(
        default=False,
        verbose_name="Requires Transportation"
    )
    
    # Status Tracking
    is_verified = models.BooleanField(
        default=False,
        verbose_name="Registration Verified"
    )
    
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_registrations'
    )
    
    verification_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Verification Date"
    )
    
    verification_notes = models.TextField(
        blank=True,
        verbose_name="Verification Notes"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completion Date")

    class Meta:
        verbose_name = 'Registration'
        verbose_name_plural = 'Registrations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['attendee']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['register_date']),
            models.Index(fields=['closer']),
        ]

    def __str__(self):
        return f"Registration #{self.id} - {self.attendee.name} - {self.course}"
    
    def save(self, *args, **kwargs):
        # Auto-set completed_at if payment status is DONE
        if self.payment_status == 'DONE' and not self.completed_at:
            self.completed_at = timezone.now()
        
        # Auto-verify if payment is completed
        if self.payment_status in ['PAID_FULL', 'DONE', 'OVERPAID'] and not self.is_verified:
            self.is_verified = True
            if not self.verification_date:
                self.verification_date = timezone.now()
        
        super().save(*args, **kwargs)
    
    @property
    def total_fee(self):
        """Calculate total fee before discount"""
        return (
            (self.pre_registration_fee or Decimal('0.00')) +
            (self.registration_fee or Decimal('0.00')) +
            (self.material_fee or Decimal('0.00')) +
            (self.other_fees or Decimal('0.00'))
        )
    
    @property
    def net_fee(self):
        """Calculate net fee after discount"""
        total = self.total_fee
        discount = self.discount_amount or Decimal('0.00')
        return total - discount
    
    @property
    def amount_paid(self):
        """Calculate amount paid based on payment status"""
        if self.payment_status == 'PAID_FULL':
            return self.net_fee
        elif self.payment_status == 'PAID_PARTIAL':
            # For partial payments, you might want to add a field for amount_paid
            return self.net_fee * Decimal('0.5')  # Assuming 50% paid
        elif self.payment_status in ['DONE', 'OVERPAID']:
            return self.net_fee
        else:
            return Decimal('0.00')
    
    @property
    def balance_due(self):
        """Calculate balance due"""
        return self.net_fee - self.amount_paid
    
    @property
    def is_fully_paid(self):
        """Check if registration is fully paid"""
        return self.payment_status in ['PAID_FULL', 'DONE', 'OVERPAID']
    
    @property
    def days_since_registration(self):
        """Calculate days since registration"""
        if self.register_date:
            delta = date.today() - self.register_date
            return delta.days
        return None
    
    def get_payment_status_display_with_color(self):
        """Get payment status with CSS class for UI"""
        status_map = {
            'PENDING': ('Pending', 'warning'),
            'PAID_PARTIAL': ('Paid Partial', 'info'),
            'PAID_FULL': ('Paid Full', 'success'),
            'OVERPAID': ('Overpaid', 'success'),
            'REFUNDED': ('Refunded', 'secondary'),
            'CANCELLED': ('Cancelled', 'danger'),
            'DONE': ('Completed', 'success'),
        }
        return status_map.get(self.payment_status, (self.get_payment_status_display(), 'secondary'))


@receiver(post_save, sender=User)
def set_user_permissions(sender, instance, created, **kwargs):
    """Automatically set is_staff and is_superuser based on role"""
    if instance.role == 'ADMIN':
        if not instance.is_staff or not instance.is_superuser:
            instance.is_staff = True
            instance.is_superuser = True
            # Save without triggering signal again
            User.objects.filter(pk=instance.pk).update(
                is_staff=True,
                is_superuser=True
            )
    elif instance.role == 'STAFF':
        if not instance.is_staff or instance.is_superuser:
            instance.is_staff = True
            instance.is_superuser = False
            User.objects.filter(pk=instance.pk).update(
                is_staff=True,
                is_superuser=False
            )