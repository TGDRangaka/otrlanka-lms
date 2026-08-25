# Copyright (c) 2024, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from lms.lms.utils import guest_access_allowed


class LMSProgram(Document):
	def validate(self):
		self.validate_program_courses()
		self.validate_program_members()
		self.update_count()

	def validate_program_courses(self):
		courses = [row.course for row in self.program_courses]
		duplicates = {course for course in courses if courses.count(course) > 1}
		if len(duplicates):
			frappe.throw(
				_("Course {0} has already been added to this program.").format(
					frappe.bold(next(iter(duplicates)))
				)
			)

	def validate_program_members(self):
		members = [row.member for row in self.program_members]
		duplicates = {member for member in members if members.count(member) > 1}
		if len(duplicates):
			frappe.throw(
				_("Member {0} has already been added to this program.").format(
					frappe.bold(next(iter(duplicates)))
				)
			)

	def update_count(self):
		course_count = len(self.program_courses)
		member_count = len(self.program_members)

		if self.course_count != course_count:
			self.course_count = course_count

		if self.member_count != member_count:
			self.member_count = member_count

	def on_update(self):
		self.auto_enroll_members_in_courses()
		self.auto_unenroll_removed_members()
		self.auto_unenroll_removed_courses()

	def auto_enroll_members_in_courses(self):
		"""Auto-create LMS Enrollment for every program member across every program course.

		This ensures that when an admin assigns a student to a program, the student
		is immediately enrolled in all courses belonging to that program without any
		manual step. Courses with disable_self_learning, paid_course, or unpublished
		status are handled gracefully via the lms_program_auto_enroll flag which
		bypasses those guards (equivalent to an admin enrolling on behalf of the student).
		Any per-course failure is logged individually and never aborts the program save.
		"""
		courses = [row.course for row in self.program_courses]
		members = [row.member for row in self.program_members]

		if not courses or not members:
			return

		for member in members:
			for course in courses:
				if frappe.db.exists("LMS Enrollment", {"course": course, "member": member}):
					continue
				frappe.flags.lms_program_auto_enroll = True
				try:
					enrollment = frappe.get_doc(
						{
							"doctype": "LMS Enrollment",
							"course": course,
							"member": member,
						}
					)
					enrollment.insert(ignore_permissions=True)
				except Exception:
					frappe.log_error(
						title=f"Program auto-enroll failed: {member} → {course} ({self.name})"
					)
				finally:
					frappe.flags.lms_program_auto_enroll = False

	def auto_unenroll_removed_members(self):
		"""When members are removed from a program, delete their LMS Enrollment
		for each of this program's courses — but only if no other program still
		gives them access to that course."""
		previous = self.get_doc_before_save()
		if not previous:
			return

		old_members = {row.member for row in previous.program_members}
		new_members = {row.member for row in self.program_members}
		removed_members = old_members - new_members

		if not removed_members:
			return

		courses = [row.course for row in self.program_courses]
		if not courses:
			return

		for member in removed_members:
			for course in courses:
				if self._is_enrolled_via_another_program(member, course):
					continue
				enrollment_name = frappe.db.exists(
					"LMS Enrollment", {"course": course, "member": member}
				)
				if enrollment_name:
					try:
						frappe.delete_doc(
							"LMS Enrollment", enrollment_name, ignore_permissions=True, force=True
						)
					except Exception:
						frappe.log_error(
							title=f"Program auto-unenroll failed: {member} → {course} ({self.name})"
						)

	def auto_unenroll_removed_courses(self):
		"""When courses are removed from a program, delete enrollments for all
		current members in those courses — but only if no other program still
		gives them access to that course."""
		previous = self.get_doc_before_save()
		if not previous:
			return

		old_courses = {row.course for row in previous.program_courses}
		new_courses = {row.course for row in self.program_courses}
		removed_courses = old_courses - new_courses

		if not removed_courses:
			return

		members = [row.member for row in self.program_members]
		if not members:
			return

		for course in removed_courses:
			for member in members:
				if self._is_enrolled_via_another_program(member, course):
					continue
				enrollment_name = frappe.db.exists(
					"LMS Enrollment", {"course": course, "member": member}
				)
				if enrollment_name:
					try:
						frappe.delete_doc(
							"LMS Enrollment", enrollment_name, ignore_permissions=True, force=True
						)
					except Exception:
						frappe.log_error(
							title=f"Program auto-unenroll failed: {member} → {course} ({self.name})"
						)

	def _is_enrolled_via_another_program(self, member, course):
		"""Check if the member is in any OTHER program that also has this course."""
		other_programs = frappe.get_all(
			"LMS Program Member",
			filters={"member": member, "parent": ["!=", self.name]},
			pluck="parent",
		)
		for program in other_programs:
			if frappe.db.exists(
				"LMS Program Course", {"parent": program, "course": course}
			):
				return True
		return False


def has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user

	if user == "Guest" and not guest_access_allowed():
		return False

	roles = frappe.get_roles(user)
	if "Moderator" in roles or "Course Creator" in roles:
		return True

	if ptype not in ("read", "select", "print"):
		return False

	is_enrolled = frappe.db.exists("LMS Program Member", {"parent": doc.name, "member": user})
	if is_enrolled:
		return True

	is_program_published = frappe.db.get_value("LMS Program", doc.name, "published")
	if is_program_published:
		return True

	return False
