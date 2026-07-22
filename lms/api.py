import frappe

@frappe.whitelist()
def get_lms_students_count():
    """Return count of LMS Students (users with LMS Student role)"""
    count = frappe.db.count("Has Role", {"role": "LMS Student"})
    return {
        "value": count,
        "fieldtype": "Int",
        "label": "LMS Students",
        "route": ["List", "User", {"role": "LMS Student"}]  # optional: link to User list filtered by role
    }

