"""Manual Drive actions, separate from agent tools and remembered approvals."""
import json


def delete_selected_files(team, files, confirmed=False):
    import frappe
    from drive.api.permissions import get_teams, user_has_permission

    if isinstance(files, str):
        files = json.loads(files)
    if confirmed is not True or not isinstance(team, str) or not team:
        frappe.throw("Confirmez la suppression de la sélection.", frappe.ValidationError)
    if not isinstance(files, list) or not 1 <= len(files) <= 50:
        frappe.throw("Sélectionnez entre 1 et 50 fichiers.", frappe.ValidationError)
    if any(not isinstance(f, dict) or set(f) != {"id", "name", "modified"}
           or any(not isinstance(f[k], str) or not f[k] for k in ("id", "name", "modified"))
           or len(f["id"]) > 140 or len(f["name"]) > 500 or len(f["modified"]) > 50 for f in files):
        frappe.throw("Sélection de fichiers invalide.", frappe.ValidationError)
    if len({f["id"] for f in files}) != len(files):
        frappe.throw("Un fichier apparaît plusieurs fois.", frappe.ValidationError)
    if team not in get_teams():
        frappe.throw("Espace Drive inaccessible.", frappe.PermissionError)

    # Lock and validate the entire selection before the first mutation. The
    # enclosing POST transaction rolls back all status changes on any failure.
    documents = []
    for item in sorted(files, key=lambda f: f["id"]):
        doc = frappe.get_doc("File", item["id"], for_update=True)
        if doc.team != team or doc.is_folder or doc.status != "Active":
            frappe.throw("Le fichier n’est plus dans la sélection autorisée. Actualisez le Drive.", frappe.ValidationError)
        if not user_has_permission(doc, "read") or not (
            user_has_permission(doc, "write") or (doc.folder and user_has_permission(doc.folder, "write"))
        ):
            frappe.throw("Suppression interdite pour ce fichier.", frappe.PermissionError)
        if doc.file_name != item["name"] or str(doc.file_modified or doc.modified) != item["modified"]:
            frappe.throw("Un fichier a changé. Actualisez puis confirmez la nouvelle sélection.", frappe.TimestampMismatchError)
        documents.append(doc)
    for doc in documents:
        doc.permanent_delete()
    return {"deleted": [doc.name for doc in documents]}
