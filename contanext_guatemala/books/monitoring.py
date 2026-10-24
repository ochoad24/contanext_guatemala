import json
from collections.abc import Iterable, Mapping

from contanext_guatemala.books.snapshots import canonical_json, sha256_hex


def change_fingerprint(book_run: str, signals: Iterable[Mapping]) -> str:
	return sha256_hex(canonical_json({"book_run": book_run, "signals": list(signals)}))


def detect_post_cutoff_changes(book_run: str) -> list[dict]:
	import frappe

	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	if doc.status not in {"Sealed", "Superseded"}:
		return []
	# The frozen source baseline is generation time, not physical print confirmation.
	since = doc.generated_at
	if not since:
		return []
	signals = []
	for doctype, date_field, category in (
		("GL Entry", "posting_date", "POST_CUTOFF_GL"),
		("Stock Ledger Entry", "posting_date", "POST_CUTOFF_STOCK"),
	):
		if doctype == "Stock Ledger Entry" and doc.book_type != "INVENTORY":
			continue
		count = frappe.db.count(doctype, filters={
			"company": doc.company, date_field: ["between", [doc.period_from, doc.period_to]],
			"modified": [">", since],
		})
		if count:
			signals.append({"category": category, "count": count})
	account_count = frappe.db.count("Account", filters={"company": doc.company, "modified": [">", since]})
	if account_count:
		signals.append({"category": "POST_CUTOFF_CATALOG", "count": account_count})
	closing_sources = (
		("Period Closing Voucher", "POST_CUTOFF_CLOSING"),
		("Accounting Period", "POST_CUTOFF_CLOSING"),
	)
	for doctype, category in closing_sources:
		if frappe.db.exists("DocType", doctype):
			count = frappe.db.count(doctype, filters={"company": doc.company, "modified": [">", since]})
			if count:
				signals.append({"category": category, "count": count, "source": doctype})
	return signals


def run_operational_monitoring() -> dict:
	import frappe
	from frappe.utils import add_days, nowdate

	created = 0
	for name in frappe.get_all(
		"GT Accounting Book Run",
		filters={"status": ["in", ["Sealed", "Superseded"]]},
		pluck="name",
	):
		signals = detect_post_cutoff_changes(name)
		if signals:
			created += _create_alert(name, signals[0]["category"], signals, change_fingerprint(name, signals))
	for evidence in frappe.get_all(
		"GT Book Authorization Evidence",
		filters={"status": "Verified", "effective_to": ["<=", add_days(nowdate(), 30)]},
		fields=["name", "company", "effective_to"],
	):
		payload = [
			{
				"category": "AUTHORIZATION_EXPIRING",
				"evidence": evidence.name,
				"effective_to": evidence.effective_to,
			}
		]
		created += _create_alert(
			None,
			"AUTHORIZATION_EXPIRING",
			payload,
			change_fingerprint(evidence.name, payload),
			evidence.company,
		)
	for run in frappe.get_all(
		"GT Accounting Book Run",
		filters={"status": "Validation Failed", "reconciliation_json": ["is", "set"]},
		fields=["name", "company", "reconciliation_json"],
	):
		try:
			reconciliation = json.loads(run.reconciliation_json)
		except (TypeError, json.JSONDecodeError):
			continue
		if _contains_blocking_difference(reconciliation):
			payload = [
				{
					"category": "RECONCILIATION_DIFFERENCE",
					"reconciliation_sha256": sha256_hex(canonical_json(reconciliation)),
				}
			]
			created += _create_alert(
				run.name,
				"RECONCILIATION_DIFFERENCE",
				payload,
				change_fingerprint(run.name, payload),
				run.company,
			)
	return {"alerts_created": created}


def _contains_blocking_difference(value) -> bool:
	if isinstance(value, dict):
		if value.get("reconciled") is False:
			return True
		return any(_contains_blocking_difference(item) for item in value.values())
	if isinstance(value, list):
		return any(_contains_blocking_difference(item) for item in value)
	return False


def _create_alert(book_run, category: str, evidence: list[dict], fingerprint: str, company=None) -> int:
	import frappe

	if frappe.db.exists("GT Book Operational Alert", {"fingerprint": fingerprint}):
		return 0
	if book_run:
		company = frappe.db.get_value("GT Accounting Book Run", book_run, "company")
	frappe.get_doc({
		"doctype": "GT Book Operational Alert", "company": company, "book_run": book_run,
		"category": category, "status": "Open", "detected_at": frappe.utils.now_datetime(),
		"fingerprint": fingerprint, "evidence_json": json.dumps(evidence, ensure_ascii=False, default=str),
		"message": "Revisión humana requerida; esta alerta no modifica ni sustituye la emisión.",
	}).insert(ignore_permissions=True)
	return 1
