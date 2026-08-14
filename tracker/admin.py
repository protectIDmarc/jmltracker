from django.contrib import admin

from .models import AccessRequest, Employee, System


@admin.register(System)
class SystemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "email", "department", "status"]
    list_filter = ["status", "department"]
    search_fields = ["first_name", "last_name", "email"]


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ["employee", "request_type", "status", "requested_date", "approver"]
    list_filter = ["status", "request_type"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__email"]
    # M2M rendered as a filter widget rather than a long multi-select.
    filter_horizontal = ["systems"]
    # Set by the guarded decide action in the app, not by hand in admin.
    readonly_fields = ["created_at", "updated_at"]
