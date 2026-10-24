from contanext_guatemala.books.snapshots import canonical_json, sha256_hex


def record_book_event(doc, action: str, comment: str | None = None):
	import frappe
	from frappe.utils import now_datetime

	frappe.db.sql("SELECT name FROM `tabGT Accounting Book Run` WHERE name=%s FOR UPDATE", (doc.name,))
	previous = frappe.db.get_value(
		"GT Book Review Event",
		{"book_run": doc.name},
		"event_sha256",
		order_by="event_at desc, creation desc",
	) or ""
	artifacts = [
		{"type": row.artifact_type, "part": row.part_index, "file_url": row.file_url, "sha256": row.sha256}
		for row in doc.artifacts
	]
	event_at = now_datetime()
	payload = {
		"book_run": doc.name,
		"company": doc.company,
		"action": action,
		"actor": frappe.session.user,
		"event_at": str(event_at),
		"comment": comment,
		"emission_sha256": doc.emission_sha256,
		"artifacts": artifacts,
		"previous_event_sha256": previous,
	}
	return frappe.get_doc(
		{
			"doctype": "GT Book Review Event",
			"book_run": doc.name,
			"company": doc.company,
			"action": action,
			"actor": frappe.session.user,
			"event_at": event_at,
			"comment": comment,
			"emission_sha256": doc.emission_sha256,
			"artifact_snapshot_json": canonical_json(artifacts).decode(),
			"previous_event_sha256": previous,
			"event_sha256": sha256_hex(canonical_json(payload)),
		}
	).insert(ignore_permissions=True)
