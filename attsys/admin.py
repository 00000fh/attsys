from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Event, Attendee, Application, Registration  # ADDED missing imports

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone_number')}),
        ('Role', {'fields': ('role',)}),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions'
            )
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'role', 'is_staff', 'is_superuser'),
        }),
    )

    search_fields = ('username', 'email')
    ordering = ('username',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'venue', 'date', 'start_time', 'end_time', 'is_active', 'created_by', 'created_at')
    list_filter = ('is_active', 'date', 'created_by')
    search_fields = ('title', 'venue', 'description')
    readonly_fields = ('check_in_token', 'created_at')
    list_per_page = 20
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new event
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number', 'event', 'attended_at')
    list_filter = ('event', 'attended_at')
    search_fields = ('name', 'email', 'phone_number')
    readonly_fields = ('attended_at',)
    list_per_page = 20
    

# NEW: Add Application admin
@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'inviting_officer_display', 'applied_programme', 'event', 'email', 'submitted_at')
    list_filter = ('applied_programme', 'event', 'marriage_status', 'submitted_at')
    search_fields = ('full_name', 'email', 'ic_no', 'phone_no', 'registration_officer')
    readonly_fields = ('submitted_at',)
    list_per_page = 20
    
    # Custom method to display inviting officer (renamed from registration officer)
    def inviting_officer_display(self, obj):
        return obj.registration_officer
    inviting_officer_display.short_description = 'Inviting Officer'
    inviting_officer_display.admin_order_field = 'registration_officer'
    
    fieldsets = (
        ('Event Information', {
            'fields': ('event', 'submitted_at')
        }),
        ('Applicant Information', {
            'fields': (
                'registration_officer',  # This is now "Inviting Officer"
                'applied_programme',
                'full_name',
                'ic_no',
                'email',
                'phone_no',
                'marriage_status',
                'spm_total_credit'
            )
        }),
        ('Address Information', {
            'fields': ('address1', 'address2', 'city', 'postcode', 'state')
        }),
        ('Father\'s Information', {
            'fields': (
                'father_name',
                'father_ic',
                'father_phone',
                'father_occupation',
                'father_income',
                'father_dependants'
            )
        }),
        ('Mother\'s Information', {
            'fields': (
                'mother_name',
                'mother_ic',
                'mother_phone',
                'mother_occupation',
                'mother_income',
                'mother_dependants'
            )
        }),
        ('Programme Interest', {
            'fields': ('interest_choice1', 'interest_choice2', 'interest_choice3')
        }),
    )


# NEW: Add Registration admin
@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('attendee', 'course', 'college', 'total_fee_display', 'payment_status', 'closer', 'created_at')
    list_filter = ('payment_status', 'college', 'created_at')
    search_fields = ('attendee__name', 'attendee__email', 'course', 'college', 'closer', 'referral_number')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 20
    
    def total_fee_display(self, obj):
        return f"RM {obj.total_fee():.2f}"
    total_fee_display.short_description = 'Total Fee'
    total_fee_display.admin_order_field = 'registration_fee'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('attendee', 'course', 'college', 'register_date')
        }),
        ('Fee Information', {
            'fields': ('pre_registration_fee', 'registration_fee', 'payment_status')
        }),
        ('Staff Information', {
            'fields': ('closer', 'referral_number', 'remark')
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )