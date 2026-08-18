from django.contrib import admin

from .models import AccessRequest, Department, Employee, System


@admin.register(System)
class SystemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Where IT curates the department list.

    Retire a department by clearing is_active rather than deleting it: the
    foreign key is PROTECTed, so a delete is refused anyway while anyone is
    recorded against it.
    """

    list_display = ["name", "is_active", "employee_count"]
    list_filter = ["is_active"]
    search_fields = ["name"]

    @admin.display(description="Employees")
    def employee_count(self, obj):
        return obj.employees.count()


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "email", "department", "status"]
    list_filter = ["status", "department"]
    search_fields = ["first_name", "last_name", "email"]
    # The list renders the department of every row; without this that is one
    # extra query per employee.
    list_select_related = ["department"]


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ["employee", "request_type", "status", "requested_date", "approver"]
    list_filter = ["status", "request_type"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__email"]
    # M2M rendered as a filter widget rather than a long multi-select.
    filter_horizontal = ["systems"]
    # Set by the guarded decide action in the app, not by hand in admin.
    readonly_fields = ["created_at", "updated_at"]
